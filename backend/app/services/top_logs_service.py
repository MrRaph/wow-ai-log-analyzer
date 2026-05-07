"""Fetch + cache the WCL top logs per spec/encounter."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import GameSpec, Role, TopLog
from app.services.wcl.client import WclClient
from app.services.wcl.parser import parse_encounter_rankings
from app.services.wcl.queries import ENCOUNTER_RANKINGS

logger = logging.getLogger(__name__)


def _metric_for_role(role: Role) -> str:
    if role == Role.healer:
        return "hps"
    if role == Role.tank:
        return "dps"  # tanks ranked by damage output on retail leaderboards
    return "dps"


async def refresh_top_logs_for_spec_encounter(
    session: AsyncSession,
    *,
    spec: GameSpec,
    encounter_id: int,
    encounter_name: str | None = None,
    metric: str | None = None,
    limit: int | None = None,
    wcl_client: WclClient | None = None,
) -> list[TopLog]:
    metric = metric or _metric_for_role(spec.role)
    limit = limit or settings.top_logs_limit
    own = wcl_client is None
    client = wcl_client or WclClient()
    try:
        # WCL spec/class names use PascalCase identifiers ("Holy", "BeastMastery", ...)
        spec_name = "".join(word.capitalize() for word in spec.name_en.split())
        class_name = "".join(word.capitalize() for word in spec.class_slug.split("_"))
        payload = await client.query(
            ENCOUNTER_RANKINGS,
            {
                "encounterID": encounter_id,
                "specName": spec_name,
                "className": class_name,
                "metric": metric,
                "page": 1,
                "partition": None,
            },
        )
        rankings = parse_encounter_rankings(payload)
        if encounter_name:
            for r in rankings:
                r["encounter_name"] = encounter_name
        rankings = rankings[:limit]
    finally:
        if own:
            await client.aclose()

    await session.execute(
        delete(TopLog).where(
            TopLog.spec_slug == spec.slug,
            TopLog.encounter_id == encounter_id,
            TopLog.metric == metric,
        )
    )

    rows: list[TopLog] = []
    now = datetime.now(UTC)
    for r in rankings:
        rows.append(
            TopLog(
                spec_slug=spec.slug,
                encounter_id=r["encounter_id"],
                encounter_name=r["encounter_name"],
                difficulty=None,
                metric=metric,
                rank=r["rank"],
                amount=r["amount"],
                item_level=r.get("item_level"),
                duration_ms=r.get("duration_ms"),
                character_name=r["character_name"],
                server=r["server"],
                region=r["region"],
                wcl_report_code=r["wcl_report_code"],
                wcl_fight_id=r["wcl_fight_id"],
                recorded_at=now,
                payload=r.get("raw") or {},
            )
        )
    session.add_all(rows)
    await session.flush()
    return rows


async def list_top_logs(
    session: AsyncSession,
    *,
    spec_slug: str,
    encounter_id: int | None = None,
    metric: str | None = None,
) -> list[TopLog]:
    stmt = select(TopLog).where(TopLog.spec_slug == spec_slug)
    if encounter_id is not None:
        stmt = stmt.where(TopLog.encounter_id == encounter_id)
    if metric is not None:
        stmt = stmt.where(TopLog.metric == metric)
    stmt = stmt.order_by(TopLog.encounter_id, TopLog.rank.asc())
    return list((await session.execute(stmt)).scalars().all())


async def all_specs(session: AsyncSession) -> Iterable[GameSpec]:
    return list((await session.execute(select(GameSpec))).scalars().all())
