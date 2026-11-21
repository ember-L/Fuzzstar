"""版本化动作映射（FRD 附录 C）。启动时加载：文件缺失 → None（接口 503），内容非法 → 快速失败。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

ACTIONS = ('idle', 'happy', 'sad', 'sick', 'crouch', 'look_left', 'look_right')


def load_action_map(directory: Path) -> Optional[dict]:
    path = Path(directory) / 'action_map.yaml'
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise RuntimeError('action_map.yaml must be a mapping')
    version = data.get('version')
    if not isinstance(version, str) or not version or len(version) > 32:
        raise RuntimeError('action map version must be a non-empty string of at most 32 characters')
    actions = data.get('actions')
    if not isinstance(actions, list) or set(actions) != set(ACTIONS):
        raise RuntimeError('action map must declare exactly the seven supported actions')
    priority = data.get('priority')
    if not isinstance(priority, list) or not priority or not all(isinstance(item, str) for item in priority):
        raise RuntimeError('action map priority must be a non-empty list of sources')
    rules = data.get('rules')
    if not isinstance(rules, list) or not rules:
        raise RuntimeError('action map must contain rules')
    for rule in rules:
        if not isinstance(rule, dict) or rule.get('source') not in priority or not isinstance(rule.get('condition'), dict):
            raise RuntimeError('each rule needs a known source and a condition mapping')
        action = rule.get('action')
        values = action if isinstance(action, list) else [action]
        if not values or not all(isinstance(value, str) and value in ACTIONS for value in values):
            raise RuntimeError('rule actions must be supported action names')
    return data
