"""Add public consumer complaint intake.

Revision ID: 0101_public_complaint_intake
Revises: 0100_quality_supervision
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BINARY


revision = "0101_public_complaint_intake"
down_revision = "0100_quality_supervision"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "public_complaint_intakes",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=False),
        sa.Column("tracking_code", sa.String(32), nullable=False),
        sa.Column("query_code_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("risk_case_id", BINARY(16), nullable=True),
        sa.Column("assigned_to", BINARY(16), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("contact_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "org_id", "idempotency_hash", name="uq_public_complaint_idempotency"
        ),
        sa.UniqueConstraint("tracking_code", name="uq_public_complaint_tracking_code"),
    )
    for column in (
        "org_id",
        "tracking_code",
        "request_fingerprint",
        "status",
        "risk_case_id",
    ):
        op.create_index(
            f"ix_public_complaint_intakes_{column}",
            "public_complaint_intakes",
            [column],
        )


def downgrade():
    op.drop_table("public_complaint_intakes")
