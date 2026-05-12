"""End-to-end test: AI prompt's localized_names map carries real talent names.

Imports a fresh report, then walks the analyzer's name-resolution path and
prints the resulting ``localized_names`` map filtered to ``talent:`` keys.

    docker compose exec backend uv run python -m scripts.test_talent_names <REPORT_CODE>
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.db import async_session_factory
from app.models import Report, ReportFight, ReportPlayer
from app.services.ai.analyzer import _collect_localized_names
from app.services.report_service import (
    create_import_skeleton,
    run_report_import,
)


async def main(code: str) -> None:
    print(f"\n=== Talent-name resolution test for {code} ===\n")

    print("[1/3] Import (skeleton + run)…")
    async with async_session_factory() as s:
        async with s.begin():
            report = await create_import_skeleton(s, raw_input=code, owner_user_id=None)
        report_id = report.id
    async with async_session_factory() as s:
        async with s.begin():
            await run_report_import(s, report_id=report_id)
    print(f"  -> report_id={report_id}")

    print("\n[2/3] Picking a fight + DPS player with talent_ids…")
    async with async_session_factory() as s:
        report = (await s.execute(select(Report).where(Report.id == report_id))).scalar_one()
        fights = (
            (await s.execute(select(ReportFight).where(ReportFight.report_id == report_id)))
            .scalars().all()
        )
        target_player: ReportPlayer | None = None
        target_fight: ReportFight | None = None
        for fight in fights:
            players = (
                (await s.execute(select(ReportPlayer).where(ReportPlayer.fight_id == fight.id)))
                .scalars().all()
            )
            for p in players:
                if (p.extras or {}).get("talent_ids"):
                    target_player = p
                    target_fight = fight
                    break
            if target_player:
                break
        if not target_player or not target_fight:
            print("  ! no player with talent_ids in any fight")
            sys.exit(1)
        print(f"  -> fight={target_fight.name!r}  player={target_player.name}/{target_player.spec_slug}")
        talent_ids = (target_player.extras or {}).get("talent_ids") or []
        print(f"  player has {len(talent_ids)} talent_ids")

        # Mock the shape that _collect_localized_names expects.
        fight_summary = {
            "encounter_id": target_fight.encounter_id,
            "encounter_name": target_fight.name,
        }
        player_summary = {
            "name": target_player.name,
            "talent_ids": talent_ids,
            "buffs": [],
            "debuffs": [],
            "damage_taken": [],
        }

        for locale in ("en", "de"):
            print(f"\n[3/3] Resolving localized_names (locale={locale})…")
            names = await _collect_localized_names(
                s,
                locale=locale,
                fight_summary=fight_summary,
                player_summary=player_summary,
                casts=[],
                gear=[],
                references=[],
            )
            talent_keys = sorted(k for k in names if k.startswith("talent:"))
            spell_collisions = [
                k for k in names if k.startswith("spell:")
                and int(k.split(":", 1)[1]) in set(int(x) for x in talent_ids)
            ]
            print(f"  total localized_names entries: {len(names)}")
            print(f"  talent: keys: {len(talent_keys)} / {len(talent_ids)} talent_ids")
            print(f"  spell-namespace collisions for talent_ids: {len(spell_collisions)} (should be 0)")
            print("  Sample resolved talents:")
            for k in talent_keys[:8]:
                print(f"    {k} → {names[k]}")

            failures = []
            if len(talent_keys) < len(talent_ids) * 0.7:
                failures.append(
                    f"only {len(talent_keys)}/{len(talent_ids)} talents resolved (expected >70%)"
                )
            if spell_collisions:
                failures.append(
                    f"talent_ids leaked into spell namespace: {spell_collisions[:3]}"
                )
            if failures:
                print("\n  !!! FAILURES:")
                for f in failures:
                    print(f"    - {f}")
                sys.exit(1)

    print("\n=== PASS ===\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m scripts.test_talent_names <WCL_REPORT_CODE>")
        sys.exit(2)
    asyncio.run(main(sys.argv[1]))
