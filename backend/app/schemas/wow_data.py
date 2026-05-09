"""Schemas for the WoW localization admin endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WowDataImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    build: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    rows_imported: int
    source: str
    notes: str
    phase: str = ""


class WowDataStatusOut(BaseModel):
    """What the admin UI needs to render the WoW-data card."""

    last_import: WowDataImportOut | None
    counts: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="Rows per (kind, locale). Example: {'spell': {'en': 50000, 'de': 49980}}",
    )
    latest_known_build: str | None = None


class TopLogsEncounterRow(BaseModel):
    encounter_id: int
    encounter_name: str
    encounter_name_localized: str | None = None
    metrics: list[str]
    rows: int
    latest_recorded_at: datetime | None


class TopLogsSeedIn(BaseModel):
    encounter_id: int
    is_raid: bool = True
    # Optional: only refresh specs whose natural metric matches.
    #   "hps" → only healer specs
    #   "dps" → only non-healer specs (DPS + tanks)
    # Empty/None → all specs (full refresh, current default).
    metric: Literal["dps", "hps"] | None = None


class TopLogsSeedJobOut(BaseModel):
    """Live progress row for the admin UI's seed-jobs section."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    encounter_id: int
    encounter_name: str
    is_raid: bool
    metric_filter: str | None
    total_specs: int
    completed_specs: int
    current_spec_slug: str | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    created_at: datetime


class TopLogsCurrentTierEncounter(BaseModel):
    encounter_id: int
    encounter_name: str
    zone_id: int
    zone_name: str
    expansion_id: int
    expansion_name: str


class TopLogsCurrentTierOut(BaseModel):
    queued: int
    skipped_already_running: int
    encounters: list[TopLogsCurrentTierEncounter]
