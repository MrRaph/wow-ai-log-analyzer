"""Background task: run a queued AI analysis on the worker.

The HTTP layer creates a ``pending`` Analysis row and enqueues this task.
We hand the row over to ``analyzer.request_analysis`` which mutates it in
place to ``running`` → ``succeeded`` / ``failed``. On unhandled exceptions
we open a fresh transaction and stamp the row as ``failed`` so the
frontend's poll lands on a definitive terminal state.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.db import async_session_factory
from app.models import Analysis, AnalysisStatus
from app.services.ai import analyzer

logger = logging.getLogger(__name__)


async def run_analysis_task(_ctx: dict, analysis_id: str) -> None:
    aid = uuid.UUID(analysis_id)
    try:
        async with async_session_factory() as session:
            async with session.begin():
                row = (
                    await session.execute(select(Analysis).where(Analysis.id == aid))
                ).scalar_one_or_none()
                if row is None:
                    logger.warning("run_analysis_task: row gone, analysis_id=%s", analysis_id)
                    return
                if row.status not in (AnalysisStatus.pending, AnalysisStatus.running):
                    return  # already terminal — the task may have been re-enqueued
                await analyzer.request_analysis(
                    session,
                    report_id=row.report_id,
                    fight_id=row.fight_id,
                    player_id=row.player_id,
                    requested_by_id=row.requested_by_id,
                    locale=row.locale,
                    analysis_id=aid,
                )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Analysis worker failed for id=%s", analysis_id)
        async with async_session_factory() as session:
            async with session.begin():
                row = (
                    await session.execute(select(Analysis).where(Analysis.id == aid))
                ).scalar_one_or_none()
                if row is not None and row.status not in (
                    AnalysisStatus.succeeded,
                    AnalysisStatus.failed,
                ):
                    row.status = AnalysisStatus.failed
                    row.error = str(exc)[:1000]
