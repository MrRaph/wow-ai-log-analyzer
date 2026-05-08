"""wow localization tables

Revision ID: 0004_wow_localization
Revises: 0003_fight_extras
Create Date: 2026-05-08 00:00:03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_wow_localization"
down_revision: Union[str, None] = "0003_fight_extras"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wow_localizations",
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("game_id", sa.Integer, primary_key=True),
        sa.Column("locale", sa.String(8), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("extras", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index(
        "ix_wow_localizations_lookup",
        "wow_localizations",
        ["locale", "kind", "game_id"],
    )

    op.create_table(
        "wow_data_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("build", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="in_progress"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_imported", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source", sa.String(32), nullable=False, server_default="wago.tools"),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_wow_data_imports_build", "wow_data_imports", ["build"])


def downgrade() -> None:
    op.drop_table("wow_data_imports")
    op.drop_table("wow_localizations")
