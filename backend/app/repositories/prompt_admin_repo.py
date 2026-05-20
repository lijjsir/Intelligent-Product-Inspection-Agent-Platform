from __future__ import annotations

import hashlib
from datetime import datetime
from typing import TypeVar

from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_ops import PromptVersion
from app.models.prompt_admin import PromptDefinition, PromptSyncEvent

T = TypeVar("T")


class PromptAdminBaseRepo:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def _get_by_id(self, model: type[T], id: str) -> T | None:
        result = await self._session.execute(
            select(model).where(
                model.org_id == self._org_id,
                model.id == id,
                model.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class PromptDefinitionRepository(PromptAdminBaseRepo):
    async def create(self, data: dict) -> PromptDefinition:
        obj = PromptDefinition(**data, org_id=self._org_id)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def get(self, id: str) -> PromptDefinition | None:
        return await self._get_by_id(PromptDefinition, id)

    async def get_by_key(self, prompt_key: str) -> PromptDefinition | None:
        result = await self._session.execute(
            select(PromptDefinition).where(
                PromptDefinition.org_id == self._org_id,
                PromptDefinition.prompt_key == prompt_key,
                PromptDefinition.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        agent_key: str | None = None,
        stage_key: str | None = None,
        keyword: str | None = None,
        sync_status: str | None = None,
    ) -> list[PromptDefinition]:
        stmt = select(PromptDefinition).where(
            PromptDefinition.org_id == self._org_id,
            PromptDefinition.deleted_at.is_(None),
        )
        if agent_key:
            stmt = stmt.where(PromptDefinition.agent_key == agent_key)
        if stage_key:
            stmt = stmt.where(PromptDefinition.stage_key == stage_key)
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                PromptDefinition.prompt_key.ilike(pattern)
                | PromptDefinition.display_name.ilike(pattern)
                | PromptDefinition.usage_location.ilike(pattern)
            )
        if sync_status:
            stmt = stmt.where(PromptDefinition.sync_status == sync_status)
        stmt = stmt.order_by(PromptDefinition.agent_key, PromptDefinition.stage_key, PromptDefinition.display_name)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_code_default(
        self,
        definition_id: str,
        *,
        code_default_content: str,
        code_content_hash: str,
        sync_status: str,
    ) -> PromptDefinition | None:
        stmt = (
            update(PromptDefinition)
            .where(PromptDefinition.id == definition_id, PromptDefinition.org_id == self._org_id)
            .values(
                code_default_content=code_default_content,
                code_content_hash=code_content_hash,
                sync_status=sync_status,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return await self.get(definition_id)

    async def set_active_version(self, definition_id: str, version_id: str) -> None:
        await self._session.execute(
            update(PromptDefinition)
            .where(PromptDefinition.id == definition_id, PromptDefinition.org_id == self._org_id)
            .values(active_version_id=version_id, sync_status="db_override")
        )

    async def mark_missing_in_code(self, exclude_keys: set[str]) -> int:
        result = await self._session.execute(
            update(PromptDefinition)
            .where(
                PromptDefinition.org_id == self._org_id,
                PromptDefinition.deleted_at.is_(None),
                PromptDefinition.prompt_key.notin_(exclude_keys),
                PromptDefinition.sync_status != "missing_in_code",
            )
            .values(sync_status="missing_in_code")
        )
        return result.rowcount

    async def count_by_status(self) -> dict[str, int]:
        result = await self._session.execute(
            select(PromptDefinition.sync_status, func.count(PromptDefinition.id))
            .where(
                PromptDefinition.org_id == self._org_id,
                PromptDefinition.deleted_at.is_(None),
            )
            .group_by(PromptDefinition.sync_status)
        )
        return {row[0]: row[1] for row in result.all()}


class PromptVersionRepository(PromptAdminBaseRepo):
    """Extended prompt_versions repo for prompt-admin use (complements existing PromptVersionRepository in agent_ops)."""

    async def create_version(
        self, *, prompt_definition_id: str, content: str, change_summary: str | None = None, created_by: str | None = None
    ) -> PromptVersion:
        existing = await self._session.execute(
            select(func.coalesce(func.max(PromptVersion.version), 0))
            .where(
                PromptVersion.org_id == self._org_id,
                PromptVersion.prompt_definition_id == prompt_definition_id,
            )
        )
        next_version = existing.scalar() + 1
        obj = PromptVersion(
            org_id=self._org_id,
            name=f"v{next_version}",
            content=content,
            version=next_version,
            status="draft",
            created_by=created_by,
            prompt_definition_id=prompt_definition_id,
            content_hash=self._content_hash(content),
            change_summary=change_summary,
        )
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def get_latest_version(self, prompt_definition_id: str) -> PromptVersion | None:
        result = await self._session.execute(
            select(PromptVersion)
            .where(
                PromptVersion.org_id == self._org_id,
                PromptVersion.prompt_definition_id == prompt_definition_id,
                PromptVersion.deleted_at.is_(None),
            )
            .order_by(PromptVersion.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_versions(self, prompt_definition_id: str) -> list[PromptVersion]:
        result = await self._session.execute(
            select(PromptVersion)
            .where(
                PromptVersion.org_id == self._org_id,
                PromptVersion.prompt_definition_id == prompt_definition_id,
                PromptVersion.deleted_at.is_(None),
            )
            .order_by(PromptVersion.version.desc())
        )
        return list(result.scalars().all())

    async def get_version(self, version_id: str) -> PromptVersion | None:
        return await self._get_by_id(PromptVersion, version_id)

    async def publish_version(self, version_id: str) -> PromptVersion | None:
        await self._session.execute(
            update(PromptVersion)
            .where(PromptVersion.id == version_id, PromptVersion.org_id == self._org_id)
            .values(status="approved")
        )
        await self._session.flush()
        return await self.get_version(version_id)


class PromptSyncEventRepository(PromptAdminBaseRepo):
    async def create(self, data: dict) -> PromptSyncEvent:
        obj = PromptSyncEvent(**data, org_id=self._org_id)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj
