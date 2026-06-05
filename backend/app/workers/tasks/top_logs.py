"""Background task: weekly top-logs refresh.

Two-phase:
1. Discover the current retail raid encounters via the WCL ``worldData.zones``
   API and create a ``TopLogsSeedJob`` for any encounter we don't already
   have in the cache. Each new job is enqueued via the same ``seed_encounter``
   worker function the admin UI uses.
2. Refresh the (spec, encounter, metric) triples already in the cache. This
   keeps existing data fresh and re-uses the slide-down + incremental detail-
   fetch logic in ``refresh_top_logs_for_spec_encounter``.

The admin UI reads progress from ``top_logs_seed_jobs`` while step 1's jobs
are running.
"""
from __future__ import annotations

import logging

from arq import ArqRedis
from arq.connections import RedisSettings, create_pool
from sqlalchemy import select

from app.config import settings
from app.db import async_session_factory
from app.models import GameSpec, TopLog, TopLogsSeedJob
from app.services.top_logs_service import refresh_top_logs_for_spec_encounter
from app.services.wcl.client import create_wcl_client, to_client_flavor
from app.services.wcl_zones_service import fetch_current_raid_encounters

logger = logging.getLogger(__name__)


async def _arq_pool() -> ArqRedis:
    return await create_pool(
        RedisSettings(
            host=settings.redis_host,
            port=settings.redis_port,
            database=settings.redis_db,
        )
    )


async def _seed_missing_current_tier_encounters() -> int:
    """Phase 1: queue a seed-job for each current-tier encounter we don't
    already have any cached entries for. Returns the number queued."""
    raid = await fetch_current_raid_encounters(force_refresh=True)
    if not raid:
        return 0
    queued = 0
    async with async_session_factory() as session:
        async with session.begin():
            cached_encounter_ids = set(
                (
                    await session.execute(
                        select(TopLog.encounter_id)
                        .where(TopLog.wcl_flavor == "retail")
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )
            active_jobs = set(
                (
                    await session.execute(
                        select(TopLogsSeedJob.encounter_id).where(
                            TopLogsSeedJob.status.in_(("queued", "running")),
                            TopLogsSeedJob.metric_filter.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
        new_jobs: list[TopLogsSeedJob] = []
        async with session.begin():
            for enc in raid:
                if enc.encounter_id in cached_encounter_ids:
                    continue
                if enc.encounter_id in active_jobs:
                    continue
                job = TopLogsSeedJob(
                    encounter_id=enc.encounter_id,
                    encounter_name=enc.encounter_name,
                    is_raid=True,
                    metric_filter=None,
                    total_specs=0,
                    status="queued",
                )
                session.add(job)
                new_jobs.append(job)
        if new_jobs:
            arq = await _arq_pool()
            try:
                for job in new_jobs:
                    await session.refresh(job)
                    await arq.enqueue_job("seed_encounter_task", str(job.id))
                    queued += 1
            finally:
                await arq.close()
    return queued


async def refresh_all_top_logs(_ctx: dict) -> int:
    """Top-logs weekly refresh.

    Step 1: discover current-tier encounters and queue seed-jobs for the
    new ones (the worker fans out to every spec). Step 2: re-pull the
    (spec, encounter, metric) triples already in the cache so existing
    rankings stay current as players post fresh logs.
    """
    seeded_new = await _seed_missing_current_tier_encounters()
    logger.info("weekly top-logs: queued %d new current-tier seed jobs", seeded_new)

    refreshed = 0
    async with async_session_factory() as session:
        async with session.begin():
            specs = list(
                (await session.execute(select(GameSpec))).scalars().all()
            )
            existing = (
                await session.execute(
                    select(
                        TopLog.spec_slug,
                        TopLog.encounter_id,
                        TopLog.metric,
                        TopLog.wcl_flavor,
                    ).distinct()
                )
            ).all()
        pairs: set[tuple[str, int, str, str]] = {(s, e, m, f) for s, e, m, f in existing}
        spec_by_slug = {s.slug: s for s in specs}

        # Commit per (spec, encounter, metric) so partial progress survives
        # a crash and admins can watch counts climb in the UI.
        for spec_slug, encounter_id, metric, wcl_flavor in sorted(pairs):
            spec = spec_by_slug.get(spec_slug)
            if not spec:
                continue
            try:
                client = create_wcl_client(flavor=to_client_flavor(wcl_flavor))
                async with client:
                    async with session.begin():
                        rows = await refresh_top_logs_for_spec_encounter(
                            session,
                            spec=spec,
                            encounter_id=encounter_id,
                            metric=metric,
                            wcl_flavor=wcl_flavor,
                            wcl_client=client,
                        )
                refreshed += len(rows)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "top-logs refresh failed for spec=%s encounter=%s metric=%s flavor=%s",
                    spec.slug,
                    encounter_id,
                    metric,
                    wcl_flavor,
                )
    logger.info(
        "weekly top-logs refresh complete (%s rows refreshed, %s new seed jobs queued)",
        refreshed,
        seeded_new,
    )
    return refreshed
