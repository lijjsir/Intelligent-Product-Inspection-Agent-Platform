"""backfill dataset import MVP columns and upload session table

Revision ID: 0038_dataset_import_mvp_backfill
Revises: 0037_algo_training_model_binding
Create Date: 2026-05-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0038_dataset_import_mvp_backfill"
down_revision = "0037_algo_training_model_binding"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _columns(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = _table_names(inspector)

    if "dataset_upload_sessions" not in tables:
        op.create_table(
            "dataset_upload_sessions",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("dataset_id", sa.BINARY(16), nullable=False),
            sa.Column("created_by", sa.BINARY(16), nullable=True),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=True),
            sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("bucket", sa.String(length=120), nullable=True),
            sa.Column("object_key", sa.Text(), nullable=True),
            sa.Column("uploaded_parts_json", mysql.JSON(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("expires_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("completed_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_dataset_upload_sessions_dataset",
            "dataset_upload_sessions",
            ["dataset_id", "created_at"],
        )
        op.create_index(
            "idx_dataset_upload_sessions_owner",
            "dataset_upload_sessions",
            ["org_id", "created_by", "dataset_id"],
        )

    dataset_sample_columns = _columns(inspector, "dataset_samples")
    dataset_sample_indexes = _indexes(inspector, "dataset_samples")
    if "is_augmented" not in dataset_sample_columns:
        op.add_column("dataset_samples", sa.Column("is_augmented", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "augmentation_source_id" not in dataset_sample_columns:
        op.add_column("dataset_samples", sa.Column("augmentation_source_id", sa.BINARY(16), nullable=True))
    if "augmentation_method" not in dataset_sample_columns:
        op.add_column("dataset_samples", sa.Column("augmentation_method", sa.String(length=64), nullable=True))
    if "augmentation_params" not in dataset_sample_columns:
        op.add_column("dataset_samples", sa.Column("augmentation_params", mysql.JSON(), nullable=True))
    if "idx_dataset_samples_augmented" not in dataset_sample_indexes:
        op.create_index("idx_dataset_samples_augmented", "dataset_samples", ["dataset_id", "is_augmented", "created_at"])

    alignment_pair_columns = _columns(inspector, "dataset_alignment_pairs")
    if "confirmation_status" not in alignment_pair_columns:
        op.add_column(
            "dataset_alignment_pairs",
            sa.Column("confirmation_status", sa.String(length=32), nullable=False, server_default="suggested"),
        )

    augmentation_batch_columns = _columns(inspector, "dataset_augmentation_batches")
    if "history_json" not in augmentation_batch_columns:
        op.add_column("dataset_augmentation_batches", sa.Column("history_json", mysql.JSON(), nullable=True))

    augmentation_proposal_columns = _columns(inspector, "dataset_augmentation_proposals")
    if "source_sample_id" not in augmentation_proposal_columns:
        op.add_column("dataset_augmentation_proposals", sa.Column("source_sample_id", sa.BINARY(16), nullable=True))
    if "augmentation_method" not in augmentation_proposal_columns:
        op.add_column("dataset_augmentation_proposals", sa.Column("augmentation_method", sa.String(length=64), nullable=True))
    if "augmentation_params" not in augmentation_proposal_columns:
        op.add_column("dataset_augmentation_proposals", sa.Column("augmentation_params", mysql.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = _table_names(inspector)

    if "dataset_augmentation_proposals" in tables:
        columns = _columns(inspector, "dataset_augmentation_proposals")
        if "augmentation_params" in columns:
            op.drop_column("dataset_augmentation_proposals", "augmentation_params")
        if "augmentation_method" in columns:
            op.drop_column("dataset_augmentation_proposals", "augmentation_method")
        if "source_sample_id" in columns:
            op.drop_column("dataset_augmentation_proposals", "source_sample_id")

    if "dataset_augmentation_batches" in tables:
        columns = _columns(inspector, "dataset_augmentation_batches")
        if "history_json" in columns:
            op.drop_column("dataset_augmentation_batches", "history_json")

    if "dataset_alignment_pairs" in tables:
        columns = _columns(inspector, "dataset_alignment_pairs")
        if "confirmation_status" in columns:
            op.drop_column("dataset_alignment_pairs", "confirmation_status")

    if "dataset_samples" in tables:
        indexes = _indexes(inspector, "dataset_samples")
        columns = _columns(inspector, "dataset_samples")
        if "idx_dataset_samples_augmented" in indexes:
            op.drop_index("idx_dataset_samples_augmented", table_name="dataset_samples")
        if "augmentation_params" in columns:
            op.drop_column("dataset_samples", "augmentation_params")
        if "augmentation_method" in columns:
            op.drop_column("dataset_samples", "augmentation_method")
        if "augmentation_source_id" in columns:
            op.drop_column("dataset_samples", "augmentation_source_id")
        if "is_augmented" in columns:
            op.drop_column("dataset_samples", "is_augmented")

    if "dataset_upload_sessions" in tables:
        indexes = _indexes(inspector, "dataset_upload_sessions")
        if "idx_dataset_upload_sessions_owner" in indexes:
            op.drop_index("idx_dataset_upload_sessions_owner", table_name="dataset_upload_sessions")
        if "idx_dataset_upload_sessions_dataset" in indexes:
            op.drop_index("idx_dataset_upload_sessions_dataset", table_name="dataset_upload_sessions")
        op.drop_table("dataset_upload_sessions")
