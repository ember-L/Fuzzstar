"""T12 饮食记录与喂养参考（FRD F07-1~4，附录 E）。

kcal 估算与 RER/DER 参考均为纯规则（rules/feeding.yaml），禁止 LLM 参与；
按日聚合使用客户端本地时区偏移，保证跨本地自然日正确。
"""
import re
from datetime import date as date_type, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import APIError, get_db, utcnow
from app.feeding import FEEDING_DISCLAIMER, feeding_reference, kcal_estimate
from app.models import DietRecord, User, WeightRecord
from app.pet_api import consented_user, owned_pet

router = APIRouter(prefix='/api/v1/pets', tags=['diet'])

MAX_BACKDATE = timedelta(days=7)
FUTURE_SKEW = timedelta(seconds=60)
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def feeding_config(request: Request) -> dict:
    config = getattr(request.app.state, 'feeding_config', None)
    if config is None:
        raise APIError(503, 'CONFIG_UNAVAILABLE', '喂养参考配置暂不可用')
    return config


class DietInput(BaseModel):
    model_config = {'extra': 'forbid'}

    food_type: Literal['dry', 'wet', 'snack', 'other']
    amount_g: float
    food_name: Optional[str] = None
    fed_at: Optional[datetime] = None
    note: Optional[str] = None


def _record_payload(record: DietRecord) -> dict:
    return {'id': record.id, 'food_type': record.food_type, 'food_name': record.food_name,
            'amount_g': float(record.amount_g), 'kcal_est': None if record.kcal_est is None else float(record.kcal_est),
            'fed_at': record.fed_at.isoformat(), 'note': record.note, 'created_at': record.created_at.isoformat()}


def _day_window(day: date_type, tz_offset_minutes: int) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time()) - timedelta(minutes=tz_offset_minutes)
    return start, start + timedelta(days=1)


@router.post('/{pet_id}/diet', status_code=201)
def create_diet(pet_id: int, body: DietInput, response: Response,
                user: User = Depends(consented_user), db: Session = Depends(get_db),
                config: dict = Depends(feeding_config)):
    pet = owned_pet(pet_id, user, db)
    now = utcnow()
    fields = []
    if not 0 < body.amount_g <= 2000:
        fields.append({'field': 'amount_g', 'message': '克数需大于 0 且不超过 2000'})
    if body.food_name is not None and len(body.food_name) > 64:
        fields.append({'field': 'food_name', 'message': '食物名称不超过 64 字'})
    if body.note is not None and len(body.note) > 255:
        fields.append({'field': 'note', 'message': '备注不超过 255 字'})
    fed_at = body.fed_at
    if fed_at is not None:
        if fed_at.tzinfo is not None:
            fed_at = fed_at.astimezone(timezone.utc).replace(tzinfo=None)
        if fed_at > now + FUTURE_SKEW:
            fields.append({'field': 'fed_at', 'message': '喂食时间不能晚于当前时间'})
        elif fed_at < now - MAX_BACKDATE:
            fields.append({'field': 'fed_at', 'message': '喂食时间最多回改 7 天'})
    else:
        fed_at = now
    if fields:
        raise APIError(400, 'VALIDATION_ERROR', '记录内容校验未通过', {'fields': fields})
    amount = round(body.amount_g, 1)
    record = DietRecord(pet_id=pet.id, food_type=body.food_type, food_name=body.food_name,
                        amount_g=amount, kcal_est=kcal_estimate(config, body.food_type, amount),
                        fed_at=fed_at, note=body.note)
    db.add(record)
    db.commit()
    db.refresh(record)
    response.headers['Cache-Control'] = 'no-store'
    return _record_payload(record)


@router.get('/{pet_id}/diet')
def list_diet(pet_id: int, response: Response,
              date: Optional[str] = Query(None),
              tz_offset_minutes: int = Query(0, ge=-840, le=840),
              limit: int = Query(20, ge=1, le=50),
              user: User = Depends(consented_user), db: Session = Depends(get_db)):
    pet = owned_pet(pet_id, user, db)
    response.headers['Cache-Control'] = 'no-store'
    if date is None:
        items = db.scalars(select(DietRecord).where(DietRecord.pet_id == pet.id)
                           .order_by(DietRecord.fed_at.desc(), DietRecord.id.desc()).limit(limit)).all()
        return {'items': [_record_payload(r) for r in items], 'count': len(items)}
    if not DATE_RE.match(date):
        raise APIError(400, 'VALIDATION_ERROR', '日期格式应为 YYYY-MM-DD')
    try:
        day = date_type.fromisoformat(date)
    except ValueError:
        raise APIError(400, 'VALIDATION_ERROR', '日期格式应为 YYYY-MM-DD')
    start, end = _day_window(day, tz_offset_minutes)
    items = db.scalars(select(DietRecord).where(DietRecord.pet_id == pet.id,
                                                DietRecord.fed_at >= start, DietRecord.fed_at < end)
                       .order_by(DietRecord.fed_at.asc(), DietRecord.id.asc())).all()
    return {'date': date, 'tz_offset_minutes': tz_offset_minutes,
            'items': [_record_payload(r) for r in items],
            'total_g': round(sum(float(r.amount_g) for r in items), 1),
            'total_kcal': round(sum(float(r.kcal_est or 0) for r in items), 1),
            'count': len(items)}


@router.delete('/{pet_id}/diet/{record_id}', status_code=204)
def delete_diet(pet_id: int, record_id: int,
                user: User = Depends(consented_user), db: Session = Depends(get_db)):
    pet = owned_pet(pet_id, user, db)
    record = db.get(DietRecord, record_id)
    if record is None or record.pet_id != pet.id:
        raise APIError(404, 'NOT_FOUND', '饮食记录不存在')
    db.delete(record)
    db.commit()
    return Response(status_code=204)


@router.get('/{pet_id}/feeding-reference')
def feeding_reference_view(pet_id: int, response: Response,
                           user: User = Depends(consented_user), db: Session = Depends(get_db),
                           config: dict = Depends(feeding_config)):
    pet = owned_pet(pet_id, user, db)
    response.headers['Cache-Control'] = 'no-store'
    latest = db.scalar(select(WeightRecord).where(WeightRecord.pet_id == pet.id)
                       .order_by(WeightRecord.measured_at.desc(), WeightRecord.id.desc()).limit(1))
    if latest is None:
        return {'has_weight': False, 'guidance': '暂无体重记录，请先记录猫咪体重后再查看喂养参考。',
                'disclaimer': FEEDING_DISCLAIMER}
    reference = feeding_reference(config, weight_kg=float(latest.weight_kg),
                                  birth_date=pet.birth_date, neutered=pet.neutered, now=utcnow())
    return {'has_weight': True, 'measured_at': latest.measured_at.isoformat(), **reference}
