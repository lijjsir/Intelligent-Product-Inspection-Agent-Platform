"""gpu infra and model config gpu fields

Revision ID: 0049
Revises: 0048
Create Date: 2026-05-22 20:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade():
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
    op.create_index("ix_gpu_compute_nodes_org_id", "gpu_compute_nodes", ["org_id"], unique=False)
    op.create_index("ix_gpu_compute_nodes_created_by", "gpu_compute_nodes", ["created_by"], unique=False)

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
    op.create_index("ix_gpu_job_leases_org_id", "gpu_job_leases", ["org_id"], unique=False)
    op.create_index("ix_gpu_job_leases_resource_id", "gpu_job_leases", ["resource_id"], unique=False)
    op.create_index("ix_gpu_job_leases_node_id", "gpu_job_leases", ["node_id"], unique=False)

    op.add_column("model_configs", sa.Column("training_command_template", sa.Text(), nullable=True))
    op.add_column("model_configs", sa.Column("fine_tune_command_template", sa.Text(), nullable=True))
    op.add_column("model_configs", sa.Column("offline_eval_command_template", sa.Text(), nullable=True))
    op.add_column("model_configs", sa.Column("runtime_env_json", sa.JSON(), nullable=True))
    op.add_column("model_configs", sa.Column("default_gpu_request", sa.Integer(), nullable=True))
    op.add_column("model_configs", sa.Column("default_cpu_request", sa.Integer(), nullable=True))
    op.add_column("model_configs", sa.Column("default_memory_gb", sa.Integer(), nullable=True))


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
