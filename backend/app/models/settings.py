"""Runtime-toggleable settings (key/value table).

Used for things admins should be able to flip without redeploying:
- allow_registration
- ai_provider / ai_model overrides
"""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models._types import JSONType
from app.models.base import Base, TimestampMixin


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
