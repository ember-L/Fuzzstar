"""录音解读：情绪归一化、人设叠加回复与输出守卫（FRD F09-3/4）。

AudioProvider.interpret 输出情绪+置信度；低于阈值标「不太确定」；
解读失败→unrecognized＋通用安抚（不阻塞文字聊天）；
人设叠加回复沿用文字聊天的 JSON {reply} 契约，禁词/解析失败抛 AudioReplyError。
"""
import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.services.chat import (EMOTIONS, FORBIDDEN_WORDS, _FENCE, persona_tone,
                      pet_profile_lines)
from app.services.media import valid_audio
from app.models import (AiUsageLog, ChatMessage, ChatSession, HealthScreening,
                        MediaUpload, Pet)

AUDIO_FOOTER = '情绪解读为娱乐性参考,置信度仅供判断展示。'
AUDIO_PROMPT = (
    '请解读这段猫咪叫声录音的情绪,从 happy/relaxed/annoyed/fearful/painful/seeking_attention 中选择一个,'
    '并给出 0 到 1 之间的置信度。仅输出 JSON:{"emotion": "...", "confidence": 0.0}。'
)


class AudioReplyError(ValueError):
    """人设叠加回复不可用（格式错误或含禁词），应降级安抚模板。"""


def normalize_emotion(emotion, confidence, config: dict) -> dict:
    """情绪归一化：非法枚举→unrecognized；置信度 clamp 0–1；低于阈值标「不太确定」。"""
    if emotion not in EMOTIONS:
        return {'emotion': 'unrecognized', 'confidence': None, 'uncertain': True}
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        value = 0.0
    value = max(0.0, min(1.0, value))
    return {'emotion': emotion, 'confidence': round(value, 3),
            'uncertain': value < config['audio_confidence_threshold']}


def parse_audio_reply(raw: str, config: dict) -> str:
    text = _FENCE.sub('', raw or '').strip()
    try:
        data = json.loads(text)
        reply = data['reply']
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError('empty reply')
    except (ValueError, KeyError, TypeError) as exc:
        raise AudioReplyError('audio persona reply is not valid JSON') from exc
    if any(word in reply for word in FORBIDDEN_WORDS):
        raise AudioReplyError('audio persona reply contains forbidden words')
    return reply.strip()[:config['reply_max']]


def build_audio_persona_messages(pet: dict, screening_state, emotion: str, confidence,
                                 history: list[dict], config: dict) -> list[dict]:
    """F09-4：情绪之上叠加人设回复，同一线程、同一档案与初筛语气。"""
    profile = '、'.join(pet_profile_lines(pet))
    tone = persona_tone(screening_state)
    uncertain = ''
    if confidence is not None and confidence < config['audio_confidence_threshold']:
        uncertain = '本次解读置信度较低,回复要带一点「不太确定」的语气,但不要否定陪伴。'
    system = (
        f'你在扮演一只宠物猫,用第一人称和主人对话。档案:{profile}。{tone}'
        f'主人刚发来一段录音,情绪解读结果为 {emotion}(置信度 {confidence})。请基于该情绪给出一句人设回复;'
        f'{uncertain}'
        f'只聊日常陪伴与感受,不做诊断、不开处方、不推荐药物;回复严禁出现「确诊」「治疗」「诊断」字样。'
        f'回复不超过{config["reply_max"]}字。'
        f'仅输出 JSON:{{"reply": "一句人设回复"}}。'
        f'免责边界:{config["disclaimer"]}。'
    )
    messages = [{'role': 'system', 'content': system}]
    for item in history:
        messages.append({'role': 'user' if item['role'] == 'user' else 'assistant', 'content': item['content']})
    return messages

def _age_months(pet) -> Optional[int]:
    if pet.birth_date is None:
        return None
    today = utcnow().date()
    months = (today.year - pet.birth_date.year) * 12 + today.month - pet.birth_date.month
    if today.day < pet.birth_date.day:
        months -= 1
    return max(months, 0)


def _record_usage(engine, task, user_id, provider, kind, *, failed: bool) -> None:
    usage = getattr(provider, 'last_usage', None) or {}
    with Session(engine) as db, db.begin():
        db.add(AiUsageLog(user_id=user_id, task_id=task.id,
                          provider=getattr(provider, 'provider', 'unknown'),
                          model=getattr(provider, 'model', 'unknown'), kind=kind,
                          tokens_in=None if failed else usage.get('tokens_in'),
                          tokens_out=None if failed else usage.get('tokens_out')))


async def interpret_audio(engine, task, *, audio_provider, llm_provider, assets, chat_config: dict) -> dict:
    """执行 audio_interpret：情绪解读＋人设叠加回复；失败降级「未识别」＋安抚，不阻塞文字聊天。"""
    payload = task.payload
    with Session(engine) as db:
        media = db.get(MediaUpload, payload['media_id'])
        message = db.get(ChatMessage, payload['message_id'])
        session = db.get(ChatSession, payload['session_id'])
        if media is None or message is None or session is None:
            raise ValueError('audio task references missing rows')
        if media.version_id is None:
            raise ValueError('audio media is not verified')
        pet = db.get(Pet, session.pet_id)
        profile = {'name': pet.name, 'species': pet.species, 'breed': pet.breed, 'sex': pet.sex,
                   'age_months': _age_months(pet), 'neutered': pet.neutered, 'body_type': pet.body_type}
        latest = db.scalar(select(HealthScreening).where(HealthScreening.pet_id == pet.id)
                           .order_by(HealthScreening.created_at.desc(), HealthScreening.id.desc()))
        state = latest.state if latest is not None else None
        window = db.scalars(select(ChatMessage).where(ChatMessage.session_id == session.id,
                                                      ChatMessage.content.is_not(None))
                            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                            .limit(chat_config['context_window'])).all()
        history = [{'role': m.role, 'content': m.content} for m in reversed(window)]
        user_id = session.user_id
        session_id = session.id
        content_type = media.content_type
    data = await assets.read_photo(media)
    normalized = {'emotion': 'unrecognized', 'confidence': None, 'uncertain': True}
    reply = chat_config['audio_fallback_reply']
    if valid_audio(data, content_type) and audio_provider is not None:
        audio_url = await assets.presign_url(media.object_key, media.version_id)
        try:
            result = await audio_provider.interpret(audio_url, AUDIO_PROMPT)
            normalized = normalize_emotion(result.emotion, result.confidence, chat_config)
            _record_usage(engine, task, user_id, audio_provider, 'audio', failed=False)
        except Exception:
            _record_usage(engine, task, user_id, audio_provider, 'audio', failed=True)
            normalized = {'emotion': 'unrecognized', 'confidence': None, 'uncertain': True}
        if normalized['emotion'] != 'unrecognized':
            messages = build_audio_persona_messages(profile, state, normalized["emotion"],
                                                    normalized["confidence"], history, chat_config)
            try:
                raw = await llm_provider.chat(messages, temperature=0.7, max_tokens=300)
                reply = parse_audio_reply(raw, chat_config)
                _record_usage(engine, task, user_id, llm_provider, 'llm', failed=False)
            except Exception:
                reply = chat_config['audio_fallback_reply']
                _record_usage(engine, task, user_id, llm_provider, 'llm', failed=True)
    with Session(engine) as db, db.begin():
        pet_message = ChatMessage(session_id=session_id, role='pet', kind='text', content=reply,
                                  emotion_label=normalized['emotion'] if normalized['emotion'] != 'unrecognized' else None,
                                  emotion_confidence=normalized['confidence'], task_id=task.id)
        db.add(pet_message)
        db.flush()
        pet_message_id = pet_message.id
    return {'emotion': normalized['emotion'], 'confidence': normalized['confidence'],
            'uncertain': normalized['uncertain'], 'reply': reply, 'pet_message_id': pet_message_id}
