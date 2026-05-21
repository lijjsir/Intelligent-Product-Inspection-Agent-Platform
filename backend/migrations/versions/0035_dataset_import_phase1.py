"""add dataset import phase1 tables

Revision ID: 0035_dataset_import_phase1
Revises: 0034_chat_route_obs
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0035_dataset_import_phase1"
down_revision = "0034_chat_route_obs"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "datasets" not in tables:
        op.create_table(
            "datasets",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("created_by", sa.BINARY(16), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("modality", sa.String(length=32), nullable=False, server_default="image_text"),
            sa.Column("tags", mysql.JSON(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("image_sample_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("text_sample_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("uploaded_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("knowledge_graph_status", sa.String(length=32), nullable=False, server_default="idle"),
            sa.Column("alignment_status", sa.String(length=32), nullable=False, server_default="idle"),
            sa.Column("augmentation_status", sa.String(length=32), nullable=False, server_default="idle"),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("org_id", "created_by", "name", name="uq_datasets_owner_name"),
        )
        op.create_index("idx_datasets_org_owner", "datasets", ["org_id", "created_by", "updated_at"])

    if "dataset_samples" not in tables:
        op.create_table(
            "dataset_samples",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("dataset_id", sa.BINARY(16), nullable=False),
            sa.Column("created_by", sa.BINARY(16), nullable=True),
            sa.Column("sample_type", sa.String(length=32), nullable=False, server_default="text"),
            sa.Column("sample_name", sa.String(length=255), nullable=True),
            sa.Column("text_content", sa.Text(), nullable=True),
            sa.Column("content_type", sa.String(length=120), nullable=True),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("checksum_sha256", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("storage_backend", sa.String(length=32), nullable=True),
            sa.Column("bucket", sa.String(length=120), nullable=True),
            sa.Column("object_key", sa.Text(), nullable=True),
            sa.Column("file_url", sa.Text(), nullable=True),
            sa.Column("annotation_data", mysql.JSON(), nullable=True),
            sa.Column("quality_score", sa.Float(), nullable=True),
            sa.Column("related_entities", mysql.JSON(), nullable=True),
            sa.Column("source_metadata", mysql.JSON(), nullable=True),
            sa.Column("preview_text", sa.Text(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_dataset_samples_dataset", "dataset_samples", ["dataset_id", "created_at"])
        op.create_index("idx_dataset_samples_owner", "dataset_samples", ["org_id", "created_by", "dataset_id"])

    if "dataset_async_jobs" not in tables:
        op.create_table(
            "dataset_async_jobs",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("dataset_id", sa.BINARY(16), nullable=False),
            sa.Column("created_by", sa.BINARY(16), nullable=True),
            sa.Column("job_type", sa.String(length=64), nullable=False, server_default="upload_summary"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("payload_json", mysql.JSON(), nullable=True),
            sa.Column("result_summary", mysql.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_dataset_async_jobs_dataset", "dataset_async_jobs", ["dataset_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "dataset_async_jobs" in tables:
        op.drop_index("idx_dataset_async_jobs_dataset", table_name="dataset_async_jobs")
        op.drop_table("dataset_async_jobs")
    if "dataset_samples" in tables:
        op.drop_index("idx_dataset_samples_owner", table_name="dataset_samples")
        op.drop_index("idx_dataset_samples_dataset", table_name="dataset_samples")
        op.drop_table("dataset_samples")
    if "datasets" in tables:
        op.drop_index("idx_datasets_org_owner", table_name="datasets")
        op.drop_table("datasets")
