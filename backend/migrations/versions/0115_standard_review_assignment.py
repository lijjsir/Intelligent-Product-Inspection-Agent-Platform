"""Track standard review responsibility without changing source snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0115_standard_review_assignment"
down_revision = "0114_remove_paper_template_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("standard_document_revisions", sa.Column("review_assignment", sa.JSON(), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM standard_document_revisions WHERE review_assignment IS NOT NULL"
    )).scalar_one():
        raise RuntimeError("Review assignments have been recorded; preserve them and roll back routing instead")
    op.drop_column("standard_document_revisions", "review_assignment")
