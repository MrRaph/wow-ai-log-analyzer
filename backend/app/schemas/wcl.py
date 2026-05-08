"""Schemas for the WCL OAuth connection."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WclAuthorizationStart(BaseModel):
    authorization_url: str


class WclConnectionStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    connected: bool
    wcl_user_id: int | None = None
    wcl_user_name: str = ""
    expires_at: datetime | None = None
    scope: str = ""
