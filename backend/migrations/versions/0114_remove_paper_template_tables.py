"""Remove the retired paper-template storage tables."""

from alembic import op
import sqlalchemy as sa


revision = "0114_remove_paper_template_tables"
down_revision = "0113_inspection_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    for table in ("paper_template_rules", "paper_template_clauses", "paper_templates"):
        if table in existing:
            op.drop_table(table)


def downgrade() -> None:
    # The retired feature has no supported downgrade path. Keeping the migration
    # irreversible prevents stale template data from being silently recreated.
    pass
