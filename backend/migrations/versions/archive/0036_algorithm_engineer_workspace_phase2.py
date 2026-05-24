"""add algorithm engineer workspace phase2 tables

Revision ID: 0036_algorithm_engineer_workspace_phase2
Revises: 0035_dataset_import_phase1
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0036_algorithm_engineer_workspace_phase2"
down_revision = "0035_dataset_import_phase1"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def _resource_columns(*, include_execution: bool = False):
    columns = [
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("created_by", sa.BINARY(16), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("config_json", mysql.JSON(), nullable=True),
        sa.Column("result_summary", mysql.JSON(), nullable=True),
    ]
    if include_execution:
        columns.extend(
            [
                sa.Column("execution_mode", sa.String(length=32), nullable=True),
                sa.Column("executor_job_id", sa.String(length=128), nullable=True),
                sa.Column("started_at", mysql.DATETIME(fsp=3), nullable=True),
                sa.Column("completed_at", mysql.DATETIME(fsp=3), nullable=True),
            ]
        )
    columns.extend(
        [
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        ]
    )
    return columns


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "dataset_knowledge_graphs" not in tables:
        op.create_table(
            "dataset_knowledge_graphs",
            *_resource_columns(),
            sa.Column("dataset_id", sa.BINARY(16), nullable=False),
        )
        op.create_index("idx_dataset_knowledge_graphs_dataset", "dataset_knowledge_graphs", ["dataset_id", "created_at"])

    if "dataset_kg_entities" not in tables:
        op.create_table(
            "dataset_kg_entities",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("dataset_id", sa.BINARY(16), nullable=False),
            sa.Column("knowledge_graph_id", sa.BINARY(16), nullable=False),
            sa.Column("created_by", sa.BINARY(16), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False, server_default="Entity"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("properties_json", mysql.JSON(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_dataset_kg_entities_graph", "dataset_kg_entities", ["knowledge_graph_id", "created_at"])

    if "dataset_kg_relations" not in tables:
        op.create_table(
            "dataset_kg_relations",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("dataset_id", sa.BINARY(16), nullable=False),
            sa.Column("knowledge_graph_id", sa.BINARY(16), nullable=False),
            sa.Column("created_by", sa.BINARY(16), nullable=True),
            sa.Column("source_entity_id", sa.BINARY(16), nullable=False),
            sa.Column("target_entity_id", sa.BINARY(16), nullable=False),
            sa.Column("relation_type", sa.String(length=64), nullable=False, server_default="RELATED_TO"),
            sa.Column("properties_json", mysql.JSON(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_dataset_kg_relations_graph", "dataset_kg_relations", ["knowledge_graph_id", "created_at"])

    if "dataset_alignments" not in tables:
        op.create_table(
            "dataset_alignments",
            *_resource_columns(),
            sa.Column("dataset_id", sa.BINARY(16), nullable=False),
        )
        op.create_index("idx_dataset_alignments_dataset", "dataset_alignments", ["dataset_id", "created_at"])

    if "dataset_alignment_pairs" not in tables:
        op.create_table(
            "dataset_alignment_pairs",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("dataset_id", sa.BINARY(16), nullable=False),
            sa.Column("alignment_id", sa.BINARY(16), nullable=False),
            sa.Column("created_by", sa.BINARY(16), nullable=True),
            sa.Column("source_sample_id", sa.BINARY(16), nullable=True),
            sa.Column("target_sample_id", sa.BINARY(16), nullable=True),
            sa.Column("relation_type", sa.String(length=64), nullable=False, server_default="describes"),
            sa.Column("similarity_score", sa.Float(), nullable=True),
            sa.Column("payload_json", mysql.JSON(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_dataset_alignment_pairs_alignment", "dataset_alignment_pairs", ["alignment_id", "created_at"])

    if "dataset_augmentation_batches" not in tables:
        op.create_table(
            "dataset_augmentation_batches",
            *_resource_columns(),
            sa.Column("dataset_id", sa.BINARY(16), nullable=False),
        )
        op.create_index("idx_dataset_augmentation_batches_dataset", "dataset_augmentation_batches", ["dataset_id", "created_at"])

    if "dataset_augmentation_proposals" not in tables:
        op.create_table(
            "dataset_augmentation_proposals",
            *_resource_columns(),
            sa.Column("dataset_id", sa.BINARY(16), nullable=False),
            sa.Column("batch_id", sa.BINARY(16), nullable=False),
        )
        op.create_index("idx_dataset_augmentation_proposals_batch", "dataset_augmentation_proposals", ["batch_id", "created_at"])

    if "dataset_exports" not in tables:
        op.create_table(
            "dataset_exports",
            *_resource_columns(),
            sa.Column("dataset_id", sa.BINARY(16), nullable=False),
        )
        op.create_index("idx_dataset_exports_dataset", "dataset_exports", ["dataset_id", "created_at"])

    if "evaluation_datasets" not in tables:
        op.create_table(
            "evaluation_datasets",
            *_resource_columns(),
            sa.Column("source_dataset_id", sa.BINARY(16), nullable=False),
        )
        op.create_index("idx_evaluation_datasets_source", "evaluation_datasets", ["source_dataset_id", "created_at"])

    if "evaluation_dataset_items" not in tables:
        op.create_table(
            "evaluation_dataset_items",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("evaluation_dataset_id", sa.BINARY(16), nullable=False),
            sa.Column("source_dataset_id", sa.BINARY(16), nullable=False),
            sa.Column("dataset_sample_id", sa.BINARY(16), nullable=True),
            sa.Column("created_by", sa.BINARY(16), nullable=True),
            sa.Column("item_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("payload_json", mysql.JSON(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_evaluation_dataset_items_set", "evaluation_dataset_items", ["evaluation_dataset_id", "item_order"])

    if "training_jobs" not in tables:
        op.create_table(
            "training_jobs",
            *_resource_columns(include_execution=True),
            sa.Column("source_dataset_id", sa.BINARY(16), nullable=False),
            sa.Column("eval_set_id", sa.BINARY(16), nullable=True),
            sa.Column("experiment_id", sa.BINARY(16), nullable=True),
        )
        op.create_index("idx_training_jobs_source", "training_jobs", ["source_dataset_id", "created_at"])

    if "fine_tune_runs" not in tables:
        op.create_table(
            "fine_tune_runs",
            *_resource_columns(include_execution=True),
            sa.Column("training_job_id", sa.BINARY(16), nullable=False),
            sa.Column("base_model", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("experiment_id", sa.BINARY(16), nullable=True),
        )
        op.create_index("idx_fine_tune_runs_training_job", "fine_tune_runs", ["training_job_id", "created_at"])

    if "offline_evaluations" not in tables:
        op.create_table(
            "offline_evaluations",
            *_resource_columns(include_execution=True),
            sa.Column("eval_set_id", sa.BINARY(16), nullable=False),
            sa.Column("target_type", sa.String(length=64), nullable=False, server_default="training_job"),
            sa.Column("target_id", sa.BINARY(16), nullable=False),
            sa.Column("experiment_id", sa.BINARY(16), nullable=True),
        )
        op.create_index("idx_offline_evaluations_eval_set", "offline_evaluations", ["eval_set_id", "created_at"])

    if "online_validations" not in tables:
        op.create_table(
            "online_validations",
            *_resource_columns(include_execution=True),
            sa.Column("deployment_id", sa.BINARY(16), nullable=False),
            sa.Column("experiment_id", sa.BINARY(16), nullable=True),
        )
        op.create_index("idx_online_validations_deployment", "online_validations", ["deployment_id", "created_at"])

    if "experiments" not in tables:
        op.create_table("experiments", *_resource_columns())
        op.create_index("idx_experiments_owner", "experiments", ["org_id", "created_by", "created_at"])

    if "model_deployments" not in tables:
        op.create_table(
            "model_deployments",
            *_resource_columns(include_execution=True),
            sa.Column("source_type", sa.String(length=64), nullable=False, server_default="fine_tune"),
            sa.Column("source_id", sa.BINARY(16), nullable=False),
            sa.Column("experiment_id", sa.BINARY(16), nullable=True),
        )
        op.create_index("idx_model_deployments_source", "model_deployments", ["source_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    drop_steps = [
        ("model_deployments", ["idx_model_deployments_source"]),
        ("experiments", ["idx_experiments_owner"]),
        ("online_validations", ["idx_online_validations_deployment"]),
        ("offline_evaluations", ["idx_offline_evaluations_eval_set"]),
        ("fine_tune_runs", ["idx_fine_tune_runs_training_job"]),
        ("training_jobs", ["idx_training_jobs_source"]),
        ("evaluation_dataset_items", ["idx_evaluation_dataset_items_set"]),
        ("evaluation_datasets", ["idx_evaluation_datasets_source"]),
        ("dataset_exports", ["idx_dataset_exports_dataset"]),
        ("dataset_augmentation_proposals", ["idx_dataset_augmentation_proposals_batch"]),
        ("dataset_augmentation_batches", ["idx_dataset_augmentation_batches_dataset"]),
        ("dataset_alignment_pairs", ["idx_dataset_alignment_pairs_alignment"]),
        ("dataset_alignments", ["idx_dataset_alignments_dataset"]),
        ("dataset_kg_relations", ["idx_dataset_kg_relations_graph"]),
        ("dataset_kg_entities", ["idx_dataset_kg_entities_graph"]),
        ("dataset_knowledge_graphs", ["idx_dataset_knowledge_graphs_dataset"]),
    ]
    for table, indexes in drop_steps:
        if table in tables:
            for index in indexes:
                op.drop_index(index, table_name=table)
            op.drop_table(table)
