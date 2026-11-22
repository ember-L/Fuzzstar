"""CogVideoX-Flash（智谱）图生视频接入（F14-6/7）：萌宠动图的真实 AI 实现。

免费档并发受限：提交遇 429/5xx 按指数退避重试，轮询超时即失败，由服务层按动作粒度降级（F14-1）。
产物链路：首帧照片 → mp4 → ffmpeg 转循环 GIF（固定帧率与高度，palettemap 量化防色带）。
"""
from __future__ import annotations

import asyncio
import base64
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

import httpx
from PIL import Image

from app.providers.base import GeneratedAsset

BIGMODEL_BASE = 'https://open.bigmodel.cn/api/paas/v4'
VIDEO_MODEL = 'cogvideox-flash'
# 智谱只接受 5s / 10s 档位；GIF 规格上限 7s，故统一取 5s 生成。
VIDEO_SECONDS = 5
STYLE_SUFFIX = '固定镜头，纯色浅米色背景，写实摄影风格，动作自然连贯，主体外形与首帧保持一致'
# delogo 的安全边距：区域贴边会被 ffmpeg 判为越界直接失败。
LOGO_MARGIN = 6
# 规则里的动作描述含工程约束，模型无法执行，转写时剔除。
TECH_NOTES = ('首尾帧对齐可无缝循环',)


def build_prompt(action_prompt: str) -> str:
    """把规则里的动作描述转成模型可执行的一句话：去掉动作代号与循环约束。"""
    text = action_prompt.strip()
    parts = text.split(' ', 1)
    if len(parts) == 2 and parts[0].isalpha():
        text = parts[1]
    for note in TECH_NOTES:
        text = text.replace(note, '')
    text = text.replace('：', '，').strip('，。 ')
    return f'保持首帧里同一只小猫的外观与毛色，{text}。{STYLE_SUFFIX}'


class CogVideoError(RuntimeError):
    pass


def ffmpeg_exe() -> str:
    """优先用系统 ffmpeg；未安装时退回 imageio-ffmpeg 自带的静态二进制。"""
    found = shutil.which('ffmpeg')
    if found:
        return found
    try:
        import imageio_ffmpeg
    except ImportError as exc:  # pragma: no cover - 依赖缺失属环境问题
        raise CogVideoError('ffmpeg is required: install imageio-ffmpeg') from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_size(path: Path) -> tuple[int, int]:
    """从 ffmpeg 探测输出里取视频宽高。"""
    result = subprocess.run([ffmpeg_exe(), '-hide_banner', '-i', str(path)],
                            capture_output=True, text=True)
    match = re.search(r'(\d{2,5})x(\d{2,5})', result.stderr or '')
    if not match:
        raise CogVideoError(f'cannot probe video size: {(result.stderr or "")[-300:]}')
    return int(match.group(1)), int(match.group(2))


def watermark_filter(width: int, height: int) -> str:
    """免费档产物右下角带"AI生成"角标，按画面尺寸算出覆盖它的绝对区域。

    角标实测占比 x 0.846–0.992、y 0.925–0.977，故从 0.82/0.90 起框，保证整块覆盖。
    delogo 不接受 iw/ih 表达式，也不允许贴边，故留 LOGO_MARGIN 像素安全距离。
    """
    x = round(width * 0.82)
    y = round(height * 0.90)
    margin = LOGO_MARGIN
    return f'delogo=x={x}:y={y}:w={width - x - margin}:h={height - y - margin}:show=0'


def mp4_to_gif(video: bytes, *, fps: int, height: int) -> bytes:
    """mp4 → 无限循环 GIF；帧率与高度固定，满足 motion.yaml 的规格硬约束。

    编码取舍：轻度降噪压掉 AI 视频噪点（顺带缩小帧间差异，GIF 体积降约 15%）；
    128 色 + 无抖动在米色平滑底上不产生色带，比 192 色 Bayer 更省体积。
    """
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / 'clip.mp4'
        target = Path(folder) / 'clip.gif'
        source.write_bytes(video)
        base = (f'hqdn3d=1.5:1.5:6:6,fps={fps},scale=-1:{height}:flags=lanczos,split[a][b];'
                '[a]palettegen=max_colors=128[p];'
                '[b][p]paletteuse=dither=none')
        width, video_height = probe_size(source)
        commands = [
            [ffmpeg_exe(), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(source),
             '-vf', f'{watermark_filter(width, video_height)},{base}', '-loop', '0', str(target)],
            # 角标区域探测失败时退回无水印处理，保证动作仍能产出。
            [ffmpeg_exe(), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(source),
             '-vf', base, '-loop', '0', str(target)],
        ]
        errors = []
        for command in commands:
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0 and target.is_file():
                return target.read_bytes()
            errors.append(result.stderr[-300:])
        raise CogVideoError(f'ffmpeg gif failed: {errors[-1]}')


def square_frame(photo: bytes, *, size: int = 1024) -> bytes:
    """把竖版照片等比放大后居中贴到同色方底板。

    方形画布与 App 里的方形头像位一致：模型输出方形视频，最终 GIF 无需裁剪也不会留边。
    """
    image = Image.open(io.BytesIO(photo)).convert('RGB')
    background = image.getpixel((0, 0))
    scale = min(size / image.width, size * 0.94 / image.height)
    image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                         Image.LANCZOS)
    canvas = Image.new('RGB', (size, size), background)
    canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2))
    buffer = io.BytesIO()
    canvas.save(buffer, 'JPEG', quality=95)
    return buffer.getvalue()


class CogVideoMotionProvider:
    """用 CogVideoX-Flash 把首帧照片转成循环 GIF。"""

    def __init__(self, *, api_key: str, base_url: str = BIGMODEL_BASE, model: str = VIDEO_MODEL,
                 fps: int = 12, height: int = 480, seconds: int = VIDEO_SECONDS,
                 size: int = 1024, quality: str = 'speed',
                 submit_attempts: int = 8, poll_interval: float = 6.0, poll_timeout: float = 2400.0,
                 on_task: Optional[Callable[[str], None]] = None):
        if not api_key:
            raise ValueError('COGVIDEO_API_KEY is required')
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.fps = fps
        self.height = height
        self.seconds = seconds
        self.size = size
        self.quality = quality
        self.submit_attempts = submit_attempts
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        # 提交成功后回传任务号：免费档生成耗时可达数十分钟，任务号可用于事后取回产物。
        self.on_task = on_task

    def _headers(self) -> dict:
        return {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}

    async def _submit(self, client: httpx.AsyncClient, payload: dict) -> str:
        delay = 10.0
        last = ''
        for attempt in range(1, self.submit_attempts + 1):
            try:
                response = await client.post(f'{self.base_url}/videos/generations',
                                             json=payload, headers=self._headers())
            except httpx.HTTPError as exc:
                last = f'network {exc}'
                await asyncio.sleep(delay)
                delay = min(delay * 1.6, 90)
                continue
            if response.status_code == 200:
                return response.json()['id']
            last = f'{response.status_code} {response.text[:200]}'
            # 关水印需账号已签免责声明，未签时退回带水印产物，角标由 mp4_to_gif 擦除。
            if response.status_code in (400, 403) and 'watermark_enabled' in payload:
                payload = {key: value for key, value in payload.items() if key != 'watermark_enabled'}
                continue
            if response.status_code not in (429, 500, 502, 503):
                raise CogVideoError(f'video submit failed: {last}')
            await asyncio.sleep(delay)
            delay = min(delay * 1.6, 90)
        raise CogVideoError(f'video submit exhausted retries: {last}')

    async def _poll(self, client: httpx.AsyncClient, task_id: str) -> dict:
        deadline = self.poll_timeout
        waited = 0.0
        body: dict = {}
        while waited < deadline:
            await asyncio.sleep(self.poll_interval)
            waited += self.poll_interval
            try:
                body = (await client.get(f'{self.base_url}/async-result/{task_id}',
                                         headers=self._headers())).json()
            except (httpx.HTTPError, ValueError):
                # 网关抖动不该判任务失败，继续等下一个轮询周期。
                continue
            if body.get('task_status') != 'PROCESSING':
                return body
        raise CogVideoError(f'video task timeout: {task_id}')

    async def submit(self, image: bytes, *, prompt: str, seconds: float = VIDEO_SECONDS) -> str:
        """提交图生视频任务，返回任务号；生成在服务端异步进行。"""
        frame = square_frame(image, size=self.size)
        payload = {'model': self.model,
                   'prompt': build_prompt(prompt),
                   'duration': int(seconds),
                   'size': f'{self.size}x{self.size}',
                   'quality': self.quality,
                   'with_audio': False,
                   'watermark_enabled': False,
                   'image_url': 'data:image/jpeg;base64,' + base64.b64encode(frame).decode()}
        async with httpx.AsyncClient(timeout=120) as client:
            return await self._submit(client, payload)

    async def fetch_video(self, task_id: str) -> bytes:
        """轮询任务直到出片，再下载 mp4 字节。"""
        async with httpx.AsyncClient(timeout=120) as client:
            result = await self._poll(client, task_id)
        if result.get('task_status') not in ('SUCCESS', 'SUCCEEDED'):
            raise CogVideoError(f'video synthesis failed: {result.get("task_status")} {result.get("error")}')
        clips = result.get('video_result') or []
        url = clips[0].get('url') if clips else None
        if not url:
            raise CogVideoError('video synthesis returned no url')
        async with httpx.AsyncClient(timeout=300) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise CogVideoError(f'video download error: {exc}') from exc
            return response.content

    async def synthesize(self, image: bytes, *, prompt: str, seconds: float = VIDEO_SECONDS) -> bytes:
        """首帧图 + 提示词 → mp4 字节。"""
        task_id = await self.submit(image, prompt=prompt, seconds=seconds)
        if self.on_task is not None:
            self.on_task(task_id)
        return await self.fetch_video(task_id)

    async def enchant(self, photo: bytes, *, prompt: str) -> GeneratedAsset:
        """F14-6：卡通化会破坏与原猫的身份一致性，萌化退化为等比放大与居中裁剪。"""
        image = Image.open(io.BytesIO(photo)).convert('RGB')
        buffer = io.BytesIO()
        image.save(buffer, 'PNG')
        return GeneratedAsset(buffer.getvalue(), 'image/png')

    async def animate(self, image: bytes, *, prompt: str, seconds: float) -> GeneratedAsset:
        video = await self.synthesize(image, prompt=prompt, seconds=self.seconds)
        gif = mp4_to_gif(video, fps=self.fps, height=self.height)
        return GeneratedAsset(gif, 'image/gif')
