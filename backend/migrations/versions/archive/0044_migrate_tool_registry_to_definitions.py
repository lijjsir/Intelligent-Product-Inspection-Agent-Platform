"""migrate legacy tool_registry rows into tool_definitions/tool_versions

Revision ID: 0044
Revises: 0043
Create Date: 2026-05-21
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()

    tool_registry = sa.Table("tool_registry", metadata, autoload_with=bind)
    tool_definitions = sa.Table("tool_definitions", metadata, autoload_with=bind)
    tool_versions = sa.Table("tool_versions", metadata, autoload_with=bind)

    rows = list(bind.execute(sa.select(tool_registry)).mappings())
    now = utcnow()

    for row in rows:
        existing_definition = bind.execute(
            sa.select(tool_definitions.c.id).where(
                tool_definitions.c.org_id == row["org_id"],
                tool_definitions.c.tool_key == row["name"],
            )
        ).first()
        if existing_definition:
            continue

        version_id = uuid.uuid4().bytes

        bind.execute(
            tool_definitions.insert().values(
                id=row["id"],
                org_id=row["org_id"],
                tool_key=row["name"],
                display_name=row["display_name"],
                description=row["description"],
                category=row["category"] or "inspection_calc",
                tool_type=row["tool_type"] or ("http" if row["endpoint"] else "native"),
                status=row["status"] or ("active" if row["is_active"] else "disabled"),
                risk_level=row["risk_level"] or ("low" if row["is_readonly"] else "medium"),
                is_readonly=row["is_readonly"],
                source_type=row["source_type"] or "manual",
                source_ref=row["endpoint"],
                manifest_hash=row["manifest_hash"],
                active_version_id=version_id,
                health_status=row["health_status"] or "unknown",
                last_checked_at=None,
                created_by=None,
                created_at=row["created_at"] or now,
                updated_at=row["updated_at"] or now,
                deleted_at=None,
            )
        )

        bind.execute(
            tool_versions.insert().values(
                id=version_id,
                org_id=row["org_id"],
                tool_id=row["id"],
                version=row["version"] or "1.0.0",
                display_name=row["display_name"],
                description=row["description"],
                endpoint=row["endpoint"],
                method="POST" if row["endpoint"] else None,
                handler_path=None,
                parameters_schema=row["parameters_schema"] or {},
                returns_schema=row["returns_schema"] or {},
                auth_type="none",
                secret_ref=None,
                timeout_ms=row["timeout_ms"] or 30000,
                retry_policy=row["retry_policy"],
                rate_limit_rpm=row["rate_limit_rpm"] or 60,
                status=row["status"] or "active",
                created_by=None,
                created_at=row["created_at"] or now,
                updated_at=row["updated_at"] or now,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()

    tool_definitions = sa.Table("tool_definitions", metadata, autoload_with=bind)
    tool_versions = sa.Table("tool_versions", metadata, autoload_with=bind)
    tool_registry = sa.Table("tool_registry", metadata, autoload_with=bind)

    legacy_ids = [row[0] for row in bind.execute(sa.select(tool_registry.c.id)).all()]
    if not legacy_ids:
        return

    bind.execute(tool_versions.delete().where(tool_versions.c.tool_id.in_(legacy_ids)))
    bind.execute(tool_definitions.delete().where(tool_definitions.c.id.in_(legacy_ids)))
