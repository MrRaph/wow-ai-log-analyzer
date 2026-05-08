"""report_fights.extras

Revision ID: 0003_fight_extras
Revises: 0002_wcl_connections
Create Date: 2026-05-08 00:00:02
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_fight_extras"
down_revision: Union[str, None] = "0002_wcl_connections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "report_fights",
        sa.Column(
            "extras",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("report_fights", "extras")
