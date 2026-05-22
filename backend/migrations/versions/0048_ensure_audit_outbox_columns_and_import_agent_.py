"""ensure_audit_outbox_columns_and_import_agent_management

Revision ID: 0048
Revises: 0047
Create Date: 2026-05-22 18:00:00.000000

Ensure audit_outbox.updated_at exists with ON UPDATE clause,
and document that agent_management models are now properly registered in ORM metadata.
"""

from alembic import op
import sqlalchemy as sa

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade():
    # Ensure audit_outbox has updated_at with ON UPDATE CURRENT_TIMESTAMP(3)
    # Use raw SQL for idempotency — only add if column does not exist
    op.execute(
        """
        SET @stmt = (
            SELECT IF(
                COUNT(*) = 0,
                'ALTER TABLE audit_outbox ADD COLUMN updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)',
                'SELECT ''audit_outbox.updated_at already exists, skipping'' AS msg'
            )
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'audit_outbox'
              AND COLUMN_NAME = 'updated_at'
        );
        PREPARE stmt FROM @stmt;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        """
    )


def downgrade():
    # Non-destructive — keep the column even on downgrade
    pass
