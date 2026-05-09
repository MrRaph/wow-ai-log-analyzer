"""Tracks the progress of a single per-encounter top-logs seed run.

One row is created per ``(encounter_id, metric_filter)`` triggered seed.
The arq worker fetches a row, walks through the matching specs, increments
``completed_specs`` after each one, and finally flips ``status`` to
``succeeded`` (or ``failed`` on uncaught exception). The admin UI polls a
filtered list of these rows to render a live progress display.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TopLogsSeedJob(Base, TimestampMixin):
    __tablename__ = "top_logs_seed_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    encounter_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    is_raid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # null = "all roles", "dps" = dps + tank specs, "hps" = healer specs
    metric_filter: Mapped[str | None] = mapped_column(String(8), nullable=True)
    total_specs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_specs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Most recent spec the worker started on — gives the UI a "currently
    # processing X" line. Cleared once the job is terminal.
    current_spec_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    # "queued" → enqueued, worker hasn't picked it up yet
    # "running" → worker is iterating specs
    # "succeeded" → all specs done
    # "failed" → uncaught exception; ``error`` carries the message
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
