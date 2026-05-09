"""Redis-backed sliding-window rate limiter for auth-adjacent endpoints.

Reuses the existing arq Redis pool (``app.deps.get_arq_pool``) so we don't
need a second client. ArqRedis is a subclass of ``redis.asyncio.Redis``,
so ``INCR`` + ``EXPIRE`` work as expected.

Trust model for client identification:

  * The deployment doc requires the app to run behind an HTTPS reverse
    proxy (Caddy / nginx / Traefik) that sets ``X-Forwarded-For`` to the
    real client IP. We trust that header here. If you ever expose this
    backend directly to the internet, an attacker can spoof the header
    and bypass per-IP throttling — front it with a proxy.

  * For per-account / per-email throttling (e.g. password-reset by
    address) the caller passes the email or user-id directly so it
    doesn't matter whether the IP is reliable.

The limiter raises :class:`app.core.errors.RateLimitError` (HTTP 429) on
excess. The window is a fixed window in Redis (key TTL = window seconds);
fixed-window is good enough for brute-force defence and avoids the cost
of sorted-set sliding-window state.
"""
from __future__ import annotations

import logging
from typing import Final

from fastapi import Request

from app.core.errors import RateLimitError

logger = logging.getLogger(__name__)

_KEY_PREFIX: Final = "rl:"


def _client_ip(request: Request) -> str:
    """Best-effort real-IP extraction.

    ``X-Forwarded-For`` may contain a chain (``client, proxy1, proxy2``);
    the leftmost entry is the original client. Fall back to the direct
    socket peer when no proxy header is present (dev mode).
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first = fwd.split(",", 1)[0].strip()
        if first:
            return first
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def _enforce(redis_client, *, key: str, limit: int, window_s: int) -> None:
    """Single fixed-window check. Raises RateLimitError when over budget."""
    full_key = _KEY_PREFIX + key
    try:
        count = await redis_client.incr(full_key)
        if count == 1:
            await redis_client.expire(full_key, window_s)
    except Exception:  # noqa: BLE001
        # If Redis is briefly unreachable we'd rather let the request through
        # than 500 the user — but log loudly so an admin notices the gap.
        logger.exception("rate-limit redis op failed for key=%s", key)
        return
    if count > limit:
        logger.warning(
            "rate-limit exceeded: key=%s count=%d limit=%d window=%ds",
            key, count, limit, window_s,
        )
        raise RateLimitError(
            "Too many requests. Please slow down and try again in a minute."
        )


async def enforce_ip(
    request: Request,
    redis_client,
    *,
    bucket: str,
    limit: int,
    window_s: int,
) -> None:
    """Per-IP fixed-window limiter. ``bucket`` is the route name."""
    ip = _client_ip(request)
    await _enforce(redis_client, key=f"{bucket}:ip:{ip}", limit=limit, window_s=window_s)


async def enforce_identifier(
    redis_client,
    *,
    bucket: str,
    identifier: str,
    limit: int,
    window_s: int,
) -> None:
    """Per-account / per-email limiter. Identifier is normalised to lower-case."""
    key = f"{bucket}:id:{identifier.lower().strip()}"
    await _enforce(redis_client, key=key, limit=limit, window_s=window_s)
