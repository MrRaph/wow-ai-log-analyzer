"""Endpoints for SimulationCraft DPS simulations.

Lifecycle:

  POST   /simulations         create + enqueue worker (202 + pending row)
  GET    /simulations         paginated list of the caller's sims
  GET    /simulations/{id}    full detail (parent + every run, for the grid)
  DELETE /simulations/{id}    drop the request and its runs
  GET    /simulations/_info   fight profile catalogue + sidecar version

The worker (``run_simulation_task``) is responsible for transitioning
the rows from ``pending`` → ``running`` → terminal. The frontend polls
the detail endpoint until ``status`` is terminal.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.deps import ArqDep, CurrentUser, SessionDep
from app.models import (
    Simulation,
    SimulationRun,
    SimulationRunStatus,
    SimulationStatus,
    UserRole,
)
from app.schemas.simulation import (
    PaginatedSimulations,
    SimulationCreate,
    SimulationListItem,
    SimulationOut,
)
from app.services import simc_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/_info")
async def simulation_info() -> dict:
    """Static metadata the frontend needs to render the create form
    (fight profile catalogue, current defaults, sidecar version).

    Sidecar version is best-effort: if the simc container isn't up the
    frontend still shows the form, it just hides the build banner.
    """
    version_info: dict = {}
    try:
        version_info = await simc_service.ping_version()
    except Exception:  # noqa: BLE001
        version_info = {"banner": "", "unreachable": True}

    return {
        "fight_profiles": [
            {
                "key": key,
                "fight_style": meta["fight_style"],
                "desired_targets": meta["desired_targets"],
                "label_en": meta["label_en"],
                "label_de": meta["label_de"],
            }
            for key, meta in simc_service.FIGHT_PROFILES.items()
        ],
        "rotations": ["simc_default", "blizzard", "custom"],
        "default_iterations": settings.simc_default_iterations,
        "max_loadouts": settings.simc_max_loadouts,
        "retention_days": settings.simc_retention_days,
        "simc_build": version_info.get("banner", ""),
        "sidecar_reachable": not version_info.get("unreachable", False),
    }


@router.post("", response_model=SimulationOut, status_code=status.HTTP_202_ACCEPTED)
async def create_simulation(
    payload: SimulationCreate,
    session: SessionDep,
    user: CurrentUser,
    arq: ArqDep,
) -> SimulationOut:
    """Create a pending Simulation + its child SimulationRun rows and
    enqueue the worker. Returns 202 with ``status="pending"``."""
    if len(payload.loadouts) > settings.simc_max_loadouts:
        raise ValidationAppError(
            f"At most {settings.simc_max_loadouts} loadouts per simulation."
        )

    iterations = payload.iterations or settings.simc_default_iterations

    # Sanity-check the profile: must mention a class line so simc has
    # any chance of parsing it. /simc paste always has e.g.
    # "demonhunter=… spec=havoc". Reject obviously empty input early so
    # the worker doesn't spin up just to fail.
    head = payload.simc_profile.lower()
    if "spec=" not in head and "specialization=" not in head:
        raise ValidationAppError(
            "Profile doesn't look like a /simc paste — couldn't find a "
            "spec= or specialization= line. Paste the full text the "
            "in-game /simc command produced."
        )

    parent = Simulation(
        requested_by_id=user.id,
        label=payload.label or "",
        simc_profile=payload.simc_profile,
        loadouts=[ld.model_dump() for ld in payload.loadouts],
        fight_profiles=list(payload.fight_profiles),
        iterations=iterations,
        status=SimulationStatus.pending,
    )
    session.add(parent)
    await session.flush()  # need parent.id for the children

    for li, loadout in enumerate(payload.loadouts):
        for fp in payload.fight_profiles:
            session.add(
                SimulationRun(
                    simulation_id=parent.id,
                    loadout_index=li,
                    loadout_name=loadout.name or f"Loadout {li + 1}",
                    rotation=loadout.rotation,
                    fight_profile_key=fp,
                    status=SimulationRunStatus.pending,
                )
            )

    await session.commit()
    await session.refresh(parent)

    await arq.enqueue_job("run_simulation_task", str(parent.id))

    return await _detail(session, parent.id)


@router.get("", response_model=PaginatedSimulations)
async def list_my_simulations(
    session: SessionDep,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedSimulations:
    base = select(Simulation).where(Simulation.requested_by_id == user.id)
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await session.execute(
            base.order_by(Simulation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    items = [
        SimulationListItem(
            id=r.id,
            label=r.label,
            status=r.status,
            iterations=r.iterations,
            fight_profiles=r.fight_profiles or [],
            loadout_count=len(r.loadouts or []),
            created_at=r.created_at,
            finished_at=r.finished_at,
        )
        for r in rows
    ]
    return PaginatedSimulations(
        items=items, total=int(total), page=page, page_size=page_size
    )


@router.get("/{simulation_id}", response_model=SimulationOut)
async def get_simulation(
    simulation_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> SimulationOut:
    row = (
        await session.execute(
            select(Simulation)
            .options(selectinload(Simulation.runs))
            .where(Simulation.id == simulation_id)
        )
    ).scalar_one_or_none()
    if not row:
        raise NotFoundError("Simulation not found.")
    if row.requested_by_id != user.id and user.role != UserRole.admin:
        # 404 (not 403) so the endpoint can't be used to enumerate IDs.
        raise NotFoundError("Simulation not found.")
    return SimulationOut.model_validate(row)


@router.delete("/{simulation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_simulation(
    simulation_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> None:
    row = (
        await session.execute(select(Simulation).where(Simulation.id == simulation_id))
    ).scalar_one_or_none()
    if not row:
        raise NotFoundError("Simulation not found.")
    if row.requested_by_id != user.id and user.role != UserRole.admin:
        raise ForbiddenError("You can only delete your own simulations.")
    await session.delete(row)
    await session.commit()


async def _detail(session, sim_id: uuid.UUID) -> SimulationOut:
    row = (
        await session.execute(
            select(Simulation)
            .options(selectinload(Simulation.runs))
            .where(Simulation.id == sim_id)
        )
    ).scalar_one()
    return SimulationOut.model_validate(row)
