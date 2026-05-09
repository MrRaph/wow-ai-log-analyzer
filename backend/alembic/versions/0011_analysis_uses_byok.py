"""add uses_byok flag to analyses

When True the worker uses the requesting user's own AI config (BYOK) instead
of the app-wide one. Existing rows default to False (legacy app-wide path).

Revision ID: 0011_analysis_uses_byok
Revises: 0010_user_ai_config
Create Date: 2026-05-09 00:30:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_analysis_uses_byok"
down_revision: Union[str, None] = "0010_user_ai_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("uses_byok", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
    )


def downgrade() -> None:
    op.drop_column("analyses", "uses_byok")
