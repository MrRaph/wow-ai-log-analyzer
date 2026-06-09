"""Import + cache a Warcraft Logs report into our local DB."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.models import (
    Report,
    ReportFight,
    ReportPlayer,
    ReportPlayerGear,
)
from app.services.wcl.client import WclClient, create_wcl_client, normalize_wcl_flavor, to_client_flavor
from app.services.wcl_zones_service import get_expansion_slug_for_zone
from app.services.wcl.parser import (
    aggregate_boss_casts,
    parse_damage_done_table,
    parse_deaths_table,
    parse_enemy_cast_events_page,
    parse_gear_from_player_details,
    parse_healing_done_table,
    parse_player_details,
    parse_report_input_details,
    parse_report_overview,
    parse_report_rankings_for_fight,
)
from app.services.wcl.queries import (
    REPORT_ENEMY_CAST_EVENTS,
    REPORT_OVERVIEW,
    REPORT_PLAYER_DETAILS,
    REPORT_RANKINGS,
    REPORT_TABLES,
)

logger = logging.getLogger(__name__)

# Bumped whenever the shape of ``ReportFight.extras`` / ``ReportPlayer.extras``
# / ``ReportPlayerGear`` / ``ReportPlayerCast`` changes in a way the AI prompt
# or analyser needs. Stored verbatim into ``extras['_v']`` on every fresh
# import; ``run_report_import`` re-imports a report when any fight's stored
# ``_v`` is below this value. Missing ``_v`` is treated as version 0
# (= ancient), which forces a refresh.
#
# History:
#   v1: initial shape (basic per-fight/per-player rollups).
#   v2 (v0.2.0): added talent_ids/stats/active_time_ms in player.extras,
#                gear rows in report_player_gear, talents_loadout JSONB.
#   v3 (v0.3.0): added wcl_fight_start_ms + fight-relative-second
#                phase_transitions + boss_casts on fight.extras;
#                mana_recovery is lazy-fetched at analysis time so it
#                doesn't gate this version.
REPORT_DATA_VERSION = 3


async def fetch_boss_cast_timeline(
    client: WclClient,
    *,
    code: str,
    fight_id: int,
    fight_start_ms: int,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    """Walk ``report.events(dataType: Casts, hostilityType: Enemies)`` for one
    fight and return the compact per-ability cast timeline the AI prompt wants.

    Pagination: WCL returns up to ``limit`` events per page (we ask for 1000)
    and includes ``nextPageTimestamp`` whenever there's more data. We follow
    it but cap at ``max_pages`` (= 10k events worst case) so one runaway log
    can't stall the import — long fights with 4-6 boss abilities cycling
    every 25-45s typically fit in 1-2 pages.

    Returns the same shape as ``aggregate_boss_casts``: a list of
    ``{ability_id, count, cast_seconds: [...]}`` entries. Empty list on
    upstream failure (logged) so the import can still complete; missing
    boss-cast data just means the AI doesn't get the timeline for this
    fight, not that the import fails.
    """
    collected: list[dict[str, Any]] = []
    next_ts: float | None = None
    for _ in range(max_pages):
        variables: dict[str, Any] = {"code": code, "fightIDs": [fight_id]}
        if next_ts is not None:
            variables["startTime"] = next_ts
        try:
            payload = await client.query(REPORT_ENEMY_CAST_EVENTS, variables)
        except Exception:  # noqa: BLE001
            logger.exception(
                "boss cast events fetch failed for code=%s fight=%s", code, fight_id
            )
            return []
        page, next_ts = parse_enemy_cast_events_page(payload)
        collected.extend(page)
        if next_ts is None:
            break
    return aggregate_boss_casts(collected, fight_start_ms=fight_start_ms)


async def create_import_skeleton(
    session: AsyncSession, *, raw_input: str, owner_user_id: Any | None
) -> Report:
    """Quickly insert (or return) a Report row in ``importing`` state.

    The HTTP endpoint calls this synchronously so it can return immediately
    with a stable ``report.id`` the frontend can poll. The actual WCL fetch
    happens in :func:`run_report_import` on the arq worker.

    Idempotent: re-importing a code that is already in the DB returns the
    existing row (whether ``importing``/``ready``/``failed``). For ``failed``
    rows the caller may want to re-trigger the worker — that's handled at
    the API layer, not here.
    """
    code, flavor = parse_report_input_details(raw_input)
    existing = (
        await session.execute(
            select(Report).where(Report.wcl_code == code, Report.wcl_flavor == flavor)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    report = Report(
        wcl_code=code,
        wcl_flavor=flavor,
        title="",
        owner_user_id=owner_user_id,
        import_status="importing",
        raw_meta={},
    )
    session.add(report)
    await session.flush()
    return report


async def report_data_is_current(session: AsyncSession, report_id: Any) -> bool:
    """Return ``True`` iff every fight on the report carries the current
    ``REPORT_DATA_VERSION`` stamp. Empty (no fights) → ``False`` because
    a freshly-skeletoned but never-imported report counts as not current.

    Missing ``_v`` (older code's writes) is treated as version 0, which is
    always below the current constant — so legacy data automatically
    triggers a refresh on the next analysis without any per-row migration.
    """
    fights = (
        await session.execute(
            select(ReportFight.extras).where(ReportFight.report_id == report_id)
        )
    ).all()
    if not fights:
        return False
    return all(
        int((extras or {}).get("_v") or 0) >= REPORT_DATA_VERSION
        for (extras,) in fights
    )


async def run_report_import(
    session: AsyncSession,
    *,
    report_id: Any,
    wcl_client: WclClient | None = None,
) -> None:
    """Fetch the WCL overview + per-fight player rollups for a skeleton report.

    Drives ``import_status``: ``importing`` → ``ready`` (or ``failed`` on
    exception). Idempotent — calling on a ``ready`` row that already has
    fights does nothing besides refreshing the status, UNLESS the stored
    data was written by an older code version (different
    ``REPORT_DATA_VERSION``). In that case the existing fights are wiped
    and a full re-import runs so the analyser can rely on the current
    fight/player extras shape.
    """
    report = (
        await session.execute(select(Report).where(Report.id == report_id))
    ).scalar_one_or_none()
    if report is None:
        raise NotFoundError("Report not found.")
    if report.import_status == "ready" and report.start_time is not None:
        if await report_data_is_current(session, report_id):
            return
        logger.info(
            "report %s data is older than current version %d — re-importing",
            report_id,
            REPORT_DATA_VERSION,
        )
        # Cascade through fights → players → casts/gear/analyses. We keep
        # the Report row itself (analyses referencing it survive the
        # version bump cleanly — their historical structured output is
        # unchanged, only the *next* analysis sees fresh data).
        await session.execute(
            delete(ReportFight).where(ReportFight.report_id == report_id)
        )
        report.import_status = "importing"
        await session.flush()

    code = report.wcl_code
    owner_user_id = report.owner_user_id
    own_client = wcl_client is None
    flavor = normalize_wcl_flavor(report.wcl_flavor)
    if wcl_client is None and owner_user_id is not None:
        from app.services.wcl_oauth_service import build_user_wcl_client

        wcl_client = await build_user_wcl_client(session, user_id=owner_user_id, flavor=flavor)
    client = wcl_client or create_wcl_client(flavor=to_client_flavor(flavor))
    try:
        overview = parse_report_overview(
            await client.query(REPORT_OVERVIEW, {"code": code}),
            wcl_flavor=flavor,
        )
        report.title = overview["title"]
        report.zone_id = overview["zone_id"]
        report.zone_name = overview["zone_name"]
        report.region = overview["region"]
        report.game_version = overview["game_version"]
        report.start_time = overview["start_time"]
        report.end_time = overview["end_time"]

        # If the zone expansion wasn't embedded in the REPORT_OVERVIEW
        # response (can happen when the classic API returns a sparse zone
        # object), refine the coarse "classic" slug via the zones-cache now.
        if report.game_version == "classic" and report.zone_id:
            try:
                refined = await get_expansion_slug_for_zone(
                    report.zone_id, flavor, wcl_client=client
                )
                if refined:
                    report.game_version = refined
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Could not resolve expansion for report %s zone_id=%s — keeping 'classic'",
                    code,
                    report.zone_id,
                )

        await session.flush()

        fights_by_id: dict[int, ReportFight] = {}
        for f in overview["fights"]:
            fight_extras = f.pop("extras", {}) or {}
            fight = ReportFight(report_id=report.id, **f, extras=fight_extras)
            session.add(fight)
            fights_by_id[f["fight_id"]] = fight
        await session.flush()

        all_fight_ids = list(fights_by_id.keys())
        if all_fight_ids:
            # Boss-cast timeline per fight — one ``report.events`` walk each.
            # Done as its own pass (not inside _populate_players) because this
            # data is fight-scoped, not player-scoped: every player on the
            # fight sees the same boss-cast pattern.
            for fight_wcl_id, fight_row in fights_by_id.items():
                fight_start_ms = int(
                    (fight_row.extras or {}).get("wcl_fight_start_ms") or 0
                )
                boss_casts = await fetch_boss_cast_timeline(
                    client,
                    code=code,
                    fight_id=fight_wcl_id,
                    fight_start_ms=fight_start_ms,
                )
                # Mutate in place — JSONB will pick this up on the next flush.
                # ``_v`` is the version stamp the analyser checks to decide
                # whether this row's shape matches what the current code
                # expects to read.
                merged_extras = dict(fight_row.extras or {})
                merged_extras["boss_casts"] = boss_casts
                merged_extras["_v"] = REPORT_DATA_VERSION
                fight_row.extras = merged_extras
            await session.flush()

            await _populate_players(session, client, code, all_fight_ids, fights_by_id)

        report.import_status = "ready"
        report.import_error = None
    finally:
        if own_client:
            await client.aclose()


async def _get_report_with_data(
    session: AsyncSession,
    code: str,
    *,
    wcl_flavor: str = "retail",
) -> Report | None:
    stmt = (
        select(Report)
        .where(Report.wcl_code == code, Report.wcl_flavor == wcl_flavor)
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
    """Materialise one ``ReportPlayer`` per (fight, player), with **per-fight**
    role/spec/dps/hps numbers.

    We query playerDetails + DamageDone + Healing + Deaths *per fight* rather
    than pooling across the whole report, because a single character can play
    a different spec on different bosses (a monk who tanks Mug'Zee but heals
    Imperator Averzian). Pooled data assigns the player whatever role they
    had in *most* of the report, which is wrong on the fights where they
    swapped — and exactly the case the user wants to analyse.

    Per-fight casts / buffs / debuffs / damage_taken are *deliberately not*
    fetched here — they're lazy-loaded by the analyser the first time a
    specific (player, fight) is analysed, and cached on the player row.
    """
    for fight_id in fight_ids:
        fight = fights_by_id.get(fight_id)
        if fight is None:
            continue
        try:
            details_payload = await client.query(
                REPORT_PLAYER_DETAILS, {"code": code, "fightIDs": [fight_id]}
            )
        except Exception:  # noqa: BLE001
            logger.exception("playerDetails fetch failed for fight=%s", fight_id)
            continue
        players = parse_player_details(details_payload)
        if not players:
            continue

        try:
            damage_payload = await client.query(
                REPORT_TABLES,
                {"code": code, "fightIDs": [fight_id], "dataType": "DamageDone"},
            )
            damage_by_actor = parse_damage_done_table(damage_payload)
        except Exception:  # noqa: BLE001
            logger.exception("DamageDone fetch failed for fight=%s", fight_id)
            damage_by_actor = {}
        try:
            healing_payload = await client.query(
                REPORT_TABLES,
                {"code": code, "fightIDs": [fight_id], "dataType": "Healing"},
            )
            healing_by_actor = parse_healing_done_table(healing_payload)
        except Exception:  # noqa: BLE001
            logger.exception("Healing fetch failed for fight=%s", fight_id)
            healing_by_actor = {}
        try:
            deaths_payload = await client.query(
                REPORT_TABLES,
                {"code": code, "fightIDs": [fight_id], "dataType": "Deaths"},
            )
            deaths_by_actor = parse_deaths_table(deaths_payload)
        except Exception:  # noqa: BLE001
            logger.exception("Deaths fetch failed for fight=%s", fight_id)
            deaths_by_actor = {}

        # Fetch WCL parse-percentile data for *every* player in this fight
        # in two calls (one per metric). The dps call gives us tank+dps
        # rankings, the hps call gives us healer rankings — we read each
        # player from the bucket matching their per-fight role. The maps
        # are keyed by lowercased character name (WCL rankings use *global*
        # character IDs while our ``actor_id`` is report-local).
        hps_metrics: dict[str, dict[str, Any]] = {}
        dps_metrics: dict[str, dict[str, Any]] = {}
        try:
            hps_payload = await client.query(
                REPORT_RANKINGS,
                {"code": code, "fightIDs": [fight_id], "playerMetric": "hps"},
            )
            hps_metrics = parse_report_rankings_for_fight(
                hps_payload, fight_id=fight_id, roles={"healers"}
            )
        except Exception:  # noqa: BLE001
            logger.exception("HPS rankings fetch failed for fight=%s", fight_id)
        try:
            dps_payload = await client.query(
                REPORT_RANKINGS,
                {"code": code, "fightIDs": [fight_id], "playerMetric": "dps"},
            )
            dps_metrics = parse_report_rankings_for_fight(
                dps_payload, fight_id=fight_id, roles={"dps", "tanks"}
            )
        except Exception:  # noqa: BLE001
            logger.exception("DPS rankings fetch failed for fight=%s", fight_id)

        for p in players:
            actor_id = p["actor_id"]
            damage = damage_by_actor.get(actor_id, {})
            healing = healing_by_actor.get(actor_id, {})
            deaths = deaths_by_actor.get(actor_id, 0)
            gear = parse_gear_from_player_details(p["raw"])
            name_key = (p.get("name") or "").strip().lower()
            metrics = (
                hps_metrics.get(name_key)
                if p["role"] == "healer"
                else dps_metrics.get(name_key)
            )

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
                extras={
                    "talent_ids": p.get("talent_ids") or [],
                    # Primary attribute (Str/Agi/Int) + secondary stats
                    # (Mastery/Crit/Haste/Versatility) + tertiary
                    # (Speed/Leech/Avoidance) snapshot at peak (max). Used
                    # by the AI to compare against top-log references and
                    # call out under-statted slots vs the percentile.
                    "stats": p.get("stats") or {},
                    # Player's in-combat / alive time on this fight. Equals
                    # fight duration on a kill; less than fight duration on
                    # a wipe where the player died early. The DPS/HPS we
                    # store is *already* normalised against this (WCL's
                    # ``activeTime`` semantics), but the analyzer also
                    # surfaces it raw so the AI prompt can use it as the
                    # honest denominator for per-minute cast rates and
                    # cooldown-usage expectations — instead of penalising a
                    # dead player for the rotation they couldn't do.
                    "active_time_ms": max(
                        int(damage.get("active_time_ms") or 0),
                        int(healing.get("active_time_ms") or 0),
                    ),
                    # Always set ``parse_metrics`` (even when WCL has no
                    # ranking data) so the analyzer's ``has_parse_metrics``
                    # marker is True and we don't re-fetch later.
                    "parse_metrics": metrics or {
                        "rank_percent": None,
                        "ilvl_percent": None,
                        "total_parses": None,
                        "rank": None,
                        "out_of": None,
                    },
                    # Version stamp matched against ``REPORT_DATA_VERSION`` —
                    # if a future code update bumps the constant, the
                    # analyser sees this player as stale and triggers a
                    # full re-import for the parent report. Lazy-fetched
                    # fields (buffs/debuffs/casts/mana_recovery) are NOT
                    # gated on this number; only the shape produced by the
                    # import flow is.
                    "_v": REPORT_DATA_VERSION,
                },
            )
            session.add(db_player)
            await session.flush()
            for g in gear:
                session.add(ReportPlayerGear(player_id=db_player.id, **g))

    await session.flush()


async def get_report(session: AsyncSession, *, code: str, wcl_flavor: str = "retail") -> Report:
    report = await _get_report_with_data(session, code, wcl_flavor=wcl_flavor)
    if not report:
        raise NotFoundError("Report not found.")
    return report
