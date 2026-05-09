"""Docker daemon control for the admin "System" card.

Opt-in via ``settings.admin_docker_control``. When disabled, every public
function in this module raises ``UpstreamError`` with a clear message —
endpoints in :mod:`app.api.v1.admin` map that to a 503 so the UI can
explain *why* the System card is empty.

We intentionally only expose actions on **the compose stack we belong to**
(filtered by ``com.docker.compose.project == settings.docker_compose_project``)
so an admin can't accidentally restart unrelated containers on the same
host. Mounting the docker socket gives the process root-on-host privileges,
so the smaller the visible surface, the better.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.core.errors import NotFoundError, UpstreamError

logger = logging.getLogger(__name__)


@dataclass
class ContainerInfo:
    name: str
    service: str
    image: str
    status: str  # running / exited / created / restarting / paused / dead
    health: str | None  # healthy / unhealthy / starting / None (no healthcheck)
    started_at: str | None
    finished_at: str | None
    is_local_ai: bool


def _ensure_enabled() -> None:
    if not settings.admin_docker_control:
        raise UpstreamError(
            "Docker control is disabled (set ADMIN_DOCKER_CONTROL=true to enable).",
        )


def _client() -> Any:
    """Build a lazy docker client. Raises UpstreamError if the socket is missing."""
    _ensure_enabled()
    try:
        import docker  # noqa: PLC0415 — keep import lazy so non-control deploys never touch it
    except ImportError as exc:
        raise UpstreamError("docker SDK not installed in this image.") from exc
    try:
        return docker.from_env()
    except Exception as exc:  # noqa: BLE001
        raise UpstreamError(
            f"Could not connect to the Docker daemon (is /var/run/docker.sock mounted?): {exc}"
        ) from exc


def _container_to_info(c: Any) -> ContainerInfo:
    attrs = c.attrs or {}
    state = attrs.get("State") or {}
    config = attrs.get("Config") or {}
    labels = config.get("Labels") or {}
    health_raw = (state.get("Health") or {}).get("Status")
    service = labels.get("com.docker.compose.service") or ""
    return ContainerInfo(
        name=c.name,
        service=service,
        image=(c.image.tags[0] if c.image and c.image.tags else attrs.get("Image", "")),
        status=state.get("Status") or "unknown",
        health=health_raw,
        started_at=state.get("StartedAt"),
        finished_at=state.get("FinishedAt"),
        is_local_ai=(service == "local-ai"),
    )


def _project_label_matches(c: Any) -> bool:
    labels = (c.attrs.get("Config") or {}).get("Labels") or {}
    return labels.get("com.docker.compose.project") == settings.docker_compose_project


async def list_stack_containers() -> list[ContainerInfo]:
    """Return every container belonging to our compose project (running or not)."""

    def _sync() -> list[ContainerInfo]:
        client = _client()
        out: list[ContainerInfo] = []
        # ``all=True`` includes stopped containers — admins want to see
        # those too (e.g. local-ai when ai_provider != "local"). We filter
        # in Python because docker-py's label-filter conversion has been
        # observed to silently drop matches in some daemon versions.
        for c in client.containers.list(all=True):
            if _project_label_matches(c):
                out.append(_container_to_info(c))
        out.sort(key=lambda i: (i.service, i.name))
        return out

    return await asyncio.to_thread(_sync)


def _find_one_sync(name_or_service: str) -> Any:
    client = _client()
    for c in client.containers.list(all=True):
        if not _project_label_matches(c):
            continue
        if c.name == name_or_service:
            return c
        labels = (c.attrs.get("Config") or {}).get("Labels") or {}
        if labels.get("com.docker.compose.service") == name_or_service:
            return c
    raise NotFoundError(f"Container '{name_or_service}' not found in this compose stack.")


async def restart(name_or_service: str, *, timeout: int = 30) -> ContainerInfo:
    def _sync() -> ContainerInfo:
        c = _find_one_sync(name_or_service)
        c.restart(timeout=timeout)
        c.reload()
        return _container_to_info(c)

    return await asyncio.to_thread(_sync)


async def start(name_or_service: str) -> ContainerInfo:
    def _sync() -> ContainerInfo:
        c = _find_one_sync(name_or_service)
        if c.status != "running":
            c.start()
        c.reload()
        return _container_to_info(c)

    return await asyncio.to_thread(_sync)


async def stop(name_or_service: str, *, timeout: int = 30) -> ContainerInfo:
    def _sync() -> ContainerInfo:
        c = _find_one_sync(name_or_service)
        if c.status == "running":
            c.stop(timeout=timeout)
        c.reload()
        return _container_to_info(c)

    return await asyncio.to_thread(_sync)


async def ensure_local_ai(target_running: bool) -> ContainerInfo | None:
    """Bring the ``local-ai`` container into the desired state if present.

    Used by the admin-settings endpoint when ``ai_provider`` toggles between
    ``local`` and anything else. Returns ``None`` silently when the
    container does not exist (e.g. compose was started without the
    ``local-ai`` profile and never created the container).
    """
    if not settings.admin_docker_control:
        # Silent no-op rather than raising — admins who haven't opted in
        # shouldn't get errors when they switch providers.
        return None

    def _sync() -> ContainerInfo | None:
        try:
            c = _find_one_sync("local-ai")
        except NotFoundError:
            return None
        running = c.status == "running"
        if target_running and not running:
            c.start()
            logger.info("local-ai started by admin-settings switch")
        elif (not target_running) and running:
            c.stop(timeout=30)
            logger.info("local-ai stopped by admin-settings switch")
        c.reload()
        return _container_to_info(c)

    return await asyncio.to_thread(_sync)
