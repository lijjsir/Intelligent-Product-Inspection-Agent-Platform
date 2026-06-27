from __future__ import annotations

from datetime import datetime
import logging
from time import perf_counter
import traceback
from types import SimpleNamespace
from typing import Any

from agent.contracts import AgentOutput
from agent.contracts.quality_contracts import (
    NormalizedAttachment,
    NormalizedRequest,
    PersistableOutput,
    ResultAggregate,
    StabilityAggregate,
    TaskAggregate,
)
from agent.router.manager_provider import get_agent_manager
from agent.llm.pricing import ModelPricing
from app.core.datetime import utcnow, utcnow_iso
from app.core.ids import uuid7
from app.models.task import InspectionTask
from app.repositories.alert_repo import AlertRepository
from app.repositories.agent_ops_repo import RagAnalysisRepository
from app.repositories.chat_repo import ChatMessageRepository, ChatSessionRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.task_execution_event_repo import TaskExecutionEventRepository
from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.repositories.user_token_usage_repo import UserTokenUsageSummaryRepository
from app.services.file_storage_service import FileStorageService
from app.services.result_trace_utils import build_trace_metrics
from app.services.stream_service import chat_stream_broker, stream_broker
from infra.database.session import get_session


logger = logging.getLogger(__name__)

InspectionState = dict[str, Any]


def _normalize_image_urls_for_runtime(image_urls: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw in image_urls or []:
        url = str(raw or "").strip()
        if not url:
            continue
        if url.startswith(("http://", "https://", "data:")):
            normalized.append(url)
            continue
        normalized.append(FileStorageService().to_data_url(url) or url)
    return normalized


def _linked_chat_session_id(task: InspectionTask) -> str:
    metadata = task.meta_data if isinstance(task.meta_data, dict) else {}
    return str(metadata.get("chat_session_id") or "").strip()


async def _record_token_usage(
    *,
    token_ledger_repo: TokenLedgerRepository,
    user_token_usage_repo: UserTokenUsageSummaryRepository,
    task: InspectionTask,
    result_id: str,
    state: InspectionState,
    usage_events: list[dict[str, Any]],
) -> int:
    total_tokens = 0
    for event in usage_events:
        prompt_tokens = int(event.get("prompt_tokens") or 0)
        completion_tokens = int(event.get("completion_tokens") or 0)
        event_total_tokens = int(event.get("total_tokens") or (prompt_tokens + completion_tokens))
        if event_total_tokens <= 0:
            continue
        total_tokens += event_total_tokens
        cost_amount = ModelPricing.estimate_cost(
            str(event.get("model_key") or state.get("model_id") or ""),
            prompt_tokens,
            completion_tokens,
            input_price_per_million=(
                float(state.get("model_input_price_per_million"))
                if state.get("model_input_price_per_million") is not None else None
            ),
            output_price_per_million=(
                float(state.get("model_output_price_per_million"))
                if state.get("model_output_price_per_million") is not None else None
            ),
        )
        await token_ledger_repo.create(
            {
                "id": str(uuid7()),
                "org_id": task.org_id,
                "user_id": task.created_by,
                "task_id": task.id,
                "result_id": result_id,
                "model_config_id": state.get("model_config_id"),
                "model_key": str(event.get("model_key") or state.get("model_id") or "unknown"),
                "product_line": task.product_id,
                "trace_id": state.get("trace_id"),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": event_total_tokens,
                "cost_amount": cost_amount,
            }
        )
        await user_token_usage_repo.increment(
            org_id=task.org_id,
            user_id=task.created_by,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=event_total_tokens,
            cost_amount=cost_amount,
        )
    return total_tokens


def _build_manager_task_request(task: InspectionTask) -> NormalizedRequest:
    metadata = dict(task.meta_data or {})
    workflow_run_id = str(
        (metadata.get("execution") or {}).get("workflow_run_id")
        or metadata.get("workflow_run_id")
        or uuid7()
    )
    image_urls = _normalize_image_urls_for_runtime(task.image_urls or [])
    attachments = [
        NormalizedAttachment(
            id=str((item or {}).get("id") or (item or {}).get("hash") or index),
            name=str((item or {}).get("name") or f"task-image-{index + 1}"),
            url=image_urls[index] if index < len(image_urls) else str((item or {}).get("url") or ""),
            kind="image",
            content_type="image/*",
        )
        for index, item in enumerate(list(task.image_items or []))
    ]
    if not attachments:
        attachments = [
            NormalizedAttachment(id=f"image-{index}", name=f"task-image-{index + 1}", url=url, kind="image", content_type="image/*")
            for index, url in enumerate(image_urls)
        ]
    ext = {
        **metadata,
        "surface": "quality_task",
        "allowed_modes": ["action", "report", "answer"],
        "action_intent": "quality_inspection_execute",
        "image_urls": image_urls,
        "evidence_packet_required": metadata.get("manager_skip_rag_evidence") is not True,
    }
    # Only skip RAG evidence if explicitly requested in metadata
    if bool(metadata.get("manager_skip_rag_evidence") is True):
        ext["manager_skip_rag_evidence"] = True
    if metadata.get("selected_rag_space_id") or metadata.get("selected_rag_space"):
        ext["rag_scope"] = {
            "enabled": True,
            "rag_space_id": metadata.get("selected_rag_space_id") or (metadata.get("selected_rag_space") or {}).get("id"),
            "scope_node_ids": list(metadata.get("selected_rag_scope_node_ids") or []),
        }
    return NormalizedRequest(
        request_kind="task",
        request_id=f"task-run-{task.id}",
        workflow_run_id=workflow_run_id,
        org_id=task.org_id,
        user_id=task.created_by,
        workspace="quality_task",
        query=f"执行质量检测 task_id={task.id} product_id={task.product_id} spec_code={task.spec_code}",
        metadata={
            **metadata,
            "task_id": task.id,
            "product_id": task.product_id,
            "spec_code": task.spec_code,
            "priority": task.priority,
        },
        ext=ext,
        attachments=attachments,
        image_urls=image_urls,
        product_id=task.product_id,
        spec_code=task.spec_code,
    )


async def _persist_task_agent_artifacts(session, *, task: InspectionTask, output: AgentOutput) -> None:
    from app.repositories.agent_artifact_repo import AgentArtifactRepository

    repo = AgentArtifactRepository(session)
    payload = dict((output.raw_state or {}).get("response_payload") or {})
    route_trace = dict(payload.get("route_trace") or {})
    capability_by_artifact: dict[str, str] = {}
    for obs in list(route_trace.get("observations") or []):
        if isinstance(obs, dict):
            for artifact_id in list(obs.get("artifact_ids") or []):
                capability_by_artifact[str(artifact_id)] = str(obs.get("capability_key") or "")
    for item in list(payload.get("artifacts") or []):
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("artifact_id") or "").strip()
        if not artifact_id:
            continue
        await repo.create_once(
            {
                "org_id": task.org_id,
                "session_id": _linked_chat_session_id(task) or None,
                "task_id": task.id,
                "workflow_run_id": str((output.persistable_output.quality_trace.trace_id if output.persistable_output.quality_trace else "") or ""),
                "request_id": str((output.raw_state or {}).get("request_id") or f"task-run-{task.id}"),
                "artifact_id": artifact_id,
                "agent_name": str(item.get("source_agent") or (output.route_decision.selected_agent if output.route_decision else "unknown")),
                "capability": capability_by_artifact.get(artifact_id) or None,
                "artifact_type": str(item.get("type") or "unknown"),
                "status": str(item.get("status") or "success"),
                "content_json": dict(item.get("content") or {}),
                "metrics_json": dict(item.get("metrics") or {}),
                "citations_json": list(item.get("citations") or []),
                "error_json": item.get("error") if isinstance(item.get("error"), dict) else None,
                "confidence": item.get("confidence"),
            }
        )


async def _materialize_manager_task_output(
    *,
    session,
    task: InspectionTask,
    output: AgentOutput,
    result_repo: ResultRepository,
    stability_repo: StabilityRepository,
    alert_repo: AlertRepository,
    token_ledger_repo: TokenLedgerRepository,
    user_token_usage_repo: UserTokenUsageSummaryRepository,
    pipeline_latency_ms: int,
) -> tuple[Any, Any]:
    persistable = output.persistable_output
    if not (persistable and persistable.result and persistable.stability):
        logger.warning(
            "inspection_pipeline persistable_output missing result/stability "
            "task_id=%s – rebuilding from raw agent output",
            task.id,
        )
        quality = dict(output.quality or {})
        result_card = dict(output.result_card or {})
        persistable = PersistableOutput(
            task=TaskAggregate(
                product_id=task.product_id,
                spec_code=task.spec_code,
                status="done",
                priority=int(task.priority or 5),
                image_count=len(task.image_urls or []),
            ),
            result=ResultAggregate(
                verdict=str(result_card.get("verdict") or quality.get("verdict") or "manual_required"),
                overall_score=float(result_card.get("overall_score") or quality.get("confidence") or 0.0),
                llm_model="quality_analysis",
                citations={"items": list(output.citations or [])},
                reasoning_chain={
                    "quality": quality,
                    "result_card": result_card,
                    "rag_summary": output.rag_summary,
                },
            ),
            stability=StabilityAggregate(
                risk_score=float(quality.get("risk_score") or 0.5),
                risk_level=str(quality.get("risk_level") or "medium"),
                evidence_score=float(quality.get("evidence_coverage") or 0.0),
                confidence_score=float(quality.get("confidence") or 0.0),
                traceability_score=float(quality.get("traceability") or 0.0),
                faithfulness_score=float(quality.get("faithfulness") or 0.0),
                physical_hallucination_score=float(
                    1.0 if "low_evidence" in list(quality.get("hallucination_flags") or []) else 0.0
                ),
            ),
            token_usage=[],
            rag_queries=[],
        )
    result_data = persistable.result
    stability_data = persistable.stability
    quality_trace = persistable.quality_trace
    reasoning_chain = dict(result_data.reasoning_chain or {})
    if quality_trace:
        reasoning_chain.setdefault("trace", quality_trace.model_dump(exclude_none=True))
    result = await result_repo.upsert_by_task(
        {
            "id": result_data.id or str(uuid7()),
            "task_id": task.id,
            "org_id": task.org_id,
            "verdict": result_data.verdict or "manual_required",
            "overall_score": float(result_data.overall_score or 0.0),
            "defects": reasoning_chain.get("defects") or [],
            "citations": result_data.citations or {"items": output.citations},
            "reasoning_chain": reasoning_chain,
            "llm_model": result_data.llm_model or "quality_analysis",
            "prompt_version": (quality_trace.prompt_version if quality_trace else None) or "agent_manager_prompt_v1",
            "tokens_used": sum(int(item.total_tokens or 0) for item in persistable.token_usage),
            "latency_ms": max(1, int(pipeline_latency_ms)),
        }
    )
    stability = await stability_repo.upsert_by_task(
        {
            "id": str(uuid7()),
            "result_id": result.id,
            "task_id": task.id,
            "org_id": task.org_id,
            "evidence_score": float(stability_data.evidence_score or 0.0),
            "consistency_score": float(stability_data.faithfulness_score or 0.0),
            "confidence_score": float(stability_data.confidence_score or 0.0),
            "traceability_score": float(stability_data.traceability_score or 0.0),
            "anomaly_score": float(stability_data.physical_hallucination_score or 0.0),
            "risk_score": float(stability_data.risk_score or 0.0),
            "risk_level": stability_data.risk_level or "medium",
            "dimension_detail": {},
            "sampling_results": {"route_trace": (output.raw_state or {}).get("response_payload", {}).get("route_trace")},
            "root_cause": None,
            "hallucination_risk": stability_data.physical_hallucination_score,
            "overconfidence": None,
            "created_at": utcnow(),
        }
    )
    for alert in list(persistable.alerts or []):
        await alert_repo.create(
            {
                "id": str(uuid7()),
                "org_id": task.org_id,
                "rule_id": None,
                "stability_id": stability.id,
                "alert_type": "quality_analysis",
                "severity": alert.severity,
                "title": alert.title,
                "detail": {"message": alert.message},
                "status": "open",
                "channels": {"in_app": True},
                "created_at": utcnow(),
            }
        )
    await _record_token_usage(
        token_ledger_repo=token_ledger_repo,
        user_token_usage_repo=user_token_usage_repo,
        task=task,
        result_id=result.id,
        state={
            "model_id": result_data.llm_model or "quality_analysis",
            "model_config_id": None,
            "trace_id": quality_trace.trace_id if quality_trace else None,
        },
        usage_events=[item.model_dump() for item in list(persistable.token_usage or [])],
    )
    rag_queries = list(persistable.rag_queries or [])
    rag_repo = RagAnalysisRepository(session, str(task.org_id)) if rag_queries else None
    for index, item in enumerate(rag_queries):
        create_log = getattr(rag_repo, "create_log_once", None)
        if create_log is None:
            create_log = rag_repo.create_log
        await create_log(
            {
                "idempotency_key": f"agent_manager_task:{task.id}:{index}",
                "task_id": task.id,
                "session_id": _linked_chat_session_id(task) or None,
                "user_id": task.created_by,
                "query": item.query,
                "rag_space_id": item.rag_space_id,
                "top_k": int(item.top_k or 0),
                "hit_count": item.hit_count,
                "hit_rate": item.hit_rate,
                "citation_coverage": item.citation_coverage,
                "latency_ms": int(item.latency_ms or 0),
                "source_graph": item.source_graph or "evidence_capability",
                "agent_name": item.agent_name or "orchestrator",
                "sub_route": item.sub_route or "evidence_arbitration",
                "trace_id": item.trace_id,
                "top_score": float(item.top_score or 0.0),
                "metadata_json": dict(item.metadata or {}),
            }
        )
    await _persist_task_agent_artifacts(session, task=task, output=output)
    return result, stability


async def _append_chat_result_summary(
    *,
    org_id: str,
    user_id: str | None,
    session_id: str,
    task: InspectionTask,
    result,
    stability_obj,
) -> None:
    content = (
        "智能体执行完成，检测结果已同步到任务链路。\n\n"
        f"任务 ID：{task.id}\n"
        f"检测结论：{result.verdict}\n"
        f"综合评分：{float(result.overall_score or 0.0):.3f}\n"
        f"稳定性等级：{stability_obj.risk_level}\n"
        f"风险分数：{float(stability_obj.risk_score or 0.0):.3f}"
    )
    async with get_session() as session:
        session_repo = ChatSessionRepository(session)
        if not await session_repo.get(org_id, str(user_id or task.created_by), session_id):
            return
        message_repo = ChatMessageRepository(session)
        message = await message_repo.create(
            session_id=session_id,
            org_id=org_id,
            user_id=None,
            role="assistant",
            content=content,
            message_type="task_result",
            payload={
                "answer": content,
                "summary": "任务执行完成",
                "action_state": "task_finished",
                "created_task": {
                    "id": str(task.id),
                    "status": "done",
                    "product_id": str(task.product_id),
                    "spec_code": str(task.spec_code),
                    "priority": int(task.priority),
                    "image_count": len(task.image_urls or []),
                },
                "result": {
                    "id": str(result.id),
                    "verdict": str(result.verdict),
                    "overall_score": float(result.overall_score or 0.0),
                    "risk_level": str(stability_obj.risk_level),
                    "risk_score": float(stability_obj.risk_score or 0.0),
                },
                "message_type": "task_result",
            },
        )
        await session_repo.touch(org_id, str(user_id or task.created_by), session_id)
        await session.commit()
        await chat_stream_broker.publish(
            session_id,
            {
                "event": "message_final",
                "session_id": session_id,
                "message_id": str(message.id),
                "content": content,
                "payload": {
                    "answer": content,
                    "summary": "任务执行完成",
                    "action_state": "task_finished",
                    "created_task": {
                        "id": str(task.id),
                        "status": "done",
                        "product_id": str(task.product_id),
                        "spec_code": str(task.spec_code),
                        "priority": int(task.priority),
                        "image_count": len(task.image_urls or []),
                    },
                    "result": {
                        "id": str(result.id),
                        "verdict": str(result.verdict),
                        "overall_score": float(result.overall_score or 0.0),
                        "risk_level": str(stability_obj.risk_level),
                        "risk_score": float(stability_obj.risk_score or 0.0),
                    },
                    "message_type": "task_result",
                },
            },
        )


async def _append_chat_failure_summary(
    *,
    org_id: str,
    user_id: str | None,
    session_id: str,
    task: InspectionTask,
    error_message: str,
) -> None:
    content = (
        "智能体执行失败，任务状态已更新为失败。\n\n"
        f"任务 ID：{task.id}\n"
        f"产品编号：{task.product_id}\n"
        f"检测标准：{task.spec_code}\n"
        f"失败原因：{error_message}"
    )
    async with get_session() as session:
        session_repo = ChatSessionRepository(session)
        if not await session_repo.get(org_id, str(user_id or task.created_by), session_id):
            return
        message_repo = ChatMessageRepository(session)
        message = await message_repo.create(
            session_id=session_id,
            org_id=org_id,
            user_id=None,
            role="assistant",
            content=content,
            message_type="error",
            payload={
                "answer": content,
                "summary": "任务执行失败",
                "action_state": "task_failed",
                "created_task": {
                    "id": str(task.id),
                    "status": "failed",
                    "product_id": str(task.product_id),
                    "spec_code": str(task.spec_code),
                    "priority": int(task.priority),
                    "image_count": len(task.image_urls or []),
                },
                "error": error_message,
                "message_type": "error",
            },
        )
        await session_repo.touch(org_id, str(user_id or task.created_by), session_id)
        await session.commit()
        await chat_stream_broker.publish(
            session_id,
            {
                "event": "run_failed",
                "session_id": session_id,
                "message_id": str(message.id),
                "content": content,
                "payload": {
                    "answer": content,
                    "summary": "任务执行失败",
                    "action_state": "task_failed",
                    "created_task": {
                        "id": str(task.id),
                        "status": "failed",
                        "product_id": str(task.product_id),
                        "spec_code": str(task.spec_code),
                        "priority": int(task.priority),
                        "image_count": len(task.image_urls or []),
                    },
                    "error": error_message,
                    "message_type": "error",
                },
            },
        )


async def run_inspection_pipeline(task_id: str, org_id: str) -> dict:
    """执行完整的 AI 质检流水线，包括状态流转、图推理、结果持久化和稳定性分析。"""
    async with get_session() as session:
        task_repo = TaskRepository(session)
        result_repo = ResultRepository(session)
        stability_repo = StabilityRepository(session)
        alert_repo = AlertRepository(session)
        token_ledger_repo = TokenLedgerRepository(session)
        user_token_usage_repo = UserTokenUsageSummaryRepository(session)
        task = await task_repo.get(org_id, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        linked_chat_session_id = _linked_chat_session_id(task)
        task_snapshot = {
            "id": str(task.id),
            "org_id": str(task.org_id),
            "created_by": str(task.created_by),
            "product_id": str(task.product_id),
            "spec_code": str(task.spec_code),
            "priority": int(task.priority or 5),
            "image_count": len(task.image_urls or []),
            "metadata": dict(task.meta_data or {}),
        }

        await task_repo.update_status(org_id, task_id, "running")
        running_metadata = dict(task.meta_data or {})
        running_metadata["execution"] = {
            **dict(running_metadata.get("execution") or {}),
            "started_at": utcnow_iso(),
        }
        await task_repo.patch_metadata(org_id, task_id, running_metadata)
        await session.commit()

        async def emit(event: dict) -> None:
            """为流水线事件补齐服务端时间戳并发布到任务事件流。"""
            event.setdefault("ts", utcnow_iso())
            async with get_session() as event_session:
                event_repo = TaskExecutionEventRepository(event_session)
                await event_repo.create(
                    {
                        "org_id": org_id,
                        "task_id": task_id,
                        "event_type": str(event.get("type") or "event"),
                        "stage": event.get("stage"),
                        "status": event.get("status"),
                        "message": event.get("message"),
                        "payload_json": event,
                    }
                )
                await event_session.commit()
            await stream_broker.publish(task_id, event)

        await emit({"type": "status", "status": "running", "message": "任务开始执行"})
        pipeline_started_at = perf_counter()

        try:
            manager_request = _build_manager_task_request(task)
            await emit({"type": "agent_stage", "stage": "manager", "status": "running", "message": "AgentManager 开始调度"})
            router_output = await get_agent_manager().run(manager_request, db_session=session)
            if router_output.status != "completed":
                error_payload = dict(router_output.error or {})
                message = (
                    error_payload.get("message")
                    or router_output.agent_output.get("answer")
                    or "AgentManager task execution failed"
                )
                raw_error = dict(error_payload.get("detail") or {}).get("raw_error")
                if raw_error:
                    message = f"{message}: {raw_error}"
                await emit(
                    {
                        "type": "agent_stage",
                        "stage": "manager",
                        "status": "failed",
                        "message": message,
                        "error": router_output.error,
                    }
                )
                raise RuntimeError(str(message))
            agent_output = AgentOutput.model_validate(router_output.agent_output)
            from agent.contracts.quality_contracts import RouteDecision, RouteSignals

            rd = router_output.route_decision
            agent_output.route_decision = RouteDecision(
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
            route_trace = dict((agent_output.raw_state or {}).get("response_payload", {}).get("route_trace") or {})
            for obs in list(route_trace.get("observations") or []):
                if isinstance(obs, dict):
                    await emit(
                        {
                            "type": "agent_stage",
                            "stage": obs.get("capability_key") or obs.get("owner_agent") or "agent",
                            "status": obs.get("status") or "completed",
                            "message": obs.get("summary") or "",
                            "agent_name": obs.get("owner_agent"),
                            "payload": obs,
                        }
                    )
            result, stability_obj = await _materialize_manager_task_output(
                session=session,
                task=task,
                output=agent_output,
                result_repo=result_repo,
                stability_repo=stability_repo,
                alert_repo=alert_repo,
                token_ledger_repo=token_ledger_repo,
                user_token_usage_repo=user_token_usage_repo,
                pipeline_latency_ms=max(
                    1,
                    int(round((perf_counter() - pipeline_started_at) * 1000)),
                ),
            )
            await emit({"type": "result", "verdict": result.verdict, "overall_score": float(result.overall_score)})
            await emit({"type": "stability", "risk_level": stability_obj.risk_level, "risk_score": float(stability_obj.risk_score)})
            await task_repo.update_status(org_id, task_id, "done")
            done_metadata = dict(task.meta_data or {})
            done_metadata["execution"] = {
                **dict(done_metadata.get("execution") or {}),
                "finished_at": utcnow_iso(),
                "latency_ms": max(1, int(round((perf_counter() - pipeline_started_at) * 1000))),
                "source_graph": "agent_manager",
                "selected_agent": router_output.route_decision.selected_agent,
            }
            await task_repo.patch_metadata(org_id, task_id, done_metadata)
            await session.commit()
            await emit({"type": "status", "status": "done"})
            if linked_chat_session_id:
                await _append_chat_result_summary(
                    org_id=org_id,
                    user_id=str(task.created_by),
                    session_id=linked_chat_session_id,
                    task=task,
                    result=result,
                    stability_obj=stability_obj,
                )
            return {"task_id": task_id, "status": "done"}

        except Exception as exc:
            logger.exception("inspection_pipeline failed task_id=%s", task_id)
            try:
                await session.rollback()
            except Exception:
                logger.exception("inspection_pipeline failed to rollback task_id=%s", task_id)
            try:
                async with get_session() as failure_session:
                    failure_repo = TaskRepository(failure_session)
                    failed_task = await failure_repo.get(org_id, task_id)
                    failed_metadata = (
                        dict(failed_task.meta_data or {})
                        if failed_task is not None
                        else dict(task_snapshot["metadata"])
                    )
                    failed_metadata["execution"] = {
                        **dict(failed_metadata.get("execution") or {}),
                        "finished_at": utcnow_iso(),
                        "error": str(exc),
                    }
                    await failure_repo.update_status(org_id, task_id, "failed")
                    await failure_repo.patch_metadata(org_id, task_id, failed_metadata)
                    await failure_session.commit()
            except Exception:
                logger.exception("inspection_pipeline failed to persist failure status task_id=%s", task_id)
            try:
                await emit(
                    {
                        "type": "error",
                        "status": "failed",
                        "message": str(exc),
                        "trace": traceback.format_exc(limit=2),
                    }
                )
            except Exception:
                logger.exception("inspection_pipeline failed to emit error event task_id=%s", task_id)
            try:
                if linked_chat_session_id:
                    await _append_chat_failure_summary(
                        org_id=org_id,
                        user_id=str(task_snapshot["created_by"]),
                        session_id=linked_chat_session_id,
                        task=SimpleNamespace(
                            id=task_snapshot["id"],
                            created_by=task_snapshot["created_by"],
                            product_id=task_snapshot["product_id"],
                            spec_code=task_snapshot["spec_code"],
                            priority=task_snapshot["priority"],
                            image_urls=[None] * int(task_snapshot["image_count"]),
                        ),
                        error_message=str(exc),
                    )
            except Exception:
                logger.exception("inspection_pipeline failed to append chat failure task_id=%s", task_id)
            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(exc),
            }

        finally:
            # Safety net: ensure task status is never left as "running" permanently.
            try:
                async with get_session() as safety_session:
                    safety_repo = TaskRepository(safety_session)
                    safety_task = await safety_repo.get(org_id, task_id)
                    if safety_task and str(safety_task.status) == "running":
                        await safety_repo.update_status(org_id, task_id, "failed")
                        safety_metadata = dict(safety_task.meta_data or {})
                        safety_metadata["execution"] = {
                            **dict(safety_metadata.get("execution") or {}),
                            "finished_at": utcnow_iso(),
                            "error": "inspection pipeline terminated without finalizing task status",
                        }
                        await safety_repo.patch_metadata(org_id, task_id, safety_metadata)
                        await safety_session.commit()
                        logger.error(
                            "inspection_pipeline safety net: force-finalized stuck task_id=%s",
                            task_id,
                        )
            except Exception:
                logger.exception("inspection_pipeline safety net failed task_id=%s", task_id)
