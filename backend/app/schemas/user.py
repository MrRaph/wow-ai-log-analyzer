"""User / admin / invite schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    role: UserRole
    is_active: bool
    locale: str
    created_at: datetime
    last_login_at: datetime | None = None


class UserUpdateMe(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    locale: str | None = Field(default=None, pattern=r"^(en|de)$")
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


class InviteIn(BaseModel):
    email: EmailStr
    locale: str = Field(default="en", pattern=r"^(en|de)$")


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    expires_at: datetime
    accepted_at: datetime | None
    revoked: bool
    created_at: datetime


class AdminSettingsOut(BaseModel):
    allow_registration: bool
    ai_provider: str
    ai_model: str


class AdminSettingsUpdate(BaseModel):
    allow_registration: bool | None = None
    ai_provider: str | None = None
    ai_model: str | None = None


class AdminUserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
