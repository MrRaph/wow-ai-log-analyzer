"""Admin endpoints for the WoW localization cache + admin top-logs tools."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, status
from sqlalchemy import distinct, func, select

from app.db import async_session_factory
from app.deps import AdminUser, LocaleDep, SessionDep
from app.models import GameSpec, TopLog, WowDataImport, WowImportStatus
from app.schemas.wow_data import (
    TopLogsEncounterRow,
    TopLogsSeedIn,
    WowDataImportOut,
    WowDataStatusOut,
)
from app.services.top_logs_service import refresh_top_logs_for_spec_encounter
from app.services.wcl.client import WclClient
from app.services.wow_data_service import (
    fetch_latest_build,
    latest_import,
    list_imports,
    localization_stats,
    resolve_encounter_names_with_fallback,
    run_full_import,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# --- WoW localisation status / refresh ---------------------------------------------


@router.get("/wow-data", response_model=WowDataStatusOut)
async def read_wow_data_status(session: SessionDep, _: AdminUser) -> WowDataStatusOut:
    last = await latest_import(session)
    counts = await localization_stats(session)
    latest_known: str | None = None
    try:
        latest_known = await fetch_latest_build()
    except Exception:  # noqa: BLE001
        # wago.tools could be down; the rest of the page is still useful.
        logger.exception("Could not contact wago.tools manifest")
    return WowDataStatusOut(
        last_import=WowDataImportOut.model_validate(last) if last else None,
        counts=counts,
        latest_known_build=latest_known,
    )


@router.get("/wow-data/imports", response_model=list[WowDataImportOut])
async def list_wow_data_imports(session: SessionDep, _: AdminUser) -> list[WowDataImportOut]:
    return [WowDataImportOut.model_validate(r) for r in await list_imports(session)]


@router.post("/wow-data/refresh", response_model=WowDataImportOut, status_code=status.HTTP_202_ACCEPTED)
async def trigger_wow_data_refresh(session: SessionDep, _: AdminUser) -> WowDataImportOut:
    """Kick off a background import and return the freshly created
    ``in_progress`` row immediately. Frontend can poll ``/wow-data`` to watch
    it flip to ``success`` / ``failed``."""
    last = await latest_import(session)
    if last and last.status == WowImportStatus.in_progress.value:
        return WowDataImportOut.model_validate(last)

    # Detached background task with its own session. We still create the
    # in-progress row inside the task to avoid a race with status reads.
    async def _runner() -> None:
        async with async_session_factory() as bg_session:
            try:
                await run_full_import(bg_session)
            except Exception:  # noqa: BLE001
                logger.exception("Background WoW data import failed")

    task = asyncio.create_task(_runner())
    task.add_done_callback(_log_task_failure)

    # Return whatever the latest row is so the UI has something to display.
    fresh = await latest_import(session)
    if fresh:
        return WowDataImportOut.model_validate(fresh)
    # Synthetic placeholder so the UI knows a refresh was triggered even if
    # the runner hasn't yet inserted the row.
    return WowDataImportOut(
        id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
        build="(pending)",
        status=WowImportStatus.in_progress.value,
        started_at=fresh.started_at if fresh else _now(),  # type: ignore[union-attr]
        finished_at=None,
        rows_imported=0,
        source="wago.tools",
        notes="",
    )


# --- Top-logs encounter management -------------------------------------------------


@router.get("/top-logs/encounters", response_model=list[TopLogsEncounterRow])
async def list_top_log_encounters(
    session: SessionDep, admin: AdminUser, locale: LocaleDep
) -> list[TopLogsEncounterRow]:
    """Return one row per cached encounter — what's currently in the top-logs cache."""
    stmt = (
        select(
            TopLog.encounter_id,
            func.max(TopLog.encounter_name).label("encounter_name"),
            func.array_agg(distinct(TopLog.metric)).label("metrics"),
            func.count().label("rows"),
            func.max(TopLog.recorded_at).label("latest"),
        )
        .group_by(TopLog.encounter_id)
        .order_by(TopLog.encounter_id)
    )
    rows = (await session.execute(stmt)).all()
    pairs = [(int(r.encounter_id), r.encounter_name or "") for r in rows]
    name_map = await resolve_encounter_names_with_fallback(
        session, locale=admin.locale or locale, encounters=pairs
    )
    return [
        TopLogsEncounterRow(
            encounter_id=int(r.encounter_id),
            encounter_name=r.encounter_name or "",
            encounter_name_localized=name_map.get(int(r.encounter_id)),
            metrics=sorted([m for m in (r.metrics or []) if m]),
            rows=int(r.rows),
            latest_recorded_at=r.latest,
        )
        for r in rows
    ]


@router.post(
    "/top-logs/seed-encounter",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=dict[str, Any],
)
async def seed_top_logs_for_encounter(
    payload: TopLogsSeedIn, session: SessionDep, _: AdminUser
) -> dict[str, Any]:
    """Refresh top logs for **one** encounter across the matching specs.

    Runs in the background (same loop the weekly cron uses). The refresh is
    *incremental*: detail data already in the cache is reused, so this is
    cheap to re-run after tweaking filters like ``TOP_LOGS_MIN_HEALERS``.

    Optional ``metric`` filter:
      - ``hps`` → only healer specs (7 specs)
      - ``dps`` → only DPS + tank specs (32 specs)
      - omit → all specs (full refresh)
    """
    encounter_id = payload.encounter_id
    is_raid = payload.is_raid
    metric_filter = payload.metric

    # Pre-compute the spec set we'll iterate, so the response can report it.
    spec_filter_q = select(GameSpec)
    if metric_filter == "hps":
        spec_filter_q = spec_filter_q.where(GameSpec.role == "healer")
    elif metric_filter == "dps":
        spec_filter_q = spec_filter_q.where(GameSpec.role != "healer")
    spec_count = (
        await session.execute(
            select(func.count()).select_from(spec_filter_q.subquery())
        )
    ).scalar_one()

    async def _runner() -> None:
        async with async_session_factory() as bg_session, WclClient() as wcl:
            # Fetch the spec list inside its own short transaction so the
            # SQLAlchemy autobegin doesn't collide with the per-spec begin()
            # block below.
            async with bg_session.begin():
                specs = list(
                    (await bg_session.execute(spec_filter_q)).scalars().all()
                )
            for spec in specs:
                try:
                    async with bg_session.begin():
                        await refresh_top_logs_for_spec_encounter(
                            bg_session,
                            spec=spec,
                            encounter_id=encounter_id,
                            is_raid=is_raid,
                            wcl_client=wcl,
                            # Spec already filtered above; let the helper
                            # default the metric from spec.role.
                        )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "seed-encounter failed for spec=%s encounter=%s",
                        spec.slug,
                        encounter_id,
                    )

    task = asyncio.create_task(_runner())
    task.add_done_callback(_log_task_failure)
    return {
        "queued": True,
        "encounter_id": encounter_id,
        "is_raid": is_raid,
        "metric": metric_filter,
        "spec_count": int(spec_count),
    }


# --- helpers --------------------------------------------------------------------


def _log_task_failure(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    if task.exception() is not None:
        logger.exception("Background admin task failed", exc_info=task.exception())


def _now() -> "datetime":
    from datetime import UTC, datetime

    return datetime.now(UTC)
