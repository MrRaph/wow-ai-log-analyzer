"""Battle.net WoW Profile API client (Client-Credentials flow).

We don't need per-user OAuth for character profile data: the same
talent-loadout + equipment endpoints the public Armory web page
shows are reachable with a Client-Credentials token. One token per
backend process, cached in memory until shortly before it expires.

Used by the /simulate page to pull authoritative talent loadouts
(including hero talents) and equipped gear, so the user no longer
needs to paste an in-game ``/simc`` string at all.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings
from app.core.errors import NotFoundError, UpstreamError, ValidationAppError

logger = logging.getLogger(__name__)

VALID_REGIONS = ("eu", "us", "kr", "tw")
# https://develop.battle.net/documentation/world-of-warcraft — Profile API
# host is region-scoped, but the OAuth /token endpoint is global.
_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=15.0, pool=15.0)


class _TokenCache:
    """Process-wide singleton for the Client-Credentials access token.

    Battle.net tokens last 24 h. We refresh ~5 min before expiry, so
    a steady stream of requests never sees an expired token in flight.
    """

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> str:
        # Cheap fast-path: still valid → return without taking the lock.
        if self._token and self._expires_at - 300 > time.time():
            return self._token
        async with self._lock:
            if self._token and self._expires_at - 300 > time.time():
                return self._token
            if not settings.blizzard_client_id or not settings.blizzard_client_secret:
                raise UpstreamError("Battle.net credentials are not configured.")
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
                try:
                    resp = await http.post(
                        settings.blizzard_oauth_token_url,
                        data={"grant_type": "client_credentials"},
                        auth=(
                            settings.blizzard_client_id,
                            settings.blizzard_client_secret,
                        ),
                    )
                except httpx.HTTPError as exc:
                    raise UpstreamError(f"Battle.net token request failed: {exc}") from exc
            if resp.status_code != 200:
                raise UpstreamError(
                    f"Battle.net token request returned {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()
            self._token = str(data["access_token"])
            self._expires_at = time.time() + int(data.get("expires_in", 3600))
            return self._token


_token_cache = _TokenCache()


def _api_base(region: str) -> str:
    region = (region or settings.blizzard_default_region).lower()
    if region not in VALID_REGIONS:
        raise ValidationAppError(
            f"Unknown region {region!r} — pick one of {', '.join(VALID_REGIONS)}."
        )
    return f"https://{region}.api.blizzard.com"


def _realm_slug(realm: str) -> str:
    """Blizzard's REST API addresses realms by ``realm-slug`` — the
    lowercase, dash-separated form of the realm name. Most realms
    have no special chars so this naïve transform is enough; the few
    that do (e.g. "Aman'Thal" → ``amanthal``) can fail and we
    surface a 404 to the caller, who picks the right slug."""
    return realm.strip().lower().replace(" ", "-").replace("'", "")


async def _get(region: str, path: str) -> dict[str, Any]:
    """Issue an authenticated GET against the region's Profile API host.

    ``path`` is the part after the host, including the leading slash.
    The ``namespace=profile-{region}`` query param is required by
    Blizzard for profile endpoints; we add it transparently. Locale
    defaults to English so spell / talent names match what simc
    profiles and the rest of our stack use; the frontend can re-render
    in the user's locale via our own ``wow_localizations`` cache.
    """
    token = await _token_cache.get()
    url = f"{_api_base(region)}{path}"
    params = {"namespace": f"profile-{region}", "locale": "en_US"}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
        try:
            resp = await http.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Battle.net request failed: {exc}") from exc
    if resp.status_code == 404:
        # Most useful 404 for the caller is "char not found / realm
        # slug wrong". We re-shape to our own NotFoundError so the
        # API layer maps it to 404 with a clean message.
        raise NotFoundError(
            "Character not found on Battle.net. Check the realm slug "
            "(lowercase, no spaces) and character name."
        )
    if resp.status_code >= 400:
        raise UpstreamError(
            f"Battle.net API {url} returned {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json()


async def get_character_profile(region: str, realm: str, name: str) -> dict[str, Any]:
    """Top-level character info: race, class, level, item level, etc.

    Endpoint: ``/profile/wow/character/{realm-slug}/{name-lower}``"""
    slug = _realm_slug(realm)
    n = quote(name.strip().lower(), safe="")
    return await _get(region, f"/profile/wow/character/{slug}/{n}")


async def get_specializations(region: str, realm: str, name: str) -> dict[str, Any]:
    """Per-spec talent loadouts incl. hero-talent picks.

    Endpoint:
    ``/profile/wow/character/{realm-slug}/{name-lower}/specializations``

    Each loadout carries a ``talent_loadout_code`` we pass straight to
    simc as ``talents=…`` — these codes are authoritative (fresh from
    Blizzard, matching the live talent-tree shape) and bypass the
    SimC Addon's saved-loadout staleness problem entirely.
    """
    slug = _realm_slug(realm)
    n = quote(name.strip().lower(), safe="")
    return await _get(region, f"/profile/wow/character/{slug}/{n}/specializations")


async def get_equipment(region: str, realm: str, name: str) -> dict[str, Any]:
    """Currently equipped gear (16 slots).

    Endpoint:
    ``/profile/wow/character/{realm-slug}/{name-lower}/equipment``

    Each item carries item ID, bonus IDs, enchantments, gem sockets
    and crafted-stat overrides — everything simc needs to build the
    profile gear lines.
    """
    slug = _realm_slug(realm)
    n = quote(name.strip().lower(), safe="")
    return await _get(region, f"/profile/wow/character/{slug}/{n}/equipment")
