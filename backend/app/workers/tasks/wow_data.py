"""Background task: refresh the localized WoW data cache when a new build appears."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

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

    The HTTP trigger inserts a ``(pending)`` placeholder row before
    enqueueing this task so the admin UI shows ``in_progress`` immediately;
    we adopt that row here whether we run the import or skip it.
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

        # Skip only if the previous success was *complete*. A "partial"
        # success means at least one locale CSV (typically deDE for fresh
        # builds) failed to download — we want to retry next time so the
        # missing rows fill in.
        last_was_complete = bool(
            last_success and last_success.build == latest and "partial" not in (last_success.notes or "")
        )
        if last_was_complete:
            logger.info(
                "wow_data: build %s already fully imported on %s — skipping",
                latest,
                last_success.finished_at,
            )
            # Clean up any pending placeholder so the UI doesn't hang.
            pending = (
                await session.execute(
                    select(WowDataImport)
                    .where(
                        WowDataImport.build == "(pending)",
                        WowDataImport.status == WowImportStatus.in_progress.value,
                    )
                    .order_by(WowDataImport.started_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if pending is not None:
                pending.build = latest
                pending.status = WowImportStatus.success.value
                pending.phase = ""
                pending.finished_at = datetime.now(UTC)
                pending.notes = (
                    f"skipped: build {latest} already imported on "
                    f"{last_success.finished_at.isoformat() if last_success.finished_at else '<unknown>'}"
                )
                pending.rows_imported = last_success.rows_imported
                await session.commit()
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
