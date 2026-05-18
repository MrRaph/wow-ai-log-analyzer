"""add share_token column to analyses

Lets analysis owners opt in to a public share link. ``None`` keeps the
analysis private (the default); any non-null value lets anyone with that
token read the analysis anonymously via ``GET /shared-analyses/{token}``.

Owners can flip this on or off at any time by hitting
``POST /analyses/{id}/share`` (generates a fresh token) or
``DELETE /analyses/{id}/share`` (clears it back to NULL).

We give the column a unique-but-nullable index so multiple analyses
can coexist as "private" (NULL), exactly one can own any given token
when set, and lookups by token stay O(1).

Revision ID: 0014_analysis_share_token
Revises: 0013_talents_loadout_jsonb
Create Date: 2026-05-13 02:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_analysis_share_token"
down_revision: Union[str, None] = "0013_talents_loadout_jsonb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("share_token", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_analyses_share_token",
        "analyses",
        ["share_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_analyses_share_token", table_name="analyses")
    op.drop_column("analyses", "share_token")
