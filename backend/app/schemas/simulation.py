"""Pydantic schemas for the SimulationCraft endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.simulation import SimulationRunStatus, SimulationStatus

Rotation = Literal["simc_default", "blizzard", "custom"]
FightProfileKey = Literal["single_target", "council", "mythic_plus"]
Precision = Literal["fast", "medium", "precise"]

# Iteration count for each precision preset. The /info endpoint exposes
# these so the frontend can show an indicative count next to the button.
# Tuned so "fast" returns in ~10 s on a fast box, "medium" in ~25 s, and
# "precise" in ~45-60 s for a single-target Patchwerk run. M+ DungeonSlice
# scales roughly 3x because the fight is longer + multi-target work.
PRECISION_ITERATIONS: dict[str, int] = {
    "fast": 1000,
    "medium": 2500,
    "precise": 5000,
}


class LoadoutIn(BaseModel):
    """One talent build the user wants to compare.

    ``talents`` holds the talent-string portion the user pasted (just
    the ``talents=…``/``class_talents=…``/``spec_talents=…`` lines, or
    a single B64 talent string the in-game UI exports). Empty means
    "use whatever the base /simc profile already has".
    """

    name: str = Field(default="", max_length=120)
    talents: str = Field(default="", max_length=20000)


class SimulationCreate(BaseModel):
    """Payload for ``POST /simulations``.

    The cartesian product ``loadouts × fight_profiles × rotations``
    becomes the per-row ``SimulationRun`` table. The frontend renders
    the grid along whichever axes have > 1 entry, so a 1-loadout +
    1-fight + 2-rotation request collapses to a simple two-row
    "with / without Blizzard" comparison.
    """

    label: str = Field(default="", max_length=255)
    simc_profile: str = Field(min_length=20, max_length=200_000)
    fight_profiles: list[FightProfileKey] = Field(min_length=1, max_length=3)
    loadouts: list[LoadoutIn] = Field(min_length=1, max_length=3)
    # 1-3 rotation modes to simulate. Defaults to community APL only.
    # ``custom`` lets advanced users keep whatever ``actions=`` block
    # they pasted in the profile.
    rotations: list[Rotation] = Field(
        default_factory=lambda: ["simc_default"], min_length=1, max_length=3
    )
    precision: Precision = "precise"


class SimulationAbility(BaseModel):
    name: str = ""
    school: str = ""
    dps: float = 0.0
    pct: float = 0.0
    damage_per_iter: float = 0.0
    executes: float = 0.0
    hits: float = 0.0
    crit_pct: float = 0.0


class SimulationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    simulation_id: uuid.UUID
    loadout_index: int
    loadout_name: str
    rotation: Rotation
    fight_profile_key: FightProfileKey
    status: SimulationRunStatus
    dps_mean: float
    dps_min: float
    dps_max: float
    dps_stddev: float
    fight_length_mean: float
    abilities: list[SimulationAbility]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SimulationOut(BaseModel):
    """Full detail view — includes every run for the comparison grid."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requested_by_id: uuid.UUID | None
    label: str
    simc_profile: str
    loadouts: list[LoadoutIn]
    fight_profiles: list[FightProfileKey]
    rotations: list[Rotation]
    iterations: int
    precision: Precision
    status: SimulationStatus
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    simc_build: str | None
    created_at: datetime
    updated_at: datetime
    runs: list[SimulationRunOut] = Field(default_factory=list)


class SimulationListItem(BaseModel):
    """Lightweight view used by ``GET /simulations`` (no per-run detail)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    status: SimulationStatus
    iterations: int
    precision: Precision
    fight_profiles: list[FightProfileKey]
    rotations: list[Rotation]
    loadout_count: int
    created_at: datetime
    finished_at: datetime | None


class PaginatedSimulations(BaseModel):
    items: list[SimulationListItem]
    total: int
    page: int
    page_size: int
