"""CLI helper: seed the top-logs cache for a given encounter across all specs.

Usage::

    uv run python -m scripts.seed_top_logs <encounter_id>

The daily worker only re-fetches (spec, encounter) pairs that already exist in
the cache, so this script is the canonical way to introduce a *new* encounter
to the rotation. Pick a current-tier raid encounter ID from
https://www.warcraftlogs.com/zones (each encounter has a stable numeric id).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from app.db import async_session_factory
from app.models import GameSpec
from app.services.top_logs_service import refresh_top_logs_for_spec_encounter
from app.services.wcl.client import WclClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("seed_top_logs")


async def _run(encounter_id: int) -> int:
    total = 0
    async with WclClient() as wcl, async_session_factory() as session:
        async with session.begin():
            specs = (await session.execute(select(GameSpec))).scalars().all()
        for spec in specs:
            try:
                async with session.begin():
                    rows = await refresh_top_logs_for_spec_encounter(
                        session, spec=spec, encounter_id=encounter_id, wcl_client=wcl
                    )
                logger.info("seeded %s rows for spec=%s encounter=%s", len(rows), spec.slug, encounter_id)
                total += len(rows)
            except Exception:
                logger.exception("failed for spec=%s encounter=%s", spec.slug, encounter_id)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("encounter_id", type=int)
    args = parser.parse_args()
    total = asyncio.run(_run(args.encounter_id))
    print(f"Seeded {total} rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
