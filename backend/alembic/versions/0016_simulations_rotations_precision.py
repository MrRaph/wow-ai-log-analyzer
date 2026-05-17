"""add rotations + precision columns to simulations

Refactors the comparison axes: rotation moves from per-loadout (where it
forced the user to duplicate a loadout to compare with vs without
Blizzard's One-Button assist) to a top-level ``rotations`` list. The
worker now expands the cartesian product ``loadouts × fight_profiles ×
rotations`` into ``simulation_runs`` rows.

``precision`` records the symbolic preset (``fast`` / ``medium`` /
``precise``) so the UI can render those labels back rather than guessing
from the raw iteration count. The integer ``iterations`` column stays as
the authoritative value the worker passes to simc.

Pre-existing data: there is none in the wild yet (0015 hasn't shipped
beyond this branch), so the migration is purely additive. We backfill
``rotations`` to ``["simc_default"]`` and ``precision`` to ``precise``
for any row Alembic finds, then drop the defaults so future rows must
specify both explicitly.

Revision ID: 0016_simulations_rotations_precision
Revises: 0015_simulations
Create Date: 2026-05-17 03:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_simulations_rotations_precision"
down_revision: Union[str, None] = "0015_simulations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulations",
        sa.Column(
            "rotations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"simc_default\"]'::jsonb"),
        ),
    )
    op.add_column(
        "simulations",
        sa.Column(
            "precision",
            sa.String(length=16),
            nullable=False,
            server_default="precise",
        ),
    )


def downgrade() -> None:
    op.drop_column("simulations", "precision")
    op.drop_column("simulations", "rotations")
