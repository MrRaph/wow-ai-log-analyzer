"""add phase column to wow_data_imports

Lets the admin UI show which sub-phase of the wago.tools import is currently
running (spells / items / encounters / done) instead of an opaque "in_progress".

Revision ID: 0009_wow_data_phase
Revises: 0008_top_logs_seed_jobs
Create Date: 2026-05-08 22:30:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_wow_data_phase"
down_revision: Union[str, None] = "0008_top_logs_seed_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wow_data_imports",
        sa.Column("phase", sa.String(length=32), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("wow_data_imports", "phase")
