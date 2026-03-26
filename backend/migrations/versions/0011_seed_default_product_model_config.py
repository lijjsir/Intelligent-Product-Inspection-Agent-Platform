"""seed default product recognition model config

Revision ID: 0011_seed_default_product_model
Revises: 0010_task_spec_id_to_spec_code
Create Date: 2026-03-26
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0011_seed_default_product_model"
down_revision = "0010_task_spec_id_to_spec_code"
branch_labels = None
depends_on = None


MODEL_ROW_ID = uuid.UUID("a3179c20-8d26-4d44-93f6-4bc4d1cb4a11")
MODEL_KEY = "ep-20260325082100-v7vs6"
MODEL_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3"


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(
        sa.text(
            """
            SELECT COUNT(1)
            FROM model_configs
            WHERE org_id IS NULL
              AND model_key = :model_key
              AND deleted_at IS NULL
            """
        ),
        {"model_key": MODEL_KEY},
    ).scalar_one()
    if existing:
        return

    model_table = sa.table(
        "model_configs",
        sa.column("id", mysql.BINARY(16)),
        sa.column("org_id", mysql.BINARY(16)),
        sa.column("provider", sa.String(32)),
        sa.column("model_key", sa.String(128)),
        sa.column("display_name", sa.String(128)),
        sa.column("endpoint", sa.String(512)),
        sa.column("api_key_enc", sa.Text()),
        sa.column("model_type", sa.String(32)),
        sa.column("priority", sa.Integer()),
        sa.column("rpm_limit", sa.Integer()),
        sa.column("input_price_per_million", sa.Numeric(12, 4)),
        sa.column("output_price_per_million", sa.Numeric(12, 4)),
        sa.column("is_active", sa.Boolean()),
        sa.column("health_status", sa.String(16)),
        sa.column("health_message", sa.String(256)),
        sa.column("deleted_at", mysql.DATETIME(fsp=3)),
    )
    op.bulk_insert(
        model_table,
        [
            {
                "id": MODEL_ROW_ID.bytes,
                "org_id": None,
                "provider": "volcengine",
                "model_key": MODEL_KEY,
                "display_name": "当前产品识别主模型",
                "endpoint": MODEL_ENDPOINT,
                "api_key_enc": None,
                "model_type": "multimodal",
                "priority": 10,
                "rpm_limit": 60,
                "input_price_per_million": None,
                "output_price_per_million": None,
                "is_active": True,
                "health_status": "unknown",
                "health_message": None,
                "deleted_at": None,
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM model_configs
            WHERE id = :row_id
              AND org_id IS NULL
              AND model_key = :model_key
            """
        ).bindparams(
            row_id=MODEL_ROW_ID.bytes,
            model_key=MODEL_KEY,
        )
    )
