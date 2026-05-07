"""Password hashing + JWT helpers."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.core.errors import AuthError

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenKind = Literal["access", "refresh", "invite", "reset"]


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd.verify(password, hashed)
    except Exception:  # noqa: BLE001
        return False


def _expiry_for(kind: TokenKind) -> datetime:
    now = datetime.now(UTC)
    if kind == "access":
        return now + timedelta(minutes=settings.jwt_access_ttl_minutes)
    if kind == "refresh":
        return now + timedelta(days=settings.jwt_refresh_ttl_days)
    if kind == "invite":
        return now + timedelta(days=14)
    if kind == "reset":
        return now + timedelta(hours=1)
    raise ValueError(f"unknown token kind: {kind}")


def create_token(subject: str, kind: TokenKind, extra: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int(_expiry_for(kind).timestamp()),
        "type": kind,
        "jti": secrets.token_urlsafe(16),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_kind: TokenKind | None = None) -> dict[str, Any]:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise AuthError("Invalid or expired token.") from exc
    if expected_kind and data.get("type") != expected_kind:
        raise AuthError("Token type mismatch.")
    return data


def generate_secure_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)
