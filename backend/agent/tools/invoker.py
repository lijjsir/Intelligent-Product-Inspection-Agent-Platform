"""ToolInvoker — unified tool execution with validation, timeout, error handling, and audit logging."""

from __future__ import annotations

import asyncio
import logging
import uuid
from time import perf_counter
from typing import Any

from agent.integrations.bk_aidev.approval_bridge import create_tool_approval
from agent.integrations.bk_aidev.tool_safety import (
    ToolSafetyPolicy,
    configured_tool_safety_policy,
    sanitize_tool_output,
)
from agent.tools.contracts import ToolContext, ToolResult
from agent.tools.registry import ToolRegistry


logger = logging.getLogger(__name__)


class ToolBlockedError(Exception):
    pass


class ToolApprovalRequired(ToolBlockedError):
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
            approval = None
            if isinstance(exc, ToolApprovalRequired):
                approval = await create_tool_approval(
                    db_session=self._db_session,
                    spec=spec,
                    arguments=arguments,
                    context=context,
                )
            return ToolResult(
                tool_name=tool_name, status="blocked",
                data={"approval": approval} if approval else None,
                error=str(exc), latency_ms=None,
            )

        try:
            handler = self._registry.get_handler(tool_name)
            data = await asyncio.wait_for(
                handler(arguments, context),
                timeout=spec.timeout_ms / 1000,
            )
            data = sanitize_tool_output(data, self._safety_policy(context))
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
            raise ToolApprovalRequired(
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
            from app.repositories.tool_repo import ToolRepository

            tool = await ToolRepository(self._db_session).get_by_tool_key(
                context.org_id,
                tool_name,
            )
            if tool is None:
                return execution_id
            input_redacted = sanitize_tool_output(arguments, self._safety_policy(context))
            obj = ToolExecution(
                id=execution_id,
                tool_name=tool_name,
                agent_id=None,
                tool_id=tool.id,
                task_id=self._execution_task_id(context, execution_id),
                call_index=0,
                input_payload=input_redacted,
                output_payload=data,
                status=status,
                error_message=error,
                latency_ms=latency_ms,
                trace_id=context.trace_id,
                execution_type="runtime",
                org_id=context.org_id,
                input_redacted=input_redacted,
                output_redacted=data,
            )
            self._db_session.add(obj)
            await self._db_session.flush()
        except Exception:
            logger.exception("failed to record tool execution tool_name=%s", tool_name)
        return execution_id

    @staticmethod
    def _execution_task_id(context: ToolContext, execution_id: str) -> str:
        value = str(context.request_id or context.workflow_run_id or "").strip()
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError):
            seed = f"{context.org_id}:{value or execution_id}"
            return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))

    @staticmethod
    def _safety_policy(context: ToolContext) -> ToolSafetyPolicy:
        contextual = context.metadata.get("sensitive_values") or []
        if isinstance(contextual, str):
            contextual = [contextual]
        return configured_tool_safety_policy(contextual)
