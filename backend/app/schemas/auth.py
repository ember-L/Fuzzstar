"""Authentication request/response models."""
from typing import Literal

from pydantic import BaseModel, Field


class LoginInput(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class RefreshInput(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=128)


class VerifyEmailInput(BaseModel):
    token: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal['bearer'] = 'bearer'
    expires_in: int = 1800
