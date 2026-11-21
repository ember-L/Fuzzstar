"""Pet profile and consent routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import consented_user, current_user, owned_pet
from app.core.errors import APIError
from app.models import Pet, User, WeightRecord
from app.schemas.pets import PolicyVersions, PetProfile, TrainingConsent
from app.services.consents import consent_state, grant_consent
from app.services.pets import (
    PetInput, PetLimitReached, PetNotFound, create_pet, delete_pet, list_pets, update_pet,
)

router = APIRouter(prefix='/api/v1')


def _latest_weight(db: Session, pet_id: int):
    latest = db.scalar(select(WeightRecord).where(WeightRecord.pet_id == pet_id)
                       .order_by(WeightRecord.measured_at.desc(), WeightRecord.id.desc()).limit(1))
    if latest is None:
        return None
    return {'weight_kg': float(latest.weight_kg), 'measured_at': latest.measured_at.isoformat()}


def _profile_payload(db: Session, pet: Pet) -> dict:
    return {**PetProfile.model_validate(pet).model_dump(), 'latest_weight': _latest_weight(db, pet.id)}


@router.get('/consents')
def read_consents(request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    return consent_state(db, user, request)


@router.post('/consents')
def accept_consents(data: PolicyVersions, request: Request, response: Response,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    state = consent_state(db, user, request)
    if not all(state['links'].values()):
        raise APIError(503, 'CONSENT_UNAVAILABLE', '隐私政策和服务协议原文尚未配置')
    if data.model_dump() != state['required']:
        raise APIError(409, 'CONSENT_VERSION_CHANGED', '协议已更新，请重新阅读并同意')
    if not state['granted']:
        for kind, version in state['required'].items():
            grant_consent(db, user.id, kind, version, True)
        db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return {**state, 'granted': True}


@router.post('/consents/training')
def set_training_consent(data: TrainingConsent, request: Request, response: Response,
                         user: User = Depends(consented_user), db: Session = Depends(get_db)):
    # F12-3：单独弹窗授权，默认 false；拒绝不影响任何功能；v1 无训练数据读取路径。
    version = request.app.state.policy_versions['privacy']
    grant_consent(db, user.id, 'training', version, data.granted)
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return {'training_granted': data.granted}


@router.get('/pets', response_model=list[PetProfile])
def read_pets(response: Response, user: User = Depends(consented_user), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    return [_profile_payload(db, pet) for pet in list_pets(db, user.id)]


@router.post('/pets', status_code=201, response_model=PetProfile)
def add_pet(data: PetInput, response: Response, user: User = Depends(consented_user), db: Session = Depends(get_db)):
    try:
        pet = create_pet(db, user.id, data)
    except PetLimitReached as exc:
        raise APIError(409, 'PET_LIMIT_REACHED', '最多可添加 5 只猫咪') from exc
    except PetNotFound as exc:
        raise APIError(401, 'AUTH_REQUIRED', '请重新登录') from exc
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return _profile_payload(db, pet)


@router.get('/pets/{pet_id}', response_model=PetProfile)
def read_pet(response: Response, pet: Pet = Depends(owned_pet), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    return _profile_payload(db, pet)


@router.patch('/pets/{pet_id}', response_model=PetProfile)
def edit_pet(changes: dict, response: Response, pet: Pet = Depends(owned_pet), db: Session = Depends(get_db)):
    try:
        data = PetInput.model_validate({**PetInput.model_validate(pet, from_attributes=True).model_dump(), **changes})
    except ValueError as exc:
        raise APIError(400, 'VALIDATION_ERROR', '请检查猫咪档案字段') from exc
    try:
        updated = update_pet(db, pet.user_id, pet.id, data)
    except PetNotFound as exc:
        raise APIError(404, 'NOT_FOUND', '未找到这只猫咪') from exc
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return _profile_payload(db, updated)


@router.delete('/pets/{pet_id}', status_code=204)
def remove_pet(pet: Pet = Depends(owned_pet), db: Session = Depends(get_db)):
    try:
        delete_pet(db, pet.user_id, pet.id)
    except PetNotFound as exc:
        raise APIError(404, 'NOT_FOUND', '未找到这只猫咪') from exc
    db.commit()
    return Response(status_code=204)
