"""End-to-end persist test: import a report and assert DB has the new fields.

Runs the full ``create_import_skeleton`` + ``run_report_import`` pipeline
inside the backend container. Verifies that the DB INSERT actually
succeeds with the new ``talentTree`` shape (the v0.1.0 image had a
VARCHAR column that rejected list payloads).

    docker compose exec backend uv run python -m scripts.test_import_persist <REPORT_CODE>
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter

from sqlalchemy import select

from app.db import async_session_factory
from app.models import Report, ReportFight, ReportPlayer, ReportPlayerGear
from app.services.report_service import (
    create_import_skeleton,
    run_report_import,
)


async def main(code: str) -> None:
    print(f"\n=== Persist test: import {code} ===\n")

    print("[1/3] Creating skeleton…")
    async with async_session_factory() as s:
        async with s.begin():
            report = await create_import_skeleton(s, raw_input=code, owner_user_id=None)
        report_id = report.id
    print(f"  -> report_id={report_id}")

    print("\n[2/3] Running run_report_import (the path that was crashing)…")
    async with async_session_factory() as s:
        async with s.begin():
            await run_report_import(s, report_id=report_id)
    print("  -> import returned without exception")

    print("\n[3/3] Inspecting persisted rows…")
    async with async_session_factory() as s:
        report = (
            await s.execute(select(Report).where(Report.id == report_id))
        ).scalar_one()
        fights = (
            (await s.execute(select(ReportFight).where(ReportFight.report_id == report_id)))
            .scalars().all()
        )
        fight_ids = [f.id for f in fights]
        players = (
            (await s.execute(select(ReportPlayer).where(ReportPlayer.fight_id.in_(fight_ids))))
            .scalars().all()
        ) if fight_ids else []
        gear_rows = (
            (await s.execute(select(ReportPlayerGear).where(ReportPlayerGear.player_id.in_([p.id for p in players]))))
            .scalars().all()
        ) if players else []

    talents_set = sum(1 for p in players if p.talents_loadout)
    extras_talent_ids = sum(1 for p in players if (p.extras or {}).get("talent_ids"))
    extras_stats = sum(1 for p in players if (p.extras or {}).get("stats"))
    talents_types = Counter(type(p.talents_loadout).__name__ for p in players if p.talents_loadout is not None)

    print(f"  report.import_status: {report.import_status}  error={report.import_error!r}")
    print(f"  fights:               {len(fights)}")
    print(f"  players:              {len(players)}")
    print(f"  gear rows:            {len(gear_rows)}  (avg {len(gear_rows) // max(len(players),1)}/player)")
    print(f"  with talents_loadout: {talents_set}/{len(players)}  types={dict(talents_types)}")
    print(f"  with extras.talent_ids: {extras_talent_ids}/{len(players)}")
    print(f"  with extras.stats:      {extras_stats}/{len(players)}")

    if players:
        sample = players[0]
        loadout = sample.talents_loadout
        if isinstance(loadout, list):
            loadout_preview = f"list[{len(loadout)}], first={loadout[0] if loadout else None}"
        elif isinstance(loadout, str):
            loadout_preview = f"str[{len(loadout)}]: {loadout[:100]}"
        else:
            loadout_preview = repr(loadout)[:100]
        print(f"\n  Sample player: {sample.name}/{sample.spec_slug}")
        print(f"    talents_loadout: {loadout_preview}")
        extras = sample.extras or {}
        print(f"    extras.talent_ids: {len(extras.get('talent_ids') or [])}")
        print(f"    extras.stats keys: {sorted((extras.get('stats') or {}).keys())}")

    failures = []
    if report.import_status != "ready":
        failures.append(f"import_status != ready ({report.import_status})")
    if not players:
        failures.append("no players persisted")
    if players and talents_set == 0:
        failures.append("no players have talents_loadout")
    if players and extras_talent_ids == 0:
        failures.append("no players have extras.talent_ids")
    if players and extras_stats == 0:
        failures.append("no players have extras.stats")
    if players and not gear_rows:
        failures.append("no gear rows persisted")

    if failures:
        print("\n  !!! FAILURES:")
        for f in failures:
            print(f"    - {f}")
        sys.exit(1)
    print("\n=== PASS ===\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m scripts.test_import_persist <WCL_REPORT_CODE>")
        sys.exit(2)
    asyncio.run(main(sys.argv[1]))
