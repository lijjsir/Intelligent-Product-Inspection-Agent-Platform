"""gpu infra and model config gpu fields

Revision ID: 0054
Revises: 0053
Create Date: 2026-05-22 20:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return index_name in {i["name"] for i in inspector.get_indexes(table_name)}


def upgrade():
    if not _has_table("gpu_compute_nodes"):
        op.create_table(
            "gpu_compute_nodes",
            sa.Column("id", mysql.BINARY(16), primary_key=True, nullable=False),
            sa.Column("org_id", mysql.BINARY(16), nullable=False),
            sa.Column("created_by", mysql.BINARY(16), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("host", sa.String(length=255), nullable=False),
            sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"),
            sa.Column("ssh_username", sa.String(length=128), nullable=False),
            sa.Column("ssh_password_enc", sa.Text(), nullable=True),
            sa.Column("ssh_private_key_enc", sa.Text(), nullable=True),
            sa.Column("total_gpu_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("available_gpu_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("gpu_bitmap", sa.String(length=255), nullable=False, server_default="0"),
            sa.Column("cpu_usage", sa.Float(), nullable=True),
            sa.Column("memory_usage", sa.Float(), nullable=True),
            sa.Column("gpu_usage", sa.Float(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="offline"),
            sa.Column("last_heartbeat", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("load_score", sa.Float(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        )
    if not _has_index("gpu_compute_nodes", "ix_gpu_compute_nodes_org_id"):
        op.create_index("ix_gpu_compute_nodes_org_id", "gpu_compute_nodes", ["org_id"], unique=False)
    if not _has_index("gpu_compute_nodes", "ix_gpu_compute_nodes_created_by"):
        op.create_index("ix_gpu_compute_nodes_created_by", "gpu_compute_nodes", ["created_by"], unique=False)

    if not _has_table("gpu_job_leases"):
        op.create_table(
            "gpu_job_leases",
            sa.Column("id", mysql.BINARY(16), primary_key=True, nullable=False),
            sa.Column("org_id", mysql.BINARY(16), nullable=False),
            sa.Column("resource_type", sa.String(length=64), nullable=False),
            sa.Column("resource_id", mysql.BINARY(16), nullable=False),
            sa.Column("node_id", mysql.BINARY(16), nullable=False),
            sa.Column("gpu_indices", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="leased"),
            sa.Column("leased_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("released_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        )
    if not _has_index("gpu_job_leases", "ix_gpu_job_leases_org_id"):
        op.create_index("ix_gpu_job_leases_org_id", "gpu_job_leases", ["org_id"], unique=False)
    if not _has_index("gpu_job_leases", "ix_gpu_job_leases_resource_id"):
        op.create_index("ix_gpu_job_leases_resource_id", "gpu_job_leases", ["resource_id"], unique=False)
    if not _has_index("gpu_job_leases", "ix_gpu_job_leases_node_id"):
        op.create_index("ix_gpu_job_leases_node_id", "gpu_job_leases", ["node_id"], unique=False)

    model_config_columns = {
        "training_command_template": sa.Text(),
        "fine_tune_command_template": sa.Text(),
        "offline_eval_command_template": sa.Text(),
        "runtime_env_json": sa.JSON(),
        "default_gpu_request": sa.Integer(),
        "default_cpu_request": sa.Integer(),
        "default_memory_gb": sa.Integer(),
    }
    for col_name, column_type in model_config_columns.items():
        if not _has_column("model_configs", col_name):
            op.add_column("model_configs", sa.Column(col_name, column_type, nullable=True))


def downgrade():
    op.drop_column("model_configs", "default_memory_gb")
    op.drop_column("model_configs", "default_cpu_request")
    op.drop_column("model_configs", "default_gpu_request")
    op.drop_column("model_configs", "runtime_env_json")
    op.drop_column("model_configs", "offline_eval_command_template")
    op.drop_column("model_configs", "fine_tune_command_template")
    op.drop_column("model_configs", "training_command_template")
    op.drop_index("ix_gpu_job_leases_node_id", table_name="gpu_job_leases")
    op.drop_index("ix_gpu_job_leases_resource_id", table_name="gpu_job_leases")
    op.drop_index("ix_gpu_job_leases_org_id", table_name="gpu_job_leases")
    op.drop_table("gpu_job_leases")
    op.drop_index("ix_gpu_compute_nodes_created_by", table_name="gpu_compute_nodes")
    op.drop_index("ix_gpu_compute_nodes_org_id", table_name="gpu_compute_nodes")
    op.drop_table("gpu_compute_nodes")
