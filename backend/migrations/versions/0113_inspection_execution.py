"""Frozen published requirements, policy releases and reviewed item evaluation."""
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BINARY
from alembic import op
revision="0113_inspection_execution"
down_revision="0112_knowledge_admission"
branch_labels=depends_on=None


def upgrade():
    uid=BINARY(16)
    op.create_table("inspection_policy_publications",sa.Column("id",uid,primary_key=True),sa.Column("org_id",uid,nullable=False),
        sa.Column("spec_id",uid,nullable=False),sa.Column("request_key",sa.String(128),nullable=False),sa.Column("payload_hash",sa.String(64),nullable=False),
        sa.Column("snapshot",sa.JSON,nullable=False),sa.Column("status",sa.String(32),nullable=False),sa.Column("published_by",uid,nullable=False),
        sa.Column("created_at",sa.DateTime,nullable=False),sa.UniqueConstraint("org_id","request_key"))
    op.create_table("inspection_execution_runs",sa.Column("id",uid,primary_key=True),sa.Column("org_id",uid,nullable=False),
        sa.Column("task_id",uid,sa.ForeignKey("inspection_tasks.id"),nullable=False),sa.Column("session_id",uid),
        sa.Column("request_key",sa.String(128),nullable=False),sa.Column("payload_hash",sa.String(64),nullable=False),
        sa.Column("snapshot",sa.JSON,nullable=False),sa.Column("evaluation",sa.JSON,nullable=False),sa.Column("status",sa.String(32),nullable=False),
        sa.Column("row_version",sa.Integer,nullable=False),sa.Column("created_by",uid,nullable=False),sa.Column("reviewed_by",uid),
        sa.Column("created_at",sa.DateTime,nullable=False),sa.Column("reviewed_at",sa.DateTime),sa.UniqueConstraint("org_id","request_key"))
    op.create_table("inspection_execution_actions",sa.Column("id",uid,primary_key=True),sa.Column("org_id",uid,nullable=False),
        sa.Column("run_id",uid,sa.ForeignKey("inspection_execution_runs.id"),nullable=False),sa.Column("actor_id",uid,nullable=False),
        sa.Column("request_key",sa.String(128),nullable=False),sa.Column("payload_hash",sa.String(64),nullable=False),sa.Column("action",sa.String(32),nullable=False),
        sa.Column("reason",sa.Text,nullable=False),sa.Column("created_at",sa.DateTime,nullable=False),sa.UniqueConstraint("org_id","request_key"))
    for table,columns in {"inspection_policy_publications":["org_id","spec_id"],"inspection_execution_runs":["org_id","task_id","session_id"],"inspection_execution_actions":["org_id","run_id"]}.items():
        for column in columns:op.create_index(f"ix_{table}_{column}",table,[column])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM inspection_execution_runs")).scalar_one():
        raise RuntimeError("Preserve executed snapshots; roll back routing instead of deleting history")
    op.drop_table("inspection_execution_actions");op.drop_table("inspection_execution_runs");op.drop_table("inspection_policy_publications")
