"""Locale helpers for the backend.

The frontend handles user-facing UI translation via next-intl. The backend
needs locale awareness only for outgoing emails (subject/body), wowhead URL
construction, and AI analysis output language.
"""
from __future__ import annotations

from fastapi import Header

SUPPORTED_LOCALES = ("en", "de")
DEFAULT_LOCALE = "en"


def normalize_locale(value: str | None) -> str:
    if not value:
        return DEFAULT_LOCALE
    code = value.split("-")[0].split(",")[0].strip().lower()
    return code if code in SUPPORTED_LOCALES else DEFAULT_LOCALE


def locale_dependency(
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    x_locale: str | None = Header(default=None, alias="X-Locale"),
) -> str:
    """FastAPI dependency that picks the request locale.

    Priority: explicit X-Locale header > Accept-Language > default.
    """
    return normalize_locale(x_locale or accept_language)
