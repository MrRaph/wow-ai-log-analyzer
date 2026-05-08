"""arq worker definition.

Run via ``arq app.workers.arq_app.WorkerSettings`` (Compose does this for the
``worker`` service).
"""
from __future__ import annotations

import logging

from arq.connections import RedisSettings
from arq.cron import cron

from app.config import settings
from app.workers.tasks.analysis import run_analysis_task
from app.workers.tasks.report_import import import_report_task
from app.workers.tasks.top_logs import refresh_all_top_logs
from app.workers.tasks.wow_data import refresh_wow_data

logger = logging.getLogger(__name__)


def _parse_field(field: str) -> int | set[int] | None:
    """Convert one cron field into the int / set[int] / None form arq expects."""
    field = field.strip()
    if field in ("", "*"):
        return None
    if "," in field:
        return {int(x) for x in field.split(",") if x.strip()}
    if "-" in field:
        start, end = field.split("-", 1)
        return set(range(int(start), int(end) + 1))
    if "/" in field:
        # arq has no native step support; treat "*/n" as "any" and let the
        # min-fire-interval be the natural cadence of the schedule.
        return None
    return int(field)


def _parse_cron(expr: str) -> dict[str, int | set[int] | None]:
    parts = expr.split()
    if len(parts) != 5:
        logger.warning("Bad TOP_LOGS_CRON %r — falling back to '0 4 * * *'", expr)
        parts = ["0", "4", "*", "*", "*"]
    minute, hour, day, month, weekday = parts
    try:
        return {
            "minute": _parse_field(minute),
            "hour": _parse_field(hour),
            "day": _parse_field(day),
            "month": _parse_field(month),
            "weekday": _parse_field(weekday),
        }
    except ValueError:
        logger.exception("Could not parse TOP_LOGS_CRON %r — falling back to 04:00 daily.", expr)
        return {"minute": 0, "hour": 4}


_cron_kwargs = {k: v for k, v in _parse_cron(settings.top_logs_cron).items() if v is not None}


class WorkerSettings:
    redis_settings = RedisSettings(
        host=settings.redis_host, port=settings.redis_port, database=settings.redis_db
    )
    functions = [
        refresh_all_top_logs,
        refresh_wow_data,
        import_report_task,
        run_analysis_task,
    ]
    cron_jobs = [
        cron(refresh_all_top_logs, name="refresh_all_top_logs", **_cron_kwargs),
        # WoW DBC dumps drop ~daily right after a patch and only every couple
        # of weeks otherwise, so checking once a week (Tuesday 03:00 UTC, well
        # before the EU reset top-logs job) is plenty.
        cron(refresh_wow_data, name="refresh_wow_data", weekday=2, hour=3, minute=0),
    ]
    keep_result = 86400
    # Number of jobs that may run in parallel inside this worker process.
    # Top-logs refresh, report import and analysis can all coexist; bump
    # this if you see jobs queueing up.
    max_jobs = 4
    # Long enough that a slow Anthropic call or a large Mythic raid import
    # never gets killed mid-flight. arq's default 300s was occasionally
    # tight on local-AI runs with thinking enabled.
    job_timeout = 600
    # Don't retry analysis or import jobs by default — failures are stored
    # on the row itself and the user can re-trigger from the UI.
    max_tries = 1
