from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, Callable

from agent.adapters.base import BaseAgentAdapter
from agent.contracts.quality_contracts import NormalizedAttachment, NormalizedRequest
from agent.response.trust_protocol import build_trust_answer_protocol
from agent.router.agent_manager import AgentManager
from agent.router.manager_provider import get_agent_manager
from app.core.ids import uuid7

logger = logging.getLogger(__name__)


class PipelineAgentResponse(str):
    """String-compatible adapter result carrying auditable response metadata."""

    metadata: dict[str, Any]

    def __new__(cls, content: str, metadata: dict[str, Any] | None = None):
        value = super().__new__(cls, str(content or ""))
        value.metadata = dict(metadata or {})
        return value


class PipelineAgentAdapter(BaseAgentAdapter):
    """Bridge a meeting agent to the unified ManagerLoop execution pipeline.

    The meeting service historically expects an adapter to return a string. A
    ``PipelineAgentResponse`` keeps that contract while carrying route,
    citation, trust, and degradation metadata to the persistence layer.
    """

    def __init__(self, manager: AgentManager | None = None) -> None:
        self._manager = manager

    async def invoke(
        self,
        *,
        room_id: str,
        agent_def: Any,
        query: str,
        context_messages: list[dict[str, str]],
        emit: Callable,
        runtime_model: dict[str, Any] | None = None,
        request_context: dict[str, Any] | None = None,
        db_session: Any = None,
    ) -> str:
        context = self._context_for_request(
            room_id=room_id,
            agent_def=agent_def,
            request_context=request_context,
            context_messages=context_messages,
            runtime_model=runtime_model,
        )
        context["query"] = str(query or "")
        await self._emit(
            emit,
            {
                "event": "agent_pipeline_started",
                "room_id": room_id,
                "workflow_run_id": context["workflow_run_id"],
                "agent_id": context.get("agent_id"),
                "agent_name": context.get("agent_name"),
                "adapter_type": "pipeline",
            },
        )
        try:
            output = await self._run_manager(context, db_session=db_session)
            response = self._response_from_output(output, question=query, context=context)
        except asyncio.TimeoutError as exc:
            response = self._failure_response(
                query,
                context,
                status="failed",
                code="PIPELINE_TIMEOUT",
                message="统一 Agent 执行超时，请稍后重试。",
                raw_error=str(exc),
            )
        except Exception as exc:
            logger.exception(
                "pipeline agent invocation failed room_id=%s workflow_run_id=%s",
                room_id,
                context["workflow_run_id"],
            )
            response = self._failure_response(
                query,
                context,
                status="failed",
                code="PIPELINE_EXECUTION_FAILED",
                message="统一 Agent 执行失败，请稍后重试。",
                raw_error=str(exc),
            )

        metadata = dict(getattr(response, "metadata", {}) or {})
        await self._emit(
            emit,
            {
                "event": "agent_pipeline_completed",
                "room_id": room_id,
                "message_id": context.get("assistant_message_id"),
                "workflow_run_id": context["workflow_run_id"],
                "agent_id": context.get("agent_id"),
                "agent_name": context.get("agent_name"),
                "adapter_type": "pipeline",
                "status": metadata.get("pipeline_status", "failed"),
                "selected_subgraph": metadata.get("selected_subgraph"),
                "trust_protocol": metadata.get("trust_protocol"),
                "citations": metadata.get("citations", []),
                "degrade_reason": metadata.get("degrade_reason"),
            },
        )
        await self._emit_deltas(
            emit,
            content=str(response),
            room_id=room_id,
            message_id=context.get("assistant_message_id"),
            workflow_run_id=context["workflow_run_id"],
        )
        return response

    async def should_participate(
        self,
        *,
        agent_def: Any,
        messages_since_last: int,
        seconds_since_last: float,
        recent_content: str,
    ) -> bool:
        # Participation policy is deliberately adapter-independent. Keeping
        # the same policy as the direct LLM adapter avoids changing meeting
        # behavior when an agent is migrated to the pipeline backend.
        strategy = getattr(agent_def, "participation_strategy", None) or {}
        if not strategy.get("auto_reply", True):
            return False
        if seconds_since_last < int(strategy.get("cooldown_seconds", 30)):
            return False
        strategies = strategy.get("strategies", {})
        message_count = strategies.get("message_count", {})
        if message_count.get("enabled") and messages_since_last >= int(message_count.get("every_n_messages", 5)):
            return True
        silence_timer = strategies.get("silence_timer", {})
        if silence_timer.get("enabled") and seconds_since_last >= int(silence_timer.get("after_seconds", 300)):
            return True
        topic_match = strategies.get("topic_match", {})
        keywords = [str(item).lower() for item in list(topic_match.get("keywords", [])) if str(item).strip()]
        return bool(topic_match.get("enabled") and keywords and any(item in recent_content.lower() for item in keywords))

    async def generate_autonomous_reply(
        self,
        *,
        room_id: str,
        agent_def: Any,
        recent_messages: list[dict[str, str]],
        emit: Callable,
        runtime_model: dict[str, Any] | None = None,
        request_context: dict[str, Any] | None = None,
        db_session: Any = None,
    ) -> str:
        context = dict(request_context or {})
        context.setdefault("request_id", str(uuid7()))
        context.setdefault("workflow_run_id", str(uuid7()))
        context.setdefault("assistant_message_id", str(uuid7()))
        return await self.invoke(
            room_id=room_id,
            agent_def=agent_def,
            query="基于最近会议上下文主动提醒",
            context_messages=recent_messages,
            emit=emit,
            runtime_model=runtime_model,
            request_context=context,
            db_session=db_session,
        )

    async def _run_manager(self, context: dict[str, Any], *, db_session: Any = None) -> Any:
        manager = self._manager or get_agent_manager()
        request = self._build_request(context)
        if db_session is not None or self._manager is not None:
            return await manager.run(request, db_session=db_session)

        # A real manager needs a live session for model selection, memory
        # retrieval, governance, and candidate extraction. Open it here so
        # the meeting's read session can safely finish before execution.
        from infra.database.session import get_session

        async with get_session() as session:
            return await manager.run(request, db_session=session)

    @staticmethod
    def _build_request(context: dict[str, Any]) -> NormalizedRequest:
        attachments = []
        for item in list(context.get("attachments") or []):
            if isinstance(item, NormalizedAttachment):
                attachments.append(item)
            elif isinstance(item, dict):
                try:
                    attachments.append(NormalizedAttachment.model_validate(item))
                except Exception:
                    continue
        return NormalizedRequest(
            request_kind="chat",
            request_id=str(context["request_id"]),
            workflow_run_id=str(context["workflow_run_id"]),
            session_id=str(context.get("session_id") or f"meeting:{context['room_id']}"),
            assistant_message_id=str(context.get("assistant_message_id") or ""),
            org_id=str(context.get("org_id") or "meeting-org"),
            user_id=str(context.get("user_id") or "") or None,
            workspace="meeting_room",
            plan_tier=str(context.get("plan_tier") or "basic"),
            capabilities=list(context.get("capabilities") or []),
            query=str(context.get("query") or ""),
            metadata=dict(context.get("metadata") or {}),
            ext=dict(context.get("ext") or {}),
            attachments=attachments,
            image_urls=[str(item) for item in list(context.get("image_urls") or []) if str(item).strip()],
            route_hints=dict(context.get("route_hints") or {}),
        )

    @staticmethod
    def _context_for_request(
        *,
        room_id: str,
        agent_def: Any,
        request_context: dict[str, Any] | None,
        context_messages: list[dict[str, str]],
        runtime_model: dict[str, Any] | None,
    ) -> dict[str, Any]:
        context = dict(request_context or {})
        context.setdefault("room_id", room_id)
        context.setdefault("request_id", str(uuid7()))
        context.setdefault("workflow_run_id", str(uuid7()))
        context.setdefault("assistant_message_id", str(uuid7()))
        context.setdefault("session_id", f"meeting:{room_id}")
        context.setdefault("query", "")
        metadata = dict(context.get("metadata") or {})
        metadata.setdefault("source", "meeting_room")
        metadata.setdefault("room_id", room_id)
        metadata.setdefault("pipeline_agent_name", str(getattr(agent_def, "name", "") or ""))
        ext = dict(context.get("ext") or {})
        ext.setdefault("surface", "chat")
        ext.setdefault("allowed_modes", ["answer", "report"])
        ext.setdefault("forbidden_modes", ["action"])
        ext["history_messages"] = list(context_messages)
        ext.setdefault("meeting_context", {"room_id": room_id, "recent_messages": list(context_messages)})
        ext["pipeline_agent_definition"] = {
            "name": str(getattr(agent_def, "name", "AI 助手") or "AI 助手"),
            "system_prompt": str(getattr(agent_def, "system_prompt", "") or ""),
            "adapter_type": "pipeline",
        }
        context["metadata"] = metadata
        context["ext"] = ext
        context["agent_id"] = context.get("agent_id") or str(getattr(agent_def, "id", "") or "")
        context["agent_name"] = context.get("agent_name") or str(getattr(agent_def, "name", "AI 助手") or "AI 助手")
        if runtime_model:
            # Do not put credentials into the request context or persisted
            # metadata; ManagerLoop resolves the active runtime itself.
            context.setdefault(
                "runtime_model",
                {
                    key: runtime_model.get(key)
                    for key in ("model_id", "provider", "base_url", "runtime_key")
                    if runtime_model.get(key)
                },
            )
        return context

    @classmethod
    def _response_from_output(cls, output: Any, *, question: str, context: dict[str, Any]) -> PipelineAgentResponse:
        agent_output = dict(getattr(output, "agent_output", {}) or {})
        status = str(getattr(output, "status", "failed") or "failed").lower()
        if status not in {"completed", "blocked", "failed"}:
            status = "failed"
        answer = str(agent_output.get("answer") or agent_output.get("summary") or "").strip()
        if not answer:
            answer = cls._fallback_answer(status)
        trust = agent_output.get("trust_protocol")
        if not isinstance(trust, dict):
            trust = build_trust_answer_protocol(
                question=question,
                answer=answer,
                status=status,
                citations=[item for item in list(agent_output.get("citations") or []) if isinstance(item, dict)],
                route_trace=agent_output.get("route_trace") if isinstance(agent_output.get("route_trace"), dict) else {},
                trace_id=str(agent_output.get("trace_id") or context.get("workflow_run_id")),
                route_confidence=getattr(getattr(output, "route_decision", None), "confidence", None),
                refusal_reason=str(getattr(output, "degrade_reason", "") or "").strip() or None,
            ).model_dump(mode="json")
        metadata = cls._metadata(output, agent_output, status=status, trust_protocol=trust, context=context)
        return PipelineAgentResponse(answer, metadata)

    @classmethod
    def _failure_response(
        cls,
        question: str,
        context: dict[str, Any],
        *,
        status: str,
        code: str,
        message: str,
        raw_error: str = "",
    ) -> PipelineAgentResponse:
        trust = build_trust_answer_protocol(
            question=question,
            answer=message,
            status="unavailable" if code in {"PIPELINE_MODEL_UNAVAILABLE", "PIPELINE_TIMEOUT"} else status,
            route_trace={"reason": "pipeline_failure"},
            trace_id=str(context.get("workflow_run_id") or ""),
            refusal_reason=message,
            degrade_reasons=[code],
        ).model_dump(mode="json")
        return PipelineAgentResponse(
            message,
            {
                "adapter_type": "pipeline",
                "pipeline_status": status,
                "trust_protocol": trust,
                "citations": [],
                "degrade_reason": message,
                "error": {"code": code, "message": message, "raw_error": raw_error},
                "trace_id": context.get("workflow_run_id"),
            },
        )

    @staticmethod
    def _metadata(
        output: Any,
        agent_output: dict[str, Any],
        *,
        status: str,
        trust_protocol: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        decision = getattr(output, "route_decision", None)
        if hasattr(decision, "model_dump"):
            decision = decision.model_dump(mode="json")
        elif not isinstance(decision, dict):
            decision = {}
        route_trace = agent_output.get("route_trace")
        if not isinstance(route_trace, dict):
            route_trace = {}
        return {
            "adapter_type": "pipeline",
            "pipeline_status": status,
            "manager_status": status,
            "selected_agent": decision.get("selected_agent"),
            "selected_subgraph": decision.get("sub_route"),
            "route_decision": decision,
            "route_trace": _jsonable(route_trace),
            "capabilities_used": list(agent_output.get("capabilities_used") or []),
            "citations": _jsonable([item for item in list(agent_output.get("citations") or []) if isinstance(item, dict)]),
            "trust_protocol": _jsonable(trust_protocol),
            "trace_id": agent_output.get("trace_id") or trust_protocol.get("trace_id") or context.get("workflow_run_id"),
            "trace_url": agent_output.get("trace_url"),
            "degrade_reason": getattr(output, "degrade_reason", None),
            "error": _jsonable(getattr(output, "error", None)),
        }

    @staticmethod
    def _fallback_answer(status: str) -> str:
        if status == "blocked":
            return "当前请求超出会议 Agent 的可执行边界，未执行受限操作。"
        if status == "failed":
            return "会议 Agent 这次没有生成有效回复，请稍后重试。"
        return "我已收到你的请求，但当前没有生成有效回复。"

    @staticmethod
    async def _emit(emit: Callable, event: dict[str, Any]) -> None:
        if not callable(emit):
            return
        result = emit(event)
        if inspect.isawaitable(result):
            await result

    @classmethod
    async def _emit_deltas(
        cls,
        emit: Callable,
        *,
        content: str,
        room_id: str,
        message_id: str | None,
        workflow_run_id: str,
    ) -> None:
        if not content:
            return
        # ManagerLoop is intentionally non-streaming at the public contract;
        # emit small chunks here so meeting clients retain the normal UX.
        for start in range(0, len(content), 3):
            await cls._emit(
                emit,
                {
                    "event": "message_delta",
                    "room_id": room_id,
                    "message_id": message_id,
                    "workflow_run_id": workflow_run_id,
                    "delta": content[start : start + 3],
                },
            )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


__all__ = ["PipelineAgentAdapter", "PipelineAgentResponse"]
