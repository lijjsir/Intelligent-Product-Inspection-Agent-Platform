from __future__ import annotations

from datetime import date, datetime
import logging
from time import perf_counter
from typing import Any

from agent.contracts import AgentOutput, NormalizedAttachment, NormalizedRequest, PersistableOutput
from agent.llm.pricing import ModelPricing
from agent.subgraphs.quality_judgement import QualityJudgementSubgraph
from agent.topology_catalog import get_registered_subgraphs
from app.core.ids import uuid7
from app.core.config import settings
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
from app.repositories.user_token_usage_repo import UserTokenUsageSummaryRepository
from app.services.task_service import TaskService
from infra.database.session import get_session

logger = logging.getLogger(__name__)


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
            message_repo = ChatMessageRepository(session)
            session_repo = ChatSessionRepository(session)
            current_message = await message_repo.get(request.org_id, str(request.assistant_message_id))
            current_payload = current_message.payload if current_message and isinstance(current_message.payload, dict) else {}
            if current_payload.get("status") == "interrupted":
                return False
            await message_repo.update_assistant_message(
                org_id=request.org_id,
                message_id=str(request.assistant_message_id),
                content=str(output.answer or ""),
                message_type=str(output.message_type or "assistant_text"),
                payload=response_payload,
            )
            await session_repo.touch(request.org_id, str(request.user_id or ""), str(request.session_id))

            if output.route_decision:
                rag_repo = RagAnalysisRepository(session, request.org_id)
                for item in list(output.persistable_output.rag_queries or []):
                    metadata = dict(item.metadata or {})
                    metadata.setdefault("agent", output.route_decision.selected_agent)
                    metadata.setdefault("sub_route", output.route_decision.sub_route)
                    await rag_repo.create_log(
                        {
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

            await session.commit()

        if output.route_decision:
            await self._record_route_decision_log(request, output)

        if callable(emit):
            await emit(
                {
                    "event": "message_final",
                    "session_id": request.session_id,
                    "message_id": request.assistant_message_id,
                    "workflow_run_id": request.workflow_run_id,
                    "content": str(output.answer or ""),
                    "payload": response_payload,
                    "quality": dict(output.quality or {}),
                }
            )
        return materialization_error is None

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
            base_payload.get("sub_route")
            or base_payload.get("intent")
            or (output.route_decision.sub_route if output.route_decision else None)
            or "general_chat"
        )
        trace_id = base_payload.get("trace_id") or (
            output.persistable_output.quality_trace.trace_id
            if output.persistable_output and output.persistable_output.quality_trace
            else None
        )

        from agent.response.response_builder import ResponseBuilder

        return ResponseBuilder.build(
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
        )

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
            token_repo = TokenLedgerRepository(session)
            user_summary_repo = UserTokenUsageSummaryRepository(session)
            task_service = TaskService(session, request.org_id)

            reasoning_chain = dict(result_data.reasoning_chain or {})
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
                        "trace": (
                            persistable_output.quality_trace.model_dump(exclude_none=True)
                            if persistable_output.quality_trace
                            else {}
                        ),
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
                await alert_repo.create(
                    {
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

            if persist_usage:
                for item in persistable_output.token_usage:
                    ledger = await token_repo.create(
                        {
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
                    if request.user_id:
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
                    await alert_repo.create(
                        {
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

                if not _triggered:
                    await alert_repo.create(
                        {
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

            usage = self._legacy_usage(output)
            if usage["total_tokens"] > 0:
                ledger = await token_repo.create(
                    {
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
                if request.user_id:
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
