from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Pet, User


class PetInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=64)
    species: Literal['cat'] = 'cat'
    breed: str | None = Field(default=None, max_length=64)
    sex: Literal['male', 'female', 'unknown'] = 'unknown'
    birth_date: date | None = None
    neutered: bool = False
    body_type: Literal['slim', 'standard', 'chubby'] = 'standard'

    @field_validator('birth_date')
    @classmethod
    def birth_date_not_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError('birth date cannot be in the future')
        return value


class PetNotFound(Exception):
    pass


class PetLimitReached(Exception):
    pass


def list_pets(session: Session, user_id: int) -> list[Pet]:
    return list(session.scalars(select(Pet).where(Pet.user_id == user_id, Pet.status == 'active').order_by(Pet.id)))


def get_pet(session: Session, user_id: int, pet_id: int) -> Pet:
    pet = session.scalar(select(Pet).where(Pet.id == pet_id, Pet.user_id == user_id, Pet.status == 'active'))
    if pet is None:
        raise PetNotFound()
    return pet


def create_pet(session: Session, user_id: int, data: PetInput, limit: int = 5) -> Pet:
    # Lock the owner row so concurrent MySQL transactions cannot exceed the limit.
    owner = session.scalar(select(User).where(User.id == user_id, User.status == 'active').with_for_update())
    if owner is None:
        raise PetNotFound()
    active_ids = session.scalars(
        select(Pet.id).where(Pet.user_id == user_id, Pet.status == 'active').with_for_update()
    ).all()
    if len(active_ids) >= limit:
        raise PetLimitReached()
    pet = Pet(user_id=user_id, **data.model_dump())
    session.add(pet)
    session.flush()
    return pet


def update_pet(session: Session, user_id: int, pet_id: int, data: PetInput) -> Pet:
    pet = get_pet(session, user_id, pet_id)
    for key, value in data.model_dump().items():
        setattr(pet, key, value)
    session.flush()
    return pet


def delete_pet(session: Session, user_id: int, pet_id: int) -> None:
    pet = get_pet(session, user_id, pet_id)
    pet.status = 'deleted'
    pet.deleted_at = datetime.now(UTC).replace(tzinfo=None)
    session.flush()
