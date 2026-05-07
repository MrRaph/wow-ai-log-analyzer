"""Async Warcraft Logs API v2 GraphQL client.

We use the OAuth2 client-credentials flow. The token is cached in-memory until
60 seconds before its real expiry. All requests are routed through tenacity
retry with exponential backoff (capped) and respect 429 ``Retry-After`` if
present.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

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


class WclClient:
    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_url: str | None = None,
        token_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._client_id = client_id or settings.wcl_client_id
        self._client_secret = client_secret or settings.wcl_client_secret
        self._api_url = api_url or settings.wcl_api_url
        self._token_url = token_url or settings.wcl_oauth_token_url
        self._timeout = timeout
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

    # ------------------------------------------------------------------ token

    async def _ensure_token(self) -> str:
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
                    self._api_url,
                    json={"query": gql, "variables": variables or {}},
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 401:
                    self._token = None  # force refresh on next call
                    raise UpstreamError("WCL token rejected; will refresh.")
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
        # Unreachable due to reraise=True above, but mypy needs it.
        raise UpstreamError("WCL query failed without a successful attempt.")
