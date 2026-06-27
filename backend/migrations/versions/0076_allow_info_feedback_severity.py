"""allow info feedback severity

Revision ID: 0076_allow_info_feedback_severity
Revises: 0075_meeting_room_v2_boundaries
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0076_allow_info_feedback_severity"
down_revision = "0075_meeting_room_v2_boundaries"
branch_labels = None
depends_on = None

CHECK_NAME = "ck_result_feedbacks_severity"
TABLE_NAME = "result_feedbacks"
ALLOWED_VALUES = ("info", "low", "medium", "high", "critical")
LEGACY_VALUES = ("low", "medium", "high", "critical")


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


def _render_check(values: tuple[str, ...]) -> str:
    joined = ",".join(repr(value) for value in values)
    return f"CHECK (severity IS NULL OR severity IN ({joined}))"


def upgrade():
    if _has_check_constraint(TABLE_NAME, CHECK_NAME):
        op.execute(f"ALTER TABLE {TABLE_NAME} DROP CHECK {CHECK_NAME}")
    op.execute(
        f"ALTER TABLE {TABLE_NAME} ADD CONSTRAINT {CHECK_NAME} {_render_check(ALLOWED_VALUES)}"
    )


def downgrade():
    if _has_check_constraint(TABLE_NAME, CHECK_NAME):
        op.execute(f"ALTER TABLE {TABLE_NAME} DROP CHECK {CHECK_NAME}")
    op.execute(
        f"ALTER TABLE {TABLE_NAME} ADD CONSTRAINT {CHECK_NAME} {_render_check(LEGACY_VALUES)}"
    )
