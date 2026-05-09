"""Localized World of Warcraft game data — populated from wago.tools."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models._types import JSONType
from app.models.base import Base, TimestampMixin


class WowLocalization(Base):
    """Single row per (kind, game_id, locale).

    ``kind`` is one of:
    - ``spell``   — Spells (also covers Talents and Boss abilities, since both
                    are spells in the WoW data model)
    - ``item``    — Items
    - ``encounter`` — Raid/dungeon bosses (matches WCL's encounter_id =
                     JournalEncounter.ID)

    ``extras`` carries kind-specific metadata (item quality, encounter's
    DungeonEncounterID, etc.).
    """

    __tablename__ = "wow_localizations"
    __table_args__ = (
        Index("ix_wow_localizations_lookup", "locale", "kind", "game_id"),
    )

    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    locale: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    extras: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class WowImportStatus(str, enum.Enum):
    in_progress = "in_progress"
    success = "success"
    failed = "failed"


class WowDataImport(Base, TimestampMixin):
    """One row per import run — let admins see what's in the cache."""

    __tablename__ = "wow_data_imports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    build: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=WowImportStatus.in_progress.value)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="wago.tools", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Updated by ``run_full_import`` after each phase so the admin UI can
    # show "Lade Spell-Namen…" / "Lade Items…" / "Lade Encounter…" instead
    # of just a generic "Importing…". Empty when the run is terminal.
    phase: Mapped[str] = mapped_column(String(32), default="", nullable=False)
