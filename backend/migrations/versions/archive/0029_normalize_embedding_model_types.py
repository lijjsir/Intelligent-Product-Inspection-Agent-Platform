"""normalize embedding model types

Revision ID: 0029_normalize_embed_type
Revises: 0028_repair_embed_model
Create Date: 2026-05-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0029_normalize_embed_type"
down_revision = "0028_repair_embed_model"
branch_labels = None
depends_on = None


EMBEDDING_KEYS = (
    "doubao-embedding-vision-251215",
    "ep-20260311135919-gktlx",
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE model_configs
            SET model_type = 'embedding',
                health_status = 'unknown',
                health_message = NULL
            WHERE deleted_at IS NULL
              AND provider = 'volcengine'
              AND model_key IN :model_keys
              AND model_type <> 'embedding'
            """
        ).bindparams(sa.bindparam("model_keys", expanding=True)),
        {"model_keys": EMBEDDING_KEYS},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE model_configs
            SET model_type = 'chat',
                health_status = 'unknown',
                health_message = NULL
            WHERE deleted_at IS NULL
              AND provider = 'volcengine'
              AND model_key IN :model_keys
              AND display_name IN ('doubao-embedding-vision', 'Volcengine Embedding')
            """
        ).bindparams(sa.bindparam("model_keys", expanding=True)),
        {"model_keys": EMBEDDING_KEYS},
    )
