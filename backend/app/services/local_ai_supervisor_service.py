"""HTTP client for the local-ai sidecar's management API.

The supervisor runs alongside ``llama-server`` inside the local-ai
container and exposes :8081 with a small JSON API (status, config patch,
model list, model delete, start/stop). We keep this module thin — it's
just a typed HTTP client that maps supervisor responses onto Pydantic
schemas the admin endpoints can hand back to the frontend unchanged.

Failure modes:
  * Container not up (compose --profile local-ai never started, or admin
    stopped it) → httpx raises ConnectError → we map to UpstreamError so
    the admin UI shows a clear "supervisor unreachable" message rather
    than a generic 500.
  * Supervisor reachable but returns 4xx/5xx → propagate the body as the
    error message so the admin sees what the supervisor said.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.core.errors import NotFoundError, UpstreamError

logger = logging.getLogger(__name__)


# Conservative default — model downloads/load can be long, but every
# *single* HTTP call to the supervisor itself returns in milliseconds
# because long-running operations are kicked off in a worker thread on
# the supervisor side. So 10s is plenty.
_DEFAULT_TIMEOUT = httpx.Timeout(10.0, read=30.0, connect=5.0)


def _base_url() -> str:
    return settings.local_ai_supervisor_url.rstrip("/")


async def _request(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    expect_json: bool = True,
) -> Any:
    url = f"{_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            r = await client.request(method, url, json=json)
    except httpx.HTTPError as exc:
        # Most common cause: the local-ai container isn't running.
        # Surface the URL so the admin can tell whether they have a
        # config issue (wrong host) vs a "container not up" issue.
        raise UpstreamError(
            f"local-ai supervisor unreachable at {url}: {exc}"
        ) from exc

    if r.status_code == 404:
        raise NotFoundError(_extract_error(r) or "Not found.")
    if r.status_code >= 400:
        raise UpstreamError(
            f"local-ai supervisor returned {r.status_code}: "
            f"{_extract_error(r) or r.text[:200]}"
        )
    if not expect_json:
        return None
    try:
        return r.json()
    except ValueError as exc:
        raise UpstreamError(
            f"local-ai supervisor returned non-JSON response: {r.text[:200]}"
        ) from exc


def _extract_error(r: httpx.Response) -> str | None:
    try:
        data = r.json()
    except ValueError:
        return None
    if isinstance(data, dict):
        if isinstance(data.get("detail"), str):
            return data["detail"]
        if isinstance(data.get("detail"), list) and data["detail"]:
            first = data["detail"][0]
            if isinstance(first, dict) and "msg" in first:
                return str(first["msg"])
    return None


# --- API surface used by app.api.v1.admin --------------------------------


async def get_status() -> dict:
    return await _request("GET", "/api/v1/status")


async def patch_config(
    *,
    config: dict | None = None,
    desired_running: bool | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if config is not None:
        body["config"] = config
    if desired_running is not None:
        body["desired_running"] = desired_running
    return await _request("PATCH", "/api/v1/config", json=body)


async def start_inference() -> dict:
    return await _request("POST", "/api/v1/start")


async def stop_inference() -> dict:
    return await _request("POST", "/api/v1/stop")


async def list_models() -> list[dict]:
    out = await _request("GET", "/api/v1/models")
    return list(out) if isinstance(out, list) else []


async def delete_model(filename: str) -> None:
    await _request("DELETE", f"/api/v1/models/{filename}", expect_json=False)


async def ensure_running(target_running: bool) -> None:
    """Best-effort alignment of the supervisor's desired-running flag.

    Used by the FastAPI startup hook and the admin-settings endpoint to
    align the local-ai container with the admin's chosen ai_provider.
    Logs and swallows errors — the supervisor may simply not be running
    yet (compose without --profile local-ai), and a backend startup
    should never crash on that.
    """
    try:
        if target_running:
            await start_inference()
        else:
            await stop_inference()
    except UpstreamError as exc:
        logger.info("local-ai supervisor not reachable; skipping alignment: %s", exc)
    except Exception:  # noqa: BLE001
        logger.exception("local-ai supervisor alignment failed")
