"""Record classification basis without limiting categories to a reference shortlist."""
import sqlalchemy as sa
from alembic import op

revision = "0109_category_basis"
down_revision = "0108_quality_product_identity"
branch_labels = depends_on = None


def upgrade():
    op.add_column("product_categories", sa.Column("classification_basis", sa.Text(), nullable=True))
    from app.core.quality_category_directory import DIRECTORY
    table = sa.table("product_categories", sa.column("name"), sa.column("classification_basis"))
    for item in DIRECTORY:
        op.execute(table.update().where(table.c.name == item["name"], table.c.classification_basis.is_(None)).values(
            classification_basis=f'{item["source_title"]}；产品项：{item["name"]}；{item["source_url"]}'))


def downgrade():
    op.drop_column("product_categories", "classification_basis")
