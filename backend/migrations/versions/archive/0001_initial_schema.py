"""initial schema

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-03-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("plan", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("settings", mysql.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        ),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "users",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("org_id", mysql.BINARY(16), nullable=False, index=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="inspector"),
        sa.Column("mfa_secret", sa.String(64), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("sso_provider", sa.String(32), nullable=True),
        sa.Column("sso_subject", sa.String(256), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        ),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("org_id", "username", name="uk_org_username"),
        sa.UniqueConstraint("org_id", "email", name="uk_org_email"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "inspection_tasks",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("org_id", mysql.BINARY(16), nullable=False, index=True),
        sa.Column("created_by", mysql.BINARY(16), nullable=False),
        sa.Column("product_id", sa.String(64), nullable=False),
        sa.Column("spec_code", sa.String(64), nullable=False),
        sa.Column("strategy_id", mysql.BINARY(16), nullable=True),
        sa.Column("image_urls", mysql.JSON, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.SmallInteger, nullable=False, server_default="5"),
        sa.Column("metadata", mysql.JSON, nullable=True),
        sa.Column("started_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        ),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "inspection_results",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("task_id", mysql.BINARY(16), nullable=False, unique=True),
        sa.Column("org_id", mysql.BINARY(16), nullable=False, index=True),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("overall_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("defects", mysql.JSON, nullable=True),
        sa.Column("citations", mysql.JSON, nullable=True),
        sa.Column("reasoning_chain", mysql.JSON, nullable=True),
        sa.Column("llm_model", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("reviewed_by", mysql.BINARY(16), nullable=True),
        sa.Column("reviewed_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        ),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["inspection_tasks.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "stability_reports",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("result_id", mysql.BINARY(16), nullable=False, unique=True),
        sa.Column("task_id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("evidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("consistency_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("traceability_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("anomaly_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("dimension_detail", mysql.JSON, nullable=True),
        sa.Column("sampling_results", mysql.JSON, nullable=True),
        sa.Column("root_cause", sa.Text, nullable=True),
        sa.Column("handled_by", mysql.BINARY(16), nullable=True),
        sa.Column("handled_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("handle_action", sa.String(32), nullable=True),
        sa.Column("handle_note", sa.Text, nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.ForeignKeyConstraint(["result_id"], ["inspection_results.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["inspection_tasks.id"]),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "alert_events",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("stability_id", mysql.BINARY(16), nullable=True),
        sa.Column("alert_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("detail", mysql.JSON, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("channels", mysql.JSON, nullable=True),
        sa.Column("dispatched_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("ack_by", mysql.BINARY(16), nullable=True),
        sa.Column("ack_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("resolved_by", mysql.BINARY(16), nullable=True),
        sa.Column("resolved_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "tool_registry",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("org_id", mysql.BINARY(16), nullable=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("parameters_schema", mysql.JSON, nullable=False),
        sa.Column("returns_schema", mysql.JSON, nullable=False),
        sa.Column("endpoint", sa.String(512), nullable=True),
        sa.Column("timeout_ms", sa.Integer, nullable=False, server_default="30000"),
        sa.Column("retry_policy", mysql.JSON, nullable=True),
        sa.Column("access_roles", mysql.JSON, nullable=False),
        sa.Column("rate_limit_rpm", sa.SmallInteger, nullable=False, server_default="60"),
        sa.Column("is_readonly", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "tool_executions",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("task_id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("tool_id", mysql.BINARY(16), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("call_index", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("input_payload", mysql.JSON, nullable=True),
        sa.Column("output_payload", mysql.JSON, nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "audit_outbox",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("payload", mysql.JSON, nullable=False),
        sa.Column("processed", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade():
    op.drop_table("audit_outbox")
    op.drop_table("tool_executions")
    op.drop_table("tool_registry")
    op.drop_table("alert_events")
    op.drop_table("stability_reports")
    op.drop_table("inspection_results")
    op.drop_table("inspection_tasks")
    op.drop_table("users")
    op.drop_table("organizations")
