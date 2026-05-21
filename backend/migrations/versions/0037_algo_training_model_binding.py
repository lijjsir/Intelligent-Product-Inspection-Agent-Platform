"""bind training and fine-tune resources to model configs

Revision ID: 0037_algo_training_model_binding
Revises: 0036_algorithm_engineer_workspace_phase2
Create Date: 2026-05-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0037_algo_training_model_binding"
down_revision = "0036_algorithm_engineer_workspace_phase2"
branch_labels = None
depends_on = None


def _table_columns(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    training_columns = _table_columns(inspector, "training_jobs")
    if "model_config_id" not in training_columns:
        op.add_column("training_jobs", sa.Column("model_config_id", sa.BINARY(16), nullable=True))
        op.create_index("idx_training_jobs_model_config", "training_jobs", ["model_config_id", "created_at"])

    fine_tune_columns = _table_columns(inspector, "fine_tune_runs")
    if "model_config_id" not in fine_tune_columns:
        op.add_column("fine_tune_runs", sa.Column("model_config_id", sa.BINARY(16), nullable=True))
        op.create_index("idx_fine_tune_runs_model_config", "fine_tune_runs", ["model_config_id", "created_at"])

    op.execute(
        """
        UPDATE fine_tune_runs ft
        JOIN model_configs mc
          ON (mc.model_key = ft.base_model OR mc.display_name = ft.base_model)
         AND (mc.org_id <=> ft.org_id OR mc.org_id IS NULL)
        SET ft.model_config_id = mc.id
        WHERE ft.deleted_at IS NULL
          AND ft.model_config_id IS NULL
          AND ft.base_model IS NOT NULL
          AND ft.base_model <> ''
        """
    )

    unresolved = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM fine_tune_runs
            WHERE deleted_at IS NULL
              AND (model_config_id IS NULL)
            """
        )
    ).scalar_one()
    if int(unresolved or 0) > 0:
        raise RuntimeError("fine_tune_runs contains rows that cannot be mapped to model_configs")

    unresolved_training = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM training_jobs
            WHERE deleted_at IS NULL
              AND model_config_id IS NULL
            """
        )
    ).scalar_one()
    if int(unresolved_training or 0) > 0:
        raise RuntimeError("training_jobs contains rows missing model_config_id; populate them before migration")

    op.alter_column("training_jobs", "model_config_id", existing_type=sa.BINARY(16), nullable=False)
    op.alter_column("fine_tune_runs", "model_config_id", existing_type=sa.BINARY(16), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    training_columns = _table_columns(inspector, "training_jobs")
    if "model_config_id" in training_columns:
        op.drop_index("idx_training_jobs_model_config", table_name="training_jobs")
        op.drop_column("training_jobs", "model_config_id")

    fine_tune_columns = _table_columns(inspector, "fine_tune_runs")
    if "model_config_id" in fine_tune_columns:
        op.drop_index("idx_fine_tune_runs_model_config", table_name="fine_tune_runs")
        op.drop_column("fine_tune_runs", "model_config_id")
