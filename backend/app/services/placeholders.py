"""占位片库：3 体型 × 7 动作，版本化 manifest（FRD F03-4 / ARCHITECTURE 分身资产管线）。

艺术为程序化临时占位（软圆猫咪剪影，暖橙基调），无第三方版权素材；
正式授权素材到位后按新版本整库替换（T19）。所有动作均为相位整数倍周期运动，
首尾帧对齐，循环播放无跳帧。规格：≤5s、720p、H.264、无声。
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

BODY_TYPES = ('slim', 'standard', 'chubby')
ACTIONS = ('idle', 'happy', 'sad', 'sick', 'crouch', 'look_left', 'look_right')
DEFAULT_VERSION = 'v1'

BG = (255, 247, 236)
SHADOW = (240, 224, 202)
FUR = (254, 174, 54)
FUR_LIGHT = (255, 214, 140)
BELLY = (255, 237, 215)
LINE = (116, 58, 16)

# 体型比例（相对画布高）：slim 窄长、standard 匀称、chubby 宽圆
PROPORTIONS = {'slim': (0.30, 0.36), 'standard': (0.38, 0.40), 'chubby': (0.50, 0.44)}


def _trig(phase: float) -> tuple[float, float]:
    s, c = math.sin(phase), math.cos(phase)
    # 吸附浮点噪声，保证 phase=0 与 phase=2π 渲染逐字节一致（首尾对齐）。
    if abs(s) < 1e-9:
        s = 0.0
    if abs(c - 1) < 1e-9:
        c = 1.0
    if abs(c + 1) < 1e-9:
        c = -1.0
    return s, c


def render_frame(
    body_type: str, action: str, phase: float, *, width: int, height: int, supersample: int = 1
) -> Image.Image:
    if body_type not in PROPORTIONS:
        raise ValueError(f'unknown body type: {body_type}')
    if action not in ACTIONS:
        raise ValueError(f'unknown action: {action}')
    s, c = _trig(phase)
    W, H = width * supersample, height * supersample
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    bw, bh = PROPORTIONS[body_type]
    body_w, body_h = bw * H, bh * H
    cx = W / 2
    ground = H * 0.90

    dx = dy = head_dx = head_dy = tail = ear_drop = 0.0
    squash = 1.0
    eyes = 'open'
    if action == 'idle':
        squash = 1 + 0.02 * s
    elif action == 'happy':
        dy = -0.05 * H * abs(s)
        tail = 25 * math.sin(2 * phase)
    elif action == 'sad':
        head_dy = 0.05 * H * (1 - c) / 2
        ear_drop = 0.6 * (1 - c) / 2
    elif action == 'sick':
        dx = 0.02 * W * s
        head_dy = 0.03 * H * (1 - c) / 2
        eyes = 'half'
    elif action == 'crouch':
        squash = 0.82 + 0.02 * s
    elif action == 'look_left':
        head_dx = -0.07 * W * max(0.0, s)
    elif action == 'look_right':
        head_dx = 0.07 * W * max(0.0, s)

    body_h_now = body_h * squash
    body_cy = ground - body_h_now / 2 + dy
    # 地面阴影
    d.ellipse([cx - body_w * 0.55, ground - H * 0.02, cx + body_w * 0.55, ground + H * 0.03], fill=SHADOW)
    # 尾巴（身体右后侧弧线，happy 时摆动）
    tail_box = [cx + body_w * 0.30, body_cy - body_h_now * 0.10, cx + body_w * 0.85, body_cy + body_h_now * 0.55]
    d.arc(tail_box, start=-70 + tail, end=60 + tail, fill=FUR, width=max(2, int(H * 0.035)))
    # 身体
    d.ellipse(
        [cx - body_w / 2 + dx, body_cy - body_h_now / 2, cx + body_w / 2 + dx, body_cy + body_h_now / 2], fill=FUR
    )
    d.ellipse(
        [cx - body_w * 0.28 + dx, body_cy - body_h_now * 0.10, cx + body_w * 0.28 + dx, body_cy + body_h_now * 0.46],
        fill=BELLY,
    )
    d.ellipse(
        [cx - body_w * 0.42 + dx, body_cy - body_h_now * 0.46, cx - body_w * 0.05 + dx, body_cy - body_h_now * 0.12],
        fill=FUR_LIGHT,
    )
    # 头
    head_r = body_w * 0.40
    head_cx = cx + dx + head_dx
    head_cy = body_cy - body_h_now / 2 - head_r * 0.35 + dy + head_dy
    ear_h = head_r * 0.55 * (1 - ear_drop)
    for side in (-1, 1):
        ex = head_cx + side * head_r * 0.62
        d.polygon(
            [
                (ex - head_r * 0.28, head_cy - head_r * 0.45),
                (ex + head_r * 0.28, head_cy - head_r * 0.45),
                (ex + side * head_r * 0.10, head_cy - head_r * 0.45 - ear_h),
            ],
            fill=FUR,
        )
    d.ellipse([head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r], fill=FUR)
    d.ellipse(
        [head_cx - head_r * 0.75, head_cy - head_r * 0.85, head_cx - head_r * 0.10, head_cy - head_r * 0.25],
        fill=FUR_LIGHT,
    )
    # 眼睛
    eye_y = head_cy - head_r * 0.05
    for side in (-1, 1):
        ex = head_cx + side * head_r * 0.42 + head_dx * 0.15
        if eyes == 'half':
            d.line([ex - head_r * 0.16, eye_y, ex + head_r * 0.16, eye_y], fill=LINE, width=max(2, int(H * 0.008)))
        else:
            r = head_r * 0.11
            d.ellipse([ex - r, eye_y - r, ex + r, eye_y + r], fill=LINE)
    # 鼻子与嘴
    ny = head_cy + head_r * 0.28
    d.polygon([(head_cx - head_r * 0.10, ny), (head_cx + head_r * 0.10, ny), (head_cx, ny + head_r * 0.12)], fill=LINE)
    d.arc(
        [head_cx - head_r * 0.22, ny, head_cx, ny + head_r * 0.28],
        start=0,
        end=120,
        fill=LINE,
        width=max(1, int(H * 0.005)),
    )
    d.arc(
        [head_cx, ny, head_cx + head_r * 0.22, ny + head_r * 0.28],
        start=60,
        end=180,
        fill=LINE,
        width=max(1, int(H * 0.005)),
    )
    if supersample > 1:
        img = img.resize((width, height), Image.LANCZOS)
    return img


def _encode(frames: list[Image.Image], out: Path, *, width: int, height: int, fps: int) -> None:
    cmd = [
        'ffmpeg',
        '-y',
        '-loglevel',
        'error',
        '-f',
        'rawvideo',
        '-pix_fmt',
        'rgb24',
        '-s',
        f'{width}x{height}',
        '-r',
        str(fps),
        '-i',
        'pipe:0',
        '-an',
        '-c:v',
        'libx264',
        '-preset',
        'fast',
        '-crf',
        '28',
        '-pix_fmt',
        'yuv420p',
        '-movflags',
        '+faststart',
        str(out),
    ]
    subprocess.run(cmd, input=b''.join(frame.tobytes() for frame in frames), check=True, capture_output=True)


def build_library(
    root: Path,
    *,
    version: str = DEFAULT_VERSION,
    width: int = 1280,
    height: int = 720,
    fps: int = 24,
    duration: float = 4.0,
    supersample: int = 2,
) -> dict:
    if width % 2 or height % 2:
        raise ValueError('width and height must be even for yuv420p')
    if not 0 < duration <= 5:
        raise ValueError('placeholder clips must be at most 5 seconds')
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    n_frames = max(2, round(fps * duration))
    clips: dict = {}
    for body_type in BODY_TYPES:
        clips[body_type] = {}
        for action in ACTIONS:
            frames = [
                render_frame(
                    body_type, action, 2 * math.pi * i / n_frames, width=width, height=height, supersample=supersample
                )
                for i in range(n_frames)
            ]
            rel = f'{body_type}/{action}.mp4'
            out = root / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            _encode(frames, out, width=width, height=height, fps=fps)
            data = out.read_bytes()
            clips[body_type][action] = {'file': rel, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    manifest = {
        'version': version,
        'art': 'programmatic-placeholder-v1',
        'spec': {
            'width': width,
            'height': height,
            'fps': fps,
            'duration_s': duration,
            'codec': 'h264',
            'audio': False,
            'loop_aligned': True,
        },
        'body_types': list(BODY_TYPES),
        'actions': list(ACTIONS),
        'clips': clips,
    }
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


@dataclass(frozen=True)
class Library:
    root: Path
    manifest: dict

    def clip_path(self, version: str, body_type: str, action: str) -> Path | None:
        if version != self.manifest['version']:
            return None
        clip = self.manifest.get('clips', {}).get(body_type, {}).get(action)
        if not clip or clip.get('file') != f'{body_type}/{action}.mp4':
            return None
        return self.root / clip['file']


def load_library(root: Path) -> Library | None:
    root = Path(root)
    path = root / 'manifest.json'
    if not path.is_file():
        return None
    manifest = json.loads(path.read_text(encoding='utf-8'))
    return Library(root=root, manifest=manifest)


def manifest_payload(library: Library, *, base_url: str) -> dict:
    manifest = library.manifest
    version = manifest['version']
    groups = {
        body_type: {action: f'{base_url}/{version}/{body_type}/{action}.mp4' for action in manifest['actions']}
        for body_type in manifest['body_types']
    }
    return {
        'version': version,
        'spec': manifest['spec'],
        'body_types': manifest['body_types'],
        'actions': manifest['actions'],
        'groups': groups,
    }
