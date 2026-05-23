from __future__ import annotations

from datetime import datetime
import traceback
from typing import Any

from agent.subgraphs.inspection_task import InspectionGraph, InspectionState
from agent.llm.gateway import LLMGateway
from agent.llm.langfuse_tracer import LangfuseTracer
from agent.llm.pricing import ModelPricing
from agent.stability.alert_trigger import should_trigger
from agent.stability.analyzer import analyze
from app.core.datetime import utcnow, utcnow_iso
from app.core.ids import uuid7
from app.models.task import InspectionTask
from app.repositories.alert_repo import AlertRepository
from app.repositories.chat_repo import ChatMessageRepository, ChatSessionRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.task_execution_event_repo import TaskExecutionEventRepository
from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.repositories.user_token_usage_repo import UserTokenUsageSummaryRepository
from app.services.model_config_service import ModelConfigService
from app.services.inspection_standard_service import InspectionStandardService
from app.services.file_storage_service import FileStorageService
from app.services.stream_service import chat_stream_broker, stream_broker
from infra.database.session import get_session


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


def _build_runtime_state(
    task: InspectionTask,
    runtime: dict[str, Any],
    *,
    trace_id: str,
    timeline_seed: list[dict[str, Any]],
) -> InspectionState:
    """根据任务记录和选中的运行时模型构造图执行的初始状态。"""
    return {
        "task_id": task.id,
        "org_id": task.org_id,
        "product_id": task.product_id,
        "spec_code": task.spec_code,
        "image_urls": _normalize_image_urls_for_runtime(task.image_urls or []),
        "image_items": list(task.image_items or []),
        "model_id": str(runtime.get("model_id") or "unknown"),
        "model_config_id": runtime.get("model_config_id"),
        "model_base_url": runtime.get("base_url"),
        "model_api_key": runtime.get("api_key"),
        "model_provider": runtime.get("provider"),
        "model_input_price_per_million": runtime.get("input_price_per_million"),
        "model_output_price_per_million": runtime.get("output_price_per_million"),
        "trace_id": trace_id,
        "timeline": list(timeline_seed),
        "usage_events": [],
        "runtime_errors": [],
    }


def _runtime_key(runtime: dict[str, Any]) -> str:
    """生成运行时模型的稳定标识，供失败切换时排除已失败模型。"""
    return str(runtime.get("runtime_key") or runtime.get("model_config_id") or runtime.get("model_id") or "unknown")


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
        model_config_service = ModelConfigService(session, org_id)
        standard_service = InspectionStandardService(session, org_id)

        task = await task_repo.get(org_id, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        linked_chat_session_id = _linked_chat_session_id(task)

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

        try:
            runtime_models = await model_config_service.list_runtime_models()
            gateway = LLMGateway()
            graph = InspectionGraph()
            excluded_runtime_ids: set[str] = set()
            timeline_seed: list[dict[str, Any]] = []
            state: InspectionState | None = None

            runtime = await gateway.select_runtime(runtime_models, excluded_runtime_ids=excluded_runtime_ids)
            if not runtime:
                raise RuntimeError("no runtime model available")

            trace = LangfuseTracer().start_trace(
                task_id=task.id,
                org_id=task.org_id,
                model_key=runtime["model_id"],
                name="inspection_pipeline",
                source_type="inspection",
            )
            graph = InspectionGraph()
            while True:
                state = _build_runtime_state(
                    task,
                    runtime,
                    trace_id=str(trace["trace_id"]),
                    timeline_seed=timeline_seed,
                )
                state = await graph.run(state, on_event=emit)

                runtime_errors = state.get("runtime_errors") or []
                if not runtime_errors:
                    break

                excluded_runtime_ids.add(_runtime_key(runtime))
                next_available = await gateway.has_available_runtime(
                    runtime_models,
                    excluded_runtime_ids=excluded_runtime_ids,
                )
                detail = "; ".join(str(item.get("message") or "runtime failure") for item in runtime_errors)
                if not next_available:
                    raise RuntimeError(f"all runtime models failed: {detail}")

                timeline_seed = list(state.get("timeline") or [])
                timeline_seed.append(
                    {
                        "stage": "gateway",
                        "message": f"Model {runtime.get('model_id')} failed, switching fallback model",
                        "ts": utcnow_iso(),
                    }
                )
                await emit(
                    {
                        "type": "model_failover",
                        "from_model_id": runtime.get("model_id"),
                        "from_model_config_id": runtime.get("model_config_id"),
                        "reason": detail,
                    }
                )
                runtime = await gateway.select_runtime(
                    runtime_models,
                    excluded_runtime_ids=excluded_runtime_ids,
                )
                if not runtime:
                    break

            if state is None:
                raise RuntimeError("inspection graph did not produce a state")

            conclusion = state.get("conclusion") or {}
            reasoning_chain = dict(state.get("reasoning_chain") or {})
            standard_evaluation = await standard_service.evaluate(
                spec_code=task.spec_code,
                image_urls=task.image_urls or [],
                defects=state.get("defects") or [],
                citations=state.get("citations") or [],
                reasoning_chain=reasoning_chain,
                model_verdict=str(conclusion.get("verdict") or "uncertain"),
                overall_score=float(conclusion.get("overall_score") or 0.5),
            )
            state["standard_evaluation"] = standard_evaluation
            reasoning_chain["standard_evaluation"] = standard_evaluation
            reasoning_chain["trace"] = {
                "trace_id": state.get("trace_id"),
                "trace_url": trace.get("trace_url"),
                "task_id": task.id,
                "org_id": task.org_id,
                "model_key": state.get("model_id"),
            }
            result_payload = {
                "id": str(uuid7()),
                "task_id": task.id,
                "org_id": task.org_id,
                "verdict": standard_evaluation.get("verdict") or conclusion.get("verdict") or "uncertain",
                "overall_score": float(conclusion.get("overall_score") or 0.5),
                "defects": state.get("defects") or [],
                "citations": {"items": state.get("citations") or []},
                "reasoning_chain": reasoning_chain,
                "llm_model": state.get("model_id") or "unknown",
                "prompt_version": "phase3-v1",
                "tokens_used": 0,
                "latency_ms": None,
            }
            result = await result_repo.upsert_by_task(result_payload)

            usage_events = state.get("usage_events") or []
            total_tokens = await _record_token_usage(
                token_ledger_repo=token_ledger_repo,
                user_token_usage_repo=user_token_usage_repo,
                task=task,
                result_id=result.id,
                state=state,
                usage_events=usage_events,
            )

            if total_tokens > 0:
                result.tokens_used = total_tokens
                await session.flush()

            stability = await analyze(
                {
                    "defects": state.get("defects") or [],
                    "citations": state.get("citations") or [],
                    "conclusion": conclusion,
                }
            )
            trust_scoring = reasoning_chain.get("trust_scoring") if isinstance(reasoning_chain, dict) else None
            stability_payload = {
                "id": str(uuid7()),
                "result_id": result.id,
                "task_id": task.id,
                "org_id": task.org_id,
                "evidence_score": stability["evidence_score"],
                "consistency_score": stability["consistency_score"],
                "confidence_score": stability["confidence_score"],
                "traceability_score": stability["traceability_score"],
                "anomaly_score": stability["anomaly_score"],
                "risk_score": stability["risk_score"],
                "risk_level": stability["risk_level"],
                "dimension_detail": stability.get("dimension_detail"),
                "sampling_results": {"timeline": state.get("timeline") or []},
                "root_cause": None,
                "hallucination_risk": float(trust_scoring.get("hallucination_risk")) if isinstance(trust_scoring, dict) and trust_scoring.get("hallucination_risk") is not None else None,
                "overconfidence": float(trust_scoring.get("overconfidence")) if isinstance(trust_scoring, dict) and trust_scoring.get("overconfidence") is not None else None,
                "created_at": utcnow(),
            }
            stability_obj = await stability_repo.upsert_by_task(stability_payload)

            if should_trigger(stability):
                from app.services.rule_engine_service import RuleEngineService
                import logging
                _logger = logging.getLogger(__name__)
                rule_engine = RuleEngineService(session)

                metrics = {
                    "risk_score_100": float(stability.get("risk_score_100", 0)),
                    "risk_score": float(stability.get("risk_score", 0)),
                    "evidence_score": float(stability.get("evidence_score", 0)),
                    "consistency_score": float(stability.get("consistency_score", 0)),
                    "confidence_score": float(stability.get("confidence_score", 0)),
                    "traceability_score": float(stability.get("traceability_score", 0)),
                    "anomaly_score": float(stability.get("anomaly_score", 0)),
                }

                matches = await rule_engine.evaluate_and_get_matches(
                    org_id=task.org_id,
                    alert_type="stability_risk",
                    metrics=metrics,
                )

                matched_any = False
                for rule in matches:
                    if await rule_engine.is_in_cooldown(rule, task.org_id):
                        _logger.info(
                            "Rule %s is in cooldown, suppressing alert", str(rule.id)
                        )
                        continue

                    matched_any = True
                    alert_id = str(uuid7())
                    await alert_repo.create(
                        {
                            "id": alert_id,
                            "org_id": task.org_id,
                            "rule_id": str(rule.id),
                            "stability_id": stability_obj.id,
                            "alert_type": "stability_risk",
                            "severity": rule.severity,
                            "title": f"任务 {task.id} 触发稳定性风险告警 (规则: {rule.name})",
                            "detail": {
                                "risk_level": stability.get("risk_level"),
                                "risk_score": stability.get("risk_score_100"),
                                "metric_values": metrics,
                                "rule_condition": rule.condition_config,
                            },
                            "status": "open",
                            "channels": rule.notification_channels or {"in_app": True},
                            "created_at": utcnow(),
                        }
                    )
                    try:
                        from worker.tasks.alert_dispatch_task import dispatch_alert
                        dispatch_alert.delay(alert_id)
                    except Exception:
                        _logger.exception("Failed to enqueue dispatch for alert %s", alert_id)

                if not matched_any:
                    severity = "critical" if stability.get("risk_level") == "critical" else "warning"
                    fallback_alert_id = str(uuid7())
                    await alert_repo.create(
                        {
                            "id": fallback_alert_id,
                            "org_id": task.org_id,
                            "rule_id": None,
                            "stability_id": stability_obj.id,
                            "alert_type": "stability_risk",
                            "severity": severity,
                            "title": f"任务 {task.id} 触发稳定性风险告警，等级 {stability.get('risk_level')}",
                            "detail": {
                                "risk_level": stability.get("risk_level"),
                                "risk_score": stability.get("risk_score_100"),
                            },
                            "status": "open",
                            "channels": {"in_app": True},
                            "created_at": utcnow(),
                        }
                    )
                    try:
                        from worker.tasks.alert_dispatch_task import dispatch_alert
                        dispatch_alert.delay(fallback_alert_id)
                    except Exception:
                        _logger.exception("Failed to enqueue dispatch for fallback alert %s", fallback_alert_id)

                await emit({"type": "alert", "message": "stability risk alert triggered"})

            await task_repo.update_status(org_id, task_id, "done")
            done_metadata = dict(task.meta_data or {})
            done_metadata["execution"] = {
                **dict(done_metadata.get("execution") or {}),
                "finished_at": utcnow_iso(),
            }
            await task_repo.patch_metadata(org_id, task_id, done_metadata)
            await session.commit()


            await emit({"type": "status", "status": "done"})
            await emit(
                {
                    "type": "model_selected",
                    "model_id": state.get("model_id"),
                    "model_config_id": state.get("model_config_id"),
                    "provider": state.get("model_provider"),
                }
            )
            await emit(
                {
                    "type": "standard_gate",
                    "spec_code": task.spec_code,
                    "verdict": standard_evaluation.get("verdict"),
                    "reasons": standard_evaluation.get("reasons") or [],
                }
            )
            await emit({"type": "result", "verdict": result.verdict, "overall_score": float(result.overall_score)})
            await emit(
                {
                    "type": "stability",
                    "risk_level": stability_obj.risk_level,
                    "risk_score": float(stability_obj.risk_score),
                }
            )
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
            await task_repo.update_status(org_id, task_id, "failed")
            failed_metadata = dict(task.meta_data or {})
            failed_metadata["execution"] = {
                **dict(failed_metadata.get("execution") or {}),
                "finished_at": utcnow_iso(),
                "error": str(exc),
            }
            await task_repo.patch_metadata(org_id, task_id, failed_metadata)
            await session.commit()
            await emit(
                {
                    "type": "error",
                    "status": "failed",
                    "message": str(exc),
                    "trace": traceback.format_exc(limit=2),
                }
            )
            if linked_chat_session_id:
                await _append_chat_failure_summary(
                    org_id=org_id,
                    user_id=str(task.created_by),
                    session_id=linked_chat_session_id,
                    task=task,
                    error_message=str(exc),
                )
            raise
