"""cleanup reverted regulatory schema

Revision ID: 0066
Revises: 0065
Create Date: 2026-05-24 18:30:00.000000
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


REGULATORY_TABLES = (
    "regulatory_public_opinions",
    "regulatory_enforcement_cases",
    "regulatory_complaints",
    "regulatory_sampling_inspections",
    "regulatory_policy_documents",
    "regulatory_media_assets",
    "regulatory_enterprises",
)

DEMO_NAMESPACE = uuid.UUID("7b0b27f0-6de2-4f58-9f44-4d8e014c4f29")
TARGET_ORG_SLUGS = ("admin", "user")
ID_PARTS = {
    "rag_spaces": ("rag-space:ready-to-eat", "rag-space:cold-chain-dairy"),
    "rag_nodes": ("rag-node:ready-to-eat", "rag-node:cold-chain-dairy"),
    "rag_documents": ("rag-doc:ready-to-eat", "rag-doc:cold-chain-dairy"),
    "inspection_standard_libraries": ("standard:ready-to-eat", "standard:cold-chain-dairy"),
}


def _demo_uuid_bytes(org_slug: str, suffix: str) -> bytes:
    return uuid.uuid5(DEMO_NAMESPACE, f"regulatory-demo:{org_slug}:{suffix}").bytes


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _drop_table_if_exists(table_name: str) -> None:
    if _has_table(table_name):
        op.drop_table(table_name)


def _delete_seed_rows(table_name: str, suffixes: tuple[str, ...]) -> None:
    if not _has_table(table_name):
        return
    ids = [_demo_uuid_bytes(org_slug, suffix) for org_slug in TARGET_ORG_SLUGS for suffix in suffixes]
    if not ids:
        return
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=op.get_bind())
    op.get_bind().execute(sa.delete(table).where(table.c.id.in_(ids)))


def upgrade() -> None:
    for table_name in REGULATORY_TABLES:
        _drop_table_if_exists(table_name)
    for table_name, suffixes in ID_PARTS.items():
        _delete_seed_rows(table_name, suffixes)


def downgrade() -> None:
    return None
