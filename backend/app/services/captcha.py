"""Cloudflare Turnstile verification.

Disabled by default. When ``settings.turnstile_enabled`` is True, the
relevant auth endpoints must call :func:`verify_or_raise` with the token
the frontend received from the widget. Verification calls Cloudflare's
``siteverify`` endpoint (https://challenges.cloudflare.com/turnstile/v0/siteverify);
a successful response has ``"success": true``.

Tokens are single-use and short-lived (Cloudflare side: ~5 min). We do
not cache successful verifications — replays are prevented by Cloudflare.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.core.errors import ValidationAppError

logger = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT_SECONDS = 8.0


async def verify_or_raise(token: str | None, *, remote_ip: str | None = None) -> None:
    """Validate a Turnstile token. No-op when Turnstile is disabled.

    Raises :class:`ValidationAppError` when the token is missing/invalid so
    callers don't have to branch on the enabled flag themselves.
    """
    if not settings.turnstile_enabled:
        return
    if not settings.turnstile_secret_key:
        # Fail closed: misconfigured backend should not silently let traffic
        # through with no protection.
        logger.error("turnstile_enabled=True but turnstile_secret_key is empty")
        raise ValidationAppError("Captcha is misconfigured on the server.")
    if not token:
        raise ValidationAppError("Captcha verification is required.")

    payload = {"secret": settings.turnstile_secret_key, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(VERIFY_URL, data=payload)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Turnstile siteverify failed: %s", exc)
        raise ValidationAppError("Captcha verification failed (network).") from exc

    if not body.get("success"):
        codes = ",".join(body.get("error-codes") or []) or "unknown"
        logger.info("Turnstile rejected token: %s", codes)
        raise ValidationAppError("Captcha verification failed.")
