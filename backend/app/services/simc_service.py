"""HTTP client + helpers for the simc sidecar.

The sidecar exposes:
  GET  /healthz
  GET  /version    → simc git revision banner
  POST /simulate   → runs one simulation, returns parsed DPS + abilities

This module is intentionally thin: it knows how to talk to the sidecar
and how to assemble a per-fight-profile request from our high-level
"single_target" / "council" / "mythic_plus" profile keys. The
heavy-lifting parsing happens in the sidecar (cf. ``simc-sidecar/server.py``);
we just shuttle dicts back and forth.

Profile knobs we expose (other simc options stay sidecar-side):
  single_target:  Patchwerk, 1 target
  council:        Patchwerk, 3 targets
  mythic_plus:    DungeonSlice (simc's canonical M+ sim, varies pull count
                  + add waves to approximate a real M+ chunk)

Errors are mapped to ``UpstreamError`` (sidecar down / network) or
``ValidationAppError`` (bad profile / simc rejected the input) so the
worker can surface a usable error string to the user.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import settings
from app.core.errors import UpstreamError, ValidationAppError

logger = logging.getLogger(__name__)


# Maps the user-facing fight-profile keys to simc engine flags. Keep
# this in sync with the frontend's profile picker.
FIGHT_PROFILES: dict[str, dict[str, Any]] = {
    "single_target": {
        "fight_style": "Patchwerk",
        "desired_targets": 1,
        "label_en": "Raid — Single Target",
        "label_de": "Raid — Single Target",
    },
    "council": {
        "fight_style": "Patchwerk",
        "desired_targets": 3,
        "label_en": "Raid — Council (3 bosses)",
        "label_de": "Raid — Council (3 Bosse)",
    },
    "mythic_plus": {
        # DungeonSlice approximates a chunk of an M+ key (mixed boss +
        # trash + add waves with realistic timing). It's simc's canonical
        # M+ profile and what the community sims against for talent
        # comparisons.
        "fight_style": "DungeonSlice",
        "desired_targets": 1,  # DungeonSlice spawns its own waves
        "label_en": "Mythic+ pulls (DungeonSlice)",
        "label_de": "Mythic+ Pulls (DungeonSlice)",
    },
}


# Lines in a /simc profile that represent talent loadouts. We strip
# whichever the user-supplied profile has and replace it with the
# loadout's own talent block, so the same character can be re-sim'd
# against different builds.
_TALENT_KEYS = ("talents", "class_talents", "spec_talents", "hero_talents")
_TALENT_LINE_RE = re.compile(
    rf"^\s*(?:{'|'.join(_TALENT_KEYS)})\s*=.*$",
    re.MULTILINE,
)


def _client() -> httpx.AsyncClient:
    timeout = httpx.Timeout(
        connect=10.0,
        read=settings.simc_request_timeout_s,
        write=30.0,
        pool=15.0,
    )
    return httpx.AsyncClient(timeout=timeout, base_url=settings.simc_base_url.rstrip("/"))


def _strip_talent_lines(profile: str) -> str:
    return _TALENT_LINE_RE.sub("", profile)


def apply_loadout_talents(profile: str, loadout_talents: str) -> str:
    """Replace the profile's talent block with the loadout's.

    ``loadout_talents`` may be one or more lines of the form
    ``talents=...`` / ``class_talents=...`` / ``spec_talents=...``
    (whatever the user pasted from /simc for that talent build). We
    drop the existing talent lines from the base profile and append
    the loadout's block so the rest of the profile (gear, stats,
    character meta) is preserved.
    """
    stripped = _strip_talent_lines(profile).rstrip()
    talents = (loadout_talents or "").strip()
    if not talents:
        return stripped + "\n"
    return stripped + "\n\n# loadout talents\n" + talents + "\n"


async def ping_version() -> dict[str, Any]:
    """Probe the sidecar for its simc build version. Used by the
    admin "SimC" card and the /healthz aggregator."""
    try:
        async with _client() as client:
            r = await client.get("/version", timeout=30)
    except httpx.HTTPError as exc:
        raise UpstreamError(
            f"simc sidecar unreachable at {settings.simc_base_url}: {exc}"
        ) from exc
    if r.status_code >= 400:
        raise UpstreamError(f"simc /version returned {r.status_code}: {r.text[:500]}")
    return r.json()


async def run_simulation(
    *,
    profile: str,
    fight_profile_key: str,
    iterations: int,
    rotation: str,
    threads: int | None = None,
    target_error: float | None = None,
) -> dict[str, Any]:
    """Hand a profile to the sidecar's /simulate endpoint and return
    the parsed result. Raises ``UpstreamError`` if the sidecar is
    unreachable / 5xx, ``ValidationAppError`` if simc itself rejected
    the profile (4xx)."""
    if fight_profile_key not in FIGHT_PROFILES:
        raise ValidationAppError(f"unknown fight profile {fight_profile_key!r}")
    fp = FIGHT_PROFILES[fight_profile_key]
    payload: dict[str, Any] = {
        "profile": profile,
        "fight_style": fp["fight_style"],
        "desired_targets": fp["desired_targets"],
        "iterations": iterations,
        "rotation": rotation,
        "assume_raid_prep": True,
    }
    if threads is not None:
        payload["threads"] = threads
    if target_error is not None:
        payload["target_error"] = target_error

    try:
        async with _client() as client:
            r = await client.post("/simulate", json=payload)
    except httpx.HTTPError as exc:
        raise UpstreamError(
            f"simc sidecar unreachable at {settings.simc_base_url}: {exc}"
        ) from exc

    if 400 <= r.status_code < 500:
        # 4xx → bad profile / unsupported flag — surface to the user.
        try:
            detail = r.json().get("detail")
        except Exception:  # noqa: BLE001
            detail = r.text
        raise ValidationAppError(f"simc rejected the profile: {detail}")
    if r.status_code >= 500:
        raise UpstreamError(f"simc sidecar errored ({r.status_code}): {r.text[:500]}")
    return r.json()
