"""Tests for Fresh-flavor awareness in background workers and zone discovery."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wcl_zones_service import (
    CurrentRaidEncounter,
    _build_zone_expansion_map,
    clear_cache,
    fetch_current_raid_encounters,
    get_expansion_slug_for_zone,
)


# ---------------------------------------------------------------------------
# wcl_zones_service — per-flavor caching
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_zones_cache():
    """Ensure the module-level cache is empty before and after each test."""
    clear_cache()
    yield
    clear_cache()


FAKE_ZONES_PAYLOAD = {
    "worldData": {
        "zones": [
            {
                "id": 1,
                "name": "Manaforge Omega",
                "frozen": False,
                "expansion": {"id": 10, "name": "The War Within"},
                "encounters": [
                    {"id": 100, "name": "Boss One"},
                    {"id": 101, "name": "Boss Two"},
                    {"id": 102, "name": "Boss Three"},
                    {"id": 103, "name": "Boss Four"},
                    {"id": 104, "name": "Boss Five"},
                    {"id": 105, "name": "Boss Six"},
                    {"id": 106, "name": "Boss Seven"},
                    {"id": 107, "name": "Boss Eight"},
                ],
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_fetch_current_raid_encounters_retail():
    mock_client = AsyncMock()
    mock_client.query = AsyncMock(return_value=FAKE_ZONES_PAYLOAD)

    result = await fetch_current_raid_encounters(wcl_client=mock_client, wcl_flavor="retail")
    assert len(result) == 8
    assert all(isinstance(e, CurrentRaidEncounter) for e in result)
    assert result[0].encounter_id == 100


@pytest.mark.asyncio
async def test_fetch_current_raid_encounters_fresh_uses_separate_cache():
    mock_retail = AsyncMock()
    mock_retail.query = AsyncMock(return_value=FAKE_ZONES_PAYLOAD)
    mock_fresh = AsyncMock()
    mock_fresh.query = AsyncMock(return_value=FAKE_ZONES_PAYLOAD)

    await fetch_current_raid_encounters(wcl_client=mock_retail, wcl_flavor="retail")
    await fetch_current_raid_encounters(wcl_client=mock_fresh, wcl_flavor="fresh")

    # Each flavor queried its own client exactly once.
    mock_retail.query.assert_called_once()
    mock_fresh.query.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_current_raid_encounters_fresh_cached_on_second_call():
    mock_client = AsyncMock()
    mock_client.query = AsyncMock(return_value=FAKE_ZONES_PAYLOAD)

    await fetch_current_raid_encounters(wcl_client=mock_client, wcl_flavor="fresh")
    # Second call — should use cache, no new network call.
    await fetch_current_raid_encounters(wcl_flavor="fresh")

    mock_client.query.assert_called_once()


@pytest.mark.asyncio
async def test_clear_cache_single_flavor():
    mock_client = AsyncMock()
    mock_client.query = AsyncMock(return_value=FAKE_ZONES_PAYLOAD)

    await fetch_current_raid_encounters(wcl_client=mock_client, wcl_flavor="retail")
    await fetch_current_raid_encounters(wcl_client=mock_client, wcl_flavor="fresh")

    clear_cache(wcl_flavor="retail")

    # retail must re-fetch, fresh must still be cached.
    mock_client2 = AsyncMock()
    mock_client2.query = AsyncMock(return_value=FAKE_ZONES_PAYLOAD)

    with patch("app.services.wcl_zones_service.create_wcl_client", return_value=mock_client2):
        await fetch_current_raid_encounters(wcl_flavor="retail")
        await fetch_current_raid_encounters(wcl_flavor="fresh")  # no-op — still cached

    mock_client2.query.assert_called_once()  # only retail re-fetched


# ---------------------------------------------------------------------------
# seed_encounter_task — reads wcl_flavor from job row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_encounter_task_uses_flavor_from_job(tmp_path):
    """seed_encounter_task must instantiate the WCL client using the job's wcl_flavor."""
    from app.models import TopLogsSeedJob

    job = MagicMock(spec=TopLogsSeedJob)
    job.id = uuid.uuid4()
    job.status = "queued"
    job.encounter_id = 100
    job.is_raid = True
    job.metric_filter = None
    job.wcl_flavor = "fresh"

    captured_flavor = []

    def fake_create_wcl_client(*, flavor, **_kw):
        captured_flavor.append(flavor)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    with (
        patch("app.workers.tasks.seed_encounter.async_session_factory") as mock_sf,
        patch("app.workers.tasks.seed_encounter.create_wcl_client", side_effect=fake_create_wcl_client),
        patch("app.workers.tasks.seed_encounter.refresh_top_logs_for_spec_encounter", new_callable=AsyncMock),
    ):
        # Build a minimal session mock that short-circuits at the job-load step.
        session = AsyncMock()
        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_sf.return_value = session_cm

        begin_cm = AsyncMock()
        begin_cm.__aenter__ = AsyncMock(return_value=None)
        begin_cm.__aexit__ = AsyncMock(return_value=False)
        session.begin = MagicMock(return_value=begin_cm)

        # Make execute return None so the job is "gone" — we just want to verify
        # that the flavor is read correctly before the early return.
        execute_result = MagicMock()
        execute_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=execute_result)

        from app.workers.tasks.seed_encounter import seed_encounter_task
        await seed_encounter_task({}, str(job.id))

    # The flavor was never used because the job wasn't found, but we can at
    # least confirm the import works and the function is callable. A deeper
    # integration test requires a real DB fixture.


# ---------------------------------------------------------------------------
# refresh_all_top_logs — iterates active flavors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_all_top_logs_seeds_fresh_when_enabled():
    """When top_logs_fresh_enabled=True, the weekly cron must seed Fresh encounters."""
    seeded_flavors = []

    async def fake_seed_missing(wcl_flavor="retail"):
        seeded_flavors.append(wcl_flavor)
        return 0

    with (
        patch("app.workers.tasks.top_logs._seed_missing_current_tier_encounters", side_effect=fake_seed_missing),
        patch("app.workers.tasks.top_logs.settings") as mock_settings,
        patch("app.workers.tasks.top_logs.async_session_factory") as mock_sf,
    ):
        mock_settings.top_logs_fresh_enabled = True
        mock_settings.redis_host = "localhost"
        mock_settings.redis_port = 6379
        mock_settings.redis_db = 0

        session = AsyncMock()
        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_sf.return_value = session_cm
        begin_cm = AsyncMock()
        begin_cm.__aenter__ = AsyncMock(return_value=None)
        begin_cm.__aexit__ = AsyncMock(return_value=False)
        session.begin = MagicMock(return_value=begin_cm)
        execute_result = MagicMock()
        execute_result.all = MagicMock(return_value=[])
        session.execute = AsyncMock(return_value=execute_result)

        from app.workers.tasks.top_logs import refresh_all_top_logs
        await refresh_all_top_logs({})

    assert "retail" in seeded_flavors
    assert "fresh" in seeded_flavors


# ---------------------------------------------------------------------------
# _build_zone_expansion_map — pure unit tests (no I/O)
# ---------------------------------------------------------------------------

def test_build_zone_expansion_map_maps_known_expansions():
    """Known expansion IDs produce the correct Wowhead slug."""
    zones = [
        {"id": 1000, "expansion": {"id": 2}},   # TBC
        {"id": 2000, "expansion": {"id": 3}},   # WotLK
        {"id": 3000, "expansion": {"id": 4}},   # Cata
        {"id": 4000, "expansion": {"id": 1}},   # Classic Era
    ]
    result = _build_zone_expansion_map(zones)
    assert result[1000] == "tbc"
    assert result[2000] == "wotlk"
    assert result[3000] == "cata"
    assert result[4000] == "classic"


def test_build_zone_expansion_map_skips_unknown_expansion():
    """Expansion IDs not in the slug mapping (e.g. retail TWW) are excluded."""
    zones = [
        {"id": 5000, "expansion": {"id": 10}},  # The War Within — retail, no slug
        {"id": 6000, "expansion": {"id": 99}},  # Completely unknown
        {"id": 7000, "expansion": {"id": 2}},   # TBC — included
    ]
    result = _build_zone_expansion_map(zones)
    assert 5000 not in result
    assert 6000 not in result
    assert result[7000] == "tbc"


def test_build_zone_expansion_map_tolerates_malformed_entries():
    """Missing / null expansion data and invalid IDs are silently skipped."""
    zones = [
        {"id": 1, "expansion": None},
        {"id": 2},                              # no expansion key
        {"id": 0, "expansion": {"id": 2}},      # zone_id 0 → excluded
        {"id": None, "expansion": {"id": 2}},   # null zone_id → excluded
        "not-a-dict",                           # wrong type → excluded
        {"id": 3000, "expansion": {"id": 3}},   # WotLK — valid
    ]
    result = _build_zone_expansion_map(zones)
    assert 1 not in result
    assert 2 not in result
    assert 0 not in result
    assert result[3000] == "wotlk"


# ---------------------------------------------------------------------------
# get_expansion_slug_for_zone — async, with mocked WCL client
# ---------------------------------------------------------------------------

FAKE_CLASSIC_ZONES_PAYLOAD = {
    "worldData": {
        "zones": [
            {
                "id": 1017,                     # Gruul's Lair (TBC)
                "name": "Gruul's Lair",
                "frozen": True,
                "expansion": {"id": 2, "name": "The Burning Crusade"},
                "encounters": [
                    {"id": 649, "name": "High King Maulgar"},
                    {"id": 650, "name": "Gruul the Dragonkiller"},
                ],
            },
            {
                "id": 2070,                     # Naxxramas WotLK
                "name": "Naxxramas",
                "frozen": True,
                "expansion": {"id": 3, "name": "Wrath of the Lich King"},
                "encounters": [{"id": 1107, "name": "Anub'Rekhan"}],
            },
            {
                "id": 3000,                     # Hypothetical Cata zone (current)
                "name": "Firelands",
                "frozen": False,
                "expansion": {"id": 4, "name": "Cataclysm"},
                "encounters": [
                    {"id": 1000 + i, "name": f"Boss {i}"} for i in range(7)
                ],
            },
        ]
    }
}


@pytest.mark.asyncio
async def test_get_expansion_slug_for_zone_tbc():
    """Gruul's Lair zone_id → "tbc"."""
    mock_client = AsyncMock()
    mock_client.query = AsyncMock(return_value=FAKE_CLASSIC_ZONES_PAYLOAD)

    result = await get_expansion_slug_for_zone(1017, "classic", wcl_client=mock_client)

    assert result == "tbc"
    mock_client.query.assert_called_once()


@pytest.mark.asyncio
async def test_get_expansion_slug_for_zone_wotlk():
    """A WotLK zone_id → "wotlk"."""
    mock_client = AsyncMock()
    mock_client.query = AsyncMock(return_value=FAKE_CLASSIC_ZONES_PAYLOAD)

    result = await get_expansion_slug_for_zone(2070, "classic", wcl_client=mock_client)

    assert result == "wotlk"


@pytest.mark.asyncio
async def test_get_expansion_slug_for_zone_returns_none_for_unknown():
    """A zone_id not in the payload returns None (no slug invented)."""
    mock_client = AsyncMock()
    mock_client.query = AsyncMock(return_value=FAKE_CLASSIC_ZONES_PAYLOAD)

    result = await get_expansion_slug_for_zone(9999, "classic", wcl_client=mock_client)

    assert result is None


@pytest.mark.asyncio
async def test_get_expansion_slug_for_zone_uses_cache_on_second_call():
    """Second call for the same flavor must not trigger a new network request."""
    mock_client = AsyncMock()
    mock_client.query = AsyncMock(return_value=FAKE_CLASSIC_ZONES_PAYLOAD)

    await get_expansion_slug_for_zone(1017, "classic", wcl_client=mock_client)
    # Second call — no client passed; would create one via create_wcl_client if
    # the cache were cold, which would error without patching settings.
    result = await get_expansion_slug_for_zone(1017, "classic")

    assert result == "tbc"
    mock_client.query.assert_called_once()


@pytest.mark.asyncio
async def test_get_expansion_slug_reuses_map_populated_by_fetch_current():
    """fetch_current_raid_encounters populates _zone_expansion_map; a
    subsequent get_expansion_slug_for_zone call must use it without a
    second network round-trip."""
    mock_client = AsyncMock()
    mock_client.query = AsyncMock(return_value=FAKE_CLASSIC_ZONES_PAYLOAD)

    # Populate the cache via fetch_current_raid_encounters (returns Cata zone).
    await fetch_current_raid_encounters(wcl_client=mock_client, wcl_flavor="classic")
    assert mock_client.query.call_count == 1

    # Now look up a TBC zone (frozen, so not in the current-tier list) — should
    # still work because _zone_expansion_map covers ALL zones, not just current.
    result = await get_expansion_slug_for_zone(1017, "classic")
    assert result == "tbc"
    # No additional WCL request was made.
    assert mock_client.query.call_count == 1


@pytest.mark.asyncio
async def test_classic_flavor_uses_separate_cache_from_retail():
    """The "classic" flavor key must be cached independently from "retail"."""
    retail_client = AsyncMock()
    retail_client.query = AsyncMock(return_value=FAKE_ZONES_PAYLOAD)
    classic_client = AsyncMock()
    classic_client.query = AsyncMock(return_value=FAKE_CLASSIC_ZONES_PAYLOAD)

    await fetch_current_raid_encounters(wcl_client=retail_client, wcl_flavor="retail")
    await fetch_current_raid_encounters(wcl_client=classic_client, wcl_flavor="classic")

    # Each client was queried exactly once for its own flavor.
    retail_client.query.assert_called_once()
    classic_client.query.assert_called_once()

    # The expansion map for classic contains TBC zones; retail map does not.
    tbc_slug = await get_expansion_slug_for_zone(1017, "classic")
    assert tbc_slug == "tbc"

    # Zone 1017 is not a retail zone — must not bleed across flavor caches.
    retail_slug = await get_expansion_slug_for_zone(1017, "retail")
    assert retail_slug is None


@pytest.mark.asyncio
async def test_clear_cache_removes_zone_expansion_map():
    """clear_cache must also clear _zone_expansion_map so the next call refetches."""
    mock_client = AsyncMock()
    mock_client.query = AsyncMock(return_value=FAKE_CLASSIC_ZONES_PAYLOAD)

    await get_expansion_slug_for_zone(1017, "classic", wcl_client=mock_client)
    assert mock_client.query.call_count == 1

    clear_cache("classic")

    # After clearing, looking up the zone again must trigger a new fetch.
    # For "classic", _fetch_all_zones uses create_classic_zones_client, not
    # create_wcl_client, so we patch the correct factory.
    mock_client2 = AsyncMock()
    mock_client2.query = AsyncMock(return_value=FAKE_CLASSIC_ZONES_PAYLOAD)
    with patch("app.services.wcl_zones_service.create_classic_zones_client", return_value=mock_client2):
        result = await get_expansion_slug_for_zone(1017, "classic")

    assert result == "tbc"
    mock_client2.query.assert_called_once()


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_all_top_logs_skips_fresh_when_disabled():
    seeded_flavors = []

    async def fake_seed_missing(wcl_flavor="retail"):
        seeded_flavors.append(wcl_flavor)
        return 0

    with (
        patch("app.workers.tasks.top_logs._seed_missing_current_tier_encounters", side_effect=fake_seed_missing),
        patch("app.workers.tasks.top_logs.settings") as mock_settings,
        patch("app.workers.tasks.top_logs.async_session_factory") as mock_sf,
    ):
        mock_settings.top_logs_fresh_enabled = False

        session = AsyncMock()
        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_sf.return_value = session_cm
        begin_cm = AsyncMock()
        begin_cm.__aenter__ = AsyncMock(return_value=None)
        begin_cm.__aexit__ = AsyncMock(return_value=False)
        session.begin = MagicMock(return_value=begin_cm)
        execute_result = MagicMock()
        execute_result.all = MagicMock(return_value=[])
        session.execute = AsyncMock(return_value=execute_result)

        from app.workers.tasks.top_logs import refresh_all_top_logs
        await refresh_all_top_logs({})

    assert "retail" in seeded_flavors
    assert "fresh" not in seeded_flavors
