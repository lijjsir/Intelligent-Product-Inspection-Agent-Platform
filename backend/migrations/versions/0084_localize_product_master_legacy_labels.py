"""localize product master legacy labels

Revision ID: 0084_localize_product_master_legacy_labels
Revises: 0083_chat_messages_quality_report_index
Create Date: 2026-06-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0084_localize_product_master_legacy_labels"
down_revision = "0083_chat_messages_quality_report_index"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    conn = op.get_bind()
    if _has_table("product_lines"):
        conn.execute(sa.text(
            """
            UPDATE product_lines
            SET description = '由历史检测任务的产品编号自动创建。'
            WHERE description = 'Auto-created from legacy inspection task product_id.'
            """
        ))
    if _has_table("product_skus"):
        conn.execute(sa.text(
            """
            UPDATE product_skus
            SET description = '由历史检测任务的产品编号自动创建。'
            WHERE description = 'Auto-created from legacy inspection task product_id.'
            """
        ))
    if _has_table("product_batches"):
        conn.execute(sa.text(
            """
            UPDATE product_batches
            SET name = '未指定批次'
            WHERE batch_no = 'UNSPECIFIED' AND name = 'Unspecified batch'
            """
        ))
        conn.execute(sa.text(
            """
            UPDATE product_batches
            SET description = '为没有批次号的历史任务自动创建的兼容批次。'
            WHERE description = 'Auto-created compatibility batch for tasks without batch_no.'
            """
        ))


def downgrade() -> None:
    conn = op.get_bind()
    if _has_table("product_lines"):
        conn.execute(sa.text(
            """
            UPDATE product_lines
            SET description = 'Auto-created from legacy inspection task product_id.'
            WHERE description = '由历史检测任务的产品编号自动创建。'
            """
        ))
    if _has_table("product_skus"):
        conn.execute(sa.text(
            """
            UPDATE product_skus
            SET description = 'Auto-created from legacy inspection task product_id.'
            WHERE description = '由历史检测任务的产品编号自动创建。'
            """
        ))
    if _has_table("product_batches"):
        conn.execute(sa.text(
            """
            UPDATE product_batches
            SET name = 'Unspecified batch'
            WHERE batch_no = 'UNSPECIFIED' AND name = '未指定批次'
            """
        ))
        conn.execute(sa.text(
            """
            UPDATE product_batches
            SET description = 'Auto-created compatibility batch for tasks without batch_no.'
            WHERE description = '为没有批次号的历史任务自动创建的兼容批次。'
            """
        ))
