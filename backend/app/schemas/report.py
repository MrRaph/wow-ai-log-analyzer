"""Report / fight / player schemas exposed by the API."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    talents_loadout: str | None
    casts: list[ReportPlayerCastOut] = Field(default_factory=list)
    gear: list[ReportPlayerGearOut] = Field(default_factory=list)


class ReportFightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fight_id: int
    encounter_id: int | None
    name: str
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
    title: str
    zone_id: int | None
    zone_name: str
    region: str
    game_version: str
    start_time: datetime
    end_time: datetime
    fights: list[ReportFightOut] = Field(default_factory=list)


class ReportImportIn(BaseModel):
    """User submits either a WCL URL or a code."""

    wcl_url_or_code: str = Field(min_length=1, max_length=512)


class ReportSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    wcl_code: str
    title: str
    zone_name: str
    start_time: datetime
    end_time: datetime
