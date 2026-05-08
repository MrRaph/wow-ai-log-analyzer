"""Background task: refresh the localized WoW data cache when a new build appears."""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.db import async_session_factory
from app.models import WowDataImport, WowImportStatus
from app.services.wow_data_service import fetch_latest_build, run_full_import

logger = logging.getLogger(__name__)


async def refresh_wow_data(_ctx: dict) -> dict:
    """If wago.tools knows about a newer build than we last imported, pull it.

    Idempotent: re-running for the same build is essentially a no-op (just
    re-upserts the same rows). We still skip when possible to avoid wasting
    bandwidth.
    """
    latest = await fetch_latest_build()
    async with async_session_factory() as session:
        last_success = (
            await session.execute(
                select(WowDataImport)
                .where(WowDataImport.status == WowImportStatus.success.value)
                .order_by(WowDataImport.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if last_success and last_success.build == latest:
            logger.info(
                "wow_data: build %s already imported on %s — skipping",
                latest,
                last_success.finished_at,
            )
            return {"skipped": True, "build": latest}

        logger.info(
            "wow_data: importing build %s (last=%s)",
            latest,
            last_success.build if last_success else "<none>",
        )
        run = await run_full_import(session, build=latest)
        return {
            "skipped": False,
            "build": run.build,
            "rows_imported": run.rows_imported,
            "status": run.status,
        }
