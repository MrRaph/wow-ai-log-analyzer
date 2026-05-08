"""Analysis schemas — both the request and the structured AI output."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.analysis import AnalysisStatus

Severity = Literal["critical", "high", "medium", "low", "info"]


class AnalysisFinding(BaseModel):
    """One discrete piece of feedback the AI returns about the player."""

    severity: Severity
    title: str
    detail: str
    estimated_loss_pct: float | None = Field(
        default=None,
        description="Estimated DPS/HPS the player loses by *not* fixing this, in percent.",
        ge=0,
        le=100,
    )
    category: Literal["rotation", "cooldowns", "stats", "talents", "gear", "trinkets", "consumables", "mechanics", "other"]
    related_spell_ids: list[int] = Field(default_factory=list)
    related_item_ids: list[int] = Field(default_factory=list)


class AnalysisStructured(BaseModel):
    """Top-level shape the AI is asked to return as JSON."""

    headline: str = Field(description="One-line TL;DR of the player's biggest problem.")
    overall_score: int = Field(ge=0, le=100, description="0-100 grade for this performance.")
    role_focus: Literal["dps", "healer", "tank"]
    strengths: list[str] = Field(default_factory=list)
    findings: list[AnalysisFinding] = Field(default_factory=list)
    rotation_summary: str = ""
    cooldown_usage_summary: str = ""
    stat_recommendations: str = ""
    talent_recommendations: str = ""
    gear_and_trinket_notes: str = ""
    comparison_to_top_logs: str = ""


class AnalysisIn(BaseModel):
    report_id: uuid.UUID
    fight_id: uuid.UUID
    player_id: uuid.UUID


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: AnalysisStatus
    locale: str
    provider: str
    model: str
    summary: str
    structured: AnalysisStructured | dict
    error: str | None
    prompt_tokens: int
    completion_tokens: int
    created_at: datetime
    updated_at: datetime


class AnalysisListItem(BaseModel):
    """Compact summary returned by ``GET /analyses`` for the user's history list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: AnalysisStatus
    locale: str
    provider: str
    model: str
    created_at: datetime
    headline: str = ""
    overall_score: int | None = None
    role_focus: str | None = None
    # Just enough to render the list row
    report_id: uuid.UUID
    report_code: str
    fight_id: uuid.UUID
    fight_name: str = ""
    fight_name_localized: str | None = None
    encounter_id: int | None = None
    player_id: uuid.UUID
    player_name: str
    player_class: str
    player_spec: str


class PaginatedAnalyses(BaseModel):
    items: list[AnalysisListItem]
    total: int
    page: int
    page_size: int


class TopLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    spec_slug: str
    encounter_id: int
    encounter_name: str
    encounter_name_localized: str | None = None
    difficulty: int | None
    metric: str
    rank: int
    amount: float
    item_level: float | None
    duration_ms: int | None
    character_name: str
    server: str
    region: str
    wcl_report_code: str
    wcl_fight_id: int
    recorded_at: datetime
