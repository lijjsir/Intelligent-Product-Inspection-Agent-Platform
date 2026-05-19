"""quality tracing 数据源迁移到 Langfuse API

list_traces 读路径从 piap-mysql 五表拼装改为 Langfuse REST API。
piap-mysql 表保留（供 build_report / billing / analytics / feedback 等使用）。
新增复合索引优化 hybrid 模式下的业务字段补全查询。

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-16
"""
from alembic import op

revision = "0025_quality_tracing_langfuse"
down_revision = "0024_chat_message_scores"
branch_labels = None
depends_on = None


def upgrade():
    # 复合索引：list_by_task_ids 批量补全 verdict 使用
    op.create_index(
        "idx_inspection_results_org_task",
        "inspection_results",
        ["org_id", "task_id"],
    )


def downgrade():
    op.drop_index("idx_inspection_results_org_task", table_name="inspection_results")
