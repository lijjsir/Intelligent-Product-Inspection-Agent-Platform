from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.core.exceptions import NotFoundError, ForbiddenError
from app.repositories.result_repo import ResultRepository
from app.repositories.task_repo import TaskRepository
from app.services.result_trace_utils import (
    build_trace_metrics,
    derive_latency_ms,
    extract_citation_items,
)

REVIEW_ROLES = {"expert", "platform_operator"}


class ResultService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = ResultRepository(session)

    async def get_by_task(self, task_id: str):
        return await self._repo.get_by_task(self._org_id, task_id)

    async def get_response_by_task(self, task_id: str) -> dict | None:
        result = await self._repo.get_by_task(self._org_id, task_id)
        if result is None:
            return None
        task = await TaskRepository(self._session).get(self._org_id, task_id)
        return self.build_result_response_payload(result, task=task)

    async def get_by_id(self, result_id: str):
        return await self._repo.get_by_id(self._org_id, result_id)

    @staticmethod
    def build_result_response_payload(result, *, task=None) -> dict:
        citations = result.citations
        citation_items = extract_citation_items(citations)
        reasoning_chain = dict(result.reasoning_chain or {})
        trace = dict(reasoning_chain.get("trace") or {})
        standard_evaluation = reasoning_chain.get("standard_evaluation")
        output_text = ""
        if isinstance(standard_evaluation, dict):
            output_text = str(standard_evaluation.get("summary") or "")
        trace_metrics = build_trace_metrics(
            reasoning_chain=reasoning_chain,
            input_text=str(getattr(task, "meta_data", None) or result.task_id or ""),
            output_text=output_text,
            citations=citation_items,
            synthesize_missing=False,
        )
        trace.update({key: value for key, value in trace_metrics.items() if value is not None})
        if trace:
            reasoning_chain["trace"] = trace

        return {
            "id": result.id,
            "task_id": result.task_id,
            "org_id": result.org_id,
            "verdict": result.verdict,
            "overall_score": float(result.overall_score or 0.0),
            "defects": result.defects,
            "citations": citations,
            "reasoning_chain": reasoning_chain,
            "llm_model": result.llm_model,
            "prompt_version": result.prompt_version,
            "tokens_used": result.tokens_used,
            "latency_ms": derive_latency_ms(result.latency_ms, task=task),
            "reviewed_by": result.reviewed_by,
            "reviewed_at": result.reviewed_at,
            "review_note": result.review_note,
            "created_at": result.created_at,
        }

    async def list_results(self, query):
        return await self._repo.list_paged(
            self._org_id,
            verdict=query.verdict,
            product_id=query.product_id,
            model_key=query.model_key,
            task_id=query.task_id,
            page=query.page,
            size=query.size,
        )

    async def review(self, result_id: str, actor_user_id: str, actor_role: str, payload: dict) -> dict:
        if actor_role not in REVIEW_ROLES:
            raise ForbiddenError(f"role {actor_role} cannot review results")
        result = await self._repo.get_by_id(self._org_id, result_id)
        if not result:
            raise NotFoundError("Result not found")
        await self._repo.upsert_by_task({
            "org_id": self._org_id,
            "task_id": result.task_id,
            "verdict": payload["verdict"],
            "overall_score": result.overall_score,
            "defects": result.defects,
            "citations": result.citations,
            "reasoning_chain": result.reasoning_chain,
            "llm_model": result.llm_model,
            "prompt_version": result.prompt_version,
            "tokens_used": result.tokens_used,
            "latency_ms": result.latency_ms,
            "reviewed_by": actor_user_id,
            "reviewed_at": utcnow(),
            "review_note": payload.get("note", ""),
            "id": result.id,
        })
        reviewed = await self._repo.get_by_id(self._org_id, result_id)
        return {
            "id": reviewed.id,
            "task_id": reviewed.task_id,
            "org_id": reviewed.org_id,
            "verdict": reviewed.verdict,
            "overall_score": float(reviewed.overall_score or 0.0),
            "reviewed_by": reviewed.reviewed_by,
            "reviewed_at": reviewed.reviewed_at,
            "review_note": reviewed.review_note,
        }
