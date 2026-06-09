"""Async Warcraft Logs API v2 GraphQL client.

Two modes:

- *Client credentials* (default). Uses the OAuth2 client-credentials flow to
  obtain a token cached in-memory; routes queries to ``/api/v2/client``. Public
  data only.
- *User token*. The caller passes a ``user_token_provider`` callable that
  returns a fresh access token (and is responsible for refreshing). Queries
  are routed to ``/api/v2/user``, which can see the user's private logs.

All requests use tenacity for retry and respect 429 ``Retry-After``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal, cast

import httpx
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config import settings
from app.core.errors import UpstreamError

logger = logging.getLogger(__name__)

UserTokenProvider = Callable[[], Awaitable[str]]
WclFlavor = Literal["retail", "fresh", "classic"]
WclClientFlavor = Literal["retail", "fresh"]


class WclClient:
    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_url: str | None = None,
        user_api_url: str | None = None,
        token_url: str | None = None,
        timeout: float = 30.0,
        user_token_provider: UserTokenProvider | None = None,
    ) -> None:
        self._client_id = client_id or settings.wcl_client_id
        self._client_secret = client_secret or settings.wcl_client_secret
        self._api_url = api_url or settings.wcl_api_url
        self._user_api_url = user_api_url or settings.wcl_user_api_url
        self._token_url = token_url or settings.wcl_oauth_token_url
        self._timeout = timeout
        self._user_token_provider = user_token_provider
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

    async def _http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> "WclClient":
        await self._http_client()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    @property
    def uses_user_token(self) -> bool:
        return self._user_token_provider is not None

    # ------------------------------------------------------------------ token

    async def _ensure_token(self) -> str:
        if self._user_token_provider is not None:
            return await self._user_token_provider()
        async with self._lock:
            now = time.time()
            if self._token and self._token_exp - 60 > now:
                return self._token
            if not self._client_id or not self._client_secret:
                raise UpstreamError(
                    "Warcraft Logs credentials are not configured. Set WCL_CLIENT_ID and WCL_CLIENT_SECRET."
                )
            client = await self._http_client()
            data = {"grant_type": "client_credentials"}
            try:
                resp = await client.post(
                    self._token_url, data=data, auth=(self._client_id, self._client_secret)
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise UpstreamError(f"WCL OAuth token request failed: {exc}") from exc
            payload = resp.json()
            self._token = str(payload["access_token"])
            self._token_exp = now + float(payload.get("expires_in", 3600))
            return self._token

    # ------------------------------------------------------------------ query

    async def query(self, gql: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._ensure_token()
        client = await self._http_client()
        api_url = self._user_api_url if self.uses_user_token else self._api_url
        retrying = AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential_jitter(initial=1, max=15),
            retry=retry_if_exception_type((httpx.HTTPError, UpstreamError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                resp = await client.post(
                    api_url,
                    json={"query": gql, "variables": variables or {}},
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 401:
                    if not self.uses_user_token:
                        self._token = None  # force refresh on next call
                    raise UpstreamError("WCL token rejected.")
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "5"))
                    await asyncio.sleep(retry_after)
                    raise UpstreamError("WCL rate limited.")
                if resp.status_code >= 500:
                    raise UpstreamError(f"WCL upstream error: {resp.status_code}")
                resp.raise_for_status()
                payload = resp.json()
                if "errors" in payload and payload["errors"]:
                    msg = "; ".join(e.get("message", "?") for e in payload["errors"])
                    raise UpstreamError(f"WCL GraphQL error: {msg}")
                return payload.get("data", {})
        raise UpstreamError("WCL query failed without a successful attempt.")


def _client_credentials_for_flavor(flavor: WclFlavor) -> tuple[str, str]:
    if flavor == "fresh":
        return settings.wcl_fresh_client_id, settings.wcl_fresh_client_secret
    if flavor == "classic":
        # classic.warcraftlogs.com currently shares the retail OAuth client
        # registry and API v2 host in this project setup.
        return settings.wcl_client_id, settings.wcl_client_secret
    return settings.wcl_client_id, settings.wcl_client_secret


def _api_urls_for_flavor(flavor: WclFlavor) -> tuple[str, str, str]:
    if flavor == "fresh":
        return (
            settings.wcl_fresh_api_url,
            settings.wcl_fresh_user_api_url,
            settings.wcl_fresh_oauth_token_url,
        )
    if flavor == "classic":
        # Classic report data (fights, casts, rankings…) is accessible through
        # the retail API host — the report namespace is global across all WCL
        # game versions.  Only worldData.zones needs the classic-specific host
        # (see wcl_zones_service.create_classic_zones_client).
        return settings.wcl_api_url, settings.wcl_user_api_url, settings.wcl_oauth_token_url
    return settings.wcl_api_url, settings.wcl_user_api_url, settings.wcl_oauth_token_url


def create_classic_zones_client() -> WclClient:
    """Client pointing at classic.warcraftlogs.com solely for worldData.zones.

    Classic report data (fights, casts, rankings) is served through the retail
    host; only the zone-discovery query needs this endpoint so that it returns
    TBC/WotLK/Cata zones instead of retail zones.  Shares OAuth credentials
    with the retail client.
    """
    return WclClient(
        client_id=settings.wcl_client_id,
        client_secret=settings.wcl_client_secret,
        api_url=settings.wcl_classic_api_url,
        user_api_url=settings.wcl_user_api_url,
        token_url=settings.wcl_oauth_token_url,
    )


def create_wcl_client(
    *, flavor: WclFlavor = "retail", user_token_provider: UserTokenProvider | None = None
) -> WclClient:
    client_id, client_secret = _client_credentials_for_flavor(flavor)
    api_url, user_api_url, token_url = _api_urls_for_flavor(flavor)
    return WclClient(
        client_id=client_id,
        client_secret=client_secret,
        api_url=api_url,
        user_api_url=user_api_url,
        token_url=token_url,
        user_token_provider=user_token_provider,
    )


def normalize_wcl_flavor(flavor: str | None) -> WclFlavor:
    f = (flavor or "retail").strip().lower()
    if f in {"retail", "fresh", "classic"}:
        return cast(WclFlavor, f)
    return "retail"


def to_client_flavor(flavor: str | None) -> WclClientFlavor:
    """Map a flavor string to the WclClientFlavor used to create a WclClient.

    "classic" uses the retail API host for all report/ranking queries —
    the global WCL report namespace is served through www.warcraftlogs.com.
    Only worldData.zones needs a classic-specific host; that is handled in
    wcl_zones_service via create_classic_zones_client().
    """
    return "fresh" if normalize_wcl_flavor(flavor) == "fresh" else "retail"
