"""add feedback severity status and export jobs

Revision ID: 0065
Revises: 0064
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app.models.base import UUIDBinary

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("result_feedbacks", sa.Column("severity", sa.String(16), nullable=True, server_default=None))
    op.add_column("result_feedbacks", sa.Column("status", sa.String(16), nullable=False, server_default="pending"))
    op.add_column("result_feedbacks", sa.Column("assigned_to", UUIDBinary, nullable=True))
    op.add_column("result_feedbacks", sa.Column("resolution", sa.Text, nullable=True))
    op.add_column("result_feedbacks", sa.Column("resolved_at", mysql.DATETIME(fsp=3), nullable=True))
    op.add_column("result_feedbacks", sa.Column("source_type", sa.String(24), nullable=True, server_default="result"))
    op.add_column("result_feedbacks", sa.Column("task_id", UUIDBinary, nullable=True))

    op.execute(
        "ALTER TABLE result_feedbacks ADD CONSTRAINT ck_result_feedbacks_status "
        "CHECK (status IN ('pending','processing','resolved','closed','reopened'))"
    )
    op.execute(
        "ALTER TABLE result_feedbacks ADD CONSTRAINT ck_result_feedbacks_severity "
        "CHECK (severity IS NULL OR severity IN ('low','medium','high','critical'))"
    )
    op.execute(
        "ALTER TABLE result_feedbacks ADD CONSTRAINT ck_result_feedbacks_source_type "
        "CHECK (source_type IS NULL OR source_type IN ('result','chat','meeting'))"
    )

    op.create_index("ix_result_feedbacks_status", "result_feedbacks", ["status"])
    op.create_index("ix_result_feedbacks_severity", "result_feedbacks", ["severity"])

    op.create_table(
        "export_jobs",
        sa.Column("id", UUIDBinary, primary_key=True),
        sa.Column("org_id", UUIDBinary, nullable=False, index=True),
        sa.Column("actor_id", UUIDBinary, nullable=False, index=True),
        sa.Column("report_name", sa.String(256), nullable=False),
        sa.Column("report_type", sa.String(32), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("template", sa.String(32), nullable=True, server_default="standard"),
        sa.Column("config_json", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("file_url", sa.String(512), nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("expires_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
    )
    op.execute(
        "ALTER TABLE export_jobs ADD CONSTRAINT ck_export_jobs_status "
        "CHECK (status IN ('pending','running','success','failed','expired'))"
    )
    op.execute(
        "ALTER TABLE export_jobs ADD CONSTRAINT ck_export_jobs_report_type "
        "CHECK (report_type IN ('single_task','batch_summary','quality_analysis','feedback_report','evidence_trace'))"
    )
    op.execute(
        "ALTER TABLE export_jobs ADD CONSTRAINT ck_export_jobs_format "
        "CHECK (format IN ('pdf','docx','xlsx','csv','json'))"
    )


def downgrade():
    op.drop_table("export_jobs")
    op.drop_index("ix_result_feedbacks_severity", "result_feedbacks")
    op.drop_index("ix_result_feedbacks_status", "result_feedbacks")
    op.execute("ALTER TABLE result_feedbacks DROP CHECK ck_result_feedbacks_source_type")
    op.execute("ALTER TABLE result_feedbacks DROP CHECK ck_result_feedbacks_severity")
    op.execute("ALTER TABLE result_feedbacks DROP CHECK ck_result_feedbacks_status")
    op.drop_column("result_feedbacks", "task_id")
    op.drop_column("result_feedbacks", "source_type")
    op.drop_column("result_feedbacks", "resolved_at")
    op.drop_column("result_feedbacks", "resolution")
    op.drop_column("result_feedbacks", "assigned_to")
    op.drop_column("result_feedbacks", "status")
    op.drop_column("result_feedbacks", "severity")
