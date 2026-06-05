"""Per-user Warcraft Logs OAuth connection (access + refresh token)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserWclConnection(Base, TimestampMixin):
    __tablename__ = "user_wcl_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    flavor: Mapped[str] = mapped_column(String(16), primary_key=True, default="retail")
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    wcl_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wcl_user_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
