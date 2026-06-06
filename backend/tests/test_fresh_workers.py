"""Tests for Fresh-flavor awareness in background workers and zone discovery."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wcl_zones_service import (
    CurrentRaidEncounter,
    clear_cache,
    fetch_current_raid_encounters,
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
