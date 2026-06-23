from __future__ import annotations

from typing import Any

from agent.contracts.quality_contracts import (
    PersistableOutput,
    QualityTraceEvent,
    RagQueryLog,
    ResultAggregate,
    StabilityAggregate,
    TaskAggregate,
    TokenUsageEvent,
)


class QualityResultMaterializationService:
    """质量检测结果落库服务 — 从 QualityAnalysisGraph 调用。

    封装 ResultRepository、StabilityRepository、TaskRepository、
    TaskExecutionEventRepository 的写入逻辑。
    """

    def __init__(self, db_session):
        self.db = db_session

    async def build_persistable_output(
        self,
        *,
        org_id: str,
        workflow_run_id: str,
        final_state: dict[str, Any],
        standard_evaluation: dict[str, Any],
    ) -> PersistableOutput:
        """构建标准 PersistableOutput，含 result / stability / quality_trace / rag_queries。"""
        assessment = final_state.get("final_assessment") or {}
        answer = final_state.get("answer") or ""
        report = final_state.get("report") or ""
        evidence_packet = final_state.get("evidence_packet") or {}
        llm_prompt = final_state.get("llm_prompt", "")
        request = final_state.get("request") if isinstance(final_state.get("request"), dict) else {}
        ext = dict(request.get("ext") or {})
        ext.update(dict(final_state.get("ext") or {}))
        metadata = dict(request.get("metadata") or {})
        metadata.update(dict(final_state.get("metadata") or {}))
        llm_meta = dict(final_state.get("llm_meta") or {})
        usage = dict(llm_meta.get("usage") or {})

        task_id = (
            final_state.get("task_id")
            or ext.get("task_id")
            or metadata.get("task_id")
        )
        product_id = (
            final_state.get("product_id")
            or ext.get("product_id")
            or metadata.get("product_id")
        )
        spec_code = (
            final_state.get("spec_code")
            or ext.get("spec_code")
            or metadata.get("spec_code")
        )
        image_urls = list(final_state.get("image_urls") or ext.get("image_urls") or metadata.get("image_urls") or [])
        image_items = list(final_state.get("image_items") or ext.get("image_items") or metadata.get("image_items") or [])
        image_count = max(len(image_urls), len(image_items))
        model_key = str(
            llm_meta.get("model")
            or metadata.get("model_key")
            or metadata.get("model_id")
            or final_state.get("model_id")
            or "quality_analysis"
        )

        result = ResultAggregate(
            task_id=str(task_id) if task_id else None,
            verdict=assessment.get("final_verdict", "uncertain"),
            overall_score=assessment.get("overall_score"),
            llm_model=model_key,
            citations=final_state.get("citations") or {},
            reasoning_chain={
                "standard_evaluation": standard_evaluation,
                "report": report,
                "llm_prompt": llm_prompt,
            },
        )

        stability = StabilityAggregate(
            risk_score=assessment.get("risk_score"),
            risk_level=assessment.get("risk_level", "low"),
            evidence_score=float(len(evidence_packet.get("sources", {})) if evidence_packet else 0),
            confidence_score=assessment.get("confidence"),
            traceability_score=assessment.get("traceability_score"),
            faithfulness_score=assessment.get("faithfulness_score"),
            physical_hallucination_score=assessment.get("physical_hallucination_score"),
        )

        quality_trace = QualityTraceEvent(
            trace_id=llm_meta.get("trace_id") or final_state.get("trace_id") or final_state.get("workflow_run_id") or workflow_run_id,
            workflow_version="quality_analysis_graph_v1",
            route_subgraph="quality_analysis",
            has_citation=bool(final_state.get("citations")),
        )

        rag_queries = []
        if evidence_packet:
            rag_query = evidence_packet.get("query", "")
            rag_queries.append(
                RagQueryLog(
                    query=rag_query,
                    rag_space_id=evidence_packet.get("rag_space_id"),
                    top_k=evidence_packet.get("top_k") or 0,
                    hit_count=len(evidence_packet.get("rag_hits") or []),
                    source_graph="evidence_arbitration",
                    agent_name="evidence",
                    sub_route="evidence_arbitration",
                    metadata={
                        "memory_hit_count": len(evidence_packet.get("memory_hits") or []),
                        "kg_hit_count": len(evidence_packet.get("kg_hits") or []),
                    },
                )
            )

        token_usage = []
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        if total_tokens > 0:
            token_usage.append(
                TokenUsageEvent(
                    model_key=model_key,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost_amount=float(usage.get("cost_amount") or 0.0),
                    trace_id=quality_trace.trace_id,
                )
            )

        return PersistableOutput(
            task=TaskAggregate(
                id=str(task_id) if task_id else None,
                product_id=str(product_id) if product_id else None,
                spec_code=str(spec_code) if spec_code else None,
                status=str(ext.get("status") or metadata.get("status") or "done"),
                priority=int(ext.get("priority") or metadata.get("priority") or 0) or None,
                image_count=image_count,
            ),
            result=result,
            stability=stability,
            token_usage=token_usage,
            quality_trace=quality_trace,
            rag_queries=rag_queries,
        )

    async def persist_success(
        self,
        *,
        task_id: str,
        org_id: str,
        final_state: dict[str, Any],
        standard_evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        """任务成功时持久化结果。"""
        try:
            from app.repositories.result_repo import ResultRepository
            from app.repositories.task_repo import TaskRepository

            persistable = await self.build_persistable_output(
                org_id=org_id,
                workflow_run_id=final_state.get("workflow_run_id", ""),
                final_state=final_state,
                standard_evaluation=standard_evaluation,
            )

            await ResultRepository(self.db).upsert_by_task(
                org_id=org_id,
                task_id=task_id,
                result_data=persistable.model_dump(),
            )

            await TaskRepository(self.db).update_status(
                org_id=org_id,
                task_id=task_id,
                status="done",
            )

            return {"status": "persisted", "task_id": task_id}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc)}

    async def persist_failure(
        self,
        *,
        task_id: str,
        org_id: str,
        error_message: str,
    ) -> dict[str, Any]:
        """任务失败时记录错误。"""
        try:
            from app.repositories.task_repo import TaskRepository

            await TaskRepository(self.db).update_status(
                org_id=org_id,
                task_id=task_id,
                status="failed",
                error=error_message,
            )

            return {"status": "failed_logged", "task_id": task_id}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc)}

    async def emit_event(
        self,
        *,
        task_id: str,
        org_id: str,
        event_type: str,
        message: str,
        stage: str | None = None,
    ) -> None:
        """发送 SSE 事件。"""
        try:
            from app.repositories.task_execution_event_repo import TaskExecutionEventRepository

            await TaskExecutionEventRepository(self.db).create(
                org_id=org_id,
                task_id=task_id,
                event_type=event_type,
                message=message,
                stage=stage,
            )
        except Exception:
            pass
