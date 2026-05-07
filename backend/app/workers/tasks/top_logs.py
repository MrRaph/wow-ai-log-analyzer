"""Background task: refresh top logs for every spec/encounter once a day."""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.db import async_session_factory
from app.models import GameSpec, TopLog
from app.services.top_logs_service import refresh_top_logs_for_spec_encounter
from app.services.wcl.client import WclClient

logger = logging.getLogger(__name__)


async def refresh_all_top_logs(_ctx: dict) -> int:
    """Refresh top logs for every (spec, encounter) we already track.

    Strategy: for each known spec, look at all encounter_ids we already have
    cached entries for, and re-pull them. The first time the worker runs
    after install there will be no entries — admins seed an encounter once
    via ``POST /admin/top-logs/refresh``.
    """
    refreshed = 0
    async with WclClient() as wcl, async_session_factory() as session:
        async with session.begin():
            specs = (await session.execute(select(GameSpec))).scalars().all()
            existing = (
                await session.execute(
                    select(TopLog.spec_slug, TopLog.encounter_id, TopLog.metric).distinct()
                )
            ).all()
            pairs: set[tuple[str, int, str]] = {(s, e, m) for s, e, m in existing}
            for spec in specs:
                for spec_slug, encounter_id, metric in pairs:
                    if spec_slug != spec.slug:
                        continue
                    try:
                        rows = await refresh_top_logs_for_spec_encounter(
                            session,
                            spec=spec,
                            encounter_id=encounter_id,
                            metric=metric,
                            wcl_client=wcl,
                        )
                        refreshed += len(rows)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "top-logs refresh failed for spec=%s encounter=%s metric=%s",
                            spec.slug,
                            encounter_id,
                            metric,
                        )
    logger.info("top-logs refresh complete (%s rows)", refreshed)
    return refreshed
