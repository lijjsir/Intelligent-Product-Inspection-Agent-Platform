from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.repositories.feedback_repo import FeedbackRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.services.base import TenantAwareService


class QualityReportService(TenantAwareService):
    def __init__(self, session, org_id: str):
        super().__init__(session, org_id)
        self._feedback_repo = FeedbackRepository(session)
        self._result_repo = ResultRepository(session)
        self._stability_repo = StabilityRepository(session)
        self._token_ledger_repo = TokenLedgerRepository(session)

    async def build_report(self, start_date: date | None = None, end_date: date | None = None):
        results = await self._result_repo.list_by_range(self._org_id, start_date, end_date)
        feedbacks = await self._feedback_repo.list_by_range(self._org_id, start_date, end_date)
        stabilities = await self._stability_repo.list_by_range(self._org_id, start_date, end_date)

        total_results = len(results)
        hallucination_count = sum(1 for item in results if not self._has_citations(item.citations))
        thumbs_down_count = sum(1 for item in feedbacks if item.feedback_type == "down")
        avg_risk_score = round(
            sum(float(item.risk_score or 0.0) for item in stabilities) / len(stabilities),
            4,
        ) if stabilities else 0.0

        model_counter: dict[str, list] = defaultdict(list)
        result_by_id = {item.id: item for item in results}
        feedbacks_by_result: dict[str, list] = defaultdict(list)
        for feedback in feedbacks:
            feedbacks_by_result[feedback.result_id].append(feedback)
        for item in results:
            model_counter[item.llm_model].append(item)

        model_metrics = []
        for model_key, model_results in sorted(model_counter.items()):
            downs = sum(
                1
                for result in model_results
                for feedback in feedbacks_by_result.get(result.id, [])
                if feedback.feedback_type == "down"
            )
            result_count = len(model_results)
            model_metrics.append(
                {
                    "model_key": model_key,
                    "result_count": result_count,
                    "pass_rate": round(sum(1 for item in model_results if item.verdict == "pass") / result_count, 4)
                    if result_count else 0.0,
                    "hallucination_rate": round(sum(1 for item in model_results if not self._has_citations(item.citations)) / result_count, 4)
                    if result_count else 0.0,
                    "thumbs_down_rate": round(downs / result_count, 4) if result_count else 0.0,
                }
            )

        return {
            "total_results": total_results,
            "hallucination_rate": round(hallucination_count / total_results, 4) if total_results else 0.0,
            "thumbs_down_rate": round(thumbs_down_count / total_results, 4) if total_results else 0.0,
            "avg_risk_score": avg_risk_score,
            "feedback_distribution": dict(Counter((item.category or "uncategorized") for item in feedbacks)),
            "hallucination_trend": self._build_result_trend(results, lambda item: 0 if self._has_citations(item.citations) else 1),
            "thumbs_down_trend": self._build_feedback_trend(feedbacks),
            "model_metrics": model_metrics,
        }

    @staticmethod
    def _has_citations(citations) -> bool:
        if not citations:
            return False
        if isinstance(citations, dict):
            items = citations.get("items")
            return bool(items)
        if isinstance(citations, list):
            return bool(citations)
        return True

    @staticmethod
    def _build_result_trend(results, mapper):
        buckets: dict[str, list[int]] = defaultdict(list)
        for item in results:
            buckets[item.created_at.strftime("%Y-%m-%d")].append(int(mapper(item)))
        return [
            {"bucket": bucket, "value": round(sum(values) / len(values), 4)}
            for bucket, values in sorted(buckets.items())
        ]

    @staticmethod
    def _build_feedback_trend(feedbacks):
        totals: dict[str, dict[str, int]] = defaultdict(lambda: {"all": 0, "down": 0})
        for item in feedbacks:
            bucket = item.created_at.strftime("%Y-%m-%d")
            totals[bucket]["all"] += 1
            if item.feedback_type == "down":
                totals[bucket]["down"] += 1
        return [
            {"bucket": bucket, "value": round(values["down"] / values["all"], 4) if values["all"] else 0.0}
            for bucket, values in sorted(totals.items())
        ]

    async def list_traces(self, limit: int = 100) -> list[dict]:
        results = await self._result_repo.list_by_range(self._org_id)
        feedbacks = await self._feedback_repo.list_by_range(self._org_id)
        ledger_items = await self._token_ledger_repo.list_filtered(self._org_id)
        return self._build_quality_traces(results, feedbacks, ledger_items, limit=limit)

    @staticmethod
    def _build_quality_traces(results, feedbacks, ledger_items, limit: int = 100) -> list[dict]:
        ledger_by_result: dict[str, list] = defaultdict(list)
        for item in ledger_items:
            if item.result_id:
                ledger_by_result[item.result_id].append(item)

        feedbacks_by_result: dict[str, list] = defaultdict(list)
        for item in feedbacks:
            feedbacks_by_result[item.result_id].append(item)

        traces: list[dict] = []
        for result in sorted(results, key=lambda item: item.created_at, reverse=True):
            reasoning_chain = result.reasoning_chain or {}
            trace_meta = reasoning_chain.get("trace") if isinstance(reasoning_chain, dict) else {}
            score_events = reasoning_chain.get("langfuse_scores") if isinstance(reasoning_chain, dict) else []
            if not isinstance(trace_meta, dict):
                trace_meta = {}
            if not isinstance(score_events, list):
                score_events = []

            ledger_group = ledger_by_result.get(result.id, [])
            feedback_group = feedbacks_by_result.get(result.id, [])

            latest_score = None
            score_candidates = [item for item in score_events if isinstance(item, dict)]
            if score_candidates:
                latest_score = max(score_candidates, key=lambda item: item.get("scored_at") or "")

            trace_id = str(
                trace_meta.get("trace_id")
                or (ledger_group[0].trace_id if ledger_group and ledger_group[0].trace_id else "")
                or result.task_id
            )
            model_key = str(
                trace_meta.get("model_key")
                or result.llm_model
                or (ledger_group[0].model_key if ledger_group else "")
            )
            total_tokens = sum(int(item.total_tokens or 0) for item in ledger_group)
            thumbs_down_count = sum(1 for item in feedback_group if item.feedback_type == "down")

            traces.append(
                {
                    "trace_id": trace_id,
                    "trace_url": trace_meta.get("trace_url"),
                    "result_id": result.id,
                    "task_id": result.task_id,
                    "verdict": result.verdict,
                    "model_key": model_key,
                    "total_tokens": total_tokens,
                    "feedback_count": len(feedback_group),
                    "thumbs_down_count": thumbs_down_count,
                    "last_score_value": None if not latest_score else float(latest_score.get("value") or 0.0),
                    "last_score_at": None if not latest_score else latest_score.get("scored_at"),
                    "created_at": result.created_at,
                }
            )

        return traces[:limit]
