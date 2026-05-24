"""merge post-branch heads after integrating zl/tgg feature migrations

Revision ID: 0045_merge_post_branch_heads
Revises: 0038_alert_rule_fk, 0038_dataset_import_mvp_backfill, 0044
Create Date: 2026-05-21
"""

revision = "0045_merge_post_branch_heads"
down_revision = ("0038_alert_rule_fk", "0038_dataset_import_mvp_backfill", "0044")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
