"""add paper template tables

Revision ID: 0073
Revises: 0072
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paper_templates",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("template_id", sa.String(128), nullable=False),
        sa.Column("template_name", sa.String(255), nullable=False),
        sa.Column("school_name", sa.String(255), nullable=True),
        sa.Column("degree_type", sa.String(64), nullable=True),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_bucket", sa.String(128), nullable=True),
        sa.Column("source_object_key", sa.String(512), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id"),
    )

    op.create_table(
        "paper_template_clauses",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("template_id", sa.String(128), nullable=False),
        sa.Column("clause_id", sa.String(128), nullable=False),
        sa.Column("parent_clause_id", sa.String(128), nullable=True),
        sa.Column("section_title", sa.String(255), nullable=True),
        sa.Column("clause_title", sa.String(255), nullable=True),
        sa.Column("clause_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("applies_to", mysql.JSON(), nullable=True),
        sa.Column("rule_codes", mysql.JSON(), nullable=True),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("severity", sa.String(32), nullable=True),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("paragraph_index", sa.Integer(), nullable=True),
        sa.Column("source_file_name", sa.String(255), nullable=True),
        sa.Column("source_hash", sa.String(128), nullable=True),
        sa.Column("qdrant_point_id", sa.String(191), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "clause_id", name="uq_paper_template_clause"),
    )
    op.create_index("ix_paper_template_clauses_template_id", "paper_template_clauses", ["template_id"])

    op.create_table(
        "paper_template_rules",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("template_id", sa.String(128), nullable=False),
        sa.Column("rule_code", sa.String(128), nullable=False),
        sa.Column("rule_name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("check_type", sa.String(64), nullable=False),
        sa.Column("expected", mysql.JSON(), nullable=True),
        sa.Column("source_clause_ids", mysql.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "rule_code", name="uq_paper_template_rule"),
    )
    op.create_index("ix_paper_template_rules_template_id", "paper_template_rules", ["template_id"])


def downgrade():
    op.drop_table("paper_template_rules")
    op.drop_table("paper_template_clauses")
    op.drop_table("paper_templates")
