"""T17 F13: GIF export pipeline — 480p, ≤5s, burned-in watermark.

Export-only: runtime playback keeps using MP4 clips (ARCH:236). The watermark
「绒星 · AI 参考」 is rendered server-side so shared files always carry it.
"""
import asyncio
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

WATERMARK_TEXT = '绒星 · AI 参考'
GIF_HEIGHT = 480
GIF_MAX_SECONDS = 5
GIF_FPS = 12
FONT_CANDIDATES = [
    '/System/Library/Fonts/PingFang.ttc',
    '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
]


def resolve_watermark_font() -> str:
    override = os.environ.get('GIF_WATERMARK_FONT')
    if override and Path(override).is_file():
        return override
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError('watermark font not found; set GIF_WATERMARK_FONT to a CJK font file')


def _escape_drawtext(value: str) -> str:
    return value.replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'")


def build_gif_filter(font_path: str) -> str:
    font = _escape_drawtext(font_path)
    text = _escape_drawtext(WATERMARK_TEXT)
    return (f'fps={GIF_FPS},scale=-2:{GIF_HEIGHT}:flags=lanczos,'
            f"drawtext=fontfile='{font}':text='{text}':fontsize=24:fontcolor=white@0.9:"
            'x=w-tw-16:y=h-th-16:box=1:boxcolor=black@0.35:boxborderw=6,'
            'split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3')


def _run(args):
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f'ffmpeg/ffprobe failed: {proc.stderr[-400:]}')
    return proc.stdout


def _export_sync(clip_bytes: bytes, font_path: str):
    with TemporaryDirectory() as tmp:
        src, out = Path(tmp) / 'in.mp4', Path(tmp) / 'out.gif'
        src.write_bytes(clip_bytes)
        _run(['ffmpeg', '-y', '-i', str(src), '-vf', build_gif_filter(font_path),
              '-t', str(GIF_MAX_SECONDS), '-loop', '0', str(out)])
        info = json.loads(_run(['ffprobe', '-v', 'error', '-show_entries', 'format=format_name,duration',
                                '-show_entries', 'stream=codec_type,height', '-of', 'json', str(out)]))
        if 'gif' not in info['format']['format_name']:
            raise RuntimeError('export did not produce a GIF')
        video = next(s for s in info['streams'] if s['codec_type'] == 'video')
        if video['height'] != GIF_HEIGHT:
            raise RuntimeError(f'export height {video["height"]} != {GIF_HEIGHT}')
        duration = float(info['format']['duration'])
        if duration > GIF_MAX_SECONDS + 0.1:
            raise RuntimeError(f'export duration {duration}s exceeds {GIF_MAX_SECONDS}s')
        return out.read_bytes(), duration


async def export_gif(task, *, assets, font_path=None) -> dict:
    payload = task.payload
    font = font_path or resolve_watermark_font()
    clip = await assets.read_object(payload['clip_key'], payload['clip_version_id'])
    data, duration = await asyncio.to_thread(_export_sync, clip, font)
    key = f'gifs/{task.pet_id}/{task.id}/{payload["action"]}.gif'
    version = await assets.write(key, data, 'image/gif')
    return {'key': key, 'version_id': version, 'bytes': len(data),
            'height': GIF_HEIGHT, 'duration_s': round(duration, 2)}
