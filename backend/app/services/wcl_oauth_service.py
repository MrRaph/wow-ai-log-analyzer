"""User-side Warcraft Logs OAuth (authorization-code flow).

Stores per-user access + refresh tokens encrypted at rest. Requests using a
user's token go to the ``/api/v2/user`` endpoint, which can see their private
logs.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import decrypt_str, encrypt_str
from app.core.errors import AuthError, NotFoundError, UpstreamError, ValidationAppError
from app.core.security import create_state_token, decode_state_token
from app.models import User, UserWclConnection
from app.services.wcl.client import WclClient, create_wcl_client, normalize_wcl_flavor, to_client_flavor

logger = logging.getLogger(__name__)

CURRENT_USER_QUERY = """
query CurrentUser {
  userData {
    currentUser {
      id
      name
    }
  }
}
"""


def _oauth_settings(flavor: str) -> dict[str, str]:
    f = normalize_wcl_flavor(flavor)
    if f == "fresh":
        return {
            "client_id": settings.wcl_fresh_client_id,
            "client_secret": settings.wcl_fresh_client_secret,
            "redirect_uri": settings.wcl_fresh_redirect_uri,
            "authorize_url": settings.wcl_fresh_oauth_authorize_url,
            "token_url": settings.wcl_fresh_oauth_token_url,
            "scope": settings.wcl_fresh_oauth_scope,
            "user_api_url": settings.wcl_fresh_user_api_url,
        }
    return {
        "client_id": settings.wcl_client_id,
        "client_secret": settings.wcl_client_secret,
        "redirect_uri": settings.wcl_redirect_uri,
        "authorize_url": settings.wcl_oauth_authorize_url,
        "token_url": settings.wcl_oauth_token_url,
        "scope": settings.wcl_oauth_scope,
        "user_api_url": settings.wcl_user_api_url,
    }


def build_authorization_url(*, user: User, flavor: str = "retail") -> str:
    cfg = _oauth_settings(flavor)
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise UpstreamError("Warcraft Logs credentials are not configured on the server.")
    state = create_state_token(str(user.id))
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "state": state,
        "scope": cfg["scope"],
    }
    return f"{cfg['authorize_url']}?{urlencode(params)}"


async def _exchange_code_for_token(code: str, *, flavor: str = "retail") -> dict[str, Any]:
    cfg = _oauth_settings(flavor)
    async with httpx.AsyncClient(timeout=20) as http:
        try:
            resp = await http.post(
                cfg["token_url"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": cfg["redirect_uri"],
                },
                auth=(cfg["client_id"], cfg["client_secret"]),
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(f"WCL token exchange failed: {exc}") from exc
    if resp.status_code != 200:
        raise UpstreamError(f"WCL token exchange returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()


async def _exchange_refresh_token(
    refresh_token: str, *, flavor: str = "retail"
) -> dict[str, Any]:
    cfg = _oauth_settings(flavor)
    async with httpx.AsyncClient(timeout=20) as http:
        try:
            resp = await http.post(
                cfg["token_url"],
                data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                auth=(cfg["client_id"], cfg["client_secret"]),
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(f"WCL refresh failed: {exc}") from exc
    if resp.status_code != 200:
        raise UpstreamError(f"WCL refresh returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()


async def _fetch_current_user(access_token: str, *, flavor: str = "retail") -> tuple[int | None, str]:
    """Best-effort: ask /api/v2/user who the token belongs to."""
    cfg = _oauth_settings(flavor)
    try:
        auth_header = "Bearer " + access_token
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.post(
                cfg["user_api_url"],
                json={"query": CURRENT_USER_QUERY},
                headers={"Authorization": auth_header},
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to fetch WCL current user — leaving identity blank.")
        return None, ""
    cu = (payload.get("data") or {}).get("userData", {}).get("currentUser") or {}
    wcl_id = cu.get("id")
    return (int(wcl_id) if wcl_id else None), str(cu.get("name") or "")


async def handle_callback(
    session: AsyncSession, *, code: str, state: str, flavor: str = "retail"
) -> User:
    if not code or not state:
        raise ValidationAppError("OAuth callback is missing code or state.")
    payload = decode_state_token(state)
    user_id_str = payload.get("sub")
    try:
        user_id = uuid.UUID(user_id_str) if user_id_str else None
    except ValueError as exc:
        raise AuthError("State token has an invalid subject.") from exc
    if not user_id:
        raise AuthError("State token has no subject.")

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise NotFoundError("Authenticated user no longer exists.")

    normalized = normalize_wcl_flavor(flavor)
    token_data = await _exchange_code_for_token(code, flavor=normalized)
    access_token = str(token_data["access_token"])
    refresh_token = token_data.get("refresh_token")
    expires_in = int(token_data.get("expires_in", 3600))
    scope = str(token_data.get("scope") or _oauth_settings(normalized)["scope"])
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

    wcl_user_id, wcl_user_name = await _fetch_current_user(access_token, flavor=normalized)

    existing = (
        await session.execute(
            select(UserWclConnection).where(
                UserWclConnection.user_id == user.id,
                UserWclConnection.flavor == normalized,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.access_token_encrypted = encrypt_str(access_token)
        existing.refresh_token_encrypted = encrypt_str(refresh_token) if refresh_token else None
        existing.expires_at = expires_at
        existing.scope = scope
        existing.wcl_user_id = wcl_user_id
        existing.wcl_user_name = wcl_user_name
    else:
        session.add(
            UserWclConnection(
                user_id=user.id,
                flavor=normalized,
                access_token_encrypted=encrypt_str(access_token),
                refresh_token_encrypted=encrypt_str(refresh_token) if refresh_token else None,
                expires_at=expires_at,
                scope=scope,
                wcl_user_id=wcl_user_id,
                wcl_user_name=wcl_user_name,
            )
        )
    await session.flush()
    return user


async def get_connection(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    flavor: str = "retail",
) -> UserWclConnection | None:
    normalized = normalize_wcl_flavor(flavor)
    return (
        await session.execute(
            select(UserWclConnection).where(
                UserWclConnection.user_id == user_id,
                UserWclConnection.flavor == normalized,
            )
        )
    ).scalar_one_or_none()


async def disconnect(session: AsyncSession, user_id: uuid.UUID, *, flavor: str = "retail") -> bool:
    conn = await get_connection(session, user_id, flavor=flavor)
    if not conn:
        return False
    await session.delete(conn)
    await session.flush()
    return True


async def _refresh_connection(session: AsyncSession, conn: UserWclConnection) -> str:
    if not conn.refresh_token_encrypted:
        raise UpstreamError(
            "Warcraft Logs token expired and there is no refresh token. Please reconnect."
        )
    refresh = decrypt_str(conn.refresh_token_encrypted)
    token_data = await _exchange_refresh_token(refresh, flavor=conn.flavor)
    access_token = str(token_data["access_token"])
    new_refresh = token_data.get("refresh_token") or refresh
    expires_in = int(token_data.get("expires_in", 3600))
    conn.access_token_encrypted = encrypt_str(access_token)
    conn.refresh_token_encrypted = encrypt_str(new_refresh)
    conn.expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    await session.flush()
    return access_token


def make_user_token_provider(session: AsyncSession, conn: UserWclConnection):
    """Return an async callable that yields a valid access token, refreshing if needed."""

    async def _provider() -> str:
        if conn.expires_at - timedelta(seconds=60) > datetime.now(UTC):
            return decrypt_str(conn.access_token_encrypted)
        return await _refresh_connection(session, conn)

    return _provider


async def build_user_wcl_client(
    session: AsyncSession, *, user_id: uuid.UUID, flavor: str = "retail"
) -> WclClient | None:
    """Return a WclClient bound to the user's token, or ``None`` if not connected."""
    normalized = normalize_wcl_flavor(flavor)
    conn = await get_connection(session, user_id, flavor=normalized)
    if not conn:
        return None
    return create_wcl_client(
        flavor=to_client_flavor(normalized),
        user_token_provider=make_user_token_provider(session, conn),
    )
