"""把离线生成的萌宠动图入库，让指定宠物直接用上这些数字分身资产。

脚本复用线上 motion_batch 任务的资产路径与结果结构，因此客户端无需改动：
GIF 落到 motions/{pet_id}/{task_id}/{action}.gif，并写一条已完成的 motion_batch 任务。

Usage (from backend/):
    python -m scripts.seed_motion_assets --email demo@rongxing.app --pet-name 团团
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.models import Pet, Task, User, UserCredential  # noqa: E402
from app.services.avatars import S3Assets  # noqa: E402
from app.services.identity import normalize_email  # noqa: E402
from app.services.motion import verify_gif  # noqa: E402


def log(message: str) -> None:
    print(message, flush=True)


def find_pet(session: Session, email: str, pet_name: str) -> Pet:
    credential = session.scalar(select(UserCredential).where(
        UserCredential.type == 'email', UserCredential.identifier == normalize_email(email)))
    if credential is None:
        raise SystemExit(f'no credential for {email}')
    user = session.get(User, credential.user_id)
    pet = session.scalar(select(Pet).where(Pet.user_id == user.id, Pet.name == pet_name))
    if pet is None:
        raise SystemExit(f'no pet named {pet_name} for {email}')
    return pet


async def seed(settings: Settings, pet: Pet, task_id: str, source_dir: Path, config: dict,
               force_usable: bool = False) -> dict:
    assets = S3Assets.from_env()
    if assets is None:
        raise SystemExit('MEDIA_S3_* is required to store motion assets')
    gifs: dict = {}
    base_key = f'motions/{pet.id}/{task_id}/base.png'
    base_version = await assets.write(base_key, (source_dir / 'base.png').read_bytes(), 'image/png')
    for action in config['actions']:
        path = source_dir / f'{action}.gif'
        if not path.is_file():
            gifs[action] = {'status': 'failed'}
            continue
        data = path.read_bytes()
        spec = verify_gif(data, max_seconds=float(config['max_seconds']),
                          max_height=int(config['height']))
        key = f'motions/{pet.id}/{task_id}/{action}.gif'
        version = await assets.write(key, data, 'image/gif')
        gifs[action] = {'status': 'ready', 'key': key, 'version_id': version, **spec}
        log(f'  {action}: {spec["width"]}x{spec["height"]} {spec["frames"]}f '
            f'{spec["duration_s"]}s {len(data) // 1024}KB')
    ready = sum(1 for item in gifs.values() if item['status'] == 'ready')
    return {'base_image': {'key': base_key, 'version_id': base_version},
            'gifs': gifs, 'ready_count': ready,
            # 预生成资产受免费档额度限制，动作数可能不足 min_ready；此时仍可下发，
            # 缺失动作由客户端回退到底图（F14-5），不会白屏。
            'usable': force_usable or ready >= int(config['min_ready']),
            'config_version': config['version']}


def publish(email: str = 'demo@rongxing.app', pet_name: str = '团团',
            source_dir: Path | None = None, force_usable: bool = False) -> dict:
    """把 source_dir 下的动图写入 MinIO 并刷新任务结果；可被生成脚本复用。"""
    settings = Settings.from_env()
    config = settings.motion_config
    if config is None:
        raise SystemExit('rules/motion.yaml is required')
    source_dir = source_dir or BACKEND_ROOT / 'assets' / 'motion'
    if not source_dir.is_dir():
        raise SystemExit(f'{source_dir} does not exist')

    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        pet = find_pet(session, email, pet_name)
        log(f'pet {pet.id} {pet.name} for {email}')
        request_key = f'seed-motion:{pet.id}:{config["version"]}'
        task = session.scalar(select(Task).where(Task.request_key == request_key))
        if task is None:
            task = Task(id=uuid.uuid4().hex, pet_id=pet.id, type='motion_batch',
                        status='running', request_key=request_key,
                        payload={'source': 'pregen', 'config_version': config['version']},
                        attempts=1)
            session.add(task)
            session.flush()
        # 资产路径里的 task_id 必须与任务主键一致，客户端按同一路径取图。
        result = asyncio.run(seed(settings, pet, task.id, source_dir, config, force_usable))
        task.status = 'succeeded'
        task.result = result
        session.commit()
        log(f'ok: task {task.id} ready {result["ready_count"]}/{len(config["actions"])}')
        return {'task_id': task.id, 'ready_count': result['ready_count'],
                'total': len(config['actions'])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--email', default='demo@rongxing.app')
    parser.add_argument('--pet-name', default='团团')
    parser.add_argument('--source', default=str(BACKEND_ROOT / 'assets' / 'motion'))
    parser.add_argument('--photo', default=str(BACKEND_ROOT.parent / 'mobile' / 'assets' / 'figma' /
                                               '59f10c90466cfa3aa84c0f88478dccedc8f69565.png'))
    parser.add_argument('--force-usable', action='store_true',
                        help='动作数不足 min_ready 也标记为可用，缺失动作由客户端回退底图')
    args = parser.parse_args()
    publish(args.email, args.pet_name, Path(args.source), args.force_usable)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
