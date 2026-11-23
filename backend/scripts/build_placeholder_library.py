"""一次性构建占位片库：python -m scripts.build_placeholder_library（backend 目录，需 ffmpeg）。"""
import argparse
from pathlib import Path

from app.services.placeholders import DEFAULT_VERSION, build_library


def main() -> None:
    parser = argparse.ArgumentParser(description='生成 3 体型 × 7 动作占位片库')
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[1] / 'assets' / 'placeholders')
    parser.add_argument('--version', default=DEFAULT_VERSION)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--fps', type=int, default=24)
    parser.add_argument('--duration', type=float, default=4.0)
    parser.add_argument('--supersample', type=int, default=2)
    args = parser.parse_args()
    manifest = build_library(args.out, version=args.version, width=args.width, height=args.height,
                             fps=args.fps, duration=args.duration, supersample=args.supersample)
    total = sum(clip['bytes'] for group in manifest['clips'].values() for clip in group.values())
    print(f"占位片库 {manifest['version']} → {args.out}（21 条，共 {total / 1024 / 1024:.1f} MiB）")


if __name__ == '__main__':
    main()
