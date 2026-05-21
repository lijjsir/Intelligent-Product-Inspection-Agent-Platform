"""ToolSyncService scans built-in tool manifests and syncs them into definition/version tables."""

from __future__ import annotations

import hashlib
import importlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.models.tool import ToolDefinition, ToolSyncEvent, ToolVersion
from app.repositories.tool_repo import ToolRepository
from app.repositories.tool_version_repo import ToolVersionRepository

BUILTIN_MODULES = [
    "agent.tools.builtin.rag_tools",
    "agent.tools.builtin.file_tools",
    "agent.tools.builtin.inspection_tools",
    "agent.tools.builtin.report_tools",
]


class ToolSyncService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = ToolRepository(session)
        self._version_repo = ToolVersionRepository(session)

    async def scan_and_sync(self) -> dict[str, Any]:
        manifests = self.collect_manifests()
        results = {"created": 0, "updated": 0, "unchanged": 0, "details": []}

        for manifest in manifests:
            result = await self._sync_one(manifest)
            results["details"].append(result)
            results[result["action"]] += 1

        return results

    def preview_manifests(self) -> list[dict[str, Any]]:
        return self.collect_manifests()

    @staticmethod
    def collect_manifests() -> list[dict[str, Any]]:
        manifests = []
        for module_name in BUILTIN_MODULES:
            try:
                module = importlib.import_module(module_name)
                manifests.extend(getattr(module, "TOOL_MANIFESTS", []))
            except ImportError:
                continue
        return manifests

    async def _sync_one(self, manifest: dict[str, Any]) -> dict[str, Any]:
        tool_key = manifest["tool_key"]
        manifest_hash = self._hash_manifest(manifest)
        existing = await self._repo.get_by_tool_key(self._org_id, tool_key)

        if not existing:
            tool = ToolDefinition(
                id=str(uuid7()),
                org_id=self._org_id,
                tool_key=tool_key,
                display_name=manifest["display_name"],
                description=manifest.get("description") or "",
                category=manifest.get("category") or self._derive_category(tool_key),
                tool_type=manifest.get("tool_type") or "native",
                status="active",
                risk_level=manifest.get("risk_level") or "low",
                is_readonly=bool(manifest.get("is_readonly", True)),
                source_type="builtin",
                source_ref=manifest.get("handler_path"),
                manifest_hash=manifest_hash,
                health_status="unknown",
                created_by=None,
            )
            tool = await self._repo.create(tool)

            version = await self._create_version(tool, manifest, version="1.0.0", status="active")
            await self._repo.save(tool, {"active_version_id": version.id})
            await self._write_sync_event(tool.id, "created", None, manifest_hash, f"builtin tool {tool_key} created")
            return {"tool_key": tool_key, "action": "created"}

        if existing.manifest_hash != manifest_hash:
            old_hash = existing.manifest_hash
            await self._repo.save(
                existing,
                {
                    "display_name": manifest["display_name"],
                    "description": manifest.get("description") or "",
                    "category": manifest.get("category") or existing.category,
                    "tool_type": manifest.get("tool_type") or existing.tool_type,
                    "risk_level": manifest.get("risk_level") or existing.risk_level,
                    "is_readonly": bool(manifest.get("is_readonly", existing.is_readonly)),
                    "source_type": "builtin",
                    "source_ref": manifest.get("handler_path"),
                    "manifest_hash": manifest_hash,
                },
            )
            version = await self._create_version(
                existing,
                manifest,
                version=await self._next_version(existing),
                status="active",
            )
            await self._repo.save(existing, {"active_version_id": version.id})
            await self._write_sync_event(existing.id, "updated", old_hash, manifest_hash, f"builtin tool {tool_key} updated")
            return {"tool_key": tool_key, "action": "updated"}

        return {"tool_key": tool_key, "action": "unchanged"}

    async def _create_version(
        self,
        tool: ToolDefinition,
        manifest: dict[str, Any],
        *,
        version: str,
        status: str,
    ) -> ToolVersion:
        record = ToolVersion(
            id=str(uuid7()),
            org_id=self._org_id,
            tool_id=tool.id,
            version=version,
            display_name=manifest["display_name"],
            description=manifest.get("description") or "",
            endpoint=manifest.get("endpoint"),
            method=manifest.get("method"),
            handler_path=manifest.get("handler_path"),
            parameters_schema=manifest.get("parameters_schema") or {"type": "object", "properties": {}},
            returns_schema=manifest.get("returns_schema") or {"type": "object", "properties": {}},
            auth_type=manifest.get("auth_type") or "none",
            secret_ref=manifest.get("secret_ref"),
            timeout_ms=int(manifest.get("timeout_ms") or 30000),
            retry_policy=manifest.get("retry_policy"),
            rate_limit_rpm=int(manifest.get("rate_limit_rpm") or 60),
            status=status,
            created_by=None,
        )
        return await self._version_repo.create(record)

    async def _next_version(self, tool: ToolDefinition) -> str:
        versions = await self._version_repo.list_by_tool(self._org_id, tool.id)
        if not versions:
            return "1.0.0"

        parts = versions[0].version.split(".")
        while len(parts) < 3:
            parts.append("0")
        try:
            major, minor, patch = (int(part) for part in parts[:3])
        except ValueError:
            return f"{versions[0].version}.1"
        return f"{major}.{minor}.{patch + 1}"

    async def _write_sync_event(
        self,
        tool_id: str,
        event_type: str,
        old_hash: str | None,
        new_hash: str | None,
        message: str,
    ) -> None:
        event = ToolSyncEvent(
            id=str(uuid7()),
            org_id=self._org_id,
            tool_id=tool_id,
            event_type=event_type,
            source_type="builtin",
            old_hash=old_hash,
            new_hash=new_hash,
            message=message,
        )
        self._session.add(event)
        await self._session.flush()

    @staticmethod
    def _hash_manifest(manifest: dict[str, Any]) -> str:
        canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @staticmethod
    def _derive_category(tool_key: str) -> str:
        if tool_key.startswith("rag."):
            return "RAG"
        if tool_key.startswith("file."):
            return "file_parse"
        if tool_key.startswith("report."):
            return "report_gen"
        return "inspection_calc"
