from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from agent.llm.langfuse_tracer import LangfuseTracer
from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.repositories.feedback_repo import FeedbackRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.repositories.chat_score_repo import ChatMessageScoreRepository
from app.repositories.chat_repo import ChatMessageRepository
from app.services.base import TenantAwareService


class QualityReportService(TenantAwareService):
    def __init__(self, session, org_id: str | None):
        super().__init__(session, org_id)
        self._feedback_repo = FeedbackRepository(session)
        self._result_repo = ResultRepository(session)
        self._stability_repo = StabilityRepository(session)
        self._token_ledger_repo = TokenLedgerRepository(session)
        self._chat_score_repo = ChatMessageScoreRepository(session)
        self._chat_message_repo = ChatMessageRepository(session)

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

    async def list_traces(self, limit: int = 100, source: str = "all") -> list[dict]:
        results = await self._result_repo.list_by_range(self._org_id)
        feedbacks = await self._feedback_repo.list_by_range(self._org_id)
        ledger_items = await self._token_ledger_repo.list_filtered(self._org_id)
        chat_scores = await self._chat_score_repo.list_by_range(self._org_id, limit=limit)
        chat_messages = await self._chat_message_repo.list_assistant_for_org(self._org_id, limit=limit)
        if source == "inspection":
            chat_scores, chat_messages = [], []
        if source == "chat":
            results, feedbacks = [], []
        trace_exists_cache: dict[str, bool | None] = {}
        tracer = LangfuseTracer()

        def langfuse_trace_exists(trace_id: str | None) -> bool | None:
            if not trace_id:
                return None
            trace_key = str(trace_id)
            if trace_key not in trace_exists_cache:
                trace_exists_cache[trace_key] = tracer.trace_exists(trace_key)
            return trace_exists_cache[trace_key]

        return self._build_quality_traces(
            results,
            feedbacks,
            ledger_items,
            limit=limit,
            chat_scores=chat_scores,
            chat_messages=chat_messages,
            langfuse_trace_exists=langfuse_trace_exists,
        )

    async def build_report(self, start_date=None, end_date=None, source: str = "all"):
        results = await self._result_repo.list_by_range(self._org_id, start_date, end_date)
        feedbacks = await self._feedback_repo.list_by_range(self._org_id, start_date, end_date)
        stabilities = await self._stability_repo.list_by_range(self._org_id, start_date, end_date)
        chat_scores = await self._chat_score_repo.list_by_range(self._org_id, start_date, end_date)
        chat_messages = await self._chat_message_repo.list_assistant_for_org(self._org_id, start_date=start_date, end_date=end_date)
        if source == "inspection":
            chat_scores, chat_messages = [], []
        elif source == "chat":
            results, feedbacks, stabilities = [], [], []

        total_results = len(results) + len(chat_messages)
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
        for msg in chat_messages:
            payload = msg.payload or {}
            model_key = str(payload.get("llm_meta", {}).get("model") or "chat_model")
            model_counter[model_key].append(msg)

        model_metrics = []
        for model_key, model_results in sorted(model_counter.items()):
            result_count = len(model_results)
            if any(hasattr(item, "verdict") for item in model_results):
                model_metrics.append({
                    "model_key": model_key,
                    "result_count": result_count,
                    "pass_rate": round(sum(1 for item in model_results if hasattr(item, "verdict") and item.verdict == "pass") / result_count, 4) if result_count else 0.0,
                    "hallucination_rate": round(sum(1 for item in model_results if hasattr(item, "citations") and not self._has_citations(item.citations)) / result_count, 4) if result_count else 0.0,
                    "thumbs_down_rate": 0.0,
                })
            else:
                model_metrics.append({
                    "model_key": model_key,
                    "result_count": result_count,
                    "pass_rate": 0.0,
                    "hallucination_rate": 0.0,
                    "thumbs_down_rate": 0.0,
                })

        return {
            "total_results": total_results,
            "hallucination_rate": round(hallucination_count / total_results, 4) if total_results else 0.0,
            "thumbs_down_rate": round(thumbs_down_count / total_results, 4) if total_results else 0.0,
            "avg_risk_score": avg_risk_score,
            "feedback_distribution": dict(Counter((item.category or "uncategorized") for item in feedbacks)),
            "hallucination_trend": self._build_result_trend(results, lambda item: 0 if self._has_citations(item.citations) else 1),
            "thumbs_down_trend": self._build_feedback_trend(feedbacks),
            "model_metrics": model_metrics,
            "chat_score_count": len(chat_scores),
            "chat_avg_trust_score": self._avg_chat_value(chat_scores, "trust_score"),
            "chat_hallucination_rate": self._chat_rate(chat_scores, "hallucination_risk", threshold=0.6),
            "chat_overconfidence_rate": self._chat_rate(chat_scores, "overconfidence", threshold=0.6),
            "chat_citation_rate": self._chat_citation_rate(chat_scores),
            "chat_trust_trend": self._build_chat_score_trend(chat_scores, "trust_score"),
        }

    @staticmethod
    def _build_quality_traces(
        results,
        feedbacks,
        ledger_items,
        limit: int = 100,
        chat_scores=None,
        chat_messages=None,
        langfuse_trace_exists=None,
    ) -> list[dict]:
        ledger_by_result: dict[str, list] = defaultdict(list)
        ledger_by_trace: dict[str, list] = defaultdict(list)
        for item in ledger_items:
            if item.result_id:
                ledger_by_result[item.result_id].append(item)
            if item.trace_id:
                ledger_by_trace[str(item.trace_id)].append(item)

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
                    "source_type": "inspection",
                    "trace_id": trace_id,
                    "trace_url": trace_meta.get("trace_url"),
                    "result_id": result.id,
                    "task_id": result.task_id,
                    "assistant_message_id": None,
                    "session_id": None,
                    "observation_id": None,
                    "verdict": result.verdict,
                    "model_key": model_key,
                    "total_tokens": total_tokens,
                    "feedback_count": len(feedback_group),
                    "thumbs_down_count": thumbs_down_count,
                    "last_score_value": None if not latest_score else float(latest_score.get("value") or 0.0),
                    "last_score_at": None if not latest_score else latest_score.get("scored_at"),
                    "trust_score": None if not latest_score else float(latest_score.get("value") or 0.0),
                    "hallucination_risk": None,
                    "overconfidence": None,
                    "has_citation": None,
                    "score_status": None,
                    "review_model": None,
                    "langfuse_status": "local_only",
                    "langfuse_synced": None,
                    "created_at": result.created_at,
                }
            )

        for score in list(chat_scores or []):
            trace_id = str(score.trace_id or "")
            ledger_group = ledger_by_trace.get(trace_id, [])
            total_tokens = sum(int(item.total_tokens or 0) for item in ledger_group)
            traces.append(
                {
                    "source_type": "chat",
                    "trace_id": trace_id,
                    "trace_url": score.trace_url,
                    "result_id": None,
                    "task_id": None,
                    "assistant_message_id": str(score.assistant_message_id),
                    "session_id": str(score.session_id),
                    "observation_id": score.observation_id,
                    "verdict": None,
                    "model_key": score.model_key,
                    "total_tokens": total_tokens,
                    "feedback_count": 0,
                    "thumbs_down_count": 0,
                    "last_score_value": None if score.trust_score is None else float(score.trust_score),
                    "last_score_at": score.langfuse_synced_at,
                    "trust_score": None if score.trust_score is None else float(score.trust_score),
                    "hallucination_risk": None if score.hallucination_risk is None else float(score.hallucination_risk),
                    "overconfidence": None if score.overconfidence is None else float(score.overconfidence),
                    "has_citation": score.has_citation,
                    "score_status": score.status,
                    "review_model": score.review_model,
                    "langfuse_status": "local_only",
                    "langfuse_synced": score.langfuse_synced_at is not None,
                    "created_at": score.created_at,
                }
            )

        scored_ids = {str(s.assistant_message_id) for s in (chat_scores or []) if s.assistant_message_id}
        for msg in list(chat_messages or []):
            if str(msg.id) in scored_ids:
                continue
            payload = msg.payload or {}
            llm_meta = payload.get("llm_meta") or {}
            trace_id = str(llm_meta.get("langfuse", {}).get("trace_id") or msg.id)
            ledger_group = ledger_by_trace.get(trace_id, [])
            traces.append(
                {
                    "source_type": "chat",
                    "trace_id": trace_id,
                    "trace_url": None,
                    "result_id": None,
                    "task_id": None,
                    "assistant_message_id": str(msg.id),
                    "session_id": str(msg.session_id),
                    "observation_id": None,
                    "verdict": None,
                    "model_key": str(llm_meta.get("model") or "chat_model"),
                    "total_tokens": sum(int(item.total_tokens or 0) for item in ledger_group)
                    or int(llm_meta.get("usage", {}).get("total_tokens") or 0),
                    "feedback_count": 0,
                    "thumbs_down_count": 0,
                    "last_score_value": None,
                    "last_score_at": None,
                    "trust_score": None,
                    "hallucination_risk": None,
                    "overconfidence": None,
                    "has_citation": None,
                    "score_status": "unscored",
                    "review_model": None,
                    "langfuse_status": "local_only",
                    "langfuse_synced": False,
                    "created_at": msg.created_at,
                }
            )

        traces = QualityReportService._normalize_langfuse_trace_statuses(
            traces,
            langfuse_trace_exists=langfuse_trace_exists,
        )
        traces.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return traces[:limit]

    @staticmethod
    def _normalize_langfuse_trace_statuses(traces: list[dict], langfuse_trace_exists=None) -> list[dict]:
        normalized: list[dict] = []
        for item in traces:
            trace = dict(item)
            trace_id = trace.get("trace_id")
            has_remote_link = bool(trace.get("trace_url"))
            has_remote_history = bool(trace.get("langfuse_synced")) or bool(trace.get("last_score_at") and has_remote_link)

            if not has_remote_history:
                trace["langfuse_status"] = "local_only"
                if trace.get("langfuse_synced") is not None:
                    trace["langfuse_synced"] = False
                normalized.append(trace)
                continue

            exists = langfuse_trace_exists(trace_id) if callable(langfuse_trace_exists) else True
            if exists is True:
                trace["langfuse_status"] = "synced"
                trace["langfuse_synced"] = True
            elif exists is False:
                trace["langfuse_status"] = "missing"
                trace["langfuse_synced"] = False
                trace["trace_url"] = None
            else:
                trace["langfuse_status"] = "unknown"
                trace["langfuse_synced"] = False
                trace["trace_url"] = None

            normalized.append(trace)
        return normalized

    @staticmethod
    def _avg_chat_value(scores, attr: str) -> float:
        values = [float(getattr(item, attr) or 0.0) for item in scores if getattr(item, attr) is not None]
        return round(sum(values) / len(values), 4) if values else 0.0

    @staticmethod
    def _chat_rate(scores, attr: str, threshold: float) -> float:
        values = [float(getattr(item, attr) or 0.0) for item in scores if getattr(item, attr) is not None]
        return round(sum(1 for value in values if value >= threshold) / len(values), 4) if values else 0.0

    @staticmethod
    def _chat_citation_rate(scores) -> float:
        values = [bool(getattr(item, "has_citation")) for item in scores if getattr(item, "has_citation") is not None]
        return round(sum(1 for value in values if value) / len(values), 4) if values else 0.0

    @staticmethod
    def _build_chat_score_trend(scores, attr: str):
        buckets: dict[str, list[float]] = defaultdict(list)
        for item in scores:
            value = getattr(item, attr, None)
            if value is None:
                continue
            buckets[item.created_at.strftime("%Y-%m-%d")].append(float(value))
        return [
            {"bucket": bucket, "value": round(sum(values) / len(values), 4)}
            for bucket, values in sorted(buckets.items())
        ]
