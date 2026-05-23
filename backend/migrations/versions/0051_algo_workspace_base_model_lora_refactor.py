"""refactor algo workspace to base-model lora flow

Revision ID: 0051_algo_workspace_base_model_lora_refactor
Revises: 0050
Create Date: 2026-05-23 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = "0051_algo_workspace_base_model_lora_refactor"
down_revision = "0050"
branch_labels = None
depends_on = None


def _uuid_bin_to_str_expr(column_sql: str) -> str:
    return (
        f"LOWER(CONCAT("
        f"SUBSTR(HEX({column_sql}), 1, 8), '-', "
        f"SUBSTR(HEX({column_sql}), 9, 4), '-', "
        f"SUBSTR(HEX({column_sql}), 13, 4), '-', "
        f"SUBSTR(HEX({column_sql}), 17, 4), '-', "
        f"SUBSTR(HEX({column_sql}), 21, 12)"
        f"))"
    )


def upgrade() -> None:
    bind = op.get_bind()
    
    def inspector():
        return sa.inspect(bind)

    def table_columns(table_name: str) -> dict[str, dict]:
        return {column["name"]: column for column in inspector().get_columns(table_name)}

    def has_column(table_name: str, column_name: str) -> bool:
        return column_name in table_columns(table_name)

    def has_index(table_name: str, index_name: str) -> bool:
        return index_name in {index["name"] for index in inspector().get_indexes(table_name)}

    model_config_columns = table_columns("model_configs")
    if "source_type" not in model_config_columns:
        op.add_column("model_configs", sa.Column("source_type", sa.String(length=32), nullable=False, server_default="external"))
    if "source_uri" not in model_config_columns:
        op.add_column("model_configs", sa.Column("source_uri", sa.String(length=512), nullable=True))
    op.execute("UPDATE model_configs SET source_uri = model_key WHERE source_uri IS NULL")
    op.alter_column("model_configs", "source_uri", existing_type=sa.String(length=512), nullable=False)

    fine_tune_columns = table_columns("fine_tune_runs")
    source_dataset_col = fine_tune_columns.get("source_dataset_id")
    eval_set_col = fine_tune_columns.get("eval_set_id")
    source_dataset_is_string = source_dataset_col is not None and "char" in str(source_dataset_col["type"]).lower()
    eval_set_is_string = eval_set_col is not None and "char" in str(eval_set_col["type"]).lower()

    if source_dataset_col is None:
        op.add_column("fine_tune_runs", sa.Column("source_dataset_id", sa.BINARY(length=16), nullable=True))
    if eval_set_col is None:
        op.add_column("fine_tune_runs", sa.Column("eval_set_id", sa.BINARY(length=16), nullable=True))
    fine_tune_columns = table_columns("fine_tune_runs")
    source_dataset_col = fine_tune_columns.get("source_dataset_id")
    eval_set_col = fine_tune_columns.get("eval_set_id")
    source_dataset_is_string = source_dataset_col is not None and "char" in str(source_dataset_col["type"]).lower()
    eval_set_is_string = eval_set_col is not None and "char" in str(eval_set_col["type"]).lower()

    if has_column("fine_tune_runs", "training_job_id") and source_dataset_is_string:
        op.execute(
            f"""
            UPDATE fine_tune_runs ft
            JOIN training_jobs tj
              ON tj.id = ft.training_job_id
            SET
              ft.source_dataset_id = COALESCE(ft.source_dataset_id, {_uuid_bin_to_str_expr('tj.source_dataset_id')}),
              ft.eval_set_id = COALESCE(
                ft.eval_set_id,
                CASE
                  WHEN tj.eval_set_id IS NULL THEN NULL
                  ELSE {_uuid_bin_to_str_expr('tj.eval_set_id')}
                END
              )
            WHERE ft.training_job_id IS NOT NULL
            """
        )
        if not has_column("fine_tune_runs", "source_dataset_id_bin"):
            op.add_column("fine_tune_runs", sa.Column("source_dataset_id_bin", sa.BINARY(length=16), nullable=True))
        if not has_column("fine_tune_runs", "eval_set_id_bin"):
            op.add_column("fine_tune_runs", sa.Column("eval_set_id_bin", sa.BINARY(length=16), nullable=True))
        op.execute(
            """
            UPDATE fine_tune_runs
            SET
              source_dataset_id_bin = COALESCE(source_dataset_id_bin, UNHEX(REPLACE(source_dataset_id, '-', ''))),
              eval_set_id_bin = COALESCE(
                eval_set_id_bin,
                CASE
                  WHEN eval_set_id IS NULL OR eval_set_id = '' THEN NULL
                  ELSE UNHEX(REPLACE(eval_set_id, '-', ''))
                END
              )
            WHERE source_dataset_id IS NOT NULL
            """
        )
        if has_index("fine_tune_runs", "ix_fine_tune_runs_source_dataset_id"):
            op.drop_index("ix_fine_tune_runs_source_dataset_id", table_name="fine_tune_runs")
        op.drop_column("fine_tune_runs", "source_dataset_id")
        op.drop_column("fine_tune_runs", "eval_set_id")
        op.alter_column("fine_tune_runs", "source_dataset_id_bin", new_column_name="source_dataset_id", existing_type=mysql.BINARY(length=16), nullable=True)
        op.alter_column("fine_tune_runs", "eval_set_id_bin", new_column_name="eval_set_id", existing_type=mysql.BINARY(length=16), nullable=True)
    elif has_column("fine_tune_runs", "training_job_id"):
        op.execute(
            """
            UPDATE fine_tune_runs ft
            JOIN training_jobs tj
              ON tj.id = ft.training_job_id
            SET
              ft.source_dataset_id = COALESCE(ft.source_dataset_id, tj.source_dataset_id),
              ft.eval_set_id = COALESCE(ft.eval_set_id, tj.eval_set_id)
            WHERE ft.training_job_id IS NOT NULL
            """
        )
    if not has_index("fine_tune_runs", "ix_fine_tune_runs_source_dataset_id"):
        op.create_index("ix_fine_tune_runs_source_dataset_id", "fine_tune_runs", ["source_dataset_id"], unique=False)
    op.alter_column("fine_tune_runs", "source_dataset_id", existing_type=mysql.BINARY(length=16), nullable=False)

    op.alter_column("offline_evaluations", "target_type", existing_type=sa.String(length=64), server_default="fine_tune")

    deployment_columns = table_columns("model_deployments")
    if "merge_mode" not in deployment_columns:
        op.add_column("model_deployments", sa.Column("merge_mode", sa.String(length=32), nullable=False, server_default="dynamic"))

    if has_index("fine_tune_runs", "ix_fine_tune_runs_training_job_id"):
        op.drop_index("ix_fine_tune_runs_training_job_id", table_name="fine_tune_runs")
    if has_column("fine_tune_runs", "training_job_id"):
        op.drop_column("fine_tune_runs", "training_job_id")
    if "training_jobs" in inspector().get_table_names():
        op.drop_table("training_jobs")


def downgrade() -> None:
    op.create_table(
        "training_jobs",
        sa.Column("source_dataset_id", sa.BINARY(length=16), nullable=False),
        sa.Column("model_config_id", sa.BINARY(length=16), nullable=False),
        sa.Column("eval_set_id", sa.BINARY(length=16), nullable=True),
        sa.Column("experiment_id", sa.BINARY(length=16), nullable=True),
        sa.Column("execution_mode", sa.String(length=32), nullable=True),
        sa.Column("executor_job_id", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.BINARY(length=16), nullable=False),
        sa.Column("org_id", sa.BINARY(length=16), nullable=False),
        sa.Column("created_by", sa.BINARY(length=16), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_jobs_source_dataset_id", "training_jobs", ["source_dataset_id"], unique=False)
    op.create_index("ix_training_jobs_model_config_id", "training_jobs", ["model_config_id"], unique=False)

    op.add_column("fine_tune_runs", sa.Column("training_job_id", sa.BINARY(length=16), nullable=True))
    op.create_index("ix_fine_tune_runs_training_job_id", "fine_tune_runs", ["training_job_id"], unique=False)
    op.drop_index("ix_fine_tune_runs_source_dataset_id", table_name="fine_tune_runs")
    op.drop_column("fine_tune_runs", "eval_set_id")
    op.drop_column("fine_tune_runs", "source_dataset_id")

    op.drop_column("model_deployments", "merge_mode")
    op.alter_column("offline_evaluations", "target_type", existing_type=sa.String(length=64), server_default="training_job")

    op.drop_column("model_configs", "source_uri")
    op.drop_column("model_configs", "source_type")
