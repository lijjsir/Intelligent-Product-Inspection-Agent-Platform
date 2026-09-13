"""normalize legacy statuses on retained transfer audit rows

Revision ID: 0097_normalize_deleted_transfer_statuses
Revises: 0096_normalize_legacy_memory_transfers
"""

from __future__ import annotations

from alembic import op


revision = "0097_normalize_deleted_transfer_statuses"
down_revision = "0096_normalize_legacy_memory_transfers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Soft-deleted same-scope rows remain audit history, but their legacy
    # status values should not leak through compatibility APIs.
    op.execute(
        "UPDATE memory_transfer_logs SET status = CASE "
        "WHEN status IN ('executed', 'confirmed') THEN 'approved' "
        "WHEN status = 'candidate' THEN 'pending_approval' "
        "ELSE status END"
    )


def downgrade() -> None:
    pass
