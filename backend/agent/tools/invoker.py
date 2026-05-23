"""ToolInvoker — unified tool execution with validation, timeout, error handling, and audit logging."""

from __future__ import annotations

import asyncio
import json
import uuid
from time import perf_counter
from typing import Any

from agent.tools.contracts import ToolContext, ToolResult
from agent.tools.registry import ToolRegistry


class ToolBlockedError(Exception):
    pass


class ToolInvoker:
    def __init__(self, registry: ToolRegistry, *, db_session: Any = None) -> None:
        self._registry = registry
        self._db_session = db_session

    async def invoke(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        # Expose db_session to handlers via context metadata
        if self._db_session is not None:
            context.metadata["__db_session__"] = self._db_session
        spec = self._registry.get(tool_name)
        started = perf_counter()

        try:
            self._validate_enabled(spec)
            self._validate_agent_scope(spec, context)
            self._validate_surface(spec, context)
            self._validate_mode(spec, context)
            self._validate_input_schema(spec, arguments)
            self._validate_confirmation(spec, context)
        except ToolBlockedError as exc:
            return ToolResult(
                tool_name=tool_name, status="blocked",
                error=str(exc), latency_ms=None,
            )

        try:
            handler = self._registry.get_handler(tool_name)
            data = await asyncio.wait_for(
                handler(arguments, context),
                timeout=spec.timeout_ms / 1000,
            )
            status = "success"
            error = None
        except asyncio.TimeoutError:
            data = None
            status = "failed"
            error = f"tool '{tool_name}' timed out after {spec.timeout_ms}ms"
        except Exception as exc:
            data = None
            status = "failed"
            error = str(exc)

        latency_ms = round((perf_counter() - started) * 1000)
        execution_id = await self._record_execution(
            tool_name=tool_name, arguments=arguments, context=context,
            status=status, data=data, error=error, latency_ms=latency_ms,
        )

        return ToolResult(
            tool_name=tool_name, status=status,
            data=data, error=error,
            execution_id=execution_id, latency_ms=latency_ms,
        )

    # ── Validation ──

    @staticmethod
    def _validate_enabled(spec) -> None:
        if not spec.enabled:
            raise ToolBlockedError(f"tool '{spec.name}' is disabled")

    @staticmethod
    def _validate_agent_scope(spec, context: ToolContext) -> None:
        if spec.agent_scope and context.agent and context.agent not in spec.agent_scope:
            raise ToolBlockedError(
                f"agent '{context.agent}' is not in tool '{spec.name}' scope"
            )

    @staticmethod
    def _validate_surface(spec, context: ToolContext) -> None:
        if spec.surfaces and context.surface and context.surface not in spec.surfaces:
            raise ToolBlockedError(
                f"surface '{context.surface}' not allowed for tool '{spec.name}'"
            )

    @staticmethod
    def _validate_mode(spec, context: ToolContext) -> None:
        if spec.mode == "action" and "action" not in context.allowed_modes:
            raise ToolBlockedError(
                f"action tool '{spec.name}' blocked: action mode not allowed on this surface"
            )

    @staticmethod
    def _validate_confirmation(spec, context: ToolContext) -> None:
        if spec.requires_confirmation and spec.name not in context.confirmed_actions:
            raise ToolBlockedError(
                f"tool '{spec.name}' requires confirmation before execution"
            )

    @staticmethod
    def _validate_input_schema(spec, arguments: dict[str, Any]) -> None:
        schema = spec.input_schema
        if not schema:
            return
        required = schema.get("required") or []
        for field in required:
            if field not in arguments or arguments[field] is None:
                raise ToolBlockedError(
                    f"tool '{spec.name}' missing required parameter: '{field}'"
                )

    # ── Execution recording ──

    async def _record_execution(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolContext,
        status: str,
        data: dict[str, Any] | None,
        error: str | None,
        latency_ms: int,
    ) -> str | None:
        execution_id = str(uuid.uuid4())
        if self._db_session is None:
            return execution_id

        try:
            from app.models.tool import ToolExecution
            obj = ToolExecution(
                id=execution_id,
                tool_name=tool_name,
                agent_id="",
                tool_id="",
                agent_name=context.agent or "",
                task_id=context.request_id or "",
                call_index=0,
                input_payload=arguments,
                output_payload=data,
                status=status,
                error_message=error,
                latency_ms=latency_ms,
                trace_id=context.trace_id,
                execution_type="runtime",
                org_id=context.org_id,
            )
            self._db_session.add(obj)
            await self._db_session.flush()
        except Exception:
            pass
        return execution_id
