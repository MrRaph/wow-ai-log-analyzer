"""Unit tests for password hashing + JWT helpers."""
from __future__ import annotations

import pytest

from app.core.errors import AuthError
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_round_trip():
    h = hash_password("hunter2-correct-horse")
    assert verify_password("hunter2-correct-horse", h) is True
    assert verify_password("wrong", h) is False


def test_jwt_round_trip():
    token = create_token("user-123", kind="access")
    data = decode_token(token, expected_kind="access")
    assert data["sub"] == "user-123"
    assert data["type"] == "access"


def test_jwt_kind_mismatch():
    token = create_token("user-123", kind="refresh")
    with pytest.raises(AuthError):
        decode_token(token, expected_kind="access")


def test_jwt_invalid_signature():
    token = create_token("user-123", kind="access")
    # Corrupt the signature by changing the first character of the signature
    # part, which always has 6 fully significant bits (unlike the last char of
    # an HS256 signature, which carries only 4 significant bits and can
    # accidentally encode the same bytes).
    header, payload, sig = token.rsplit(".", 2)
    bad_first = "B" if sig[0] != "B" else "C"
    bad = f"{header}.{payload}.{bad_first}{sig[1:]}"
    with pytest.raises(AuthError):
        decode_token(bad, expected_kind="access")
