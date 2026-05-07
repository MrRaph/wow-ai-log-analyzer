"""arq worker definition.

Run via ``arq app.workers.arq_app.WorkerSettings`` (Compose does this for the
``worker`` service).
"""
from __future__ import annotations

import logging

from arq.connections import RedisSettings
from arq.cron import cron

from app.config import settings
from app.workers.tasks.top_logs import refresh_all_top_logs

logger = logging.getLogger(__name__)


def _parse_cron(expr: str) -> dict[str, str]:
    """Convert a 5-field POSIX cron expression to arq's keyword args."""
    parts = expr.split()
    if len(parts) != 5:
        logger.warning("Bad TOP_LOGS_CRON %r — falling back to '0 4 * * *'", expr)
        parts = ["0", "4", "*", "*", "*"]
    minute, hour, day, month, weekday = parts
    return {
        "minute": minute if minute != "*" else None,  # arq accepts None for "any"
        "hour": hour if hour != "*" else None,
        "day": day if day != "*" else None,
        "month": month if month != "*" else None,
        "weekday": weekday if weekday != "*" else None,
    }


_cron_kwargs = {k: v for k, v in _parse_cron(settings.top_logs_cron).items() if v is not None}


class WorkerSettings:
    redis_settings = RedisSettings(host=settings.redis_host, port=settings.redis_port, database=settings.redis_db)
    functions = [refresh_all_top_logs]
    cron_jobs = [
        cron(refresh_all_top_logs, name="refresh_all_top_logs", **_cron_kwargs),
    ]
    keep_result = 86400
    max_jobs = 4
