"""add feedback category check constraint

Revision ID: 0064
Revises: 0063
Create Date: 2026-05-23
"""

from alembic import op

revision = "0064"
down_revision = "0063"
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


def upgrade():
    op.execute(
        f"ALTER TABLE result_feedbacks ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK (category IS NULL OR category IN ({', '.join(repr(c) for c in FEEDBACK_CATEGORIES)}))"
    )


def downgrade():
    op.execute(f"ALTER TABLE result_feedbacks DROP CHECK {CHECK_NAME}")
