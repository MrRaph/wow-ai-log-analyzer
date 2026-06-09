"""Discover the current raid encounters via the WCL ``worldData.zones`` API.

WCL's zones list is the canonical source for "what is current content" — it
includes every raid tier across every expansion, with their encounter IDs.
We pick the heaviest expansion id (latest) and the non-frozen raid zone(s)
within it. ``frozen=true`` means WCL has stopped accepting new logs for the
zone (i.e. tier is over); we always skip those.

The result is cached in-memory per flavor for the lifetime of the process:
zone-list churn is on the order of new patches (months), so even a long-running
worker doesn't need to re-fetch.

Flavor keys:
- "retail" → queries www.warcraftlogs.com (retail zones)
- "classic" → queries classic.warcraftlogs.com (TBC / WotLK / Cata zones)
- "fresh"   → queries fresh.warcraftlogs.com  (Classic Era / SoD zones)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.wcl.client import WclClient, WclFlavor, create_wcl_client, to_client_flavor
from app.services.wcl.parser import _EXPANSION_ID_TO_SLUG
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


def _normalize_flavor_key(wcl_flavor: str) -> WclFlavor:
    """Normalise to one of the three valid flavor keys."""
    if wcl_flavor in ("retail", "fresh", "classic"):
        return wcl_flavor  # type: ignore[return-value]
    return "retail"


# Per-flavor cache: {"retail": [...], "classic": [...], "fresh": [...]}
_cached: dict[str, list[CurrentRaidEncounter]] = {}

# Per-flavor zone_id → expansion_slug map — built from the same WORLD_ZONES
# payload and used by analyzer.py to refine "classic" into "tbc"/"wotlk"/etc.
_zone_expansion_map: dict[str, dict[int, str]] = {}


async def _fetch_all_zones(
    flavor_key: WclFlavor, wcl_client: WclClient | None = None
) -> list[dict]:
    """Fetch the raw zone list from WCL for the given flavor."""
    own_client = wcl_client is None
    client = wcl_client or create_wcl_client(flavor=to_client_flavor(flavor_key))
    try:
        payload = await client.query(WORLD_ZONES, {})
    finally:
        if own_client:
            await client.aclose()
    return ((payload or {}).get("worldData") or {}).get("zones") or []


def _build_zone_expansion_map(zones: list[dict]) -> dict[int, str]:
    """Return {zone_id: expansion_slug} for every zone in the list."""
    result: dict[int, str] = {}
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        try:
            zone_id = int(zone.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if not zone_id:
            continue
        try:
            exp_id = int((zone.get("expansion") or {}).get("id") or 0)
        except (TypeError, ValueError):
            exp_id = 0
        slug = _EXPANSION_ID_TO_SLUG.get(exp_id, "")
        if slug:
            result[zone_id] = slug
    return result


async def fetch_current_raid_encounters(
    *, force_refresh: bool = False, wcl_client: WclClient | None = None, wcl_flavor: str = "retail"
) -> list[CurrentRaidEncounter]:
    """Return the raid encounters of the current tier for the given flavor.

    A "raid zone" is one that is not frozen and contains at least 5 encounters
    — that filter is enough to drop dungeon zones (M+ has its own zones with
    typically 8 dungeon entries, but expansions also occasionally publish
    "Open World" zones with handful of bosses; we additionally pick zones
    from the highest expansion id only, which excludes those edge cases).
    """
    flavor_key = _normalize_flavor_key(wcl_flavor)
    if flavor_key in _cached and not force_refresh:
        return _cached[flavor_key]

    zones = await _fetch_all_zones(flavor_key, wcl_client)
    if not zones:
        logger.warning("WCL returned no zones; current-tier discovery disabled for flavor=%s", flavor_key)
        _cached[flavor_key] = []
        return _cached[flavor_key]

    # Build and cache the zone → expansion map while we have the data.
    _zone_expansion_map[flavor_key] = _build_zone_expansion_map(zones)

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
        "current %s raid: expansion=%s, %d encounters",
        flavor_key,
        latest_expansion_id,
        len(out),
    )
    _cached[flavor_key] = out
    return out


async def get_expansion_slug_for_zone(
    zone_id: int,
    wcl_flavor: str,
    *,
    wcl_client: WclClient | None = None,
) -> str | None:
    """Return the Wowhead expansion slug (e.g. "tbc", "wotlk") for a zone.

    Lazy-fetches and caches the full zone list for the flavor on first call.
    Returns ``None`` if the zone is not found or has no known expansion slug.
    """
    flavor_key = _normalize_flavor_key(wcl_flavor)
    if flavor_key not in _zone_expansion_map:
        # Trigger a fetch that also populates _zone_expansion_map.
        own_client = wcl_client is None
        client = wcl_client or create_wcl_client(flavor=to_client_flavor(flavor_key))
        try:
            zones = await _fetch_all_zones(flavor_key, client)
        finally:
            if own_client:
                await client.aclose()
        _zone_expansion_map[flavor_key] = _build_zone_expansion_map(zones)

    return _zone_expansion_map[flavor_key].get(zone_id)


def clear_cache(wcl_flavor: str | None = None) -> None:
    """Reset the in-memory cache. Used by tests + /refresh-cache admin endpoints.

    Pass wcl_flavor to clear only that flavor; omit to clear all.
    """
    if wcl_flavor is not None:
        flavor_key = _normalize_flavor_key(wcl_flavor)
        _cached.pop(flavor_key, None)
        _zone_expansion_map.pop(flavor_key, None)
    else:
        _cached.clear()
        _zone_expansion_map.clear()
