from __future__ import annotations

import difflib
import hashlib
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.prompt_admin_repo import (
    PromptDefinitionRepository,
    PromptVersionRepository,
    PromptSyncEventRepository,
)
from app.schemas.prompt_admin import (
    PromptDefinitionDetail,
    PromptDefinitionSummary,
    PromptVersionItem,
    PromptOverviewResponse,
    SyncScanResponse,
    DiffResponse,
)

logger = logging.getLogger(__name__)


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# Module-level resolver cache (in production, use Redis)
_resolver_cache: dict[str, str] = {}


def invalidate_resolver_cache(org_id: str, prompt_key: str) -> None:
    _resolver_cache.pop(f"{org_id}:{prompt_key}", None)


class PromptAdminService:
    def __init__(self, session: AsyncSession, org_id: str, actor_id: str):
        self._session = session
        self._org_id = org_id
        self._actor_id = actor_id
        self._def_repo = PromptDefinitionRepository(session, org_id)
        self._ver_repo = PromptVersionRepository(session, org_id)
        self._event_repo = PromptSyncEventRepository(session, org_id)

    # ── Queries ──

    async def overview(self) -> PromptOverviewResponse:
        counts = await self._def_repo.count_by_status()
        return PromptOverviewResponse(
            total=sum(counts.values()),
            db_override=counts.get("db_override", 0),
            code_changed=counts.get("code_changed", 0),
            conflict=counts.get("conflict", 0),
            missing_in_code=counts.get("missing_in_code", 0),
        )

    async def list_definitions(
        self,
        *,
        agent_key: str | None = None,
        stage_key: str | None = None,
        keyword: str | None = None,
        sync_status: str | None = None,
    ) -> list[PromptDefinitionSummary]:
        items = await self._def_repo.list_all(
            agent_key=agent_key, stage_key=stage_key, keyword=keyword, sync_status=sync_status
        )
        summaries: list[PromptDefinitionSummary] = []
        for d in items:
            active_ver = None
            if d.active_version_id:
                av = await self._ver_repo.get_version(d.active_version_id)
                active_ver = av.version if av else None
            summaries.append(
                PromptDefinitionSummary(
                    id=d.id,
                    prompt_key=d.prompt_key,
                    display_name=d.display_name,
                    usage_location=d.usage_location,
                    agent_name=d.agent_name,
                    stage_name=d.stage_name,
                    source_file=d.source_file,
                    sync_status=d.sync_status,
                    current_source="database" if d.active_version_id else "code_default",
                    active_version=active_ver,
                    updated_at=d.updated_at,
                )
            )
        return summaries

    async def get_definition_detail(self, prompt_key: str) -> PromptDefinitionDetail | None:
        d = await self._def_repo.get_by_key(prompt_key)
        if not d:
            return None
        versions = await self._ver_repo.list_versions(d.id)
        version_items: list[PromptVersionItem] = [
            PromptVersionItem(
                id=v.id,
                version=v.version,
                content=v.content,
                content_hash=v.content_hash or _hash(v.content),
                status=v.status,
                change_summary=v.change_summary,
                created_by=v.created_by,
                created_at=v.created_at,
                updated_at=v.updated_at,
            )
            for v in versions
        ]
        active_content = d.code_default_content or ""
        active_content_hash = d.code_content_hash or _hash(active_content)
        active_version = None
        if d.active_version_id:
            av = await self._ver_repo.get_version(d.active_version_id)
            if av:
                active_content = av.content
                active_content_hash = av.content_hash or _hash(av.content)
                active_version = av.version
        return PromptDefinitionDetail(
            id=d.id,
            prompt_key=d.prompt_key,
            display_name=d.display_name,
            description=d.description,
            agent_key=d.agent_key,
            agent_name=d.agent_name,
            stage_key=d.stage_key,
            stage_name=d.stage_name,
            usage_location=d.usage_location,
            source_file=d.source_file,
            source_symbol=d.source_symbol,
            start_line=d.start_line,
            end_line=d.end_line,
            current_source="database" if d.active_version_id else "code_default",
            sync_status=d.sync_status,
            code_default_content=d.code_default_content or "",
            active_content=active_content,
            active_version=active_version,
            active_content_hash=active_content_hash,
            versions=version_items,
        )

    # ── Version mutations ──

    async def create_version(
        self, prompt_key: str, *, content: str, change_summary: str | None = None, base_hash: str | None = None
    ) -> dict[str, Any]:
        d = await self._def_repo.get_by_key(prompt_key)
        if not d:
            raise ValueError(f"Prompt definition not found: {prompt_key}")

        # Optimistic lock: verify base_hash matches current active content
        if base_hash:
            active_hash = d.code_content_hash or _hash(d.code_default_content or "")
            if d.active_version_id:
                av = await self._ver_repo.get_version(d.active_version_id)
                if av:
                    active_hash = av.content_hash or _hash(av.content)
            if base_hash != active_hash:
                raise ValueError("内容已被他人修改，请刷新后重试")

        v = await self._ver_repo.create_version(
            prompt_definition_id=d.id,
            content=content,
            change_summary=change_summary,
            created_by=self._actor_id,
        )
        await self._event_repo.create({
            "prompt_definition_id": d.id,
            "event_type": "db_version_created",
            "new_hash": v.content_hash,
            "message": f"Draft version {v.version} created" + (f": {change_summary}" if change_summary else ""),
        })
        return {"version_id": v.id, "version": v.version, "status": v.status}

    async def publish_version(self, version_id: str) -> dict[str, Any]:
        v = await self._ver_repo.publish_version(version_id)
        if not v or not v.prompt_definition_id:
            raise ValueError(f"Version not found: {version_id}")
        await self._def_repo.set_active_version(v.prompt_definition_id, version_id)
        invalidate_resolver_cache(self._org_id, await self._get_prompt_key(v.prompt_definition_id))
        await self._event_repo.create({
            "prompt_definition_id": v.prompt_definition_id,
            "event_type": "version_published",
            "new_hash": v.content_hash,
            "message": f"Version {v.version} published",
        })
        return {"version_id": v.id, "version": v.version, "status": v.status}

    async def rollback(self, prompt_key: str, target_version_id: str) -> dict[str, Any]:
        d = await self._def_repo.get_by_key(prompt_key)
        if not d:
            raise ValueError(f"Prompt definition not found: {prompt_key}")
        target = await self._ver_repo.get_version(target_version_id)
        if not target or target.prompt_definition_id != d.id:
            raise ValueError("Target version does not belong to this prompt")
        prev_hash = d.code_content_hash
        await self._def_repo.set_active_version(d.id, target_version_id)
        invalidate_resolver_cache(self._org_id, prompt_key)
        await self._event_repo.create({
            "prompt_definition_id": d.id,
            "event_type": "rollback",
            "old_hash": prev_hash,
            "new_hash": target.content_hash,
            "message": f"Rolled back to version {target.version}",
        })
        return {"version_id": target.id, "version": target.version, "status": target.status}

    async def _get_prompt_key(self, definition_id: str) -> str:
        d = await self._def_repo.get(definition_id)
        if not d:
            raise ValueError(f"Prompt definition not found: {definition_id}")
        return d.prompt_key

    # ── Diff ──

    async def diff(self, prompt_key: str, left: str = "code_default", right: str = "active") -> DiffResponse:
        d = await self._def_repo.get_by_key(prompt_key)
        if not d:
            raise ValueError(f"Prompt definition not found: {prompt_key}")

        left_content = d.code_default_content or ""
        left_label = "代码默认版本"
        if left == "active":
            av = await self._ver_repo.get_version(d.active_version_id) if d.active_version_id else None
            left_content = av.content if av else left_content
            left_label = "当前生效版本"

        right_content = d.code_default_content or ""
        right_label = "代码默认版本"
        if right == "active":
            av = await self._ver_repo.get_version(d.active_version_id) if d.active_version_id else None
            right_content = av.content if av else right_content
            right_label = "当前生效版本"

        # If contents differ, compute unified diff for left panel display
        if left_content != right_content:
            diff_output = "\n".join(difflib.unified_diff(
                left_content.splitlines(), right_content.splitlines(),
                fromfile=left_label, tofile=right_label, lineterm="",
            ))
            left_content = diff_output if diff_output else "（无差异）"

        return DiffResponse(
            left_label=left_label,
            right_label=right_label,
            left_content=left_content,
            right_content=right_content,
        )

    # ── Sync (PromptScanner) ──

    async def scan_code_prompts(self) -> SyncScanResponse:
        code_prompts = _load_all_prompt_modules()
        if code_prompts is None:
            raise RuntimeError("Failed to load prompt modules — scan aborted to avoid data loss")
        seen_keys: set[str] = set()
        created = 0
        updated = 0

        for item in code_prompts:
            key = item["key"]
            seen_keys.add(key)
            content = item["content"]
            content_hash = _hash(content)

            existing = await self._def_repo.get_by_key(key)
            if not existing:
                await self._def_repo.create({
                    "prompt_key": key,
                    "display_name": item["display_name"],
                    "description": item.get("description"),
                    "agent_key": item.get("agent_key"),
                    "agent_name": item.get("agent_name"),
                    "stage_key": item.get("stage_key"),
                    "stage_name": item.get("stage_name"),
                    "usage_location": item.get("usage_location"),
                    "source_file": item.get("source_file"),
                    "source_symbol": item.get("source_symbol"),
                    "code_default_content": content,
                    "code_content_hash": content_hash,
                    "sync_status": "synced",
                })
                created += 1
                continue

            if existing.code_content_hash != content_hash:
                next_status = "conflict" if existing.active_version_id else "code_changed"
                await self._def_repo.update_code_default(
                    existing.id,
                    code_default_content=content,
                    code_content_hash=content_hash,
                    sync_status=next_status,
                )
                await self._event_repo.create({
                    "prompt_definition_id": existing.id,
                    "event_type": "code_changed",
                    "old_hash": existing.code_content_hash,
                    "new_hash": content_hash,
                    "message": f"Code default changed for {key}",
                })
                updated += 1
            elif existing.sync_status in ("code_changed", "conflict", "missing_in_code") and not existing.active_version_id:
                await self._def_repo.update_code_default(
                    existing.id,
                    code_default_content=content,
                    code_content_hash=content_hash,
                    sync_status="synced",
                )

        missing = await self._def_repo.mark_missing_in_code(seen_keys)
        return SyncScanResponse(
            scanned=len(code_prompts),
            created=created,
            updated=updated,
            missing=missing,
        )


# ── PromptResolver (runtime resolution) ──

class PromptResolver:
    """Resolves the effective prompt content at runtime.
    Prefers database override; falls back to code default.

    Uses the module-level _resolver_cache by default so that
    publish/rollback invalidations via invalidate_resolver_cache()
    are visible to all resolver instances.
    """

    def __init__(self, session_factory, cache=None):
        self._session_factory = session_factory
        self._cache = cache if cache is not None else _resolver_cache

    async def get(self, prompt_key: str, *, org_id: str) -> str:
        cache_key = f"{org_id}:{prompt_key}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        async with self._session_factory() as session:
            repo = PromptDefinitionRepository(session, org_id)
            d = await repo.get_by_key(prompt_key)
            if not d:
                raise RuntimeError(f"Prompt not found: {prompt_key}")

            if d.active_version_id:
                ver_repo = PromptVersionRepository(session, org_id)
                v = await ver_repo.get_version(d.active_version_id)
                content = v.content if v else (d.code_default_content or "")
            else:
                content = d.code_default_content or ""

        self._cache[cache_key] = content
        return content

    def invalidate(self, org_id: str, prompt_key: str):
        self._cache.pop(f"{org_id}:{prompt_key}", None)


# ── Code prompt loader ──

def _load_all_prompt_modules() -> list[dict[str, Any]] | None:
    """Import all prompt modules and collect their PROMPTS lists.
    Returns None on failure so callers can distinguish "no prompts defined"
    from "import error — do not proceed with scan".
    """
    try:
        from agent.prompts import ALL_PROMPTS
        return list(ALL_PROMPTS)
    except (ImportError, AttributeError) as e:
        logger.warning("Could not import prompt modules: %s", e)
        return None
