from __future__ import annotations

import importlib
import inspect
import json
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import uuid7
from app.models.tool import AgentToolBinding, ToolDefinition, ToolExecution, ToolRuntimeEvent, ToolVersion
from app.repositories.tool_binding_repo import ToolBindingRepository
from app.repositories.tool_repo import ToolRepository
from app.repositories.tool_version_repo import ToolVersionRepository
from app.services.tool_sync_service import ToolSyncService


class ToolService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = ToolRepository(session)
        self._binding_repo = ToolBindingRepository(session)
        self._version_repo = ToolVersionRepository(session)

    async def create_tool(self, payload: dict[str, Any]) -> ToolDefinition:
        body = dict(payload)

        existing = await self._repo.get_by_tool_key(self._org_id, body["tool_key"])
        if existing:
            raise ValidationError(f"tool {body['tool_key']} already exists")

        tool = ToolDefinition(
            id=str(uuid7()),
            org_id=self._org_id,
            tool_key=body["tool_key"],
            display_name=body["display_name"],
            description=body.get("description") or "",
            category=body.get("category") or "inspection_calc",
            tool_type=body.get("tool_type") or "native",
            status="active",
            risk_level=body.get("risk_level") or "low",
            is_readonly=bool(body.get("is_readonly", True)),
            source_type=body.get("source_type") or "manual",
            source_ref=body.get("source_ref"),
            manifest_hash=body.get("manifest_hash"),
            health_status="unknown",
            created_by=None,
        )
        tool = await self._repo.create(tool)

        version = ToolVersion(
            id=str(uuid7()),
            org_id=self._org_id,
            tool_id=tool.id,
            version=body.get("version") or "1.0.0",
            display_name=tool.display_name,
            description=tool.description,
            endpoint=body.get("endpoint"),
            method=body.get("method"),
            handler_path=body.get("handler_path"),
            parameters_schema=body.get("parameters_schema") or {"type": "object", "properties": {}},
            returns_schema=body.get("returns_schema") or {"type": "object", "properties": {}},
            auth_type=body.get("auth_type") or "none",
            secret_ref=body.get("secret_ref"),
            timeout_ms=int(body.get("timeout_ms") or 30000),
            retry_policy=body.get("retry_policy"),
            rate_limit_rpm=int(body.get("rate_limit_rpm") or 60),
            status="active",
            created_by=None,
        )
        version = await self._version_repo.create(version)
        await self._repo.save(tool, {"active_version_id": version.id})
        return tool

    async def list_active(self) -> list[ToolDefinition]:
        return await self._repo.list_active(self._org_id)

    async def list_tools(self, payload: dict[str, Any]) -> dict[str, Any]:
        page = int(payload.get("page") or 1)
        size = int(payload.get("size") or 12)

        tools = await self._repo.list_all(self._org_id)
        bindings = await self._binding_repo.list_all(self._org_id)
        versions = await self._resolve_active_versions(tools)
        today_executions = await self._repo.list_recent_executions(
            self._org_id,
            since=datetime.utcnow() - timedelta(days=1),
        )

        summaries = self._build_execution_summary(today_executions)
        binding_map = self._build_binding_map(bindings)

        items = [
          self._serialize_tool(tool, versions.get(tool.id), summaries.get(tool.id, {}), binding_map.get(tool.id, []))
          for tool in tools
        ]
        items = self._filter_tools(items, payload)

        total = len(items)
        start = (page - 1) * size
        return {"items": items[start:start + size], "total": total, "page": page, "size": size}

    async def get_tool_detail(self, tool_id: str) -> dict[str, Any]:
        tool = await self._repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")

        active_version = await self._get_active_version(tool)
        today_executions = await self._repo.list_recent_executions(
            self._org_id,
            tool_id=tool_id,
            since=datetime.utcnow() - timedelta(days=1),
        )
        recent_executions = await self._repo.list_executions(
            self._org_id,
            tool_id=tool_id,
            page=1,
            size=50,
        )
        versions = await self._version_repo.list_by_tool(self._org_id, tool_id)
        bindings = await self._binding_repo.list_by_tool(self._org_id, tool_id)
        summary = self._build_execution_summary(today_executions).get(tool.id, {})

        detail = self._serialize_tool(tool, active_version, summary, bindings)
        detail["active_version_id"] = active_version.id if active_version else ""
        detail["versions"] = [self._serialize_version(version) for version in versions]
        detail["executions"] = [self._serialize_execution(item) for item in recent_executions]
        detail["bindings"] = [self._serialize_binding(binding, tool, versions) for binding in bindings]
        detail["endpoint"] = active_version.endpoint if active_version else None
        detail["method"] = self._derive_method(active_version)
        detail["handler_path"] = self._resolve_handler_path(tool, active_version)
        detail["parameters_schema"] = active_version.parameters_schema if active_version else {}
        detail["returns_schema"] = active_version.returns_schema if active_version else {}
        detail["auth_type"] = active_version.auth_type if active_version else "none"
        detail["secret_ref"] = active_version.secret_ref if active_version else None
        detail["timeout_ms"] = active_version.timeout_ms if active_version else 30000
        detail["retry_policy"] = active_version.retry_policy if active_version else None
        detail["rate_limit_rpm"] = active_version.rate_limit_rpm if active_version else 60
        detail["audit_logs"] = []
        return detail

    async def update_tool(self, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        tool = await self._repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")

        allowed = {"display_name", "description", "category", "risk_level", "is_readonly"}
        updates = {k: v for k, v in payload.items() if k in allowed and v is not None}
        if updates:
            tool = await self._repo.save(tool, updates)

        active_version = await self._get_active_version(tool)
        bindings = await self._binding_repo.list_by_tool(self._org_id, tool.id)
        return self._serialize_tool(tool, active_version, {}, bindings)

    async def update_tool_status(self, tool_id: str, new_status: str) -> dict[str, Any]:
        tool = await self._repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")

        normalized = new_status.strip().lower()
        valid = {"active", "disabled", "draft", "deprecated", "deleted"}
        if normalized not in valid:
            raise ValidationError(f"invalid status {normalized}, must be one of {valid}")

        tool = await self._repo.save(tool, {"status": normalized})
        active_version = await self._get_active_version(tool)
        bindings = await self._binding_repo.list_by_tool(self._org_id, tool.id)
        return self._serialize_tool(tool, active_version, {}, bindings)

    async def get_overview(self) -> dict[str, Any]:
        tools = await self._repo.list_all(self._org_id)
        bindings = await self._binding_repo.list_all(self._org_id)
        versions = await self._resolve_active_versions(tools)
        recent = await self._repo.list_recent_executions(
            self._org_id,
            since=datetime.utcnow() - timedelta(days=1),
        )

        summaries = self._build_execution_summary(recent)
        binding_map = self._build_binding_map(bindings)
        serialized = [
            self._serialize_tool(tool, versions.get(tool.id), summaries.get(tool.id, {}), binding_map.get(tool.id, []))
            for tool in tools
        ]
        bucketed = self._build_trends(recent)
        total_calls = len(recent)
        avg_latency = int(mean([r.latency_ms for r in recent if r.latency_ms is not None])) if recent else 0

        top_failing = sorted(
            (
                {
                    "tool_id": s["id"],
                    "tool_name": s["display_name"],
                    "failure_count": s["_failure_count"],
                    "failure_rate": round(1 - s["success_rate"], 4) if s["success_rate"] else 0.0,
                }
                for s in serialized
                if s["_failure_count"] > 0
            ),
            key=lambda x: (-x["failure_count"], x["tool_name"]),
        )[:5]

        high_latency = sorted(
            (
                {
                    "tool_id": s["id"],
                    "tool_name": s["display_name"],
                    "avg_latency_ms": s["avg_latency_ms"],
                }
                for s in serialized
                if s["avg_latency_ms"] > 0
            ),
            key=lambda x: (-x["avg_latency_ms"], x["tool_name"]),
        )[:5]

        pending_risk = [
            {"tool_id": s["id"], "tool_name": s["display_name"], "risk_level": s["risk_level"]}
            for s in serialized
            if s["risk_level"] == "high" and s["status"] != "active"
        ][:5]

        critical_dependencies = sorted(
            (
                {
                    "tool_id": s["id"],
                    "tool_name": s["display_name"],
                    "dependent_agents": len(s["bound_agent_names"]),
                }
                for s in serialized
                if s["bound_agent_names"]
            ),
            key=lambda x: (-x["dependent_agents"], x["tool_name"]),
        )[:5]

        return {
            "total_tools": len(serialized),
            "active_tools": sum(1 for s in serialized if s["status"] == "active"),
            "error_tools": sum(1 for s in serialized if s["health_status"] in {"degraded", "unhealthy"}),
            "today_calls": total_calls,
            "avg_latency_ms": avg_latency,
            "high_risk_tools": sum(1 for s in serialized if s["risk_level"] == "high"),
            "call_trend": bucketed["call_trend"],
            "health_distribution": {
                "healthy": sum(1 for s in serialized if s["health_status"] == "healthy"),
                "degraded": sum(1 for s in serialized if s["health_status"] == "degraded"),
                "unhealthy": sum(1 for s in serialized if s["health_status"] == "unhealthy"),
                "unknown": sum(1 for s in serialized if s["health_status"] == "unknown"),
            },
            "error_trend": bucketed["error_trend"],
            "top_failing": top_failing,
            "high_latency": high_latency,
            "pending_risk_tools": pending_risk,
            "critical_dependencies": critical_dependencies,
        }

    async def list_executions(self, payload: dict[str, Any]) -> dict[str, Any]:
        page = int(payload.get("page") or 1)
        size = int(payload.get("size") or 20)
        rows = await self._repo.list_executions(
            self._org_id,
            tool_id=payload.get("tool_id"),
            agent_id=payload.get("agent_id"),
            status=payload.get("status"),
            execution_type=payload.get("execution_type"),
            page=page,
            size=size,
        )
        total = await self._repo.count_executions(
            self._org_id,
            tool_id=payload.get("tool_id"),
            agent_id=payload.get("agent_id"),
            status=payload.get("status"),
            execution_type=payload.get("execution_type"),
        )
        return {"items": [self._serialize_execution(r) for r in rows], "total": total, "page": page, "size": size}

    async def get_execution_overview(self) -> dict[str, Any]:
        recent = await self._repo.list_recent_executions(
            self._org_id,
            since=datetime.utcnow() - timedelta(days=1),
        )
        successes = sum(1 for r in recent if r.status == "success")
        avg_latency = int(mean([r.latency_ms for r in recent if r.latency_ms is not None])) if recent else 0
        trends = self._build_trends(recent)
        return {
            "today_calls": len(recent),
            "success_rate": round(successes / len(recent), 4) if recent else 0.0,
            "avg_latency_ms": avg_latency,
            "failed_count": sum(1 for r in recent if r.status != "success"),
            **trends,
        }

    async def test_tool(self, tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
        tool = await self._repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")

        version = await self._get_active_version(tool)
        if not version:
            raise ValidationError("tool has no active version")

        execution_id = str(uuid7())
        started_at = datetime.utcnow()
        trace_id = f"tool-test-{tool.id}-{uuid7()}"
        status = "success"
        output = None
        error = None

        self._session.add(
            ToolRuntimeEvent(
                id=str(uuid7()),
                org_id=self._org_id,
                event_type="tool.execution.started",
                tool_id=tool.id,
                execution_id=execution_id,
                payload={
                    "tool_id": tool.id,
                    "tool_name": tool.display_name,
                    "trace_id": trace_id,
                },
            )
        )

        try:
            missing = self._validate_required_params(version.parameters_schema or {}, params)
            if missing:
                raise ValidationError(f"missing required parameters: {', '.join(missing)}")
            output = await self._execute_tool_for_test(tool, version, params)
        except Exception as exc:
            status = "failed"
            error = str(exc)

        duration_ms = max(1, int((datetime.utcnow() - started_at).total_seconds() * 1000))
        await self._repo.create_execution(
            ToolExecution(
                id=execution_id,
                task_id=str(uuid7()),
                org_id=self._org_id,
                tool_id=tool.id,
                tool_name=tool.display_name,
                call_index=0,
                input_payload=params,
                output_payload=output if status == "success" else None,
                status=status,
                error_message=error,
                latency_ms=duration_ms,
                execution_type="test",
                trace_id=trace_id,
                input_redacted=params,
                output_redacted=output if status == "success" else None,
            )
        )

        event_type = "tool.execution.completed" if status == "success" else "tool.execution.failed"
        self._session.add(
            ToolRuntimeEvent(
                id=str(uuid7()),
                org_id=self._org_id,
                event_type=event_type,
                tool_id=tool.id,
                execution_id=execution_id,
                payload={
                    "tool_id": tool.id,
                    "tool_name": tool.display_name,
                    "trace_id": trace_id,
                    "status": status,
                    "duration_ms": duration_ms,
                },
            )
        )
        await self._session.flush()

        return {
            "status": status,
            "duration_ms": duration_ms,
            "output": output,
            "error": error,
            "trace_id": trace_id,
        }

    async def _resolve_active_versions(self, tools: list[ToolDefinition]) -> dict[str, ToolVersion | None]:
        resolved: dict[str, ToolVersion | None] = {}
        for tool in tools:
            resolved[tool.id] = await self._get_active_version(tool)
        return resolved

    async def _get_active_version(self, tool: ToolDefinition) -> ToolVersion | None:
        if tool.active_version_id:
            version = await self._version_repo.get(self._org_id, tool.active_version_id)
            if version:
                return version

        versions = await self._version_repo.list_by_tool(self._org_id, tool.id)
        return versions[0] if versions else None

    async def _execute_tool_for_test(
        self,
        tool: ToolDefinition,
        version: ToolVersion,
        params: dict[str, Any],
    ) -> Any:
        tool_type = (tool.tool_type or self._derive_type_fallback(tool, version)).lower()

        if tool_type in {"native", "rag"}:
            handler_path = self._resolve_handler_path(tool, version)
            if not handler_path:
                raise ValidationError("tool handler is not configured")
            module_path, func_name = handler_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            handler = getattr(module, func_name)
            result = handler(**params)
            if inspect.isawaitable(result):
                return await result
            return result

        if tool_type in {"http", "openapi", "mcp"}:
            if not version.endpoint:
                raise ValidationError("tool endpoint is not configured")
            method = (self._derive_method(version) or "POST").upper()
            async with httpx.AsyncClient(timeout=version.timeout_ms / 1000) as client:
                response = await client.request(method, version.endpoint, json=params)
                response.raise_for_status()
                if "application/json" in response.headers.get("content-type", ""):
                    return response.json()
                return {"text": response.text}

        raise ValidationError(f"tool type {tool.tool_type} is not supported")

    def _serialize_tool(
        self,
        tool: ToolDefinition,
        version: ToolVersion | None,
        summary: dict[str, Any],
        bindings: list[AgentToolBinding],
    ) -> dict[str, Any]:
        success_rate = summary.get("success_rate", 0.0)
        health = tool.health_status or "unknown"
        if tool.status == "active" and health == "unknown":
            calls = summary.get("total_calls", 0)
            if calls > 0:
                health = "healthy" if success_rate >= 0.95 else "degraded" if success_rate >= 0.7 else "unhealthy"

        return {
            "id": tool.id,
            "tool_key": tool.tool_key,
            "display_name": tool.display_name,
            "description": tool.description or "",
            "category": tool.category or self._derive_category_fallback(tool),
            "tool_type": tool.tool_type or self._derive_type_fallback(tool, version),
            "status": tool.status,
            "risk_level": tool.risk_level,
            "is_readonly": bool(tool.is_readonly),
            "source_type": tool.source_type,
            "health_status": health,
            "active_version": version.version if version else "draft",
            "bound_agent_names": [binding.agent_id for binding in bindings if binding.binding_status == "active"],
            "today_calls": summary.get("total_calls", 0),
            "success_rate": success_rate,
            "avg_latency_ms": summary.get("avg_latency_ms", 0),
            "created_at": tool.created_at,
            "updated_at": tool.updated_at,
            "_failure_count": summary.get("failure_count", 0),
        }

    def _serialize_version(self, version: ToolVersion) -> dict[str, Any]:
        return {
            "id": version.id,
            "tool_id": version.tool_id,
            "version": version.version,
            "display_name": version.display_name,
            "description": version.description or "",
            "endpoint": version.endpoint,
            "method": version.method,
            "handler_path": version.handler_path,
            "parameters_schema": version.parameters_schema or {},
            "returns_schema": version.returns_schema or {},
            "auth_type": version.auth_type,
            "timeout_ms": version.timeout_ms,
            "retry_policy": version.retry_policy,
            "rate_limit_rpm": version.rate_limit_rpm,
            "status": version.status,
            "created_by": version.created_by or "system",
            "created_at": version.created_at,
            "updated_at": version.updated_at,
        }

    def _serialize_binding(
        self,
        binding: AgentToolBinding,
        tool: ToolDefinition,
        versions: list[ToolVersion],
    ) -> dict[str, Any]:
        version_map = {version.id: version for version in versions}
        version = version_map.get(binding.tool_version_id)
        return {
            "id": binding.id,
            "agent_id": binding.agent_id,
            "agent_name": binding.agent_id,
            "tool_id": binding.tool_id,
            "tool_name": tool.display_name,
            "tool_version_id": binding.tool_version_id,
            "tool_version": version.version if version else "unknown",
            "binding_status": binding.binding_status,
            "auto_call_enabled": binding.auto_call_enabled,
            "approval_required": binding.approval_required,
            "allowed_scenarios": binding.allowed_intents or [],
            "rate_limit": None,
            "created_at": binding.created_at,
            "updated_at": binding.updated_at,
        }

    def _serialize_execution(self, item: ToolExecution) -> dict[str, Any]:
        return {
            "id": item.id,
            "tool_id": item.tool_id,
            "tool_name": item.tool_name,
            "agent_id": item.agent_id or "",
            "agent_name": item.agent_id or "未绑定",
            "task_id": item.task_id,
            "execution_type": item.execution_type or "runtime",
            "status": item.status,
            "duration_ms": int(item.latency_ms or 0),
            "input_summary": self._summarize_payload(item.input_redacted or item.input_payload),
            "output_summary": self._summarize_payload(item.output_redacted or item.output_payload),
            "error_message": item.error_message,
            "trace_id": item.trace_id or f"trace-{item.tool_id}-{item.id}",
            "created_at": item.created_at,
        }

    @staticmethod
    def _build_binding_map(bindings: list[AgentToolBinding]) -> dict[str, list[AgentToolBinding]]:
        grouped: dict[str, list[AgentToolBinding]] = defaultdict(list)
        for binding in bindings:
            grouped[binding.tool_id].append(binding)
        return grouped

    @staticmethod
    def _validate_required_params(schema: dict[str, Any], params: dict[str, Any]) -> list[str]:
        return [key for key in (schema.get("required") or []) if key not in params]

    def _filter_tools(self, items: list[dict[str, Any]], payload: dict[str, Any]) -> list[dict[str, Any]]:
        keyword = str(payload.get("keyword") or "").strip().lower()
        category = payload.get("category")
        status = payload.get("status")
        risk_level = payload.get("risk_level")
        source_type = payload.get("source_type")
        health_status = payload.get("health_status")
        has_binding = payload.get("has_binding")

        filtered = items
        if keyword:
            filtered = [
                item
                for item in filtered
                if keyword in item["display_name"].lower()
                or keyword in item["tool_key"].lower()
                or keyword in item["description"].lower()
            ]
        if category:
            filtered = [item for item in filtered if item["category"] == category]
        if status:
            filtered = [item for item in filtered if item["status"] == status]
        if risk_level:
            filtered = [item for item in filtered if item["risk_level"] == risk_level]
        if source_type:
            filtered = [item for item in filtered if item["source_type"] == source_type]
        if health_status:
            filtered = [item for item in filtered if item["health_status"] == health_status]
        if has_binding is not None:
            filtered = [item for item in filtered if (len(item["bound_agent_names"]) > 0) is bool(has_binding)]
        return filtered

    def _build_execution_summary(self, executions: list[ToolExecution]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[ToolExecution]] = defaultdict(list)
        for execution in executions:
            grouped[execution.tool_id].append(execution)

        summary: dict[str, dict[str, Any]] = {}
        for tool_id, rows in grouped.items():
            successes = sum(1 for row in rows if row.status == "success")
            latencies = [int(row.latency_ms) for row in rows if row.latency_ms is not None]
            summary[tool_id] = {
                "total_calls": len(rows),
                "success_rate": round(successes / len(rows), 4) if rows else 0.0,
                "avg_latency_ms": int(mean(latencies)) if latencies else 0,
                "failure_count": len(rows) - successes,
            }
        return summary

    def _build_trends(self, executions: list[ToolExecution]) -> dict[str, list[dict[str, Any]]]:
        now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        buckets = [now - timedelta(hours=hour) for hour in range(23, -1, -1)]
        calls: dict[datetime, int] = {bucket: 0 for bucket in buckets}
        errors: dict[datetime, int] = {bucket: 0 for bucket in buckets}
        latency: dict[datetime, list[int]] = {bucket: [] for bucket in buckets}

        for execution in executions:
            bucket = execution.created_at.replace(minute=0, second=0, microsecond=0)
            if bucket not in calls:
                continue
            calls[bucket] += 1
            if execution.status != "success":
                errors[bucket] += 1
            if execution.latency_ms is not None:
                latency[bucket].append(int(execution.latency_ms))

        return {
            "call_trend": [{"time": bucket.isoformat(), "value": calls[bucket]} for bucket in buckets],
            "error_trend": [{"time": bucket.isoformat(), "value": errors[bucket]} for bucket in buckets],
            "latency_trend": [
                {"time": bucket.isoformat(), "value": int(mean(latency[bucket])) if latency[bucket] else 0}
                for bucket in buckets
            ],
        }

    @staticmethod
    def _summarize_payload(payload: Any) -> str:
        if payload is None:
            return ""
        text = json.dumps(payload, ensure_ascii=False)
        return text if len(text) <= 160 else text[:157] + "..."

    @staticmethod
    def _derive_method(version: ToolVersion | None) -> str | None:
        if not version:
            return None
        return version.method or ("POST" if version.endpoint else None)

    @staticmethod
    def _resolve_handler_path(tool: ToolDefinition, version: ToolVersion | None) -> str | None:
        if version and version.handler_path:
            return version.handler_path
        manifests = ToolSyncService.collect_manifests()
        manifest = next((item for item in manifests if item.get("tool_key") == tool.tool_key), None)
        if manifest and manifest.get("handler_path"):
            return str(manifest["handler_path"])
        return ToolService._derive_handler_path(tool)

    @staticmethod
    def _derive_handler_path(tool: ToolDefinition) -> str | None:
        return f"agent.tools.{tool.tool_key.replace('.', '_')}"

    @staticmethod
    def _derive_category_fallback(tool: ToolDefinition) -> str:
        name = (tool.tool_key or "").lower()
        if name.startswith("rag."):
            return "RAG"
        if name.startswith("db.") or "database" in name:
            return "database"
        if "report" in name:
            return "report_gen"
        if "file" in name or "parse" in name:
            return "file_parse"
        return "inspection_calc"

    @staticmethod
    def _derive_type_fallback(tool: ToolDefinition, version: ToolVersion | None) -> str:
        if tool.tool_type:
            return tool.tool_type
        return "http" if version and version.endpoint else "native"
