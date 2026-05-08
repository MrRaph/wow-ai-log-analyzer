"""normalize top_logs.detail_payload JSONB null -> SQL NULL

Earlier code stored Python ``None`` as JSONB ``null`` because the column was
declared with bare ``JSONB``. The model now uses ``JSONB(none_as_null=True)``
so SQL NULL is used going forward. This migration cleans up the existing
JSONB null rows so ``count(detail_payload)`` / ``IS NOT NULL`` queries become
honest about which rows actually have detail data attached.

Revision ID: 0006_top_log_jsonb_null_cleanup
Revises: 0005_analysis_model_widen
Create Date: 2026-05-08 00:00:05
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006_top_log_jsonb_null_cleanup"
down_revision: Union[str, None] = "0005_analysis_model_widen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE top_logs
        SET detail_payload = NULL
        WHERE detail_payload IS NOT NULL
          AND jsonb_typeof(detail_payload) = 'null'
        """
    )


def downgrade() -> None:
    # No-op: we can't distinguish between rows that were originally JSONB
    # null and rows that were always SQL NULL.
    pass
