"""Cached top logs from WCL — refreshed by the daily worker job."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models._types import JSONType
from app.models.base import Base, TimestampMixin


class TopLog(Base, TimestampMixin):
    __tablename__ = "top_logs"
    __table_args__ = (
        Index("ix_top_logs_lookup", "spec_slug", "encounter_id", "rank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    spec_slug: Mapped[str] = mapped_column(
        ForeignKey("game_specs.slug", ondelete="CASCADE"), nullable=False, index=True
    )
    encounter_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    encounter_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric: Mapped[str] = mapped_column(String(8), nullable=False)  # "dps" | "hps"
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    item_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    character_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    server: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    region: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    wcl_report_code: Mapped[str] = mapped_column(String(32), nullable=False)
    wcl_fight_id: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    # ``none_as_null=True`` so Python ``None`` maps to SQL NULL instead of the
    # JSONB ``null`` sentinel — keeps DB queries like ``WHERE detail_payload
    # IS NULL`` and ``count(detail_payload)`` honest about which rows
    # actually have detail data attached. The variant for SQLite (used in
    # tests only) drops the option since plain JSON has no null-sentinel
    # to worry about.
    detail_payload: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True).with_variant(JSON(), "sqlite"), nullable=True
    )
