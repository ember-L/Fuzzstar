"""萌宠动图生成管线（FRD F14-1/5）：配置加载、逐动作生成、GIF 规格校验与存档。

AI 能力由 providers/motion.py 注入；本层只做编排与校验，不判断动作语义、不调 LLM。
"""

from __future__ import annotations

import io
from pathlib import Path

import yaml
from PIL import Image

from app.models import MediaUpload, Task

REQUIRED_KEYS = ('version', 'actions', 'prompts', 'health', 'gestures', 'max_seconds', 'height', 'min_ready')
MAX_SECONDS_CAP = 10


def load_motion_config(rules_dir: Path) -> dict | None:
    path = Path(rules_dir) / 'motion.yaml'
    if not path.is_file():
        return None
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise RuntimeError('motion.yaml must be a mapping')
    missing = [key for key in REQUIRED_KEYS if key not in config]
    if missing:
        raise RuntimeError(f'motion.yaml missing keys: {", ".join(missing)}')
    actions = config['actions']
    if not isinstance(actions, list) or not actions or not all(isinstance(a, str) and a for a in actions):
        raise RuntimeError('motion.yaml actions must be a non-empty list of names')
    if not 0 < float(config['max_seconds']) <= MAX_SECONDS_CAP:
        raise RuntimeError(f'motion.yaml max_seconds must be within 0-{MAX_SECONDS_CAP}')
    if not 0 < int(config['min_ready']) <= len(actions):
        raise RuntimeError('motion.yaml min_ready must be within 1 and the action count')
    for gesture, rule in config['gestures'].items():
        rule_actions = rule.get('actions') if isinstance(rule, dict) else None
        if not rule_actions or any(action not in actions for action in rule_actions):
            raise RuntimeError(f'motion.yaml gesture {gesture} references unknown actions')
    for state, action in config['health'].items():
        if action not in actions:
            raise RuntimeError(f'motion.yaml health state {state} references unknown action')
    for emotion, action in (config.get('emotions') or {}).items():
        targets = action if isinstance(action, list) else [action]
        if not targets or any(target not in actions for target in targets):
            raise RuntimeError(f'motion.yaml emotion {emotion} references unknown actions')
    if config.get('standby', actions[0]) not in actions:
        raise RuntimeError('motion.yaml standby must be a known action')
    return config


def verify_gif(data: bytes, *, max_seconds: float, max_height: int) -> dict:
    """逐条校验产物：GIF89a、循环、时长与尺寸不超上限，返回可入库的规格。"""
    image = Image.open(io.BytesIO(data))
    if image.format != 'GIF':
        raise ValueError(f'expected GIF, got {image.format}')
    frames = getattr(image, 'n_frames', 1)
    loop = image.info.get('loop')
    duration = 0.0
    for index in range(frames):
        image.seek(index)
        duration += float(image.info.get('duration', 0)) / 1000
    if duration <= 0:
        raise ValueError('GIF has no frame duration')
    if duration > max_seconds + 0.1:
        raise ValueError(f'GIF duration {duration:.2f}s exceeds {max_seconds}s')
    width, height = image.size
    if height > max_height:
        raise ValueError(f'GIF height {height} exceeds {max_height}')
    if loop != 0:
        raise ValueError('GIF must loop forever')
    return {'width': width, 'height': height, 'frames': frames, 'duration_s': round(duration, 2), 'bytes': len(data)}


async def generate_motion(task: Task, media: MediaUpload, *, config: dict, assets, provider) -> dict:
    if media.version_id is None:
        raise ValueError('motion source photo must be verified')
    photo = await assets.read_photo(media)
    base = await provider.enchant(photo, prompt=config['style_prompt'])
    base_key = f'motions/{task.pet_id}/{task.id}/base.png'
    base_version = await assets.write(base_key, base.data, base.content_type)
    gifs = {}
    for action in config['actions']:
        key = f'motions/{task.pet_id}/{task.id}/{action}.gif'
        try:
            clip = await provider.animate(
                base.data, prompt=config['prompts'].get(action, action), seconds=float(config['max_seconds'])
            )
            spec = verify_gif(clip.data, max_seconds=float(config['max_seconds']), max_height=int(config['height']))
            version = await assets.write(key, clip.data, 'image/gif')
            gifs[action] = {'status': 'ready', 'key': key, 'version_id': version, **spec}
        except Exception:
            # F14-1：单条动图失败不阻断其余动作，客户端按动作粒度降级。
            gifs[action] = {'status': 'failed'}
    ready_count = sum(1 for gif in gifs.values() if gif['status'] == 'ready')
    return {
        'base_image': {'key': base_key, 'version_id': base_version},
        'gifs': gifs,
        'ready_count': ready_count,
        'usable': ready_count >= int(config['min_ready']),
        'config_version': config['version'],
    }


def motion_view(task: Task, config: dict, storage) -> dict:
    actions = config['actions']
    payload = {
        'task_id': task.id,
        'status': task.status,
        'config_version': config['version'],
        'base_image': None,
        'gifs': {},
        'ready_count': 0,
        'usable': False,
    }
    result = task.result if task.status == 'succeeded' else None
    if result is None:
        state = 'failed' if task.status == 'failed' else 'pending'
        payload['gifs'] = {action: {'status': state, 'url': None} for action in actions}
        return payload
    base = result.get('base_image')
    if base:
        payload['base_image'] = {
            'url': storage.asset_url(base['key'], base['version_id']),
            'version_id': base['version_id'],
        }
    for action in actions:
        gif = (result.get('gifs') or {}).get(action)
        if gif and gif.get('status') == 'ready':
            payload['gifs'][action] = {
                'status': 'ready',
                'url': storage.asset_url(gif['key'], gif['version_id']),
                'version_id': gif['version_id'],
                'duration_s': gif.get('duration_s'),
                'bytes': gif.get('bytes'),
            }
        else:
            payload['gifs'][action] = {'status': 'failed', 'url': None}
    payload['ready_count'] = result.get('ready_count', 0)
    payload['usable'] = result.get('usable', False)
    return payload
