"""add WCL flavor support

Revision ID: 0019_wcl_fresh_support
Revises: 0018_simulation_custom_overrides
Create Date: 2026-06-05 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_wcl_fresh_support"
down_revision: str | None = "0018_simulation_custom_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column("wcl_flavor", sa.String(length=16), nullable=False, server_default="retail"),
    )
    op.drop_constraint("uq_reports_wcl_code", "reports", type_="unique")
    op.create_unique_constraint(
        "uq_reports_wcl_code_flavor",
        "reports",
        ["wcl_code", "wcl_flavor"],
    )

    op.add_column(
        "user_wcl_connections",
        sa.Column("flavor", sa.String(length=16), nullable=False, server_default="retail"),
    )
    op.drop_constraint("user_wcl_connections_pkey", "user_wcl_connections", type_="primary")
    op.create_primary_key(
        "user_wcl_connections_pkey", "user_wcl_connections", ["user_id", "flavor"]
    )

    op.add_column(
        "top_logs",
        sa.Column("wcl_flavor", sa.String(length=16), nullable=False, server_default="retail"),
    )


def downgrade() -> None:
    op.drop_column("top_logs", "wcl_flavor")

    op.drop_constraint("user_wcl_connections_pkey", "user_wcl_connections", type_="primary")
    op.create_primary_key("user_wcl_connections_pkey", "user_wcl_connections", ["user_id"])
    op.drop_column("user_wcl_connections", "flavor")

    op.drop_constraint("uq_reports_wcl_code_flavor", "reports", type_="unique")
    op.create_unique_constraint("uq_reports_wcl_code", "reports", ["wcl_code"])
    op.drop_column("reports", "wcl_flavor")
