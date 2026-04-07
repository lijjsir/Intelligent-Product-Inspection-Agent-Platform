"""merge develop heads after integrating chat/rag and alert management changes

Revision ID: 0016_merge_develop_heads
Revises: 0015_alert_handle_fields, 0015_rag_spaces_and_files
Create Date: 2026-04-02

"""

revision = "0016_merge_develop_heads"
down_revision = ("0015_alert_handle_fields", "0015_rag_spaces_and_files")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
