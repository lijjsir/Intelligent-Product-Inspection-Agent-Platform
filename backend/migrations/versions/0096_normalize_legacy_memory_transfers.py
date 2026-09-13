"""normalize legacy memory transfer statuses and same-scope audit rows

Revision ID: 0096_normalize_legacy_memory_transfers
Revises: 0095_unify_memory_governance
"""

from __future__ import annotations

from alembic import op


revision = "0096_normalize_legacy_memory_transfers"
down_revision = "0095_unify_memory_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A local confirmation is a governance event, not a transfer. Keep the
    # row for auditability but hide it from active transfer queries.
    op.execute(
        "UPDATE memory_transfer_logs "
        "SET deleted_at = COALESCE(deleted_at, updated_at), "
        "decision_note = COALESCE(decision_note, 'legacy same-scope audit; no cross-scope transfer') "
        "WHERE deleted_at IS NULL "
        "AND from_scope_type = to_scope_type "
        "AND from_scope_id = to_scope_id"
    )
    op.execute(
        "UPDATE memory_transfer_logs "
        "SET status = CASE "
        "WHEN status IN ('executed', 'confirmed') THEN 'approved' "
        "WHEN status = 'candidate' THEN 'pending_approval' "
        "ELSE status END "
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    # Status normalization is intentionally not reversed: the old values are
    # ambiguous and would reintroduce same-scope transfer semantics.
    pass
