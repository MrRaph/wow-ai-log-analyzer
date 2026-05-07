"""Import + cache a Warcraft Logs report into our local DB."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.models import (
    Report,
    ReportFight,
    ReportPlayer,
    ReportPlayerCast,
    ReportPlayerGear,
)
from app.services.wcl.client import WclClient
from app.services.wcl.parser import (
    parse_casts_table,
    parse_damage_done_table,
    parse_deaths_table,
    parse_gear_from_player_details,
    parse_healing_done_table,
    parse_player_details,
    parse_report_input,
    parse_report_overview,
)
from app.services.wcl.queries import (
    REPORT_CASTS,
    REPORT_OVERVIEW,
    REPORT_PLAYER_DETAILS,
    REPORT_TABLES,
)

logger = logging.getLogger(__name__)


async def import_report(
    session: AsyncSession,
    *,
    raw_input: str,
    owner_user_id: Any | None,
    wcl_client: WclClient | None = None,
) -> Report:
    """Fetch a WCL report and persist its overview + per-fight player rollups.

    Idempotent: if the report is already cached we update its scalar fields and
    skip the more expensive table queries. Use ``refresh_report`` to force a
    full re-fetch.
    """
    code = parse_report_input(raw_input)
    existing = await _get_report_with_data(session, code)
    if existing:
        return existing

    own_client = wcl_client is None
    client = wcl_client or WclClient()
    try:
        overview = parse_report_overview(await client.query(REPORT_OVERVIEW, {"code": code}))
        report = Report(
            wcl_code=overview["wcl_code"],
            title=overview["title"],
            owner_user_id=owner_user_id,
            zone_id=overview["zone_id"],
            zone_name=overview["zone_name"],
            region=overview["region"],
            game_version=overview["game_version"],
            start_time=overview["start_time"],
            end_time=overview["end_time"],
            raw_meta={},
        )
        session.add(report)
        await session.flush()

        fights_by_id: dict[int, ReportFight] = {}
        for f in overview["fights"]:
            fight = ReportFight(report_id=report.id, **f)
            session.add(fight)
            fights_by_id[f["fight_id"]] = fight
        await session.flush()

        # Group fights into a single batched table call.
        all_fight_ids = list(fights_by_id.keys())
        if all_fight_ids:
            await _populate_players(session, client, code, all_fight_ids, fights_by_id)
    finally:
        if own_client:
            await client.aclose()

    return await _get_report_with_data(session, code) or report


async def _get_report_with_data(session: AsyncSession, code: str) -> Report | None:
    stmt = (
        select(Report)
        .where(Report.wcl_code == code)
        .options(
            selectinload(Report.fights)
            .selectinload(ReportFight.players)
            .selectinload(ReportPlayer.casts),
            selectinload(Report.fights)
            .selectinload(ReportFight.players)
            .selectinload(ReportPlayer.gear),
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _populate_players(
    session: AsyncSession,
    client: WclClient,
    code: str,
    fight_ids: list[int],
    fights_by_id: dict[int, ReportFight],
) -> None:
    details_payload = await client.query(
        REPORT_PLAYER_DETAILS, {"code": code, "fightIDs": fight_ids}
    )
    players = parse_player_details(details_payload)
    if not players:
        return

    damage_payload = await client.query(
        REPORT_TABLES, {"code": code, "fightIDs": fight_ids, "dataType": "DamageDone"}
    )
    healing_payload = await client.query(
        REPORT_TABLES, {"code": code, "fightIDs": fight_ids, "dataType": "Healing"}
    )
    deaths_payload = await client.query(
        REPORT_TABLES, {"code": code, "fightIDs": fight_ids, "dataType": "Deaths"}
    )
    damage_by_actor = parse_damage_done_table(damage_payload)
    healing_by_actor = parse_healing_done_table(healing_payload)
    deaths_by_actor = parse_deaths_table(deaths_payload)

    # Map every player into *all* fights (each fight gets a row to keep the
    # schema simple — over time we could specialise per fight, but this keeps
    # storage small and works for both raid and M+ flows).
    target_fights = list(fights_by_id.values())
    for p in players:
        actor_id = p["actor_id"]
        damage = damage_by_actor.get(actor_id, {})
        healing = healing_by_actor.get(actor_id, {})
        deaths = deaths_by_actor.get(actor_id, 0)
        gear = parse_gear_from_player_details(p["raw"])

        for fight in target_fights:
            db_player = ReportPlayer(
                fight_id=fight.id,
                actor_id=actor_id,
                name=p["name"],
                server=p["server"],
                class_slug=p["class_slug"],
                spec_slug=p["spec_slug"],
                role=p["role"],
                item_level=p.get("item_level"),
                damage_done=int(damage.get("damage_done", 0)),
                dps=float(damage.get("dps", 0)) or None,
                healing_done=int(healing.get("healing_done", 0)),
                hps=float(healing.get("hps", 0)) or None,
                deaths=int(deaths),
                talents_loadout=p.get("talents_loadout"),
                extras={},
            )
            session.add(db_player)
            await session.flush()
            for g in gear:
                session.add(ReportPlayerGear(player_id=db_player.id, **g))

            # Top abilities (we keep up to 25 to fit the AI prompt comfortably)
            try:
                casts_payload = await client.query(
                    REPORT_CASTS,
                    {"code": code, "fightIDs": [fight.fight_id], "sourceID": actor_id},
                )
                casts = parse_casts_table(casts_payload)
            except Exception:  # noqa: BLE001
                logger.exception("Casts query failed for actor=%s fight=%s", actor_id, fight.fight_id)
                casts = []
            for c in sorted(casts, key=lambda c: c.get("total", 0), reverse=True)[:25]:
                session.add(ReportPlayerCast(player_id=db_player.id, **c))

    await session.flush()


async def get_report(session: AsyncSession, *, code: str) -> Report:
    report = await _get_report_with_data(session, code)
    if not report:
        raise NotFoundError("Report not found.")
    return report
