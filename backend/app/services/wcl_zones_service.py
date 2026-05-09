"""Discover the current retail raid encounters via the WCL ``worldData.zones`` API.

WCL's zones list is the canonical source for "what is current content" — it
includes every raid tier across every expansion, with their encounter IDs.
We pick the heaviest expansion id (latest) and the non-frozen raid zone(s)
within it. ``frozen=true`` means WCL has stopped accepting new logs for the
zone (i.e. tier is over); we always skip those.

The result is cached in-memory for the lifetime of the process: zone-list
churn is on the order of new patches (months), so even a long-running
worker doesn't need to re-fetch.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.wcl.client import WclClient
from app.services.wcl.queries import WORLD_ZONES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurrentRaidEncounter:
    zone_id: int
    zone_name: str
    encounter_id: int
    encounter_name: str
    expansion_id: int
    expansion_name: str


_cached: list[CurrentRaidEncounter] | None = None


async def fetch_current_raid_encounters(
    *, force_refresh: bool = False, wcl_client: WclClient | None = None
) -> list[CurrentRaidEncounter]:
    """Return the raid encounters of the current retail tier.

    A "raid zone" is one that is not frozen and contains at least 5 encounters
    — that filter is enough to drop dungeon zones (M+ has its own zones with
    typically 8 dungeon entries, but expansions also occasionally publish
    "Open World" zones with handful of bosses; we additionally pick zones
    from the highest expansion id only, which excludes those edge cases).
    """
    global _cached
    if _cached is not None and not force_refresh:
        return _cached

    own_client = wcl_client is None
    client = wcl_client or WclClient()
    try:
        payload = await client.query(WORLD_ZONES, {})
    finally:
        if own_client:
            await client.aclose()

    zones = ((payload or {}).get("worldData") or {}).get("zones") or []
    if not zones:
        logger.warning("WCL returned no zones; current-tier discovery disabled")
        _cached = []
        return _cached

    # Highest expansion id == latest expansion. WCL increments these
    # monotonically with each new expansion.
    latest_expansion_id = max(
        int((z.get("expansion") or {}).get("id") or 0) for z in zones
    )

    out: list[CurrentRaidEncounter] = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        if zone.get("frozen"):
            continue
        exp = zone.get("expansion") or {}
        if int(exp.get("id") or 0) != latest_expansion_id:
            continue
        encounters = zone.get("encounters") or []
        # Heuristic: a raid zone has multiple bosses. Mythic+ "season" zones
        # also have ~8 dungeons but those are flagged as the M+ section in
        # the UI; on the server they share the same zone shape, so we
        # additionally trust the zone *name* — anything that ends with
        # "Mythic Plus" or "Dungeons" gets dropped.
        zname = (zone.get("name") or "").strip()
        zname_lower = zname.lower()
        if "mythic+" in zname_lower or "mythic plus" in zname_lower:
            continue
        if "dungeon" in zname_lower:
            continue
        if len(encounters) < 5:
            continue
        for enc in encounters:
            if not isinstance(enc, dict):
                continue
            try:
                eid = int(enc.get("id"))
            except (TypeError, ValueError):
                continue
            out.append(
                CurrentRaidEncounter(
                    zone_id=int(zone.get("id") or 0),
                    zone_name=zname,
                    encounter_id=eid,
                    encounter_name=str(enc.get("name") or ""),
                    expansion_id=latest_expansion_id,
                    expansion_name=str(exp.get("name") or ""),
                )
            )

    logger.info(
        "current retail raid: expansion=%s, %d encounters",
        latest_expansion_id,
        len(out),
    )
    _cached = out
    return out


def clear_cache() -> None:
    """Reset the in-memory cache. Used by tests + /refresh-cache admin endpoints."""
    global _cached
    _cached = None
