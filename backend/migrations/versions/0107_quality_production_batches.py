"""Product-owned batches, keeping supplier batch numbers distinct from system IDs."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import BINARY, DATETIME

revision = "0107_quality_production_batches"
down_revision = "0106_quality_intake_numbers"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "quality_production_batches",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=False),
        sa.Column("product_id", BINARY(16), nullable=False),
        sa.Column("original_batch_no", sa.String(128), nullable=True),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("created_by", BINARY(16), nullable=False),
        sa.Column("created_at", DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("org_id", "product_id", "original_batch_no", name="uq_quality_batch_original"),
    )
    op.create_index("ix_quality_production_batches_org_id", "quality_production_batches", ["org_id"])
    op.create_index("ix_quality_production_batches_product_id", "quality_production_batches", ["product_id"])


def downgrade():
    op.drop_table("quality_production_batches")
