"""Scoped materials and reviewed knowledge; existing memory data is retained."""
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BINARY
from alembic import op

revision="0112_knowledge_admission"
down_revision="0111_standard_admission"
branch_labels=depends_on=None


def upgrade():
    uid=BINARY(16)
    op.create_table("rag_space_grants",sa.Column("id",uid,primary_key=True),sa.Column("org_id",uid,nullable=False),
        sa.Column("space_id",uid,sa.ForeignKey("rag_spaces.id"),nullable=False),sa.Column("user_id",uid,nullable=False),
        sa.Column("granted_by",uid,nullable=False),sa.Column("status",sa.String(32),nullable=False),
        sa.Column("row_version",sa.Integer,nullable=False),sa.Column("reason",sa.Text,nullable=False),
        sa.Column("allow_knowledge_submission",sa.Boolean,nullable=False,server_default=sa.false()),
        sa.Column("created_at",sa.DateTime,nullable=False),sa.Column("revoked_at",sa.DateTime),
        sa.UniqueConstraint("org_id","space_id","user_id"))
    op.create_table("knowledge_admissions",sa.Column("id",uid,primary_key=True),sa.Column("org_id",uid,nullable=False),
        sa.Column("memory_id",sa.String(64),nullable=False,unique=True),sa.Column("created_by",uid,nullable=False),
        sa.Column("request_key",sa.String(128),nullable=False),sa.Column("payload_hash",sa.String(64),nullable=False),
        sa.Column("snapshot",sa.JSON,nullable=False),sa.Column("source_refs",sa.JSON,nullable=False),
        *[sa.Column(n,sa.String(32),nullable=False) for n in ["review_status","sharing_status","publication_status"]],
        sa.Column("row_version",sa.Integer,nullable=False),*[sa.Column(n,uid) for n in ["reviewed_by","share_approved_by","published_by"]],
        sa.Column("created_at",sa.DateTime,nullable=False),sa.Column("reviewed_at",sa.DateTime),sa.Column("published_at",sa.DateTime),
        sa.UniqueConstraint("org_id","created_by","request_key"))
    op.create_table("knowledge_admission_actions",sa.Column("id",uid,primary_key=True),sa.Column("org_id",uid,nullable=False),
        sa.Column("admission_id",uid,sa.ForeignKey("knowledge_admissions.id"),nullable=False),sa.Column("actor_id",uid,nullable=False),
        sa.Column("action",sa.String(32),nullable=False),sa.Column("request_key",sa.String(128),nullable=False),
        sa.Column("payload_hash",sa.String(64),nullable=False),sa.Column("reason",sa.Text,nullable=False),
        sa.Column("details",sa.JSON,nullable=False),sa.Column("created_at",sa.DateTime,nullable=False),sa.UniqueConstraint("org_id","request_key"))
    for table,cols in {"rag_space_grants":["org_id","space_id","user_id"],"knowledge_admissions":["org_id","created_by"],
        "knowledge_admission_actions":["org_id","admission_id"]}.items():
        for col in cols:op.create_index(f"ix_{table}_{col}",table,[col])


def downgrade():
    count=op.get_bind().execute(sa.text("SELECT COUNT(*) FROM knowledge_admissions")).scalar_one()
    if count:raise RuntimeError("Preserve knowledge admission records; use application rollback instead of dropping history")
    op.drop_table("knowledge_admission_actions");op.drop_table("knowledge_admissions");op.drop_table("rag_space_grants")
