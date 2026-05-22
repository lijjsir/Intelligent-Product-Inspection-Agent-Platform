"""add meeting_agent_definitions

Revision ID: 0053
Revises: 0052
Create Date: 2026-05-23
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from alembic import op
from sqlalchemy import Boolean, Column, DateTime, String, Text, JSON, text
from sqlalchemy.dialects.mysql import BINARY


revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_agent_definitions",
        Column("id", BINARY(16), primary_key=True),
        Column("org_id", BINARY(16), nullable=False, index=True),
        Column("name", String(64), nullable=False),
        Column("system_prompt", Text, nullable=False),
        Column("model", String(64), nullable=False, server_default="deepseek-chat"),
        Column("adapter_type", String(32), nullable=False, server_default="llm"),
        Column("participation_strategy", JSON, nullable=True),
        Column("is_active", Boolean, nullable=False, server_default=text("1")),
        Column("created_by", BINARY(16), nullable=True, index=True),
        Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(3)")),
        Column("updated_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        Column("deleted_at", DateTime, nullable=True),
    )

    # Seed default agent: use a zero UUID for org_id (system-wide default)
    default_id = uuid.uuid4()
    op.execute(
        f"INSERT INTO meeting_agent_definitions "
        f"(id, org_id, name, system_prompt, model, adapter_type, participation_strategy, is_active) "
        f"VALUES ("
        f"0x{default_id.bytes.hex()}, "
        f"0x{'00000000000000000000000000000000'}, "
        f"'AI 助手', "
        f"'你是一个会议协作助手，正在参与一个多人会议室讨论。请用中文回复，语气友好、简洁、专业。根据对话内容给出有价值的回应。', "
        f"'deepseek-chat', "
        f"'llm', "
        f"'{{\"auto_reply\": true, \"cooldown_seconds\": 30, \"strategies\": {{\"message_count\": {{\"enabled\": true, \"every_n_messages\": 5}}, \"topic_match\": {{\"enabled\": false, \"keywords\": []}}, \"silence_timer\": {{\"enabled\": true, \"after_seconds\": 300}}}}}}', "
        f"1"
        f")"
    )


def downgrade() -> None:
    op.drop_table("meeting_agent_definitions")
