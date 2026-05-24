"""add feedback severity status and export jobs

Revision ID: 0068
Revises: 0067
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app.models.base import UUIDBinary

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _has_check_constraint(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND CONSTRAINT_NAME = :constraint_name
              AND CONSTRAINT_TYPE = 'CHECK'
            LIMIT 1
            """
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    )
    return result.scalar() is not None


def upgrade():
    feedback_columns = (
        ("severity", sa.Column("severity", sa.String(16), nullable=True, server_default=None)),
        ("status", sa.Column("status", sa.String(16), nullable=False, server_default="pending")),
        ("assigned_to", sa.Column("assigned_to", UUIDBinary, nullable=True)),
        ("resolution", sa.Column("resolution", sa.Text, nullable=True)),
        ("resolved_at", sa.Column("resolved_at", mysql.DATETIME(fsp=3), nullable=True)),
        ("source_type", sa.Column("source_type", sa.String(24), nullable=True, server_default="result")),
        ("task_id", sa.Column("task_id", UUIDBinary, nullable=True)),
    )
    for column_name, column in feedback_columns:
        if not _has_column("result_feedbacks", column_name):
            op.add_column("result_feedbacks", column)

    if not _has_check_constraint("result_feedbacks", "ck_result_feedbacks_status"):
        op.execute(
            "ALTER TABLE result_feedbacks ADD CONSTRAINT ck_result_feedbacks_status "
            "CHECK (status IN ('pending','processing','resolved','closed','reopened'))"
        )
    if not _has_check_constraint("result_feedbacks", "ck_result_feedbacks_severity"):
        op.execute(
            "ALTER TABLE result_feedbacks ADD CONSTRAINT ck_result_feedbacks_severity "
            "CHECK (severity IS NULL OR severity IN ('low','medium','high','critical'))"
        )
    if not _has_check_constraint("result_feedbacks", "ck_result_feedbacks_source_type"):
        op.execute(
            "ALTER TABLE result_feedbacks ADD CONSTRAINT ck_result_feedbacks_source_type "
            "CHECK (source_type IS NULL OR source_type IN ('result','chat','meeting'))"
        )

    if not _has_index("result_feedbacks", "ix_result_feedbacks_status"):
        op.create_index("ix_result_feedbacks_status", "result_feedbacks", ["status"])
    if not _has_index("result_feedbacks", "ix_result_feedbacks_severity"):
        op.create_index("ix_result_feedbacks_severity", "result_feedbacks", ["severity"])

    if not _has_table("export_jobs"):
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

    if not _has_check_constraint("export_jobs", "ck_export_jobs_status"):
        op.execute(
            "ALTER TABLE export_jobs ADD CONSTRAINT ck_export_jobs_status "
            "CHECK (status IN ('pending','running','success','failed','expired'))"
        )
    if not _has_check_constraint("export_jobs", "ck_export_jobs_report_type"):
        op.execute(
            "ALTER TABLE export_jobs ADD CONSTRAINT ck_export_jobs_report_type "
            "CHECK (report_type IN ('single_task','batch_summary','quality_analysis','feedback_report','evidence_trace'))"
        )
    if not _has_check_constraint("export_jobs", "ck_export_jobs_format"):
        op.execute(
            "ALTER TABLE export_jobs ADD CONSTRAINT ck_export_jobs_format "
            "CHECK (format IN ('pdf','docx','xlsx','csv','json'))"
        )


def downgrade():
    if _has_table("export_jobs"):
        if _has_check_constraint("export_jobs", "ck_export_jobs_format"):
            op.execute("ALTER TABLE export_jobs DROP CHECK ck_export_jobs_format")
        if _has_check_constraint("export_jobs", "ck_export_jobs_report_type"):
            op.execute("ALTER TABLE export_jobs DROP CHECK ck_export_jobs_report_type")
        if _has_check_constraint("export_jobs", "ck_export_jobs_status"):
            op.execute("ALTER TABLE export_jobs DROP CHECK ck_export_jobs_status")
        op.drop_table("export_jobs")

    if _has_index("result_feedbacks", "ix_result_feedbacks_severity"):
        op.drop_index("ix_result_feedbacks_severity", "result_feedbacks")
    if _has_index("result_feedbacks", "ix_result_feedbacks_status"):
        op.drop_index("ix_result_feedbacks_status", "result_feedbacks")
    if _has_check_constraint("result_feedbacks", "ck_result_feedbacks_source_type"):
        op.execute("ALTER TABLE result_feedbacks DROP CHECK ck_result_feedbacks_source_type")
    if _has_check_constraint("result_feedbacks", "ck_result_feedbacks_severity"):
        op.execute("ALTER TABLE result_feedbacks DROP CHECK ck_result_feedbacks_severity")
    if _has_check_constraint("result_feedbacks", "ck_result_feedbacks_status"):
        op.execute("ALTER TABLE result_feedbacks DROP CHECK ck_result_feedbacks_status")

    for column_name in ("task_id", "source_type", "resolved_at", "resolution", "assigned_to", "status", "severity"):
        if _has_column("result_feedbacks", column_name):
            op.drop_column("result_feedbacks", column_name)
