"""add custom_overrides JSONB to simulations

The new ``custom`` fight-profile lets the user pick a free-form combo of
fight style / desired_targets / max_time / target_error. The chosen
values land in this column so a simulation can be replayed
deterministically.

Revision ID: 0018_simulation_custom_overrides
Revises: 0017_loadout_compare_user_aware
Create Date: 2026-05-18 03:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_simulation_custom_overrides"
down_revision: Union[str, None] = "0016_sim_rotations_precision"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulations",
        sa.Column(
            "custom_overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("simulations", "custom_overrides")
