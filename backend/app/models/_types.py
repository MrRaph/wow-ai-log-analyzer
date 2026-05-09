"""Cross-dialect column types.

Models import these instead of dialect-specific column types directly so
the schema compiles for both production (PostgreSQL, where we want
JSONB for indexable + faster JSON ops) and tests (SQLite, where JSONB
doesn't exist — we fall back to plain JSON).
"""
from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# Resolves to JSONB on PostgreSQL, JSON on SQLite (and any other
# dialect). Use as a column type:
#
#     value: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
JSONType = JSONB().with_variant(JSON(), "sqlite")
