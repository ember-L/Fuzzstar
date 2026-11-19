"""T08 首页健康聚合：状态档+健康分+扣分明细+概览入口（FRD F04）。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_db, utcnow
from app.health import compute_health
from app.models import DietRecord, HealthEvent, HealthScreening, User, WeightRecord
from app.pet_api import consented_user, owned_pet
from app.screening_api import REDLINE_CARD, triage_rules
from app.triage import RulesBundle

router = APIRouter(prefix='/api/v1/pets', tags=['health'])


def _diet_today(pet_id: int, tz_offset_minutes: int, db: Session) -> dict:
    now = utcnow()
    local_today = (now + timedelta(minutes=tz_offset_minutes)).date()
    start = datetime.combine(local_today, datetime.min.time()) - timedelta(minutes=tz_offset_minutes)
    records = db.scalars(select(DietRecord).where(DietRecord.pet_id == pet_id,
                                                  DietRecord.fed_at >= start,
                                                  DietRecord.fed_at < start + timedelta(days=1))).all()
    return {'date': local_today.isoformat(),
            'total_g': round(sum(float(r.amount_g) for r in records), 1),
            'total_kcal': round(sum(float(r.kcal_est or 0) for r in records), 1),
            'count': len(records)}


def _latest_weight(pet_id: int, db: Session):
    latest = db.scalar(select(WeightRecord).where(WeightRecord.pet_id == pet_id)
                       .order_by(WeightRecord.measured_at.desc(), WeightRecord.id.desc()).limit(1))
    if latest is None:
        return None
    return {'weight_kg': float(latest.weight_kg), 'measured_at': latest.measured_at.isoformat()}


@router.get('/{pet_id}/health')
def pet_health(pet_id: int, response: Response,
               tz_offset_minutes: int = Query(0, ge=-840, le=840),
               user: User = Depends(consented_user),
               db: Session = Depends(get_db), bundle: RulesBundle = Depends(triage_rules)):
    pet = owned_pet(pet_id, user, db)
    labels = {s['code']: s['label'] for s in bundle.symptoms['symptoms']}
    events = db.scalars(select(HealthEvent).where(HealthEvent.pet_id == pet.id)
                        .order_by(HealthEvent.created_at.desc(), HealthEvent.id.desc())).all()
    snapshots = []
    for event in events:
        symptoms: list[str] = []
        rules_version = None
        if event.source == 'screening' and event.source_id is not None:
            screening = db.get(HealthScreening, event.source_id)
            if screening is not None:
                rules_version = screening.rules_version
                grades = (screening.triage_json or {}).get('symptom_grades', {})
                symptoms = [labels.get(code, code) for code in grades]
        snapshots.append({'id': event.id, 'source': event.source, 'source_id': event.source_id,
                          'severity': event.severity, 'score_delta': event.score_delta, 'active': event.active,
                          'resolved_at': event.resolved_at, 'created_at': event.created_at,
                          'rules_version': rules_version, 'symptoms': symptoms})
    latest = db.scalar(select(HealthScreening).where(HealthScreening.pet_id == pet.id)
                       .order_by(HealthScreening.created_at.desc(), HealthScreening.id.desc()).limit(1))
    result = compute_health(snapshots, has_screening=latest is not None, now=utcnow(),
                            decay_hours=bundle.scoring['decay']['observe_hours'])
    for item in result['deductions']:
        item['created_at'] = item['created_at'].isoformat()
    response.headers['Cache-Control'] = 'no-store'
    return {'pet_id': pet.id, 'state': result['state'], 'score': result['score'],
            'rules_version': bundle.scoring['version'], 'deductions': result['deductions'],
            'latest_screening': None if latest is None else {
                'screening_id': latest.id, 'state': latest.state, 'created_at': latest.created_at.isoformat()},
            'diet_today': _diet_today(pet.id, tz_offset_minutes, db),
            'latest_weight': _latest_weight(pet.id, db),
            'urgent_card': REDLINE_CARD if result['state'] == 'urgent' else None}
