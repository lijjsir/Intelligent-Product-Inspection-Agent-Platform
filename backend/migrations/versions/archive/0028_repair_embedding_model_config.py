"""repair default embedding model config

Revision ID: 0028_repair_embed_model
Revises: 0027_drop_legacy_rag
Create Date: 2026-05-16
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0028_repair_embed_model"
down_revision = "0027_drop_legacy_rag"
branch_labels = None
depends_on = None


EMBED_MODEL_KEY = "ep-20260311135919-gktlx"
EMBED_DISPLAY_NAME = "Volcengine Embedding"
EMBED_ENDPOINT_FALLBACK = "https://ark.cn-beijing.volces.com/api/v3"


def upgrade() -> None:
    bind = op.get_bind()

    source_rows = bind.execute(
        sa.text(
            """
            SELECT org_id, endpoint, api_key_enc, rpm_limit
            FROM model_configs
            WHERE deleted_at IS NULL
              AND is_active = 1
              AND provider = 'volcengine'
            GROUP BY org_id, endpoint, api_key_enc, rpm_limit
            """
        )
    ).mappings().all()

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

    for row in source_rows:
        org_id = row["org_id"]
        existing = bind.execute(
            sa.text(
                """
                SELECT COUNT(1)
                FROM model_configs
                WHERE deleted_at IS NULL
                  AND is_active = 1
                  AND provider = 'volcengine'
                  AND model_type IN ('embedding', 'embed', 'text_embedding')
                  AND model_key = :model_key
                  AND ((org_id IS NULL AND :org_id IS NULL) OR org_id = :org_id)
                """
            ),
            {"org_id": org_id, "model_key": EMBED_MODEL_KEY},
        ).scalar_one()
        if existing:
            continue

        op.bulk_insert(
            model_table,
            [
                {
                    "id": uuid.uuid4().bytes,
                    "org_id": org_id,
                    "provider": "volcengine",
                    "model_key": EMBED_MODEL_KEY,
                    "display_name": EMBED_DISPLAY_NAME,
                    "endpoint": row["endpoint"] or EMBED_ENDPOINT_FALLBACK,
                    "api_key_enc": row["api_key_enc"],
                    "model_type": "embedding",
                    "priority": 1,
                    "rpm_limit": row["rpm_limit"] or 60,
                    "input_price_per_million": 0.7,
                    "output_price_per_million": 0.0,
                    "is_active": True,
                    "health_status": "unknown",
                    "health_message": None,
                    "deleted_at": None,
                }
            ],
        )

    bind.execute(
        sa.text(
            """
            UPDATE model_configs
            SET is_active = 0,
                health_status = 'unhealthy',
                health_message = 'disabled by migration: chat model cannot serve embeddings'
            WHERE deleted_at IS NULL
              AND is_active = 1
              AND provider = 'deepseek'
              AND model_type IN ('embedding', 'embed', 'text_embedding')
              AND model_key = 'deepseek-v4-flash'
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM model_configs
            WHERE provider = 'volcengine'
              AND model_type IN ('embedding', 'embed', 'text_embedding')
              AND model_key = :model_key
              AND display_name = :display_name
            """
        ),
        {"model_key": EMBED_MODEL_KEY, "display_name": EMBED_DISPLAY_NAME},
    )
