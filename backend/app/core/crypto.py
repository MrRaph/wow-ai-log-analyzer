"""Symmetric encryption helpers for storing third-party tokens at rest.

The Fernet key is derived from ``settings.secret_key`` via SHA-256, so
rotating ``SECRET_KEY`` will invalidate all stored ciphertexts (the user will
just have to re-connect their WCL account).
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_str(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_str(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid ciphertext (key changed or value tampered).") from exc
