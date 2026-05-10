"""convert report_players.talents_loadout to JSONB

WCL ships the modern talent picks under ``combatantInfo.talentTree`` as a
list of ``{id, rank, nodeID}`` objects. The column was originally typed
``VARCHAR(2048)`` for the old serialized-string format, which makes the
new structured payload fail to bind on insert.

We migrate to JSONB so the structured loadout can be stored verbatim and
later queried by id/rank/nodeID. The DB is empty for fresh deployments
(reports got wiped together with the v0.1.0 cutover), so the column data
loss on the up-cast is intentional and harmless.

Revision ID: 0013_talents_loadout_jsonb
Revises: 0012_user_ai_reasoning_effort
Create Date: 2026-05-10 00:30:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_talents_loadout_jsonb"
down_revision: Union[str, None] = "0012_user_ai_reasoning_effort"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "report_players",
        "talents_loadout",
        existing_type=sa.String(length=2048),
        type_=postgresql.JSONB(),
        existing_nullable=True,
        postgresql_using="NULL",
    )


def downgrade() -> None:
    op.alter_column(
        "report_players",
        "talents_loadout",
        existing_type=postgresql.JSONB(),
        type_=sa.String(length=2048),
        existing_nullable=True,
        postgresql_using="talents_loadout::text",
    )
