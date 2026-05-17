"""add simulations + simulation_runs tables

Stores SimulationCraft DPS simulation requests and their per-(loadout × fight
profile) child runs. Cleanup is driven by a daily arq cron job using the
``simc_retention_days`` setting (default 30 d); the FK cascade on
``simulation_runs.simulation_id`` removes the children automatically.

We use ``JSONB`` (via :class:`app.models._types.JSONType`) for the loadouts,
fight profiles, and per-run ability breakdown. The ability list is capped
to top 100 entries before insert in the worker, so row size stays well
under the toast threshold.

Revision ID: 0015_simulations
Revises: 0014_analysis_share_token
Create Date: 2026-05-17 02:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_simulations"
down_revision: Union[str, None] = "0014_analysis_share_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


simulation_status = sa.Enum(
    "pending",
    "running",
    "succeeded",
    "failed",
    name="simulation_status",
)
simulation_run_status = sa.Enum(
    "pending",
    "running",
    "succeeded",
    "failed",
    name="simulation_run_status",
)


def upgrade() -> None:
    simulation_status.create(op.get_bind(), checkfirst=True)
    simulation_run_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "simulations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "requested_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("simc_profile", sa.Text(), nullable=False),
        sa.Column(
            "loadouts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "fight_profiles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("iterations", sa.Integer(), nullable=False, server_default="5000"),
        sa.Column(
            "status",
            simulation_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("simc_build", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_simulations_requested_by_id", "simulations", ["requested_by_id"])
    op.create_index("ix_simulations_status", "simulations", ["status"])
    op.create_index("ix_simulations_created_at", "simulations", ["created_at"])

    op.create_table(
        "simulation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "simulation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("simulations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("loadout_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loadout_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column(
            "rotation", sa.String(length=32), nullable=False, server_default="simc_default"
        ),
        sa.Column("fight_profile_key", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            simulation_run_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("dps_mean", sa.Float(), nullable=False, server_default="0"),
        sa.Column("dps_min", sa.Float(), nullable=False, server_default="0"),
        sa.Column("dps_max", sa.Float(), nullable=False, server_default="0"),
        sa.Column("dps_stddev", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fight_length_mean", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "abilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_simulation_runs_simulation_id", "simulation_runs", ["simulation_id"])
    op.create_index("ix_simulation_runs_status", "simulation_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_simulation_runs_status", table_name="simulation_runs")
    op.drop_index("ix_simulation_runs_simulation_id", table_name="simulation_runs")
    op.drop_table("simulation_runs")
    op.drop_index("ix_simulations_created_at", table_name="simulations")
    op.drop_index("ix_simulations_status", table_name="simulations")
    op.drop_index("ix_simulations_requested_by_id", table_name="simulations")
    op.drop_table("simulations")
    simulation_run_status.drop(op.get_bind(), checkfirst=True)
    simulation_status.drop(op.get_bind(), checkfirst=True)
