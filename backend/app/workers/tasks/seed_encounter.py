"""Background task: seed top logs for one encounter across the relevant specs.

The HTTP layer (or the weekly cron) creates a ``TopLogsSeedJob`` row in
``queued`` state and enqueues this task with the job-id. We pick up the row,
flip it to ``running``, walk the specs, increment the progress counter
after each spec, and finally flip ``status`` to ``succeeded`` or
``failed``.

The admin UI polls ``GET /admin/top-logs/seed-jobs`` while any non-terminal
job exists so the user gets a live "12/39 specs · gerade priest_holy"
display.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import async_session_factory
from app.models import GameSpec, TopLogsSeedJob
from app.services.top_logs_service import refresh_top_logs_for_spec_encounter
from app.services.wcl.client import WclClient, create_wcl_client, to_client_flavor

logger = logging.getLogger(__name__)


async def seed_encounter_task(_ctx: dict, job_id: str) -> None:
    jid = uuid.UUID(job_id)
    succeeded = False
    job_total = 0
    encounter_id: int | None = None
    try:
        async with async_session_factory() as session:
            # 1) Load + flip to running
            async with session.begin():
                job = (
                    await session.execute(
                        select(TopLogsSeedJob).where(TopLogsSeedJob.id == jid)
                    )
                ).scalar_one_or_none()
                if job is None:
                    logger.warning("seed_encounter_task: job gone, id=%s", job_id)
                    return
                if job.status not in ("queued", "running"):
                    return  # already terminal — duplicate enqueue
                job.status = "running"
                job.started_at = datetime.now(UTC)
                encounter_id = job.encounter_id
                is_raid = job.is_raid
                metric_filter = job.metric_filter
                wcl_flavor = job.wcl_flavor

            # 2) Pre-compute spec list inside its own short transaction so the
            # per-spec begin() blocks below don't fight the session autobegin.
            async with session.begin():
                spec_q = select(GameSpec)
                if metric_filter == "hps":
                    spec_q = spec_q.where(GameSpec.role == "healer")
                elif metric_filter == "dps":
                    spec_q = spec_q.where(GameSpec.role != "healer")
                specs = list((await session.execute(spec_q)).scalars().all())
                job_total = len(specs)
                tracked = (
                    await session.execute(
                        select(TopLogsSeedJob).where(TopLogsSeedJob.id == jid)
                    )
                ).scalar_one()
                tracked.total_specs = job_total
                tracked.completed_specs = 0

            # 3) Walk specs. Each spec gets its own transaction so partial
            # progress survives crashes; before each spec we update the
            # ``current_spec_slug`` field so the UI shows where we are.
            async with create_wcl_client(flavor=to_client_flavor(wcl_flavor)) as wcl:
                for spec in specs:
                    async with session.begin():
                        tracked = (
                            await session.execute(
                                select(TopLogsSeedJob).where(TopLogsSeedJob.id == jid)
                            )
                        ).scalar_one()
                        tracked.current_spec_slug = spec.slug

                    try:
                        async with session.begin():
                            await refresh_top_logs_for_spec_encounter(
                                session,
                                spec=spec,
                                encounter_id=encounter_id,
                                is_raid=is_raid,
                                wcl_flavor=wcl_flavor,
                                wcl_client=wcl,
                            )
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "seed_encounter_task: spec=%s encounter=%s failed",
                            spec.slug,
                            encounter_id,
                        )

                    async with session.begin():
                        tracked = (
                            await session.execute(
                                select(TopLogsSeedJob).where(TopLogsSeedJob.id == jid)
                            )
                        ).scalar_one()
                        tracked.completed_specs += 1

            # 4) Mark terminal succeeded.
            async with session.begin():
                tracked = (
                    await session.execute(
                        select(TopLogsSeedJob).where(TopLogsSeedJob.id == jid)
                    )
                ).scalar_one()
                tracked.status = "succeeded"
                tracked.current_spec_slug = None
                tracked.finished_at = datetime.now(UTC)
        succeeded = True
    finally:
        # If we exit any other way (arq job_timeout, container restart,
        # bare BaseException), make sure the row doesn't get stuck on
        # ``running``. Open a fresh session because the outer one may have
        # been killed mid-transaction.
        if not succeeded:
            try:
                async with async_session_factory() as cleanup_session:
                    async with cleanup_session.begin():
                        tracked = (
                            await cleanup_session.execute(
                                select(TopLogsSeedJob).where(TopLogsSeedJob.id == jid)
                            )
                        ).scalar_one_or_none()
                        if tracked is not None and tracked.status == "running":
                            tracked.status = "failed"
                            tracked.current_spec_slug = None
                            tracked.finished_at = datetime.now(UTC)
                            tracked.error = (
                                f"task interrupted after {tracked.completed_specs}"
                                f"/{tracked.total_specs} specs"
                            )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "seed_encounter_task: cleanup-on-failure DB write failed"
                )

    if succeeded:
        logger.info(
            "seed_encounter_task done job=%s encounter=%s specs=%s",
            job_id,
            encounter_id,
            job_total,
        )
