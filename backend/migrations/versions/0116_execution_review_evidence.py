"""Persist independent execution review provenance without rewriting history."""
from alembic import op
import sqlalchemy as sa

revision = "0116_execution_review_evidence"
down_revision = "0115_standard_review_assignment"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inspection_execution_actions", sa.Column("evidence_refs", sa.JSON(), nullable=True))
    op.add_column("inspection_execution_actions", sa.Column("verification_snapshot", sa.JSON(), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM inspection_execution_actions WHERE verification_snapshot IS NOT NULL OR evidence_refs IS NOT NULL")).scalar_one():
        raise RuntimeError("Review evidence has been recorded; preserve it and roll back application routing instead")
    op.drop_column("inspection_execution_actions", "verification_snapshot")
    op.drop_column("inspection_execution_actions", "evidence_refs")
