from __future__ import annotations

from datetime import date, datetime
import hashlib
import logging
from time import perf_counter
from typing import Any
import uuid

from agent.contracts import AgentOutput, NormalizedAttachment, NormalizedRequest, PersistableOutput
from agent.llm.pricing import ModelPricing
from agent.subgraphs.quality_judgement import QualityJudgementSubgraph
from agent.topology_catalog import get_registered_subgraphs
from app.core.ids import uuid7
from app.core.config import settings
from app.models.tool import ToolExecution
from app.models.task import InspectionTask
from app.repositories.agent_management_repo import AgentExecutionMetricsRepository
from app.repositories.agent_ops_repo import (
    AgentDefinitionRepository,
    AgentRuntimeRepository,
    RagAnalysisRepository,
)
from app.models.alert_rule import AlertRule
from app.repositories.alert_repo import AlertRepository
from app.repositories.chat_repo import ChatMessageRepository, ChatSessionRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.repositories.tool_repo import ToolRepository
from app.repositories.user_token_usage_repo import UserTokenUsageSummaryRepository
from app.services.chat_trust_scoring_service import build_pending_trust_score, trust_payload_from_score
from app.services.task_service import TaskService
from app.services.chat_message_lifecycle_service import ChatMessageLifecycleService
from infra.database.session import get_session

logger = logging.getLogger(__name__)

_MAX_IDEMPOTENCY_KEY_LENGTH = 191


class QualityAgentOrchestratorService:
    def __init__(self) -> None:
        self._graph = QualityJudgementSubgraph()
        from app.services.agent_manager_service import AgentManagerService
        self._agent_manager = AgentManagerService()

    @staticmethod
    def _json_safe(value: Any) -> Any:
        dropped = object()

        def convert(item: Any) -> Any:
            if callable(item):
                return dropped
            if isinstance(item, dict):
                result: dict[str, Any] = {}
                for key, raw_value in item.items():
                    converted = convert(raw_value)
                    if converted is not dropped:
                        result[str(key)] = converted
                return result
            if isinstance(item, (list, tuple, set)):
                result = []
                for raw_value in item:
                    converted = convert(raw_value)
                    if converted is not dropped:
                        result.append(converted)
                return result
            if isinstance(item, (str, int, float, bool)) or item is None:
                return item
            if isinstance(item, (datetime, date)):
                return item.isoformat()
            model_dump = getattr(item, "model_dump", None)
            if callable(model_dump):
                return convert(model_dump())
            return str(item)

        converted = convert(value)
        return None if converted is dropped else converted

    @staticmethod
    def _idempotency_key(request: NormalizedRequest, *parts: Any) -> str:
        base = str(request.ext.get("idempotency_key") or "").strip()
        if not base:
            base = ":".join(
                [
                    str(request.org_id),
                    str(request.session_id or ""),
                    str(request.assistant_message_id or ""),
                    str(request.workflow_run_id or request.request_id),
                ]
            )
        suffix = ":".join(str(part) for part in parts if str(part))
        key = f"{base}:{suffix}" if suffix else base
        if len(key) <= _MAX_IDEMPOTENCY_KEY_LENGTH:
            return key

        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        marker = ":sha256:"
        prefix_limit = _MAX_IDEMPOTENCY_KEY_LENGTH - len(marker) - len(digest)
        prefix = key[:max(0, prefix_limit)].rstrip(":")
        if not prefix:
            return f"sha256:{digest}"
        return f"{prefix}{marker}{digest}"

    async def run_chat(self, payload: dict) -> dict:
        started_at = perf_counter()
        request = NormalizedRequest(
            request_kind="chat",
            request_id=str(payload["request_id"]),
            workflow_run_id=str(payload.get("workflow_run_id") or payload["request_id"]),
            session_id=str(payload["session_id"]),
            assistant_message_id=str(payload["assistant_message_id"]),
            org_id=str(payload["org_id"]),
            user_id=str(payload["user_id"]),
            workspace=str(payload.get("workspace") or "app"),
            plan_tier=str(payload.get("plan_tier") or "basic"),
            capabilities=list(payload.get("capabilities") or []),
            query=str(payload.get("query") or ""),
            metadata=dict(payload.get("metadata") or {}),
            ext=dict(payload.get("ext") or {}),
            attachments=[
                NormalizedAttachment.model_validate(item)
                for item in list(payload.get("attachments") or [])
            ],
            image_urls=[
                str(item).strip()
                for item in list(payload.get("image_urls") or [])
                if str(item).strip()
            ],
            product_id=str(payload.get("product_id") or "") or None,
            spec_code=str(payload.get("spec_code") or "") or None,
            route_hints=dict(payload.get("route_hints") or {}),
        )
        success = True
        try:
            async with get_session() as session:
                router_output = await self._agent_manager.run_chat(payload, db_session=session)
            agent_output = AgentOutput.model_validate(router_output.agent_output)
            # Inject route_decision from router output
            from agent.contracts.quality_contracts import RouteDecision as RD, RouteSignals
            rd = router_output.route_decision
            agent_output.route_decision = RD(
                mode="router_enabled",
                selected_agent=rd.selected_agent,
                sub_route=rd.sub_route,
                reason=rd.reason,
                intent=rd.intent,
                confidence=rd.confidence,
                requires_confirmation=rd.requires_confirmation,
                route_source=rd.route_source,
                fallback_agent=rd.fallback_agent,
                signals=RouteSignals(),
            )
            result_payload = {"agent_output": agent_output.model_dump()}
        except Exception as exc:
            if not settings.enable_legacy_agent_fallback:
                raise RuntimeError(f"AgentManager failed: {exc}") from exc
            logger.exception("AgentManager failed, falling back to legacy QualityJudgementSubgraph")
            result = await self._graph.run(request)
            if isinstance(result, AgentOutput):
                agent_output = result
                result_payload = {"agent_output": agent_output.model_dump()}
            else:
                result_payload = dict(result)
                agent_output = AgentOutput.model_validate(result_payload["agent_output"])
        route_decision = agent_output.route_decision
        success = await self._persist_chat_result(request, agent_output)
        await self._record_runtime_metrics(
            request.org_id,
            route_decision.selected_agent if route_decision else "chat",
            success=success,
            latency_ms=int(round((perf_counter() - started_at) * 1000)),
        )
        return result_payload

    async def _persist_chat_result(
        self,
        request: NormalizedRequest,
        output: AgentOutput,
    ) -> bool:
        emit = request.ext.get("emit")
        materialized: dict[str, Any] | None = None
        materialization_error: str | None = None
        if self._should_materialize_chat_output(output):
            try:
                materialized = await self._materialize_chat_output(request, output)
            except Exception as exc:  # pragma: no cover - defensive runtime path
                materialization_error = str(exc)
                logger.exception("chat materialize failed session_id=%s", request.session_id)

        materialized_task = None
        task_form_defaults = dict(output.task_draft or {})
        if materialized:
            materialized_task = {
                "id": materialized["task_id"],
                "result_id": materialized.get("result_id"),
                "status": materialized["task_status"],
                "product_id": materialized["product_id"],
                "spec_code": materialized["spec_code"],
                "priority": materialized["priority"],
                "image_count": materialized["image_count"],
            }
            task_form_defaults = {
                **task_form_defaults,
                "product_id": materialized["product_id"],
                "spec_code": materialized["spec_code"],
                "priority": materialized["priority"],
                "image_urls": list(task_form_defaults.get("image_urls") or []),
            }

        response_payload = self._build_response_payload(
            request=request,
            output=output,
            task_form_defaults=task_form_defaults,
            materialized_task=materialized_task,
            materialization_error=materialization_error,
        )
        trust_scoring_request = self._build_trust_scoring_request(request, output, response_payload)
        if trust_scoring_request:
            pending_score = build_pending_trust_score(**trust_scoring_request)
            response_payload = {
                **response_payload,
                "trust_scoring": trust_payload_from_score(pending_score),
            }

        is_legacy_stream = True  # Graph handler (response_writer) already streams deltas
        if callable(emit) and not is_legacy_stream:
            answer = str(output.answer or "")
            for start in range(0, len(answer), 48):
                await emit(
                    {
                        "event": "message_delta",
                        "session_id": request.session_id,
                        "message_id": request.assistant_message_id,
                        "workflow_run_id": request.workflow_run_id,
                        "delta": answer[start : start + 48],
                    }
                )
            if output.quality:
                await emit(
                    {
                        "event": "quality_signal",
                        "session_id": request.session_id,
                        "message_id": request.assistant_message_id,
                        "workflow_run_id": request.workflow_run_id,
                        "quality": output.quality,
                    }
                )

        async with get_session() as session:
            lifecycle = ChatMessageLifecycleService(
                session,
                message_repository_cls=ChatMessageRepository,
                session_repository_cls=ChatSessionRepository,
            )
            lifecycle_completed = await lifecycle.complete_turn(
                org_id=request.org_id,
                user_id=str(request.user_id or ""),
                session_id=str(request.session_id),
                assistant_message_id=str(request.assistant_message_id),
                content=str(output.answer or ""),
                message_type=str(output.message_type or "assistant_text"),
                payload=response_payload,
            )
            if not lifecycle_completed:
                return False

            if output.route_decision:
                rag_repo = RagAnalysisRepository(session, request.org_id)
                for index, item in enumerate(list(output.persistable_output.rag_queries or [])):
                    metadata = dict(item.metadata or {})
                    metadata.setdefault("agent", output.route_decision.selected_agent)
                    metadata.setdefault("sub_route", output.route_decision.sub_route)
                    create_log = getattr(rag_repo, "create_log_once", rag_repo.create_log)
                    await create_log(
                        {
                            "idempotency_key": self._idempotency_key(request, "rag", index),
                            "task_id": None if not materialized else materialized["task_id"],
                            "session_id": str(request.session_id),
                            "user_id": str(request.user_id or ""),
                            "query": item.query,
                            "rag_space_id": item.rag_space_id,
                            "top_k": int(item.top_k or 0),
                            "hit_count": item.hit_count,
                            "hit_rate": item.hit_rate,
                            "citation_coverage": item.citation_coverage,
                            "latency_ms": int(item.latency_ms or 0),
                            "source_graph": item.source_graph,
                            "agent_name": item.agent_name or output.route_decision.selected_agent,
                            "sub_route": item.sub_route or output.route_decision.sub_route,
                            "trace_id": item.trace_id
                            or (
                                output.persistable_output.quality_trace.trace_id
                                if output.persistable_output and output.persistable_output.quality_trace
                                else None
                            )
                            or request.workflow_run_id
                            or request.request_id,
                            "top_score": float(item.top_score or metadata.get("top_score") or 0.0),
                            "metadata_json": metadata,
                        }
                    )
                await self._persist_rag_tool_executions(
                    session,
                    request=request,
                    output=output,
                    materialized_task_id=None if not materialized else str(materialized["task_id"]),
                )
                await self._persist_file_tool_executions(
                    session,
                    request=request,
                    output=output,
                    materialized_task_id=None if not materialized else str(materialized["task_id"]),
                )

            if not materialized:
                await self._persist_chat_token_usage(session, request=request, output=output)

            await session.commit()

        self._enqueue_trust_scoring(trust_scoring_request)

        if output.route_decision:
            await self._record_route_decision_log(request, output)

        await ChatMessageLifecycleService.emit_final(
            emit,
            session_id=request.session_id,
            assistant_message_id=request.assistant_message_id,
            workflow_run_id=request.workflow_run_id,
            content=str(output.answer or ""),
            payload=response_payload,
            quality=dict(output.quality or {}),
        )
        return materialization_error is None

    async def _persist_rag_tool_executions(
        self,
        session,
        *,
        request: NormalizedRequest,
        output: AgentOutput,
        materialized_task_id: str | None,
    ) -> None:
        rag_queries = list(output.persistable_output.rag_queries or [])
        if not rag_queries:
            return
        try:
            tool_repo = ToolRepository(session)
            tool = await tool_repo.get_by_tool_key(request.org_id, "rag.standard_search")
            if not tool:
                return
            for index, item in enumerate(rag_queries):
                execution_id = str(uuid.uuid5(uuid.NAMESPACE_URL, self._idempotency_key(request, "tool-rag", index)))
                existing = await session.get(ToolExecution, execution_id)
                if existing is not None:
                    continue
                metadata = dict(item.metadata or {})
                status = "success" if int(item.hit_count or 0) >= 0 else "failed"
                input_payload = {
                    "query": item.query,
                    "rag_space_id": item.rag_space_id,
                    "top_k": int(item.top_k or 0),
                }
                output_payload = {
                    "hit_count": int(item.hit_count or 0),
                    "hit_rate": float(item.hit_rate or 0.0),
                    "citation_coverage": float(item.citation_coverage or 0.0),
                    "top_score": float(item.top_score or 0.0),
                    "top_sources": list(metadata.get("top_sources") or []),
                }
                await tool_repo.create_execution(
                    ToolExecution(
                        id=execution_id,
                        task_id=materialized_task_id or str(uuid.uuid5(uuid.NAMESPACE_URL, f"{request.workflow_run_id or request.request_id}:tool-rag-task")),
                        org_id=request.org_id,
                        tool_id=str(tool.id),
                        tool_name=str(tool.display_name or "标准知识库检索"),
                        call_index=index,
                        input_payload=input_payload,
                        output_payload=output_payload,
                        status=status,
                        error_message=None,
                        latency_ms=int(item.latency_ms or 0),
                        agent_id=None,
                        trace_id=item.trace_id or request.workflow_run_id or request.request_id,
                        execution_type="runtime",
                        input_redacted=input_payload,
                        output_redacted=output_payload,
                    )
                )
        except Exception:
            logger.debug("rag tool execution log write skipped", exc_info=True)

    async def _persist_file_tool_executions(
        self,
        session,
        *,
        request: NormalizedRequest,
        output: AgentOutput,
        materialized_task_id: str | None,
    ) -> None:
        parsed_files: list[dict[str, Any]] = []
        for artifact in self._response_artifacts(output):
            if str(artifact.get("type") or "") not in {"file_summary", "file_answer", "paper_format_report"}:
                continue
            content = artifact.get("content")
            if not isinstance(content, dict):
                continue
            for item in list(content.get("parsed_files") or []):
                if isinstance(item, dict):
                    parsed_files.append(item)
        if not parsed_files:
            return
        try:
            tool_repo = ToolRepository(session)
            tool = await tool_repo.get_by_tool_key(request.org_id, "file.parse")
            if not tool:
                return
            trace_id = request.workflow_run_id or request.request_id
            for index, item in enumerate(parsed_files):
                execution_id = str(uuid.uuid5(uuid.NAMESPACE_URL, self._idempotency_key(request, "tool-file-parse", index)))
                existing = await session.get(ToolExecution, execution_id)
                if existing is not None:
                    continue
                file_name = str(item.get("name") or f"attachment-{index + 1}")
                input_payload = {
                    "file_name": file_name,
                    "file_url": str(item.get("url") or ""),
                    "content_type": str(item.get("content_type") or ""),
                }
                output_payload = {
                    "kind": item.get("kind"),
                    "text_length": len(str(item.get("text") or "")),
                    "summary": str(item.get("summary") or "")[:500],
                }
                await tool_repo.create_execution(
                    ToolExecution(
                        id=execution_id,
                        task_id=materialized_task_id or str(uuid.uuid5(uuid.NAMESPACE_URL, f"{trace_id}:tool-file-task")),
                        org_id=request.org_id,
                        tool_id=str(tool.id),
                        tool_name=str(tool.display_name or "文件内容解析"),
                        call_index=index,
                        input_payload=input_payload,
                        output_payload=output_payload,
                        status="success",
                        error_message=None,
                        latency_ms=0,
                        agent_id=None,
                        trace_id=trace_id,
                        execution_type="runtime",
                        input_redacted=input_payload,
                        output_redacted=output_payload,
                    )
                )
        except Exception:
            logger.debug("file tool execution log write skipped", exc_info=True)

    @staticmethod
    def _response_artifacts(output: AgentOutput) -> list[dict[str, Any]]:
        raw_state = output.raw_state if isinstance(output.raw_state, dict) else {}
        payload = raw_state.get("response_payload")
        if not isinstance(payload, dict):
            return []
        return [item for item in list(payload.get("artifacts") or []) if isinstance(item, dict)]

    @staticmethod
    def _build_trust_scoring_request(
        request: NormalizedRequest,
        output: AgentOutput,
        response_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not settings.trust_scoring_enabled:
            return None
        message_type = str(response_payload.get("message_type") or output.message_type or "")
        if message_type in {"task_action", "task_result", "action_blocked"}:
            return None
        answer = str(response_payload.get("answer") or output.answer or "").strip()
        if not answer:
            return None

        llm_meta = dict(response_payload.get("llm_meta") or {})
        langfuse_meta = dict(llm_meta.get("langfuse") or {})
        trace_id = (
            str(langfuse_meta.get("trace_id") or "").strip()
            or str(response_payload.get("trace_id") or "").strip()
            or (
                str(output.persistable_output.quality_trace.trace_id or "").strip()
                if output.persistable_output and output.persistable_output.quality_trace
                else ""
            )
            or str(request.workflow_run_id or request.request_id or "").strip()
        )
        observation_id = str(langfuse_meta.get("observation_id") or "").strip() or None
        model_key = (
            str(llm_meta.get("model") or "").strip()
            or QualityAgentOrchestratorService._model_key_from_route_trace(response_payload)
            or QualityAgentOrchestratorService._model_key_from_usage(output)
        )
        return {
            "org_id": str(request.org_id),
            "session_id": str(request.session_id or ""),
            "user_id": str(request.user_id or "") or None,
            "assistant_message_id": str(request.assistant_message_id or ""),
            "input_text": str(request.query or ""),
            "output_text": answer,
            "citations": list(response_payload.get("citations") or output.citations or []),
            "trace_id": trace_id or None,
            "observation_id": observation_id,
            "model_key": model_key or None,
        }

    @staticmethod
    def _model_key_from_route_trace(response_payload: dict[str, Any]) -> str | None:
        route_trace = response_payload.get("route_trace")
        if not isinstance(route_trace, dict):
            return None
        manager_model = route_trace.get("manager_model")
        if not isinstance(manager_model, dict):
            return None
        return str(manager_model.get("model_id") or "").strip() or None

    @staticmethod
    def _model_key_from_usage(output: AgentOutput) -> str | None:
        if not output.persistable_output:
            return None
        for item in reversed(list(output.persistable_output.token_usage or [])):
            model_key = str(item.model_key or "").strip()
            if model_key:
                return model_key
        return None

    @staticmethod
    def _enqueue_trust_scoring(payload: dict[str, Any] | None) -> None:
        if not payload:
            return
        try:
            from worker.tasks.chat_trust_scoring_task import score_chat_message

            score_chat_message.delay(payload)
        except Exception as exc:
            logger.warning(
                "trust scoring enqueue failed assistant_message_id=%s trace_id=%s: %s",
                payload.get("assistant_message_id"),
                payload.get("trace_id"),
                exc,
                exc_info=True,
            )

    async def _persist_chat_token_usage(
        self,
        session,
        *,
        request: NormalizedRequest,
        output: AgentOutput,
    ) -> None:
        usage_items = list(output.persistable_output.token_usage or [])
        if not usage_items:
            return

        token_repo = TokenLedgerRepository(session)
        user_summary_repo = UserTokenUsageSummaryRepository(session)
        for index, item in enumerate(usage_items):
            prompt_tokens = int(item.prompt_tokens or 0)
            completion_tokens = int(item.completion_tokens or 0)
            total_tokens = int(item.total_tokens or (prompt_tokens + completion_tokens))
            if total_tokens <= 0:
                continue
            ledger_key = self._idempotency_key(
                request,
                "chat-token",
                index,
                item.model_key,
                item.trace_id or "",
            )
            existing_ledger = None
            get_ledger = getattr(token_repo, "get_by_idempotency_key", None)
            if callable(get_ledger):
                existing_ledger = await get_ledger(ledger_key)
            create_ledger = getattr(token_repo, "create_once", token_repo.create)
            ledger = existing_ledger or await create_ledger(
                {
                    "idempotency_key": ledger_key,
                    "id": str(uuid7()),
                    "org_id": request.org_id,
                    "user_id": str(request.user_id or "") or None,
                    "task_id": None,
                    "result_id": None,
                    "model_config_id": None,
                    "model_key": item.model_key,
                    "product_line": str(request.workspace or "chat"),
                    "trace_id": item.trace_id,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cost_amount": float(item.cost_amount or 0.0),
                }
            )
            if request.user_id and existing_ledger is None:
                await user_summary_repo.increment(
                    org_id=request.org_id,
                    user_id=str(request.user_id),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost_amount=float(item.cost_amount or 0.0),
                    ledger_created_at=ledger.created_at,
                )

    async def _record_route_decision_log(
        self,
        request: NormalizedRequest,
        output: AgentOutput,
    ) -> None:
        if not output.route_decision:
            return
        try:
            from app.repositories.agent_ops_repo import AgentRouteLogRepository

            async with get_session() as session:
                route_log_repo = AgentRouteLogRepository(session, request.org_id)
                await route_log_repo.create(
                    {
                        "user_id": request.user_id or None,
                        "session_id": request.session_id,
                        "request_id": request.request_id,
                        "selected_agent": output.route_decision.selected_agent,
                        "sub_route": output.route_decision.sub_route,
                        "intent_name": output.route_decision.intent or output.route_decision.sub_route,
                        "confidence": output.route_decision.confidence,
                        "route_source": output.route_decision.route_source,
                        "reason": output.route_decision.reason,
                        "fallback_agent": output.route_decision.fallback_agent,
                        "requires_confirmation": output.route_decision.requires_confirmation,
                        "signals_json": output.route_decision.signals.model_dump(),
                        "latency_ms": 0,
                    }
                )
                await session.commit()
        except Exception:
            logger.debug("route log write skipped", exc_info=True)

    def _should_materialize_chat_output(self, output: AgentOutput) -> bool:
        route = ""
        sub_route = ""
        if output.route_decision:
            route = str(output.route_decision.selected_agent or "")
            sub_route = str(output.route_decision.sub_route or "")

        persistable = output.persistable_output
        has_structured_output = bool(
            persistable
            and persistable.task
            and persistable.result
            and persistable.stability
        )

        return route == "inspection_task" and sub_route == "inspection_execute" and has_structured_output

    def _build_response_payload(
        self,
        *,
        request: NormalizedRequest,
        output: AgentOutput,
        task_form_defaults: dict[str, Any],
        materialized_task: dict[str, Any] | None,
        materialization_error: str | None,
    ) -> dict[str, Any]:
        base_payload = {}
        if isinstance(output.raw_state, dict):
            base_payload = dict(output.raw_state.get("response_payload") or {})

        agent = (
            base_payload.get("agent")
            or (output.route_decision.selected_agent if output.route_decision else None)
            or "chat"
        )
        sub_route = (
            (output.route_decision.sub_route if output.route_decision else None)
            or base_payload.get("sub_route")
            or base_payload.get("intent")
            or "general_chat"
        )
        trace_id = base_payload.get("trace_id") or (
            output.persistable_output.quality_trace.trace_id
            if output.persistable_output and output.persistable_output.quality_trace
            else None
        )

        from agent.response.response_builder import ResponseBuilder

        payload = ResponseBuilder.build(
            agent=agent,
            sub_route=sub_route,
            answer=output.answer,
            summary=output.summary,
            message_type=output.message_type,
            citations=list(output.citations or []),
            quality=dict(output.quality or {}),
            rag_summary=dict(output.rag_summary) if output.rag_summary else None,
            retrieval_metrics=base_payload.get("retrieval_metrics"),
            task_draft=task_form_defaults or None,
            missing_slots=list((output.clarification.missing_fields if output.clarification else []) or []),
            awaiting_confirmation=bool(base_payload.get("awaiting_confirmation") or False),
            action_state=output.action_state,
            created_task=base_payload.get("created_task") or materialized_task,
            result_card=dict(output.result_card) if output.result_card else None,
            route_decision=output.route_decision.model_dump() if output.route_decision else None,
            trace_id=trace_id,
            trace_url=base_payload.get("trace_url"),
            prompt_version=base_payload.get("prompt_version", ""),
            selected_rag_space=request.ext.get("selected_rag_space") or base_payload.get("selected_rag_space"),
            artifacts=list(base_payload.get("artifacts") or []),
            route_trace=base_payload.get("route_trace"),
            capabilities_used=list(base_payload.get("capabilities_used") or []),
            satisfied=base_payload.get("satisfied"),
        )
        if base_payload.get("llm_meta"):
            payload["llm_meta"] = base_payload.get("llm_meta")
        if base_payload.get("llm_usage"):
            payload["llm_usage"] = base_payload.get("llm_usage")
        # Preserve paper_format_report and ui_schema from agent output
        if output.paper_format_report:
            payload["paper_format_report"] = output.paper_format_report
        if output.ui_schema:
            payload["ui_schema"] = output.ui_schema
        return payload

    async def _materialize_chat_output(
        self,
        request: NormalizedRequest,
        output: AgentOutput,
    ) -> dict[str, Any]:
        if output.persistable_output.task and output.persistable_output.result and output.persistable_output.stability:
            return await self._materialize_structured_output(
                request,
                output.persistable_output,
                source_graph=(
                    output.route_decision.selected_agent
                    if output.route_decision
                    else "inspection_task"
                ),
                source_kind="chat_quality_answer",
                persist_usage=True,
            )
        return await self._materialize_legacy_quality_answer(request, output)

    async def _materialize_structured_output(
        self,
        request: NormalizedRequest,
        persistable_output: PersistableOutput,
        *,
        source_graph: str,
        source_kind: str,
        persist_usage: bool,
    ) -> dict[str, Any]:
        task_data = persistable_output.task
        result_data = persistable_output.result
        stability_data = persistable_output.stability
        if not task_data or not result_data or not stability_data:
            raise ValueError("Persistable output is missing task, result, or stability aggregates")

        async with get_session() as session:
            task_repo = TaskRepository(session)
            result_repo = ResultRepository(session)
            stability_repo = StabilityRepository(session)
            alert_repo = AlertRepository(session)
            token_repo = TokenLedgerRepository(session)
            user_summary_repo = UserTokenUsageSummaryRepository(session)
            task_service = TaskService(session, request.org_id)

            reasoning_chain = dict(result_data.reasoning_chain or {})
            trust_scoring = dict(reasoning_chain.get("trust_scoring") or {})
            trace_merged = {
                **(dict(reasoning_chain.get("trace") or {})),
                **(persistable_output.quality_trace.model_dump(exclude_none=True) if persistable_output.quality_trace else {}),
            }
            if trust_scoring.get("trust_score") is not None:
                trace_merged.setdefault("trust_score", trust_scoring["trust_score"])
            if trust_scoring.get("hallucination_risk") is not None:
                trace_merged.setdefault("hallucination_risk", trust_scoring["hallucination_risk"])
            if trust_scoring.get("overconfidence") is not None:
                trace_merged.setdefault("overconfidence", trust_scoring["overconfidence"])
            if "has_citation" in trust_scoring:
                has_cit = trust_scoring["has_citation"]
                if isinstance(has_cit, bool) or isinstance(has_cit, (int, float)):
                    trace_merged.setdefault("has_citation", bool(has_cit) if isinstance(has_cit, bool) else float(has_cit) > 0)
            structured_record = dict(reasoning_chain.get("structured_record") or {})
            task_image_urls = list(request.image_urls or [])
            if not task_image_urls:
                raw_image_urls = structured_record.get("image_urls")
                if isinstance(raw_image_urls, list):
                    task_image_urls = [str(item).strip() for item in raw_image_urls if str(item).strip()]
                elif isinstance(raw_image_urls, str):
                    task_image_urls = [
                        part.strip()
                        for part in raw_image_urls.replace(";", ",").split(",")
                        if part.strip()
                    ]

            metadata = {
                "source": source_kind,
                "source_graph": source_graph,
                "chat_session_id": request.session_id,
                "assistant_message_id": request.assistant_message_id,
                "request_id": request.request_id,
                "workflow_run_id": request.workflow_run_id,
                "route_decision": (
                    persistable_output.quality_trace.model_dump()
                    if persistable_output.quality_trace
                    else {}
                ),
                "query": request.query,
                "attachments": [item.model_dump() for item in request.attachments],
                **dict(task_data.model_dump(exclude_none=True)),
            }

            task = await task_repo.get_by_chat_materialization_key(
                request.org_id,
                str(request.workflow_run_id or request.request_id),
                str(request.assistant_message_id or ""),
            )
            if task is None:
                task = await task_service.create_task(
                    created_by=str(request.user_id or request.org_id),
                    product_id=str(task_data.product_id or ""),
                    spec_code=str(task_data.spec_code or ""),
                    image_urls=task_image_urls,
                    priority=int(task_data.priority or 5),
                    metadata=metadata,
                )
            else:
                task.product_id = str(task_data.product_id or task.product_id)
                task.spec_code = str(task_data.spec_code or task.spec_code)
                task.image_urls = task_image_urls
                task.priority = int(task_data.priority or task.priority or 5)
                task.meta_data = metadata
                await session.flush()

            task_status = self._normalize_task_status(task_data.status)
            await task_repo.update_status(request.org_id, str(task.id), task_status)

            result = await result_repo.upsert_by_task(
                {
                    "id": str(result_data.id or uuid7()),
                    "task_id": str(task.id),
                    "org_id": request.org_id,
                    "verdict": str(result_data.verdict or "manual_required"),
                    "overall_score": float(result_data.overall_score or 0.0),
                    "defects": (
                        result_data.reasoning_chain or {}
                    ).get("standard_evaluation", {}).get("matched_rules", [])
                    if isinstance(result_data.reasoning_chain, dict)
                    else [],
                    "citations": dict(result_data.citations or {}),
                    "reasoning_chain": {
                        **reasoning_chain,
                        "trace": trace_merged,
                    },
                    "llm_model": str(result_data.llm_model or "quality_judgement"),
                    "prompt_version": str(
                        (persistable_output.quality_trace.prompt_version if persistable_output.quality_trace else None)
                        or "quality_judgement_v2"
                    ),
                    "tokens_used": sum(int(item.total_tokens or 0) for item in persistable_output.token_usage),
                    "latency_ms": int(
                        sum(float(item.latency_ms or 0.0) for item in persistable_output.rag_queries)
                    ),
                }
            )

            stability = await stability_repo.upsert_by_task(
                {
                    "id": str(uuid7()),
                    "result_id": str(result.id),
                    "task_id": str(task.id),
                    "org_id": request.org_id,
                    "evidence_score": float(stability_data.evidence_score or 0.0),
                    "consistency_score": float(stability_data.faithfulness_score or 0.0),
                    "confidence_score": float(stability_data.confidence_score or 0.0),
                    "traceability_score": float(stability_data.traceability_score or 0.0),
                    "anomaly_score": float(stability_data.physical_hallucination_score or 0.0),
                    "risk_score": float(stability_data.risk_score or 0.0),
                    "risk_level": str(stability_data.risk_level or "medium"),
                    "dimension_detail": {
                        "faithfulness_score": float(stability_data.faithfulness_score or 0.0),
                        "physical_hallucination_score": float(stability_data.physical_hallucination_score or 0.0),
                    },
                    "sampling_results": {
                        "route_subgraph": (
                            persistable_output.quality_trace.route_subgraph
                            if persistable_output.quality_trace
                            else source_graph
                        ),
                    },
                    "root_cause": str(result_data.verdict or "manual_required"),
                }
            )

            from app.services.rule_engine_service import RuleEngineService
            import logging
            _logger = logging.getLogger(__name__)

            metrics = {
                "risk_score": float(stability_data.risk_score or 0.0),
                "evidence_score": float(stability_data.evidence_score or 0.0),
                "consistency_score": float(stability_data.faithfulness_score or 0.0),
                "confidence_score": float(stability_data.confidence_score or 0.0),
                "traceability_score": float(stability_data.traceability_score or 0.0),
                "anomaly_score": float(stability_data.physical_hallucination_score or 0.0),
                "faithfulness_score": float(stability_data.faithfulness_score or 0.0),
                "physical_hallucination_score": float(stability_data.physical_hallucination_score or 0.0),
            }

            rule_engine = RuleEngineService(session)
            rule_matches = await rule_engine.evaluate_and_get_matches(
                org_id=request.org_id,
                alert_type="quality_review",
                metrics=metrics,
            )
            # Filter cooldown and build a pool; each rule triggers at most once
            available_rules: list[AlertRule] = []
            for rule in rule_matches:
                if not await rule_engine.is_in_cooldown(rule, request.org_id):
                    available_rules.append(rule)

            for item in persistable_output.alerts:
                rule = available_rules.pop(0) if available_rules else None
                create_alert = getattr(alert_repo, "create_once", alert_repo.create)
                created_alert = await create_alert(
                    {
                        "idempotency_key": self._idempotency_key(request, "alert", item.title),
                        "id": str(uuid7()),
                        "org_id": request.org_id,
                        "rule_id": str(rule.id) if rule else None,
                        "stability_id": str(stability.id),
                        "alert_type": "quality_review",
                        "severity": rule.severity if rule else item.severity,
                        "title": f"{item.title} (规则: {rule.name})" if rule else item.title,
                        "detail": {"message": item.message, "task_id": str(task.id), "result_id": str(result.id)},
                        "status": "open",
                        "channels": rule.notification_channels if (rule and rule.notification_channels) else {"ui": True},
                    }
                )
                qa_alert_id = str(getattr(created_alert, "id", None) or created_alert.get("id"))
                try:
                    from worker.tasks.alert_dispatch_task import dispatch_alert
                    dispatch_alert.delay(qa_alert_id)
                except Exception:
                    _logger.exception("Failed to enqueue dispatch for alert %s", qa_alert_id)

            if persist_usage:
                for index, item in enumerate(persistable_output.token_usage):
                    create_ledger = getattr(token_repo, "create_once", token_repo.create)
                    ledger_key = self._idempotency_key(request, "token", index, item.model_key)
                    existing_ledger = None
                    get_ledger = getattr(token_repo, "get_by_idempotency_key", None)
                    if callable(get_ledger):
                        existing_ledger = await get_ledger(ledger_key)
                    ledger = existing_ledger or await create_ledger(
                        {
                            "idempotency_key": ledger_key,
                            "id": str(uuid7()),
                            "org_id": request.org_id,
                            "user_id": str(request.user_id or "") or None,
                            "task_id": str(task.id),
                            "result_id": str(result.id),
                            "model_config_id": None,
                            "model_key": item.model_key,
                            "product_line": str(task.product_id),
                            "trace_id": item.trace_id,
                            "prompt_tokens": int(item.prompt_tokens or 0),
                            "completion_tokens": int(item.completion_tokens or 0),
                            "total_tokens": int(item.total_tokens or 0),
                            "cost_amount": float(item.cost_amount or 0.0),
                        }
                    )
                    if request.user_id and existing_ledger is None:
                        await user_summary_repo.increment(
                            org_id=request.org_id,
                            user_id=str(request.user_id),
                            prompt_tokens=int(item.prompt_tokens or 0),
                            completion_tokens=int(item.completion_tokens or 0),
                            total_tokens=int(item.total_tokens or 0),
                            cost_amount=float(item.cost_amount or 0.0),
                            ledger_created_at=ledger.created_at,
                        )

            await session.commit()
            return {
                "task_id": str(task.id),
                "task_status": task_status,
                "result_id": str(result.id),
                "stability_id": str(stability.id),
                "product_id": str(task.product_id),
                "spec_code": str(task.spec_code),
                "priority": int(task.priority),
                "image_count": len(task.image_urls or []),
            }

    async def _materialize_legacy_quality_answer(
        self,
        request: NormalizedRequest,
        output: AgentOutput,
    ) -> dict[str, Any]:
        async with get_session() as session:
            task_repo = TaskRepository(session)
            result_repo = ResultRepository(session)
            stability_repo = StabilityRepository(session)
            alert_repo = AlertRepository(session)
            token_repo = TokenLedgerRepository(session)
            user_summary_repo = UserTokenUsageSummaryRepository(session)

            task = await task_repo.get_by_chat_materialization_key(
                request.org_id,
                str(request.workflow_run_id or request.request_id),
                str(request.assistant_message_id or ""),
            )
            if task is None:
                task = await task_repo.create(
                    InspectionTask(
                        org_id=request.org_id,
                        created_by=str(request.user_id or request.org_id),
                        product_id=self._legacy_product_id(request, output),
                        spec_code=self._legacy_spec_code(request, output),
                        image_urls=list(request.image_urls or []),
                        status="done",
                        priority=5,
                        meta_data={
                            "source": "chat_quality_answer",
                            "source_graph": "quality_judgement",
                            "chat_session_id": request.session_id,
                            "assistant_message_id": request.assistant_message_id,
                            "request_id": request.request_id,
                            "workflow_run_id": request.workflow_run_id,
                            "query": request.query,
                            "route_reason": output.route_decision.reason if output.route_decision else "",
                        },
                    )
                )
            else:
                task.product_id = self._legacy_product_id(request, output)
                task.spec_code = self._legacy_spec_code(request, output)
                task.status = "done"
                task.meta_data = {
                    **dict(task.meta_data or {}),
                    "source": "chat_quality_answer",
                    "source_graph": "quality_judgement",
                    "chat_session_id": request.session_id,
                    "assistant_message_id": request.assistant_message_id,
                    "request_id": request.request_id,
                    "workflow_run_id": request.workflow_run_id,
                    "query": request.query,
                }
                await session.flush()

            result = await result_repo.upsert_by_task(
                {
                    "id": str(uuid7()),
                    "task_id": str(task.id),
                    "org_id": request.org_id,
                    "verdict": self._legacy_verdict(output),
                    "overall_score": float(self._legacy_overall_score(output)),
                    "defects": {
                        "failed_rules": list((output.result_card or {}).get("failed_rules") or [])
                    },
                    "citations": {"items": list(output.citations or [])},
                    "reasoning_chain": {
                        "legacy_state": self._json_safe(output.raw_state or {}),
                        "quality": self._json_safe(output.quality or {}),
                        "route_decision": (
                            output.route_decision.model_dump() if output.route_decision else None
                        ),
                    },
                    "llm_model": self._legacy_model_key(output),
                    "prompt_version": self._legacy_prompt_version(output),
                    "tokens_used": int(self._legacy_usage(output).get("total_tokens") or 0),
                    "latency_ms": int(
                        ((output.raw_state or {}).get("retrieval_metrics") or {}).get("latency_ms") or 0
                    ),
                }
            )

            stability = await stability_repo.upsert_by_task(
                {
                    "id": str(uuid7()),
                    "result_id": str(result.id),
                    "task_id": str(task.id),
                    "org_id": request.org_id,
                    "evidence_score": float((output.quality or {}).get("evidence_coverage") or 0.0),
                    "consistency_score": float((output.quality or {}).get("faithfulness") or 0.0),
                    "confidence_score": float((output.quality or {}).get("confidence") or 0.0),
                    "traceability_score": float((output.quality or {}).get("traceability") or 0.0),
                    "anomaly_score": float(
                        1.0
                        if "low_evidence" in list((output.quality or {}).get("hallucination_flags") or [])
                        else 0.0
                    ),
                    "risk_score": float((output.quality or {}).get("risk_score") or 0.0),
                    "risk_level": self._legacy_risk_level(output),
                    "dimension_detail": {
                        "faithfulness_score": float((output.quality or {}).get("faithfulness") or 0.0),
                        "hallucination_flags": list((output.quality or {}).get("hallucination_flags") or []),
                    },
                    "sampling_results": {"route_subgraph": "quality_judgement"},
                    "root_cause": str((output.summary or output.answer or "")[:255]),
                }
            )

            if self._legacy_should_alert(output):
                from app.services.rule_engine_service import RuleEngineService

                quality = output.quality or {}
                _legacy_metrics = {
                    "risk_score": float(quality.get("risk_score") or 0.0),
                    "confidence": float(quality.get("confidence") or 0.0),
                    "faithfulness": float(quality.get("faithfulness") or 0.0),
                    "evidence_coverage": float(quality.get("evidence_coverage") or 0.0),
                    "traceability": float(quality.get("traceability") or 0.0),
                }

                _legacy_rule_engine = RuleEngineService(session)
                _legacy_matches = await _legacy_rule_engine.evaluate_and_get_matches(
                    org_id=request.org_id,
                    alert_type="quality_review",
                    metrics=_legacy_metrics,
                )

                _triggered = False
                for _rule in _legacy_matches:
                    if await _legacy_rule_engine.is_in_cooldown(_rule, request.org_id):
                        continue
                    _triggered = True
                    create_alert = getattr(alert_repo, "create_once", alert_repo.create)
                    await create_alert(
                        {
                            "idempotency_key": self._idempotency_key(request, "legacy-alert", _rule.id),
                            "id": str(uuid7()),
                            "org_id": request.org_id,
                            "rule_id": str(_rule.id),
                            "stability_id": str(stability.id),
                            "alert_type": "quality_review",
                            "severity": _rule.severity,
                            "title": f"Quality review required (规则: {_rule.name})",
                            "detail": {
                                "message": output.summary or output.answer,
                                "task_id": str(task.id),
                                "result_id": str(result.id),
                            },
                            "status": "open",
                            "channels": _rule.notification_channels or {"ui": True},
                        }
                    )
                    try:
                        from worker.tasks.alert_dispatch_task import dispatch_alert
                        dispatch_alert.delay(_legacy_alert_id)
                    except Exception:
                        _logger.exception("Failed to enqueue dispatch for legacy alert %s", _legacy_alert_id)

                if not _triggered:
                    create_alert = getattr(alert_repo, "create_once", alert_repo.create)
                    await create_alert(
                        {
                            "idempotency_key": self._idempotency_key(request, "legacy-alert", "fallback"),
                            "id": str(uuid7()),
                            "org_id": request.org_id,
                            "rule_id": None,
                            "stability_id": str(stability.id),
                            "alert_type": "quality_review",
                            "severity": self._legacy_alert_severity(output),
                            "title": "Legacy quality answer requires review",
                            "detail": {
                                "message": output.summary or output.answer,
                                "task_id": str(task.id),
                                "result_id": str(result.id),
                            },
                            "status": "open",
                            "channels": {"ui": True},
                        }
                    )
                    try:
                        from worker.tasks.alert_dispatch_task import dispatch_alert
                        dispatch_alert.delay(_legacy_fallback_id)
                    except Exception:
                        _logger.exception("Failed to enqueue dispatch for legacy fallback alert %s", _legacy_fallback_id)

            usage = self._legacy_usage(output)
            if usage["total_tokens"] > 0:
                create_ledger = getattr(token_repo, "create_once", token_repo.create)
                ledger_key = self._idempotency_key(request, "legacy-token", usage["model_key"])
                existing_ledger = None
                get_ledger = getattr(token_repo, "get_by_idempotency_key", None)
                if callable(get_ledger):
                    existing_ledger = await get_ledger(ledger_key)
                ledger = existing_ledger or await create_ledger(
                    {
                        "idempotency_key": ledger_key,
                        "id": str(uuid7()),
                        "org_id": request.org_id,
                        "user_id": str(request.user_id or "") or None,
                        "task_id": str(task.id),
                        "result_id": str(result.id),
                        "model_config_id": None,
                        "model_key": usage["model_key"],
                        "product_line": str(task.product_id),
                        "trace_id": str((output.raw_state or {}).get("trace_id") or ""),
                        "prompt_tokens": int(usage["prompt_tokens"] or 0),
                        "completion_tokens": int(usage["completion_tokens"] or 0),
                        "total_tokens": int(usage["total_tokens"] or 0),
                        "cost_amount": float(usage["cost_amount"] or 0.0),
                    }
                )
                if request.user_id and existing_ledger is None:
                    await user_summary_repo.increment(
                        org_id=request.org_id,
                        user_id=str(request.user_id),
                        prompt_tokens=int(usage["prompt_tokens"] or 0),
                        completion_tokens=int(usage["completion_tokens"] or 0),
                        total_tokens=int(usage["total_tokens"] or 0),
                        cost_amount=float(usage["cost_amount"] or 0.0),
                        ledger_created_at=ledger.created_at,
                    )

            await session.commit()
            return {
                "task_id": str(task.id),
                "task_status": str(task.status),
                "result_id": str(result.id),
                "stability_id": str(stability.id),
                "product_id": str(task.product_id),
                "spec_code": str(task.spec_code),
                "priority": int(task.priority),
                "image_count": len(task.image_urls or []),
            }

    def _legacy_product_id(self, request: NormalizedRequest, output: AgentOutput) -> str:
        result_card = dict(output.result_card or {})
        return str(
            result_card.get("product_id")
            or request.product_id
            or request.metadata.get("product_id")
            or "chat_quality"
        )

    def _legacy_spec_code(self, request: NormalizedRequest, output: AgentOutput) -> str:
        result_card = dict(output.result_card or {})
        return str(
            result_card.get("spec_code")
            or request.spec_code
            or request.metadata.get("spec_code")
            or "CHAT-QUALITY-QA"
        )

    def _legacy_verdict(self, output: AgentOutput) -> str:
        result_card = dict(output.result_card or {})
        verdict = str(result_card.get("verdict") or "").strip().lower()
        if verdict:
            return verdict
        if bool((output.quality or {}).get("passed")):
            return "pass"
        return "manual_required"

    def _legacy_overall_score(self, output: AgentOutput) -> float:
        result_card = dict(output.result_card or {})
        if result_card.get("overall_score") is not None:
            return float(result_card.get("overall_score") or 0.0)
        return float((output.quality or {}).get("confidence") or 0.0)

    def _legacy_risk_level(self, output: AgentOutput) -> str:
        level = str((output.quality or {}).get("risk_level") or "yellow").lower()
        mapping = {"green": "low", "yellow": "medium", "orange": "high", "red": "critical"}
        return mapping.get(level, level or "medium")

    def _legacy_should_alert(self, output: AgentOutput) -> bool:
        return self._legacy_risk_level(output) in {"high", "critical"}

    def _legacy_alert_severity(self, output: AgentOutput) -> str:
        return "critical" if self._legacy_risk_level(output) == "critical" else "warning"

    def _legacy_model_key(self, output: AgentOutput) -> str:
        raw_state = dict(output.raw_state or {})
        reasoning = dict(raw_state.get("reasoning") or {})
        llm_meta = dict(reasoning.get("llm_meta") or {})
        return str(llm_meta.get("model") or "quality_judgement")

    def _legacy_prompt_version(self, output: AgentOutput) -> str:
        raw_state = dict(output.raw_state or {})
        return str(raw_state.get("prompt_version") or "builtin-quality-chat-v1")

    def _legacy_usage(self, output: AgentOutput) -> dict[str, Any]:
        raw_state = dict(output.raw_state or {})
        reasoning = dict(raw_state.get("reasoning") or {})
        llm_meta = dict(reasoning.get("llm_meta") or {})
        usage = dict(llm_meta.get("usage") or {})
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        return {
            "model_key": str(llm_meta.get("model") or "quality_judgement"),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_amount": ModelPricing.estimate_cost(
                str(llm_meta.get("model") or "quality_judgement"),
                prompt_tokens,
                completion_tokens,
            ),
        }

    def _normalize_task_status(self, status: str | None) -> str:
        normalized = str(status or "").strip().lower()
        if normalized in {"pending", "queued", "running", "done", "failed", "reviewing", "archived"}:
            return normalized
        if normalized in {"completed", "complete", "success", "succeeded"}:
            return "done"
        if normalized in {"error", "errored"}:
            return "failed"
        return "done"

    async def _record_runtime_metrics(
        self,
        org_id: str,
        agent_key: str,
        *,
        success: bool,
        latency_ms: int,
    ) -> None:
        async with get_session() as session:
            agent_repo = AgentDefinitionRepository(session, org_id)
            runtime_repo = AgentRuntimeRepository(session, org_id)
            metrics_repo = AgentExecutionMetricsRepository(session, org_id)
            registry_entry = next(
                (item for item in get_registered_subgraphs() if item["subgraph_key"] == agent_key),
                None,
            )
            if not registry_entry:
                return
            agent = await agent_repo.get_by_subgraph_key(agent_key)
            if not agent:
                agent = await agent_repo.create(dict(registry_entry))
            await runtime_repo.ensure_for_agent(agent)
            await metrics_repo.update_metrics(str(agent.id), success=success, latency_ms=latency_ms)
            await session.commit()
