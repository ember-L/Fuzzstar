from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from typing import Optional

from sqlalchemy import select

from app.auth import APIError, current_user, get_db
from app.consents import grant_consent, latest_consents
from app.models import Pet, User, WeightRecord
from app.pets import PetInput, PetLimitReached, PetNotFound, create_pet, delete_pet, get_pet, list_pets, update_pet

router = APIRouter(prefix='/api/v1')


class PolicyVersions(BaseModel):
    model_config = ConfigDict(extra='forbid')

    privacy: str = Field(min_length=1, max_length=32)
    terms: str = Field(min_length=1, max_length=32)


class LatestWeight(BaseModel):
    weight_kg: float
    measured_at: str


class PetProfile(PetInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # F02-2：体重不在档案手填，来自 F08 最新记录（T13）。
    latest_weight: Optional[LatestWeight] = None


def _latest_weight(db: Session, pet_id: int):
    latest = db.scalar(select(WeightRecord).where(WeightRecord.pet_id == pet_id)
                       .order_by(WeightRecord.measured_at.desc(), WeightRecord.id.desc()).limit(1))
    if latest is None:
        return None
    return {'weight_kg': float(latest.weight_kg), 'measured_at': latest.measured_at.isoformat()}


def _profile_payload(db: Session, pet: Pet) -> dict:
    return {**PetProfile.model_validate(pet).model_dump(), 'latest_weight': _latest_weight(db, pet.id)}


def consent_state(db: Session, user: User, request: Request):
    versions = request.app.state.policy_versions
    if not all(versions.values()):
        raise APIError(503, 'CONSENT_UNAVAILABLE', '隐私政策和服务协议版本尚未配置')
    latest = latest_consents(db, user.id)
    return {
        'required': versions,
        'links': request.app.state.policy_links,
        'granted': all(kind in latest and latest[kind].granted and latest[kind].version == version
                       for kind, version in versions.items()),
        'training_granted': 'training' in latest and latest['training'].granted,
    }


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


def consented_user(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not consent_state(db, user, request)['granted']:
        raise APIError(403, 'CONSENT_REQUIRED', '请先阅读并同意当前版本的协议')
    return user


def owned_pet(pet_id: int, user: User = Depends(consented_user), db: Session = Depends(get_db)):
    try:
        return get_pet(db, user.id, pet_id)
    except PetNotFound as exc:
        raise APIError(404, 'NOT_FOUND', '未找到这只猫咪') from exc


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
