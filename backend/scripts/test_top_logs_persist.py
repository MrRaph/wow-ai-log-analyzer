"""Persist test for the top-logs refresh path.

Calls ``refresh_top_logs_for_spec_encounter`` against a real spec/encounter
and asserts that the resulting rows actually carry the new combatantInfo
fields (talent_ids, stats, gear) inside ``detail_payload`` — same shape
guarantee we now make for ``report_players``.

    docker compose exec backend uv run python -m scripts.test_top_logs_persist <SPEC_SLUG> <ENCOUNTER_ID>

Example:
    docker compose exec backend uv run python -m scripts.test_top_logs_persist death_knight_unholy 3178
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter

from sqlalchemy import select

from app.db import async_session_factory
from app.models import GameSpec, TopLog
from app.services.top_logs_service import refresh_top_logs_for_spec_encounter


async def main(spec_slug: str, encounter_id: int) -> None:
    print(f"\n=== Top-logs persist test: spec={spec_slug} encounter={encounter_id} ===\n")

    async with async_session_factory() as s:
        async with s.begin():
            spec = (
                await s.execute(select(GameSpec).where(GameSpec.slug == spec_slug))
            ).scalar_one_or_none()
            if spec is None:
                print(f"  ! spec '{spec_slug}' unknown")
                sys.exit(2)
            print(f"[1/2] Refreshing top_logs (incremental=False)…")
            rows = await refresh_top_logs_for_spec_encounter(
                s,
                spec=spec,
                encounter_id=encounter_id,
                metric=None,
                is_raid=True,
                incremental=False,
            )
        print(f"  -> {len(rows)} rows persisted")

    print("\n[2/2] Reloading rows + inspecting detail_payload…")
    async with async_session_factory() as s:
        rows = (
            (await s.execute(
                select(TopLog).where(
                    TopLog.spec_slug == spec_slug,
                    TopLog.encounter_id == encounter_id,
                )
            )).scalars().all()
        )

    if not rows:
        print("  ! No rows persisted. WCL may not have rankings for this combo yet.")
        sys.exit(0)

    with_detail = [r for r in rows if r.detail_payload]
    detail_with_talents = sum(1 for r in with_detail if (r.detail_payload or {}).get("talent_ids"))
    detail_with_stats = sum(1 for r in with_detail if (r.detail_payload or {}).get("stats"))
    detail_with_gear = sum(1 for r in with_detail if (r.detail_payload or {}).get("gear"))

    loadout_types: Counter[str] = Counter()
    for r in with_detail:
        loadout = (r.detail_payload or {}).get("talents_loadout")
        if loadout is None:
            continue
        loadout_types[type(loadout).__name__] += 1

    print(f"  total rows:           {len(rows)}")
    print(f"  with detail_payload:  {len(with_detail)}/{len(rows)}")
    print(f"  detail.talent_ids:    {detail_with_talents}/{len(with_detail)}")
    print(f"  detail.stats:         {detail_with_stats}/{len(with_detail)}")
    print(f"  detail.gear:          {detail_with_gear}/{len(with_detail)}")
    print(f"  talents_loadout types: {dict(loadout_types)}")

    if with_detail:
        sample = with_detail[0]
        d = sample.detail_payload or {}
        print(f"\n  Sample top-log: rank={sample.rank} {sample.character_name}/{sample.spec_slug}")
        print(f"    talent_ids:      {len(d.get('talent_ids') or [])}")
        print(f"    stats keys:      {sorted((d.get('stats') or {}).keys())}")
        print(f"    gear count:      {len(d.get('gear') or [])}")
        loadout = d.get("talents_loadout")
        if isinstance(loadout, list):
            print(f"    talents_loadout: list[{len(loadout)}] first={loadout[0] if loadout else None}")
        else:
            print(f"    talents_loadout: {type(loadout).__name__}")

    failures = []
    if not with_detail:
        failures.append("no rows have detail_payload")
    elif detail_with_talents == 0:
        failures.append("no detail_payload rows have talent_ids")
    elif detail_with_stats == 0:
        failures.append("no detail_payload rows have stats")
    elif detail_with_gear == 0:
        failures.append("no detail_payload rows have gear")

    if failures:
        print("\n  !!! FAILURES:")
        for f in failures:
            print(f"    - {f}")
        sys.exit(1)
    print("\n=== PASS ===\n")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python -m scripts.test_top_logs_persist <SPEC_SLUG> <ENCOUNTER_ID>")
        sys.exit(2)
    asyncio.run(main(sys.argv[1], int(sys.argv[2])))
