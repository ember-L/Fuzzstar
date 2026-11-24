"""Pet profile and consent request/response models."""

from pydantic import BaseModel, ConfigDict, Field

from app.services.pets import PetInput


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
    latest_weight: LatestWeight | None = None


class TrainingConsent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    granted: bool
