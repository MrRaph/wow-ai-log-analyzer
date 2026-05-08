"""widen analyses.model

Revision ID: 0005_analysis_model_widen
Revises: 0004_wow_localization
Create Date: 2026-05-08 00:00:04
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_analysis_model_widen"
down_revision: Union[str, None] = "0004_wow_localization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "analyses",
        "model",
        existing_type=sa.String(64),
        type_=sa.String(255),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "analyses",
        "model",
        existing_type=sa.String(255),
        type_=sa.String(64),
        existing_nullable=False,
    )
