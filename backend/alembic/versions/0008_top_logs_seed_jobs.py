"""create top_logs_seed_jobs table

Tracks per-encounter seed runs (admin "seed encounter" button + weekly cron).
Used by the worker to update progress counters live, and by the admin UI to
render a progress section.

Revision ID: 0008_top_logs_seed_jobs
Revises: 0007_report_async_import
Create Date: 2026-05-08 22:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0008_top_logs_seed_jobs"
down_revision: Union[str, None] = "0007_report_async_import"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "top_logs_seed_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", sa.Integer(), nullable=False),
        sa.Column("encounter_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("is_raid", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("metric_filter", sa.String(length=8), nullable=True),
        sa.Column("total_specs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_specs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_spec_slug", sa.String(length=48), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_top_logs_seed_jobs_encounter_id",
        "top_logs_seed_jobs",
        ["encounter_id"],
    )
    op.create_index(
        "ix_top_logs_seed_jobs_status",
        "top_logs_seed_jobs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_top_logs_seed_jobs_status", table_name="top_logs_seed_jobs")
    op.drop_index("ix_top_logs_seed_jobs_encounter_id", table_name="top_logs_seed_jobs")
    op.drop_table("top_logs_seed_jobs")
