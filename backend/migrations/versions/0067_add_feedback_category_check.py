"""add feedback category check constraint

Revision ID: 0067
Revises: 0066
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

FEEDBACK_CATEGORIES = (
    "reliable",
    "wrong_verdict",
    "weak_evidence",
    "bad_bbox",
    "unclear_reasoning",
)

CHECK_NAME = "ck_result_feedbacks_category"


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
    if _has_check_constraint("result_feedbacks", CHECK_NAME):
        return
    op.execute(
        f"ALTER TABLE result_feedbacks ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK (category IS NULL OR category IN ({', '.join(repr(c) for c in FEEDBACK_CATEGORIES)}))"
    )


def downgrade():
    if not _has_check_constraint("result_feedbacks", CHECK_NAME):
        return
    op.execute(f"ALTER TABLE result_feedbacks DROP CHECK {CHECK_NAME}")
