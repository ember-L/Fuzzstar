"""健康初筛：规则硬判定 + 存档 + 存证媒体 + LLM 建议入队与降级（FRD F05-1~8）。"""
import re
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.advice import template_advice
from app.auth import APIError, get_db, utcnow
from app.media import storage_unavailable
from app.models import HealthEvent, HealthScreening, MediaUpload, Pet, ScreeningMedia, ScreeningSymptom, Task, User
from app.pet_api import consented_user, owned_pet
from app.tasks import enqueue_task
from app.triage import RulesBundle, symptoms_config, triage, validate_answers

router = APIRouter(prefix='/api/v1')

DISCLAIMER = 'AI 结果仅供日常健康管理参考,不替代专业兽医诊断'
REDLINE_CARD = {
    'title': '建议立即就医',
    'subtitle': '该症状可能危及生命,请不要等待观察,尽快前往具备急诊能力的宠物医院。',
    'preparation': ['带上本条记录与存证照片/视频', '出发前电话确认医院急诊能力',
                    '疑似中毒请携带可疑物品包装,勿自行催吐', '勿擅自喂食人用药物'],
}
_MEDIA_ID = re.compile(r'^[0-9a-f]{32}$')
ADVICE_TIMEOUT_SECONDS = 60  # 与移动端 screening_analysis 轮询超时一致


def triage_rules(request: Request) -> RulesBundle:
    bundle = getattr(request.app.state, 'triage_rules', None)
    if bundle is None:
        raise APIError(503, 'CONFIG_UNAVAILABLE', '初筛规则暂不可用')
    return bundle


def advice_templates(request: Request) -> dict:
    templates = getattr(request.app.state, 'advice_templates', None)
    if templates is None:
        raise APIError(503, 'CONFIG_UNAVAILABLE', '建议模板暂不可用')
    return templates


def _advice_view(screening: HealthScreening, task: Optional[Task], templates: dict) -> dict:
    """建议状态解析：LLM 就绪→ready；urgent 无任务模板→ready；失败/超时/耗尽→degraded 模板。"""
    if screening.llm_advice is not None:
        stored = screening.advice_json or {}
        return {'status': 'ready', 'source': 'llm', 'text': screening.llm_advice, 'tips': stored.get('tips')}
    stored = screening.advice_json
    if stored and stored.get('source') == 'template':
        status = 'ready' if screening.task_id is None else 'degraded'
        return {'status': status, 'source': 'template', 'text': stored.get('text'), 'tips': stored.get('tips')}
    fallback = template_advice(templates, screening.state)
    degraded = {'status': 'degraded', 'source': 'template', 'text': fallback['text'], 'tips': fallback['tips']}
    if task is None:
        return degraded
    if task.status == 'failed':
        return degraded
    if task.status in ('pending', 'running') and utcnow() - task.created_at > timedelta(seconds=ADVICE_TIMEOUT_SECONDS):
        return degraded
    return {'status': 'pending', 'source': None, 'text': None, 'tips': None}


class SymptomInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    code: str = Field(max_length=32)
    duration: Optional[str] = Field(default=None, max_length=8)
    frequency: Optional[str] = Field(default=None, max_length=8)
    notes: Optional[str] = None
    severe: bool = False


class ScreeningInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    spirit: Optional[str] = Field(default=None, max_length=16)
    appetite: Optional[str] = Field(default=None, max_length=16)
    symptoms: list[SymptomInput] = Field(default_factory=list, max_length=15)
    redline_options: list[str] = Field(default_factory=list, max_length=20)
    media_ids: list[str] = Field(default_factory=list, max_length=4)


def owned_screening(screening_id: int = Path(gt=0), user: User = Depends(consented_user),
                    db: Session = Depends(get_db)) -> HealthScreening:
    screening = db.scalar(select(HealthScreening).join(Pet, Pet.id == HealthScreening.pet_id).where(
        HealthScreening.id == screening_id, Pet.user_id == user.id, Pet.status == 'active',
    ))
    if screening is None:
        raise APIError(404, 'NOT_FOUND', '未找到初筛记录')
    return screening


def _card(state: str):
    return REDLINE_CARD if state == 'urgent' else None


@router.get('/config/symptoms')
def symptom_config(response: Response, _user: User = Depends(consented_user),
                   bundle: RulesBundle = Depends(triage_rules)):
    response.headers['Cache-Control'] = 'no-store'
    return symptoms_config(bundle)


@router.post('/pets/{pet_id}/screenings', status_code=201)
def submit_screening(data: ScreeningInput, request: Request, response: Response, pet_id: int,
                     user: User = Depends(consented_user), db: Session = Depends(get_db),
                     bundle: RulesBundle = Depends(triage_rules), templates: dict = Depends(advice_templates)):
    pet = owned_pet(pet_id, user, db)
    answers = {'spirit': data.spirit, 'appetite': data.appetite,
               'symptoms': [s.model_dump() for s in data.symptoms], 'redline_options': data.redline_options}
    errors = validate_answers(bundle, answers)
    if errors:
        raise APIError(400, 'VALIDATION_ERROR', '请完善标记的必填项', {'fields': errors})
    if len(set(data.media_ids)) != len(data.media_ids) or any(not _MEDIA_ID.match(m) for m in data.media_ids):
        raise APIError(400, 'VALIDATION_ERROR', '请检查存证媒体', {'fields': [{'field': 'media_ids', 'message': '媒体编号无效或重复'}]})
    media = []
    for media_id in data.media_ids:
        item = db.scalar(select(MediaUpload).join(Pet, Pet.id == MediaUpload.pet_id).where(
            MediaUpload.id == media_id, MediaUpload.pet_id == pet.id, Pet.user_id == user.id, Pet.status == 'active'))
        if item is None:
            raise APIError(404, 'NOT_FOUND', '未找到媒体上传记录')
        if item.version_id is None:
            raise APIError(409, 'MEDIA_NOT_VERIFIED', '请先上传并确认存证媒体')
        media.append(item)
    photos = sum(1 for m in media if m.kind == 'photo')
    videos = sum(1 for m in media if m.kind == 'video')
    if photos > 3 or videos > 1:
        raise APIError(400, 'VALIDATION_ERROR', '请检查存证媒体', {'fields': [{'field': 'media_ids', 'message': '照片最多 3 张、视频最多 1 条'}]})
    result = triage(bundle, answers)
    screening = HealthScreening(pet_id=pet.id, user_id=user.id, state=result['state'], redline_hit=result['redline_hit'],
                                spirit=data.spirit, appetite=data.appetite, rules_version=result['rules_version'],
                                triage_json={'redlines': result['redlines'], 'symptom_grades': result['symptom_grades']})
    db.add(screening)
    db.flush()
    for item in data.symptoms:
        db.add(ScreeningSymptom(screening_id=screening.id, symptom_code=item.code, duration=item.duration,
                                frequency=item.frequency, notes=item.notes, severe=item.severe))
    for item in media:
        db.add(ScreeningMedia(screening_id=screening.id, media_id=item.id, type=item.kind))
    if result['state'] != 'normal':
        db.add(HealthEvent(pet_id=pet.id, source='screening', source_id=screening.id, severity=result['state'],
                           score_delta=bundle.scoring['deltas'][result['state']], active=True))
    if result['state'] == 'urgent':
        # 红线零 LLM：立即持久化模板建议，不建任务、不记用量（AC-05-4）。
        screening.advice_json = template_advice(templates, result['state'])
    else:
        task = enqueue_task(db, pet.id, 'screening_analysis', str(screening.id), {'screening_id': screening.id})
        screening.task_id = task.id
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return {'screening_id': screening.id, 'state': result['state'], 'redline_hit': result['redline_hit'],
            'redlines': result['redlines'], 'symptom_grades': result['symptom_grades'],
            'rules_version': result['rules_version'], 'redline_card': _card(result['state']),
            'disclaimer': DISCLAIMER, 'task_id': screening.task_id, 'created_at': screening.created_at.isoformat()}


@router.get('/screenings/{screening_id}')
def screening_detail(response: Response, screening: HealthScreening = Depends(owned_screening),
                     db: Session = Depends(get_db), bundle: RulesBundle = Depends(triage_rules),
                     templates: dict = Depends(advice_templates)):
    labels = {s['code']: s['label'] for s in bundle.symptoms['symptoms']}
    symptoms = db.scalars(select(ScreeningSymptom).where(ScreeningSymptom.screening_id == screening.id)
                          .order_by(ScreeningSymptom.id)).all()
    media = db.scalars(select(ScreeningMedia).where(ScreeningMedia.screening_id == screening.id)
                       .order_by(ScreeningMedia.id)).all()
    snapshot = screening.triage_json or {}
    task = db.get(Task, screening.task_id) if screening.task_id else None
    response.headers['Cache-Control'] = 'no-store'
    return {'screening_id': screening.id, 'pet_id': screening.pet_id, 'state': screening.state,
            'redline_hit': screening.redline_hit, 'redlines': snapshot.get('redlines', []),
            'spirit': screening.spirit, 'appetite': screening.appetite, 'rules_version': screening.rules_version,
            'created_at': screening.created_at.isoformat(),
            'symptoms': [{'code': s.symptom_code, 'label': labels.get(s.symptom_code, s.symptom_code),
                          'duration': s.duration, 'frequency': s.frequency, 'notes': s.notes, 'severe': s.severe,
                          'grade': snapshot.get('symptom_grades', {}).get(s.symptom_code)} for s in symptoms],
            'symptom_grades': snapshot.get('symptom_grades', {}),
            'media': [{'media_id': m.media_id, 'type': m.type} for m in media],
            'redline_card': _card(screening.state), 'disclaimer': DISCLAIMER,
            'task_id': screening.task_id, 'advice': _advice_view(screening, task, templates),
            'llm_advice': screening.llm_advice, 'advice_json': screening.advice_json}


@router.get('/pets/{pet_id}/screenings')
def screening_history(response: Response, pet_id: int, limit: int = Query(20, ge=1, le=50),
                      user: User = Depends(consented_user), db: Session = Depends(get_db)):
    pet = owned_pet(pet_id, user, db)
    rows = db.scalars(select(HealthScreening).where(HealthScreening.pet_id == pet.id)
                      .order_by(HealthScreening.created_at.desc(), HealthScreening.id.desc()).limit(limit)).all()
    response.headers['Cache-Control'] = 'no-store'
    return {'items': [{'screening_id': s.id, 'state': s.state, 'redline_hit': s.redline_hit,
                       'spirit': s.spirit, 'appetite': s.appetite, 'created_at': s.created_at.isoformat()} for s in rows]}


@router.delete('/screenings/{screening_id}/media/{media_id}', status_code=204)
def delete_screening_media(request: Request, screening_id: int,
                           media_id: str = Path(pattern=r'^[0-9a-f]{32}$'),
                           screening: HealthScreening = Depends(owned_screening),
                           db: Session = Depends(get_db)):
    association = db.scalar(select(ScreeningMedia).where(ScreeningMedia.screening_id == screening.id,
                                                         ScreeningMedia.media_id == media_id))
    if association is None:
        raise APIError(404, 'NOT_FOUND', '未找到该存证媒体')
    db.delete(association)
    db.flush()
    referenced = db.scalar(select(ScreeningMedia).where(ScreeningMedia.media_id == media_id).limit(1))
    if referenced is None:
        tasks = db.scalars(select(Task).where(Task.pet_id == screening.pet_id, Task.type == 'avatar_batch')).all()
        referenced = any((t.payload or {}).get('media_id') == media_id for t in tasks)
    if referenced is None or referenced is False:
        media = db.get(MediaUpload, media_id)
        storage = request.app.state.photo_storage
        if storage is None:
            raise storage_unavailable()
        storage.client.delete_object(Bucket=storage.bucket, Key=media.object_key, VersionId=media.version_id)
        db.delete(media)
    db.commit()
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})
