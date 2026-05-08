"""report async import: add status + error, allow null start/end times

Reports are now imported via the arq worker. The HTTP endpoint creates a
skeleton row immediately (only ``wcl_code`` + ``owner_user_id`` are known),
the worker fills in the rest. Until that completes ``start_time`` and
``end_time`` are NULL, and ``import_status`` is ``"importing"``.

Revision ID: 0007_report_async_import
Revises: 0006_top_log_jsonb_null_cleanup
Create Date: 2026-05-08 21:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_report_async_import"
down_revision: Union[str, None] = "0006_top_log_jsonb_null_cleanup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column(
            "import_status",
            sa.String(length=16),
            nullable=False,
            server_default="ready",
        ),
    )
    op.add_column("reports", sa.Column("import_error", sa.Text(), nullable=True))
    op.alter_column(
        "reports", "start_time", existing_type=sa.DateTime(timezone=True), nullable=True
    )
    op.alter_column(
        "reports", "end_time", existing_type=sa.DateTime(timezone=True), nullable=True
    )


def downgrade() -> None:
    # Down: re-tighten nullability and drop the new columns. Anything still
    # marked importing/failed at the time of downgrade keeps NULL timestamps,
    # so we backfill those to epoch first.
    op.execute(
        """
        UPDATE reports
        SET start_time = COALESCE(start_time, TIMESTAMP '1970-01-01 00:00:00+00'),
            end_time   = COALESCE(end_time,   TIMESTAMP '1970-01-01 00:00:00+00')
        WHERE start_time IS NULL OR end_time IS NULL
        """
    )
    op.alter_column(
        "reports", "start_time", existing_type=sa.DateTime(timezone=True), nullable=False
    )
    op.alter_column(
        "reports", "end_time", existing_type=sa.DateTime(timezone=True), nullable=False
    )
    op.drop_column("reports", "import_error")
    op.drop_column("reports", "import_status")
