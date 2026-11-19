"""聊天人设与安全边界（FRD F09-1/2/7）。

人设上下文=档案+最新初筛状态+免责；输出 JSON {reply, emotion}；
禁词（确诊/治疗/诊断）或解析失败抛 ChatReplyError，由 API 降级模板安抚。
红线关键词命中走 redline_response：零 LLM、附就医引导卡（附录 F 文案）。
"""
import json
import re
from pathlib import Path
from typing import Optional

import yaml

EMOTIONS = ('happy', 'relaxed', 'annoyed', 'fearful', 'painful', 'seeking_attention')
FORBIDDEN_WORDS = ('确诊', '治疗', '诊断')
CHAT_DISCLAIMER = 'AI 结果仅供日常健康管理参考,不替代专业兽医诊断'
REDLINE_SUBTITLE = '该症状可能危及生命,请不要等待观察,尽快前往具备急诊能力的宠物医院。'
_FENCE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$', re.IGNORECASE)
_SICK_STATES = ('observe', 'vet', 'urgent')
_SEX_LABELS = {'male': '弟弟', 'female': '妹妹', 'unknown': '小朋友'}
_BODY_LABELS = {'slim': '偏瘦', 'standard': '标准', 'chubby': '偏胖'}


class ChatReplyError(ValueError):
    """LLM 输出不可用（格式错误或含禁词），应降级模板。"""


def load_chat_config(directory: Path) -> Optional[dict]:
    path = Path(directory) / 'chat.yaml'
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        version = data['version']
        if not isinstance(version, str) or not version or len(version) > 32:
            raise ValueError('bad version')
        for key in ('context_window', 'input_max', 'reply_max'):
            if not isinstance(data[key], int) or data[key] <= 0:
                raise ValueError(f'{key} must be a positive integer')
        keywords = data['redline_keywords']
        if not isinstance(keywords, list) or not keywords or not all(isinstance(k, str) and k.strip() for k in keywords):
            raise ValueError('redline_keywords must be a non-empty string list')
        for key in ('disclaimer', 'fallback_reply', 'redline_reply'):
            value = data[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{key} must be non-empty')
        # 免责文案本身含「诊断」一词（边界声明），禁词检查只约束回复模板。
        for key in ('fallback_reply', 'redline_reply'):
            if any(word in data[key] for word in FORBIDDEN_WORDS):
                raise ValueError(f'{key}: forbidden word')
        return {'version': version, 'context_window': data['context_window'],
                'input_max': data['input_max'], 'reply_max': data['reply_max'],
                'disclaimer': data['disclaimer'], 'redline_keywords': list(keywords),
                'fallback_reply': data['fallback_reply'], 'redline_reply': data['redline_reply']}
    except Exception as exc:
        raise RuntimeError(f'Invalid chat config: {path}') from exc


def detect_redline(text: str, config: dict) -> bool:
    return any(keyword in text for keyword in config['redline_keywords'])


def build_persona_messages(pet: dict, screening_state: Optional[str], history: list[dict], config: dict) -> list[dict]:
    """system 人设 + 最近上下文（history 已按窗口截取，role=user/pet）。"""
    profile = [f"名字:{pet['name']}", f"种类:{pet.get('species') or 'cat'}"]
    if pet.get('breed'):
        profile.append(f"品种:{pet['breed']}")
    profile.append(f"性别:{_SEX_LABELS.get(pet.get('sex'), '小朋友')}")
    if pet.get('age_months') is not None:
        profile.append(f"月龄:{pet['age_months']}个月")
    profile.append('已绝育' if pet.get('neutered') else '未绝育')
    if pet.get('body_type'):
        profile.append(f"体型:{_BODY_LABELS.get(pet['body_type'], pet['body_type'])}")
    if screening_state in _SICK_STATES:
        tone = '你最近身体不适(最新初筛提示需要关注),回复要体现不舒服、蔫蔫的语气,可以提到自己没精神或肚子不舒服,但绝不能说出具体病名或做医学判断。'
    else:
        tone = '你最近状态不错,回复活泼亲人。'
    system = (
        f"你扮演一只宠物猫,以第一人称和主人撒娇聊天。档案:{'、'.join(profile)}。{tone}"
        f"只聊日常陪伴与感受,不做诊断、不开处方、不推荐药物;回复严禁出现「确诊」「治疗」「诊断」字样。"
        f"回复不超过{config['reply_max']}字。"
        f"仅输出 JSON:{{\"reply\": \"一句人设回复\", \"emotion\": \"happy/relaxed/annoyed/fearful/painful/seeking_attention 之一\"}}。"
        f"免责边界:{config['disclaimer']}。"
    )
    messages = [{'role': 'system', 'content': system}]
    for item in history:
        messages.append({'role': 'user' if item['role'] == 'user' else 'assistant',
                         'content': item['content'] or ''})
    return messages


def parse_chat_reply(raw: str, config: dict) -> dict:
    text = _FENCE.sub('', raw or '').strip()
    try:
        data = json.loads(text)
        reply = data['reply']
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError('empty reply')
    except (ValueError, KeyError, TypeError) as exc:
        raise ChatReplyError('chat reply is not valid JSON') from exc
    if any(word in reply for word in FORBIDDEN_WORDS):
        raise ChatReplyError('chat reply contains forbidden words')
    emotion = data.get('emotion')
    if emotion not in EMOTIONS:
        emotion = 'relaxed'
    return {'reply': reply.strip()[:config['reply_max']], 'emotion': emotion}


def fallback_reply(config: dict) -> dict:
    return {'reply': config['fallback_reply'], 'emotion': 'relaxed', 'source': 'template'}


def redline_response(config: dict) -> dict:
    return {'reply': config['redline_reply'], 'emotion': 'painful', 'source': 'template',
            'guidance': {'title': '建议立即就医', 'text': REDLINE_SUBTITLE, 'route': 'screening'}}
