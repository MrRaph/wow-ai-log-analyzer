"""add wcl_flavor to top_logs_seed_jobs

Revision ID: 0020_seed_job_flavor
Revises: 0019_wcl_fresh_support
Create Date: 2026-06-06 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_seed_job_flavor"
down_revision: str | None = "0019_wcl_fresh_support"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "top_logs_seed_jobs",
        sa.Column("wcl_flavor", sa.String(length=16), nullable=False, server_default="retail"),
    )


def downgrade() -> None:
    op.drop_column("top_logs_seed_jobs", "wcl_flavor")
