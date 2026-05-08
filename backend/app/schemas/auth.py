"""Auth-related request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    invite_token: str | None = None
    # Cloudflare Turnstile token from the front-end widget. Required when
    # ``settings.turnstile_enabled`` is True; ignored otherwise.
    captcha_token: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    captcha_token: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr
    captcha_token: str | None = None


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class AcceptInviteIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    captcha_token: str | None = None
