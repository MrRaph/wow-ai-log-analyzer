"""Background task: fetch a WCL report into a skeleton row.

The HTTP layer creates an empty ``Report`` row in ``importing`` state and
enqueues this task. We open our own DB session, call the report-service
populator, and update the row to ``ready`` (or ``failed`` on exception).
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.db import async_session_factory
from app.models import Report
from app.services.report_service import run_report_import

logger = logging.getLogger(__name__)


async def import_report_task(_ctx: dict, report_id: str) -> None:
    rid = uuid.UUID(report_id)
    async with async_session_factory() as session:
        try:
            async with session.begin():
                await run_report_import(session, report_id=rid)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Report import failed for report_id=%s", report_id)
            # Open a fresh transaction so we record the failure even if the
            # populator's session got rolled back mid-way.
            async with session.begin():
                report = (
                    await session.execute(select(Report).where(Report.id == rid))
                ).scalar_one_or_none()
                if report is not None:
                    report.import_status = "failed"
                    report.import_error = str(exc)[:1000]
            return
    logger.info("Report import done report_id=%s", report_id)
