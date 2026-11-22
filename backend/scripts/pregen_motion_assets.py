"""离线批量生成萌宠动图（F14-6）：用 CogVideoX-Flash 把指定照片生成各动作 GIF。

默认针对应用内置那只猫（mobile/assets/figma 下的原图），产出落到 backend/assets/motion。
免费档限流严重：提交常返回 429，脚本按间隔重试；提交成功即在服务端排队生成，
本脚本保持若干个任务在飞，不等生成完就继续抢下一个动作的额度。

Usage (from backend/):
    python -m scripts.pregen_motion_assets --key <COGVIDEO_API_KEY>
    python -m scripts.pregen_motion_assets --key <key> --actions idle happy --out assets/motion
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.providers.cogvideo import CogVideoError, CogVideoMotionProvider, mp4_to_gif  # noqa: E402
from app.services.motion import verify_gif  # noqa: E402

import yaml  # noqa: E402

DEFAULT_PHOTO = BACKEND_ROOT.parent / 'mobile' / 'assets' / 'figma' / \
    '59f10c90466cfa3aa84c0f88478dccedc8f69565.png'
RULES = BACKEND_ROOT / 'rules' / 'motion.yaml'
# 免费档额度稀缺，按交互使用频次排队：待机与点按动作先出，滑动与负脸状态靠后。
PRIORITY = ('idle', 'happy', 'play', 'groom', 'stretch', 'yawn', 'look_left', 'look_right',
            'alert', 'sleep', 'sad', 'sick')
# 平台内容审核会误判部分动作描述（错误码 1301），这些动作改用中性表述重试。
PROMPT_OVERRIDES = {
    'sleep': '小猫安静地闭眼休息，身体随呼吸轻微起伏',
    'yawn': '小猫抬头，嘴巴轻轻张合一次后合上',
    'look_right': '小猫头部轻轻向右偏，再回到正面',
}


def log(message: str) -> None:
    print(f'[{time.strftime("%H:%M:%S")}] {message}', flush=True)


def load_actions(limit: list[str]) -> tuple[dict, list[str]]:
    config = yaml.safe_load(RULES.read_text(encoding='utf-8'))
    ordered = [action for action in PRIORITY if action in config['actions']]
    ordered += [action for action in config['actions'] if action not in ordered]
    actions = [action for action in ordered if not limit or action in limit]
    return config, actions


def save_manifest(out_dir: Path, manifest: dict, tasks: dict) -> None:
    (out_dir / 'manifest.json').write_text(
        json.dumps({'actions': manifest, 'tasks': tasks}, ensure_ascii=False, indent=2),
        encoding='utf-8')


async def run(provider: CogVideoMotionProvider, config: dict, actions: list[str],
              out_dir: Path, attempts: int, photo: bytes, retry_interval: float,
              concurrency: int, publish_to=None) -> dict:
    manifest: dict = {}
    tasks: dict = {}
    pending = list(actions)
    inflight: dict = {}
    left = {action: attempts for action in actions}
    beat = 0
    limited = 0
    last_attempt = 0.0

    # 已有合格产物的动作直接跳过，免费档额度稀缺，不重复消耗。
    for action in list(pending):
        target = out_dir / f'{action}.gif'
        if not target.is_file():
            continue
        try:
            spec = verify_gif(target.read_bytes(), max_seconds=float(config['max_seconds']),
                              max_height=int(config['height']))
        except Exception:  # noqa: BLE001 - 产物不合格就重做
            target.unlink()
            continue
        manifest[action] = {'status': 'ready', 'path': str(target.relative_to(BACKEND_ROOT)),
                            'bytes': target.stat().st_size, **spec}
        pending.remove(action)
        log(f'    skip {action} (already ready)')

    while pending or inflight:
        # 提交阶段：额度一放开就占位，服务端并行生成。
        while pending and len(inflight) < concurrency:
            # 有任务在飞时外层只 sleep 10s，这里补一道最小间隔，避免把免费池刷成限流。
            gap = time.monotonic() - last_attempt
            if gap < retry_interval:
                await asyncio.sleep(retry_interval - gap)
            last_attempt = time.monotonic()
            action = pending[0]
            prompt = PROMPT_OVERRIDES.get(action) or config['prompts'].get(action, action)
            try:
                task_id = await provider.submit(photo, prompt=prompt, seconds=provider.seconds)
            except CogVideoError as exc:
                message = str(exc)
                if 'submit exhausted' in message or '429' in message:
                    limited += 1
                    if limited % 5 == 1:
                        log(f'    rate limited x{limited} (pending {pending})')
                    break
                left[action] -= 1
                log(f'    {action} submit error ({left[action]} left): {message[:160]}')
                if left[action] <= 0:
                    manifest[action] = {'status': 'failed'}
                    pending.pop(0)
                continue
            except Exception as exc:  # noqa: BLE001 - 网关抖动不该终止整批
                left[action] -= 1
                log(f'    {action} submit exception ({left[action]} left): {str(exc)[:160]}')
                if left[action] <= 0:
                    manifest[action] = {'status': 'failed'}
                    pending.pop(0)
                await asyncio.sleep(retry_interval)
                continue
            pending.pop(0)
            tasks[action] = task_id
            inflight[action] = (task_id, asyncio.create_task(provider.fetch_video(task_id)))
            log(f'    submitted {action} task {task_id}')

        finished = [action for action, (_id, task) in inflight.items() if task.done()]
        for action in finished:
            task_id, task = inflight.pop(action)
            try:
                video = task.result()
                (out_dir / f'{action}.mp4').write_bytes(video)
                gif = mp4_to_gif(video, fps=provider.fps, height=provider.height)
                spec = verify_gif(gif, max_seconds=float(config['max_seconds']),
                                  max_height=int(config['height']))
                target = out_dir / f'{action}.gif'
                target.write_bytes(gif)
                manifest[action] = {'status': 'ready', 'path': str(target.relative_to(BACKEND_ROOT)),
                                    'bytes': len(gif), 'task_id': task_id, **spec}
                log(f'    ok {action} {spec["width"]}x{spec["height"]} {spec["frames"]}f '
                    f'{spec["duration_s"]}s {len(gif) // 1024}KB')
                if publish_to is not None:
                    # 每出一片就刷新一次线上资产，App 端无需等待整批完成。
                    try:
                        await asyncio.to_thread(publish_to)
                    except Exception as exc:  # noqa: BLE001 - 入库失败不影响继续生成
                        log(f'    seed failed: {str(exc)[:160]}')
            except Exception as exc:  # noqa: BLE001 - 单个动作失败不影响其余
                message = str(exc)
                # 槽位一旦被占，服务端要挂满整轮才释放；中途放弃既拿不到产物又照样占额度，
                # 因此超时与 1234 网络错误都按失败重排队，而不是丢掉这个动作。
                retryable = 'timeout' in message or 'video synthesis failed' in message
                if retryable and left[action] > 0:
                    left[action] -= 1
                    pending.append(action)
                    log(f'    retry {action} ({left[action]} left): {message[:120]}')
                else:
                    manifest[action] = {'status': 'failed', 'task_id': task_id, 'error': message[:200]}
                    log(f'    failed {action}: {message[:160]}')
            save_manifest(out_dir, manifest, tasks)

        if inflight:
            beat += 1
            if beat % 15 == 0:
                log(f'    ...in flight {list(inflight)} pending {len(pending)}')
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(retry_interval)
    save_manifest(out_dir, manifest, tasks)
    return manifest


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--key', default=os.environ.get('COGVIDEO_API_KEY', ''))
    parser.add_argument('--photo', default=str(DEFAULT_PHOTO))
    parser.add_argument('--out', default=str(BACKEND_ROOT / 'assets' / 'motion'))
    parser.add_argument('--actions', nargs='*', default=[])
    parser.add_argument('--attempts', type=int, default=15)
    parser.add_argument('--retry-interval', type=float, default=20.0)
    parser.add_argument('--concurrency', type=int, default=3)
    parser.add_argument('--poll-timeout', type=float, default=2400.0)
    parser.add_argument('--quality', default='speed')
    parser.add_argument('--email', default='demo@rongxing.app')
    parser.add_argument('--pet-name', default='团团')
    parser.add_argument('--fps', type=int, default=12)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--seconds', type=int, default=5)
    parser.add_argument('--seed', action='store_true',
                        help='每出一片就写入 MinIO 并刷新线上任务，App 端即时可播')
    args = parser.parse_args()

    if not args.key:
        print('COGVIDEO_API_KEY is required', file=sys.stderr)
        return 1

    photo = Path(args.photo).read_bytes()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    config, actions = load_actions(args.actions)
    log(f'actions={actions} out={out_dir} concurrency={args.concurrency} quality={args.quality}')

    provider = CogVideoMotionProvider(api_key=args.key, fps=args.fps, height=args.height,
                                      seconds=args.seconds, submit_attempts=1, poll_interval=6.0,
                                      poll_timeout=args.poll_timeout, quality=args.quality)
    # 底图沿用原猫照片，与动图同源，客户端加载动图前不会闪出另一只猫。
    (out_dir / 'base.png').write_bytes(photo)
    publish_to = None
    if args.seed:
        from scripts.seed_motion_assets import publish

        publish_to = lambda: publish(args.email, args.pet_name, out_dir, True)  # noqa: E731
    manifest = await run(provider, config, actions, out_dir, args.attempts, photo,
                         args.retry_interval, args.concurrency, publish_to)
    ready = sum(1 for item in manifest.values() if item['status'] == 'ready')
    log(f'done: {ready}/{len(actions)} ready')
    return 0 if ready == len(actions) else 2


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
