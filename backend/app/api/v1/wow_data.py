"""Admin endpoints for the WoW localization cache + admin top-logs tools."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import distinct, func, select

from app.db import async_session_factory
from app.deps import AdminUser, ArqDep, LocaleDep, SessionDep
from app.models import GameSpec, TopLog, TopLogsSeedJob, WowDataImport, WowImportStatus
from app.schemas.wow_data import (
    TopLogsEncounterRow,
    TopLogsSeedIn,
    TopLogsSeedJobOut,
    WowDataImportOut,
    WowDataStatusOut,
)
from app.config import settings
from app.services.top_logs_service import refresh_top_logs_for_spec_encounter
from app.services.wcl.client import WclClient, normalize_wcl_flavor
from app.services.wcl_zones_service import fetch_current_raid_encounters
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
async def trigger_wow_data_refresh(
    session: SessionDep, _: AdminUser, arq: ArqDep
) -> WowDataImportOut:
    """Enqueue the wago.tools import on the arq worker.

    To avoid the brief flicker between enqueue and the worker actually
    picking up the job, we insert a real ``in_progress`` placeholder row
    here (build = ``(pending)``, phase = ``starting``) and return *that*.
    The worker's :func:`run_full_import` adopts this row and fills in the
    real build number when it starts. Frontend polls ``/wow-data`` to
    watch ``status`` and ``phase`` flip live.
    """
    last = await latest_import(session)
    if last and last.status == WowImportStatus.in_progress.value:
        # Already running — don't queue another. Frontend's poll picks up
        # the live ``phase`` field on the existing row.
        return WowDataImportOut.model_validate(last)

    placeholder = WowDataImport(
        build="(pending)",
        status=WowImportStatus.in_progress.value,
        started_at=_now(),
        rows_imported=0,
        source="wago.tools",
        phase="starting",
    )
    session.add(placeholder)
    await session.commit()
    await session.refresh(placeholder)

    await arq.enqueue_job("refresh_wow_data")
    return WowDataImportOut.model_validate(placeholder)


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
    payload: TopLogsSeedIn, session: SessionDep, _: AdminUser, arq: ArqDep
) -> dict[str, Any]:
    """Queue an arq job that seeds top logs for **one** encounter.

    The actual work runs in the worker; admins watch progress via
    ``GET /admin/top-logs/seed-jobs``. Optional ``metric`` filter limits the
    spec set to healers (``hps``) or DPS+tanks (``dps``).
    """
    encounter_id = payload.encounter_id
    is_raid = payload.is_raid
    metric_filter = payload.metric
    wcl_flavor = normalize_wcl_flavor(payload.wcl_flavor)

    # Skip if a job for this encounter is already in flight, so spam-clicking
    # the button doesn't queue 5 redundant runs.
    active = (
        await session.execute(
            select(TopLogsSeedJob).where(
                TopLogsSeedJob.encounter_id == encounter_id,
                TopLogsSeedJob.metric_filter == metric_filter,
                TopLogsSeedJob.wcl_flavor == wcl_flavor,
                TopLogsSeedJob.status.in_(("queued", "running")),
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        return {
            "queued": False,
            "encounter_id": encounter_id,
            "metric": metric_filter,
            "wcl_flavor": wcl_flavor,
            "reason": "already_in_flight",
            "job_id": str(active.id),
        }

    # Pre-compute the spec count for the response (the worker will set this
    # again on the row, but the API consumer often wants to know upfront).
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

    job = TopLogsSeedJob(
        encounter_id=encounter_id,
        is_raid=is_raid,
        metric_filter=metric_filter,
        wcl_flavor=wcl_flavor,
        total_specs=int(spec_count),
        status="queued",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    await arq.enqueue_job("seed_encounter_task", str(job.id))
    return {
        "queued": True,
        "encounter_id": encounter_id,
        "is_raid": is_raid,
        "metric": metric_filter,
        "wcl_flavor": wcl_flavor,
        "spec_count": int(spec_count),
        "job_id": str(job.id),
    }


@router.get("/top-logs/current-tier-preview")
async def preview_current_tier(
    _: AdminUser,
    wcl_flavor: str = Query(default="retail", pattern="^(retail|fresh)$"),
) -> dict[str, Any]:
    """Show what ``seed-current-tier`` would queue right now, without queuing.

    Used by the admin UI so the operator can sanity-check the discovered
    list (expansion picked correctly, all expected raid zones present, no
    M+ noise) before triggering the actual seeding.
    """
    raid = await fetch_current_raid_encounters(force_refresh=True, wcl_flavor=wcl_flavor)
    if not raid:
        return {"expansion_id": None, "expansion_name": None, "encounters": []}
    # Group by zone so the UI can render "Manaforge Omega: 8 bosses, …" cards.
    zones: dict[int, dict[str, Any]] = {}
    for enc in raid:
        zone = zones.setdefault(
            enc.zone_id,
            {
                "zone_id": enc.zone_id,
                "zone_name": enc.zone_name,
                "encounters": [],
            },
        )
        zone["encounters"].append(
            {"encounter_id": enc.encounter_id, "encounter_name": enc.encounter_name}
        )
    return {
        "expansion_id": raid[0].expansion_id,
        "expansion_name": raid[0].expansion_name,
        "zones": list(zones.values()),
        "total_encounters": len(raid),
    }


@router.post(
    "/top-logs/seed-current-tier",
    status_code=status.HTTP_202_ACCEPTED,
)
async def seed_current_tier(
    session: SessionDep,
    _: AdminUser,
    arq: ArqDep,
    wcl_flavor: str = Query(default="retail", pattern="^(retail|fresh)$"),
) -> dict[str, Any]:
    """Discover the current raid tier via WCL and queue a seed-job per encounter.

    Idempotent: encounters already covered by an in-flight ``queued``/``running``
    job are skipped, so spamming the button just polls the existing jobs.
    Pass ``wcl_flavor=fresh`` to seed Fresh encounters.
    """
    flavor = normalize_wcl_flavor(wcl_flavor)
    if flavor == "fresh" and not settings.top_logs_fresh_enabled:
        return {"queued": 0, "skipped_already_running": 0, "encounters": [], "reason": "fresh_disabled"}
    raid = await fetch_current_raid_encounters(wcl_flavor=flavor)
    if not raid:
        return {"queued": 0, "skipped_already_running": 0, "encounters": []}

    # Find encounters that already have an in-flight seed job (any metric) for this flavor.
    encounter_ids = [r.encounter_id for r in raid]
    active_ids = set(
        (
            await session.execute(
                select(TopLogsSeedJob.encounter_id)
                .where(
                    TopLogsSeedJob.encounter_id.in_(encounter_ids),
                    TopLogsSeedJob.status.in_(("queued", "running")),
                    TopLogsSeedJob.metric_filter.is_(None),
                    TopLogsSeedJob.wcl_flavor == flavor,
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )

    queued: list[TopLogsSeedJob] = []
    skipped = 0
    for enc in raid:
        if enc.encounter_id in active_ids:
            skipped += 1
            continue
        job = TopLogsSeedJob(
            encounter_id=enc.encounter_id,
            encounter_name=enc.encounter_name,
            is_raid=True,
            metric_filter=None,
            wcl_flavor=flavor,
            total_specs=0,
            status="queued",
        )
        session.add(job)
        queued.append(job)
    await session.commit()
    for job in queued:
        await session.refresh(job)
        await arq.enqueue_job("seed_encounter_task", str(job.id))

    return {
        "queued": len(queued),
        "skipped_already_running": skipped,
        "encounters": [
            {
                "encounter_id": r.encounter_id,
                "encounter_name": r.encounter_name,
                "zone_id": r.zone_id,
                "zone_name": r.zone_name,
                "expansion_id": r.expansion_id,
                "expansion_name": r.expansion_name,
            }
            for r in raid
        ],
    }


@router.get(
    "/top-logs/seed-jobs",
    response_model=list[TopLogsSeedJobOut],
)
async def list_seed_jobs(
    session: SessionDep,
    _: AdminUser,
    locale: LocaleDep,
    active_only: bool = Query(default=True),
) -> list[TopLogsSeedJobOut]:
    """List recent seed jobs. ``active_only=true`` (default) returns only
    queued/running rows so the UI can render a clean live-progress section."""
    stmt = select(TopLogsSeedJob).order_by(TopLogsSeedJob.created_at.desc())
    if active_only:
        stmt = stmt.where(TopLogsSeedJob.status.in_(("queued", "running")))
    else:
        stmt = stmt.limit(50)
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return []
    pairs = list({(int(r.encounter_id), r.encounter_name or "") for r in rows})
    name_map = await resolve_encounter_names_with_fallback(
        session, locale=locale, encounters=pairs
    )
    out: list[TopLogsSeedJobOut] = []
    for r in rows:
        item = TopLogsSeedJobOut.model_validate(r)
        # Patch the encounter_name with the localized variant for free.
        localized = name_map.get(int(r.encounter_id))
        if localized:
            item.encounter_name = localized
        out.append(item)
    return out


# --- helpers --------------------------------------------------------------------


def _log_task_failure(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    if task.exception() is not None:
        logger.exception("Background admin task failed", exc_info=task.exception())


def _now() -> "datetime":
    from datetime import UTC, datetime

    return datetime.now(UTC)
