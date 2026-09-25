"""Adaptive quality supervision goals, evidence, decisions and device commands.

Revision ID: 0102_adaptive_quality_supervision
Revises: 0101_public_complaint_intake
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BINARY


revision = "0102_adaptive_quality_supervision"
down_revision = "0101_public_complaint_intake"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "inspection_goals",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=False),
        sa.Column("session_id", BINARY(16), nullable=False),
        sa.Column("plan_id", BINARY(16), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("risk_hypotheses", sa.JSON(), nullable=False),
        sa.Column("required_items", sa.JSON(), nullable=False),
        sa.Column("candidate_items", sa.JSON(), nullable=False),
        sa.Column("success_criteria", sa.JSON(), nullable=False),
        sa.Column("stop_policy", sa.JSON(), nullable=False),
        sa.Column("max_cost", sa.DECIMAL(14, 2), nullable=True),
        sa.Column("max_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_by", BINARY(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "org_id", "session_id", "version", name="uq_inspection_goal_version"
        ),
        sa.UniqueConstraint("org_id", "request_key", name="uq_inspection_goal_key"),
    )
    for column in ("org_id", "session_id", "plan_id", "status"):
        op.create_index(f"ix_inspection_goals_{column}", "inspection_goals", [column])

    op.create_table(
        "inspection_evidence_states",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=False),
        sa.Column("session_id", BINARY(16), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("device_trust_state", sa.JSON(), nullable=False),
        sa.Column("product_quality_state", sa.JSON(), nullable=False),
        sa.Column("supported_hypotheses", sa.JSON(), nullable=False),
        sa.Column("rejected_hypotheses", sa.JSON(), nullable=False),
        sa.Column("unresolved_conflicts", sa.JSON(), nullable=False),
        sa.Column("evidence_sufficiency", sa.DECIMAL(5, 4), nullable=False),
        sa.Column("remaining_uncertainty", sa.DECIMAL(5, 4), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "org_id", "session_id", "round", name="uq_inspection_evidence_round"
        ),
    )
    for column in ("org_id", "session_id"):
        op.create_index(
            f"ix_inspection_evidence_states_{column}",
            "inspection_evidence_states",
            [column],
        )

    op.create_table(
        "inspection_decisions",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=False),
        sa.Column("session_id", BINARY(16), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("input_state_id", BINARY(16), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("proposed_by", BINARY(16), nullable=False),
        sa.Column("approved_by", BINARY(16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("org_id", "request_key", name="uq_inspection_decision_key"),
    )
    for column in ("org_id", "session_id", "kind", "status", "input_state_id"):
        op.create_index(
            f"ix_inspection_decisions_{column}", "inspection_decisions", [column]
        )

    op.create_table(
        "device_commands",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=False),
        sa.Column("session_id", BINARY(16), nullable=False),
        sa.Column("decision_id", BINARY(16), nullable=False),
        sa.Column("device_id", BINARY(16), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requested_by", BINARY(16), nullable=False),
        sa.Column("approved_by", BINARY(16), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint("org_id", "request_key", name="uq_device_command_key"),
    )
    for column in ("org_id", "session_id", "decision_id", "device_id", "status"):
        op.create_index(f"ix_device_commands_{column}", "device_commands", [column])

    op.create_table(
        "supervision_events",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", BINARY(16), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column("workflow_run_id", BINARY(16), nullable=True),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", BINARY(16), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "event_key", name="uq_supervision_event_key"),
    )
    for column in (
        "org_id",
        "aggregate_type",
        "aggregate_id",
        "event_type",
        "workflow_run_id",
    ):
        op.create_index(f"ix_supervision_events_{column}", "supervision_events", [column])

    op.add_column("measurement_records", sa.Column("command_id", BINARY(16), nullable=True))
    op.add_column("measurement_records", sa.Column("sequence_no", sa.Integer(), nullable=True))
    op.add_column(
        "measurement_records",
        sa.Column("validation_status", sa.String(32), nullable=True),
    )
    op.add_column(
        "measurement_records",
        sa.Column("calibration_version", sa.String(64), nullable=True),
    )
    op.create_index("ix_measurement_records_command_id", "measurement_records", ["command_id"])

    op.add_column(
        "inspection_results", sa.Column("inspection_session_id", BINARY(16), nullable=True)
    )
    op.add_column(
        "inspection_results", sa.Column("stop_decision_id", BINARY(16), nullable=True)
    )
    op.add_column(
        "inspection_results", sa.Column("result_status", sa.String(32), nullable=True)
    )
    op.add_column("inspection_results", sa.Column("signed_by", BINARY(16), nullable=True))
    op.add_column("inspection_results", sa.Column("signed_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_inspection_results_inspection_session_id",
        "inspection_results",
        ["inspection_session_id"],
    )


def downgrade():
    op.drop_index(
        "ix_inspection_results_inspection_session_id", table_name="inspection_results"
    )
    for column in (
        "signed_at",
        "signed_by",
        "result_status",
        "stop_decision_id",
        "inspection_session_id",
    ):
        op.drop_column("inspection_results", column)

    op.drop_index("ix_measurement_records_command_id", table_name="measurement_records")
    for column in (
        "calibration_version",
        "validation_status",
        "sequence_no",
        "command_id",
    ):
        op.drop_column("measurement_records", column)

    for table in (
        "supervision_events",
        "device_commands",
        "inspection_decisions",
        "inspection_evidence_states",
        "inspection_goals",
    ):
        op.drop_table(table)
