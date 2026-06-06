"""Report / fight / player schemas exposed by the API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ReportPlayerCastOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ability_id: int
    ability_name: str
    casts: int
    hits: int
    total: int
    icon: str | None


class ReportPlayerGearOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    slot: int
    item_id: int
    item_level: int | None
    item_quality: int | None
    name: str
    icon: str | None
    enchant_id: int | None
    gem_ids: list[int]
    bonus_ids: list[int]


class ReportPlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    server: str
    class_slug: str
    spec_slug: str
    role: str
    item_level: float | None
    dps: float | None
    hps: float | None
    damage_done: int
    healing_done: int
    deaths: int
    # Modern WoW returns a list of `{id, rank, nodeID}` dicts; legacy/Classic
    # logs may emit a serialized string. JSON-serializable either way.
    talents_loadout: Any | None = None
    casts: list[ReportPlayerCastOut] = Field(default_factory=list)
    gear: list[ReportPlayerGearOut] = Field(default_factory=list)
    # ``extras`` carries auxiliary JSON we don't want serialised wholesale
    # (talent_ids, raw aura uptimes, etc.). We surface only the parse-
    # percentile fields the UI cares about via ``computed_field``s below.
    extras: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def parse_percent(self) -> float | None:
        """WCL "Parse %" — percentile vs. all public logs (gear-agnostic)."""
        m = self.extras.get("parse_metrics") if isinstance(self.extras, dict) else None
        return (m or {}).get("rank_percent")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ilvl_percent(self) -> float | None:
        """WCL "iLvl %" — percentile vs. the same item-level bracket."""
        m = self.extras.get("parse_metrics") if isinstance(self.extras, dict) else None
        return (m or {}).get("ilvl_percent")


class ReportFightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fight_id: int
    encounter_id: int | None
    name: str
    name_localized: str | None = None
    difficulty: int | None
    keystone_level: int | None
    is_kill: bool
    boss_percentage: float | None
    duration_ms: int
    start_time: datetime
    players: list[ReportPlayerOut] = Field(default_factory=list)


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    wcl_code: str
    wcl_flavor: str
    title: str
    zone_id: int | None
    zone_name: str
    region: str
    game_version: str
    # Nullable while the worker is still importing the report.
    start_time: datetime | None
    end_time: datetime | None
    # Async-import bookkeeping. ``import_status`` flips ready when the worker
    # has finished populating fights/players; ``import_error`` carries the
    # exception message on failure.
    import_status: str = "ready"
    import_error: str | None = None
    fights: list[ReportFightOut] = Field(default_factory=list)


class ReportImportIn(BaseModel):
    """User submits either a WCL URL or a code."""

    wcl_url_or_code: str = Field(min_length=1, max_length=512)


class ReportSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    wcl_code: str
    wcl_flavor: str
    title: str
    zone_name: str
    start_time: datetime | None
    end_time: datetime | None
    import_status: str = "ready"


class PaginatedReports(BaseModel):
    items: list[ReportSummaryOut]
    total: int
    page: int
    page_size: int
