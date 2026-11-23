"""萌宠动图生成接口（FRD F14-6）：整个 AI 接入面只有此文件。

真模型接入时实现 MotionProvider 的 enchant/animate 并在此注册，其余层不动；
PlaceholderMotionProvider 按照片主色程序化绘制，离线可跑通上传到播放全链路。
"""
from __future__ import annotations

import io
import math
import os
from typing import Optional, Protocol

from PIL import Image, ImageDraw

from app.providers.base import GeneratedAsset

# 与首页 hero 卡片同色（theme.ts heroBg #FFEDD7），落地即融合，不出现白底方块。
BG = (255, 237, 215)
SHADOW = (246, 226, 200)
BELLY = (255, 240, 222)
LINE = (104, 58, 24)
EYE = (58, 36, 20)


class MotionProvider(Protocol):
    async def enchant(self, photo: bytes, *, prompt: str) -> GeneratedAsset: ...

    async def animate(self, image: bytes, *, prompt: str, seconds: float) -> GeneratedAsset: ...


def _fur_from_photo(photo: bytes) -> tuple[int, int, int]:
    image = Image.open(io.BytesIO(photo)).convert('RGB')
    image.thumbnail((24, 24))
    colors = [(count, color) for count, color in (image.getcolors(maxcolors=4096) or [])
              if 20 < sum(color) / 3 < 245]
    total = sum(count for count, _color in colors)
    if not total:
        return (254, 174, 54)
    r = sum(count * color[0] for count, color in colors) // total
    g = sum(count * color[1] for count, color in colors) // total
    b = sum(count * color[2] for count, color in colors) // total
    # 提亮到可辨识的卡通色；浅色猫压一档明度，保证与浅底有对比。
    fur = (min(255, int(r * 1.25 + 40)), min(255, int(g * 1.2 + 30)), min(255, int(b * 1.2 + 20)))
    if sum(fur) / 3 > 218:
        fur = tuple(int(channel * 0.78) for channel in fur)
    return fur


def _lighten(color: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(min(255, int(channel + (255 - channel) * ratio)) for channel in color)


def _darken(color: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(max(0, int(channel * (1 - ratio))) for channel in color)


def _draw_frame(fur: tuple[int, int, int], pose: str, phase: float, size: int) -> Image.Image:
    s, c = math.sin(phase), math.cos(phase)
    image = Image.new('RGB', (size, size), BG)
    draw = ImageDraw.Draw(image)
    line = _darken(fur, 0.62)

    dx = dy = head_dx = head_dy = tail = ear_lift = 0.0
    squash, widen, eyes, mouth = 1.0, 1.0, 'open', 'smile'
    paw_lift = 0.0
    if pose == 'idle':
        squash = 1 + 0.02 * s
    elif pose == 'happy':
        dy = -0.08 * size * abs(s)
        tail = 32 * math.sin(2 * phase)
        eyes = 'smile'
    elif pose == 'play':
        paw_lift = 0.11 * size * abs(s)
        dy = -0.03 * size * abs(s)
        head_dx = 0.02 * size * s
        tail = 22 * math.sin(2 * phase)
        eyes = 'smile'
    elif pose == 'stretch':
        widen = 1 + 0.20 * (1 - c) / 2
        squash = 1 - 0.14 * (1 - c) / 2
        head_dy = 0.04 * size * (1 - c) / 2
    elif pose == 'yawn':
        mouth = 'open'
        eyes = 'half'
        head_dy = -0.03 * size * abs(s)
    elif pose == 'groom':
        head_dy = 0.06 * size * (1 - c) / 2
        head_dx = -0.03 * size * (1 - c) / 2
        paw_lift = 0.07 * size * (1 - c) / 2
        eyes = 'half'
    elif pose == 'sleep':
        squash = 0.74
        eyes = 'closed'
        dy = 0.02 * size
        mouth = 'none'
    elif pose == 'alert':
        ear_lift = 0.55
        head_dy = -0.03 * size
        squash = 1.03
    elif pose == 'sad':
        head_dy = 0.07 * size * (1 - c) / 2
        ear_lift = -0.85
        eyes = 'half'
        mouth = 'none'
    elif pose == 'sick':
        squash = 0.80
        eyes = 'half'
        dx = 0.02 * size * s
        dy = 0.02 * size
        mouth = 'none'
    elif pose == 'look_left':
        head_dx = -0.10 * size * max(0.0, s)
    elif pose == 'look_right':
        head_dx = 0.10 * size * max(0.0, s)

    body_w = size * 0.46 * widen
    # 统一叠加 1.2% 呼吸：静止姿态（睡觉/趴卧）也必须有帧间差异，否则 GIF 会被压成单帧。
    body_h = size * 0.40 * squash * (1 + 0.012 * s)
    cx, ground = size / 2, size * 0.90
    body_cy = ground - body_h / 2 + dy

    draw.ellipse([cx - body_w * 0.55, ground - size * 0.02, cx + body_w * 0.55, ground + size * 0.03], fill=SHADOW)
    # 尾巴从身体内侧起笔，被身体盖住根部，避免看起来像悬空的钩子。
    tail_box = [cx + body_w * 0.18, body_cy - body_h * 0.08, cx + body_w * 0.78, body_cy + body_h * 0.52]
    draw.arc(tail_box, start=-86 + tail, end=42 + tail, fill=fur, width=max(4, int(size * 0.038)))
    draw.ellipse([cx - body_w / 2 + dx, body_cy - body_h / 2, cx + body_w / 2 + dx, body_cy + body_h / 2],
                 fill=fur, outline=line, width=max(2, int(size * 0.006)))
    draw.ellipse([cx - body_w * 0.28 + dx, body_cy - body_h * 0.08, cx + body_w * 0.28 + dx, body_cy + body_h * 0.46],
                 fill=BELLY)
    # 前爪：play/groom 时离地抬起，其余贴着地面。
    for side in (-1, 1):
        px = cx + side * body_w * 0.22 + dx
        py = body_cy + body_h * 0.40
        draw.ellipse([px - body_w * 0.10, py - body_h * 0.10, px + body_w * 0.10, py + body_h * 0.10],
                     fill=_lighten(fur, 0.18))
        if paw_lift:
            draw.ellipse([px - body_w * 0.09, py - body_h * 0.16 - paw_lift, px + body_w * 0.09, py + body_h * 0.04 - paw_lift],
                         fill=_lighten(fur, 0.18))

    head_r = body_w * 0.42
    head_cx = cx + dx + head_dx
    head_cy = body_cy - body_h / 2 - head_r * 0.34 + head_dy + dy * 0.4
    # 垂耳（负 lift）时耳朵变矮并向外侧倒，不做成"耳朵消失"。
    drop = max(0.0, -ear_lift)
    ear_h = head_r * max(0.16, 0.52 + ear_lift * 0.5)
    for side in (-1, 1):
        ex = head_cx + side * head_r * 0.60
        tip_x = ex + side * head_r * (0.08 + 0.34 * drop)
        tip_y = head_cy - head_r * 0.42 - ear_h * (1 - 0.55 * drop)
        draw.polygon([(ex - head_r * 0.30, head_cy - head_r * 0.42), (ex + head_r * 0.30, head_cy - head_r * 0.42),
                      (tip_x, tip_y)], fill=fur, outline=line)
    draw.ellipse([head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r],
                 fill=fur, outline=line, width=max(2, int(size * 0.006)))
    draw.ellipse([head_cx - head_r * 0.72, head_cy - head_r * 0.86, head_cx - head_r * 0.12, head_cy - head_r * 0.28],
                 fill=_lighten(fur, 0.35))

    eye_y = head_cy - head_r * 0.04
    for side in (-1, 1):
        ex = head_cx + side * head_r * 0.40
        if eyes == 'closed':
            draw.arc([ex - head_r * 0.18, eye_y - head_r * 0.10, ex + head_r * 0.18, eye_y + head_r * 0.10],
                     start=200, end=340, fill=EYE, width=max(2, int(size * 0.007)))
        elif eyes == 'smile':
            draw.arc([ex - head_r * 0.16, eye_y - head_r * 0.06, ex + head_r * 0.16, eye_y + head_r * 0.20],
                     start=200, end=340, fill=EYE, width=max(2, int(size * 0.008)))
        elif eyes == 'half':
            draw.line([ex - head_r * 0.16, eye_y, ex + head_r * 0.16, eye_y], fill=EYE, width=max(2, int(size * 0.007)))
        else:
            r = head_r * 0.105
            draw.ellipse([ex - r, eye_y - r, ex + r, eye_y + r], fill=EYE)

    nose_y = head_cy + head_r * 0.26
    draw.polygon([(head_cx - head_r * 0.09, nose_y), (head_cx + head_r * 0.09, nose_y),
                  (head_cx, nose_y + head_r * 0.11)], fill=line)
    if mouth == 'open':
        draw.ellipse([head_cx - head_r * 0.16, nose_y + head_r * 0.10, head_cx + head_r * 0.16, nose_y + head_r * 0.46],
                     fill=_darken(fur, 0.45))
    elif mouth == 'smile':
        draw.arc([head_cx - head_r * 0.24, nose_y - head_r * 0.02, head_cx - head_r * 0.02, nose_y + head_r * 0.26],
                 start=10, end=110, fill=line, width=max(1, int(size * 0.005)))
        draw.arc([head_cx + head_r * 0.02, nose_y - head_r * 0.02, head_cx + head_r * 0.24, nose_y + head_r * 0.26],
                 start=70, end=170, fill=line, width=max(1, int(size * 0.005)))
    return image


def _encode_gif(frames: list[Image.Image], fps: int) -> bytes:
    buffer = io.BytesIO()
    frames[0].save(buffer, 'GIF', save_all=True, append_images=frames[1:],
                   duration=round(1000 / fps), loop=0, optimize=False, disposal=2)
    return buffer.getvalue()


class PlaceholderMotionProvider:
    """本地占位实现：无网络、无第三方素材，产出可直接播放的萌化底图与动作 GIF。"""

    def __init__(self, *, seconds: float = 3.0, fps: int = 12, height: int = 480):
        self.seconds = seconds
        self.fps = fps
        self.height = height

    async def enchant(self, photo: bytes, *, prompt: str) -> GeneratedAsset:
        fur = _fur_from_photo(photo)
        image = _draw_frame(fur, 'idle', 0.0, self.height)
        buffer = io.BytesIO()
        image.save(buffer, 'PNG')
        return GeneratedAsset(buffer.getvalue(), 'image/png')

    async def animate(self, image: bytes, *, prompt: str, seconds: float) -> GeneratedAsset:
        pose = prompt.strip().split(' ')[0]
        fur = _fur_from_photo(image)
        frames_count = max(2, round(self.fps * min(seconds, self.seconds)))
        frames = [_draw_frame(fur, pose, 2 * math.pi * index / frames_count, self.height)
                  for index in range(frames_count)]
        return GeneratedAsset(_encode_gif(frames, self.fps), 'image/gif')


def provider_from_env(env: Optional[dict] = None) -> MotionProvider:
    """MOTION_PROVIDER 选择实现；默认占位，接入真模型时在此加分支。"""
    env = os.environ if env is None else env
    kind = (env.get('MOTION_PROVIDER') or 'placeholder').strip()
    if kind == 'placeholder':
        return PlaceholderMotionProvider()
    raise RuntimeError(f'unknown MOTION_PROVIDER: {kind}')
