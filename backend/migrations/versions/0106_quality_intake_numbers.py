"""First-stage quality intake and transaction-safe readable business numbers."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import BINARY

revision = "0106_quality_intake_numbers"
down_revision = "0105_permission_matrix"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "business_number_sequences",
        sa.Column("org_id", BINARY(16), primary_key=True),
        sa.Column("prefix", sa.String(2), primary_key=True),
        sa.Column("business_date", sa.Date(), primary_key=True),
        sa.Column("last_value", sa.Integer(), nullable=False),
    )
    op.create_table(
        "business_identifiers",
        sa.Column("org_id", BINARY(16), primary_key=True),
        sa.Column("entity_kind", sa.String(64), primary_key=True),
        sa.Column("entity_id", BINARY(16), primary_key=True),
        sa.Column("display_no", sa.String(20), nullable=False),
        sa.UniqueConstraint("org_id", "display_no", name="uq_business_display_no"),
    )
    op.alter_column("quality_source_records", "occurred_at", existing_type=sa.DateTime(), nullable=True)


def downgrade():
    # Unknown event time cannot safely be converted into a fabricated timestamp.
    count = op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM quality_source_records WHERE occurred_at IS NULL"))
    if count:
        raise RuntimeError("存在未知发生时间的资料，请先导出/处理后再回退迁移")
    op.alter_column("quality_source_records", "occurred_at", existing_type=sa.DateTime(), nullable=False)
    op.drop_table("business_identifiers")
    op.drop_table("business_number_sequences")
