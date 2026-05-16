"""Quality data layer — split by responsibility.

Boundary:
  Langfuse (via REST API)           piap-mysql (local)
  ─────────────────────────         ──────────────────
  · trace 链路 / timeline           · verdict 判定结果
  · observations (LLM 调用)         · task 任务元信息
  · scores (trust / feedback)       · feedback 用户反馈统计
  · model / tokens 用量             · citations 引用证据
  · trace_url 跳转链接              · stability 稳定性维度
                                    · 聚合报告 (build_report)

  linkage: trace_id 贯穿两边，QualityTraceItem 由两边字段拼装。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime

import logging

from agent.llm.langfuse_tracer import LangfuseTracer
from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.repositories.feedback_repo import FeedbackRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.repositories.chat_score_repo import ChatMessageScoreRepository
from app.repositories.chat_repo import ChatMessageRepository
from app.services.base import TenantAwareService
from app.services.langfuse_api_client import LangfuseApiClient, LangfuseApiError

logger = logging.getLogger(__name__)


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
        result = await self.list_traces_with_meta(limit=limit, source=source)
        return result["items"]

    async def list_traces_with_meta(self, limit: int = 100, source: str = "all") -> dict:
        api_client = LangfuseApiClient()
        meta: dict = {
            "langfuse_enabled": api_client.enabled,
            "langfuse_status": "disabled" if not api_client.enabled else "unknown",
            "langfuse_error": None,
            "source": source,
            "canonical_source": "local",
        }
        if api_client.enabled:
            meta["canonical_source"] = "langfuse"
            traces, error = await self._fetch_traces_from_langfuse(source=source, limit=limit, api_client=api_client)
            if error:
                meta["langfuse_status"] = "error"
                meta["langfuse_error"] = str(error)
                meta["item_count"] = 0
                return {"items": [], "meta": meta}
            else:
                meta["langfuse_status"] = "ok"
            meta["item_count"] = len(traces)
            return {"items": traces, "meta": meta}

        traces = await self._list_traces_from_mysql(
            limit=limit,
            source=source,
            api_client=api_client,
            langfuse_available=meta["langfuse_status"] == "ok",
        )
        meta["item_count"] = len(traces)
        return {"items": traces, "meta": meta}

    async def _list_traces_from_mysql(
        self,
        *,
        limit: int,
        source: str,
        api_client: LangfuseApiClient,
        langfuse_available: bool,
    ) -> list[dict]:
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
                trace_exists_cache[trace_key] = tracer.trace_exists(trace_key) if langfuse_available else None
            return trace_exists_cache[trace_key]

        def build_trace_url(trace_id: str | None) -> str | None:
            if not trace_id:
                return None
            if api_client.enabled and langfuse_available:
                return api_client.build_trace_url(str(trace_id))
            return tracer.get_trace_url(str(trace_id))

        return self._build_quality_traces(
            results, feedbacks, ledger_items, limit=limit,
            chat_scores=chat_scores, chat_messages=chat_messages,
            langfuse_trace_exists=langfuse_trace_exists,
            build_trace_url=build_trace_url,
        )

    async def _fetch_traces_from_langfuse(
        self,
        *,
        source: str,
        limit: int,
        api_client: LangfuseApiClient,
        start_date=None,
        end_date=None,
    ) -> tuple[list[dict], str | None]:
        raw_traces: list[dict] = []
        page = 1
        fetch_limit = min(50, max(limit, 10))
        from_timestamp = self._date_start_iso(start_date)
        to_timestamp = self._date_end_iso(end_date)
        while len(raw_traces) < limit:
            try:
                kwargs = {"page": page, "limit": fetch_limit}
                if from_timestamp:
                    kwargs["from_timestamp"] = from_timestamp
                if to_timestamp:
                    kwargs["to_timestamp"] = to_timestamp
                resp = await api_client.list_traces(**kwargs)
            except LangfuseApiError as exc:
                return [], str(exc)
            data = resp.get("data", [])
            if not data:
                break
            raw_traces.extend(
                trace for trace in data if self._langfuse_trace_matches_scope(trace, source=source)
            )
            meta = resp.get("meta", {})
            if page >= meta.get("totalPages", 1):
                break
            page += 1

        hydrated_traces: list[dict] = []
        for trace in raw_traces:
            hydrated_traces.append(await self._hydrate_langfuse_trace(trace, api_client=api_client))

        items = [self._langfuse_trace_to_item(t, api_client=api_client) for t in hydrated_traces]
        items = [i for i in items if i is not None]

        await self._enrich_with_local_business_data(items)

        return items[:limit], None

    @staticmethod
    def _date_start_iso(value) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time()).isoformat()
        return None

    @staticmethod
    def _date_end_iso(value) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return datetime.combine(value, datetime.max.time()).isoformat()
        return None

    async def _hydrate_langfuse_trace(self, trace: dict, *, api_client: LangfuseApiClient) -> dict:
        hydrated = dict(trace)
        trace_id = str(hydrated.get("id") or "")
        if not trace_id:
            return hydrated

        scores = hydrated.get("scores") or []
        observations = hydrated.get("observations") or []
        needs_score_hydration = isinstance(scores, list) and any(isinstance(item, str) for item in scores)
        needs_observation_hydration = isinstance(observations, list) and any(isinstance(item, str) for item in observations)

        if needs_score_hydration or needs_observation_hydration:
            try:
                detail = await api_client.get_trace(trace_id)
                if isinstance(detail, dict):
                    hydrated.update(detail)
            except LangfuseApiError as exc:
                logger.warning("Failed to hydrate Langfuse trace detail for %s: %s", trace_id, exc)

        scores = hydrated.get("scores") or []
        if isinstance(scores, list) and any(isinstance(item, str) for item in scores):
            try:
                score_resp = await api_client.list_scores(trace_id=trace_id, limit=100)
                score_data = score_resp.get("data") or []
                if isinstance(score_data, list):
                    hydrated["scores"] = [
                        item
                        for item in score_data
                        if not isinstance(item, dict)
                        or not item.get("traceId")
                        or str(item.get("traceId")) == trace_id
                    ]
            except LangfuseApiError as exc:
                logger.warning("Failed to hydrate Langfuse scores for trace %s: %s", trace_id, exc)

        observations = hydrated.get("observations") or []
        if isinstance(observations, list) and any(isinstance(item, str) for item in observations):
            try:
                obs_resp = await api_client.list_observations(trace_id=trace_id, limit=100)
                obs_data = obs_resp.get("data") or []
                if isinstance(obs_data, list):
                    hydrated["observations"] = [
                        item
                        for item in obs_data
                        if not isinstance(item, dict)
                        or not item.get("traceId")
                        or str(item.get("traceId")) == trace_id
                    ]
            except LangfuseApiError as exc:
                logger.warning("Failed to hydrate Langfuse observations for trace %s: %s", trace_id, exc)

        return hydrated

    def _langfuse_trace_matches_scope(self, trace: dict, *, source: str) -> bool:
        metadata = trace.get("metadata") or {}
        if self._org_id and metadata.get("org_id") and str(metadata.get("org_id")) != str(self._org_id):
            return False
        if source != "all" and str(metadata.get("source_type") or "") != source:
            return False
        return True

    async def _enrich_with_local_business_data(self, items: list[dict]) -> None:
        """Fill verdict / feedback_count / citations from piap-mysql for traces
        whose Langfuse metadata is missing these business fields."""
        if not self._org_id:
            return

        inspection_task_ids = [
            i["task_id"] for i in items
            if i["source_type"] == "inspection" and i["task_id"] and not i["verdict"]
        ]
        if inspection_task_ids:
            local_results = await self._result_repo.list_by_task_ids(self._org_id, inspection_task_ids)
            result_map = {r.task_id: r for r in local_results}
            for item in items:
                if item["source_type"] == "inspection" and item["task_id"] in result_map:
                    r = result_map[item["task_id"]]
                    if not item["verdict"]:
                        item["verdict"] = r.verdict

    @staticmethod
    def _langfuse_trace_to_item(trace: dict, *, api_client: LangfuseApiClient | None = None) -> dict | None:
        tid = trace.get("id", "")
        if not tid:
            return None
        metadata = trace.get("metadata") or {}
        scores = trace.get("scores") or []
        obs = trace.get("observations") or []
        score_dicts = [s for s in scores if isinstance(s, dict)] if isinstance(scores, list) else []
        observation_dicts = [o for o in obs if isinstance(o, dict)] if isinstance(obs, list) else []
        observation_ids = [
            str(o.get("id") if isinstance(o, dict) else o)
            for o in obs
            if (isinstance(o, dict) and o.get("id")) or isinstance(o, str)
        ] if isinstance(obs, list) else []

        trust_score = None
        hallucination_risk = None
        overconfidence = None
        has_citation = None
        review_model = None
        feedback_count = 0
        thumbs_down_count = 0
        last_score_value = None
        last_score_at = None

        for s in score_dicts:
            name = s.get("name", "")
            value = float(s.get("value", 0))
            if name == "trust_score":
                trust_score = value
            elif name == "hallucination_risk":
                hallucination_risk = value
            elif name == "overconfidence":
                overconfidence = value
            elif name == "has_citation":
                has_citation = bool(value)
            elif name == "user_feedback":
                feedback_count += 1
                if value < 0.5:
                    thumbs_down_count += 1
                last_score_value = value
                last_score_at = s.get("timestamp") or s.get("createdAt")

        total_tokens = sum(
            int((o.get("usage") or {}).get("total", 0))
            for o in observation_dicts if o.get("type") == "GENERATION"
        )
        model_key = metadata.get("model_key", "")
        if not model_key and observation_dicts:
            for o in observation_dicts:
                if o.get("model"):
                    model_key = o["model"]
                    break

        trace_url = None
        if api_client and api_client.enabled:
            trace_url = api_client.build_trace_url(tid)

        return {
            "source_type": metadata.get("source_type", "inspection"),
            "trace_id": tid,
            "trace_url": trace_url,
            "result_id": metadata.get("task_id"),
            "task_id": metadata.get("task_id"),
            "assistant_message_id": None,
            "session_id": trace.get("sessionId"),
            "observation_id": observation_ids[0] if observation_ids else None,
            "verdict": metadata.get("verdict"),
            "model_key": model_key,
            "total_tokens": total_tokens,
            "feedback_count": feedback_count,
            "thumbs_down_count": thumbs_down_count,
            "last_score_value": last_score_value,
            "last_score_at": last_score_at,
            "trust_score": trust_score,
            "hallucination_risk": hallucination_risk,
            "overconfidence": overconfidence,
            "has_citation": has_citation,
            "score_status": "scored" if trust_score is not None else None,
            "review_model": review_model,
            "langfuse_status": "synced",
            "langfuse_synced": True,
            "created_at": trace.get("timestamp"),
            "total_cost": float(trace.get("totalCost") or 0.0),
        }

    async def build_report(self, start_date=None, end_date=None, source: str = "all"):
        api_client = LangfuseApiClient()
        if api_client.enabled:
            traces, error = await self._fetch_traces_from_langfuse(
                source=source,
                limit=1000,
                api_client=api_client,
                start_date=start_date,
                end_date=end_date,
            )
            if not error:
                return self._build_report_from_trace_items(traces)
            logger.warning("Langfuse report source unavailable, returning empty remote-first report: %s", error)
            return self._empty_report()

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
    def _empty_report() -> dict:
        return {
            "total_results": 0,
            "hallucination_rate": 0.0,
            "thumbs_down_rate": 0.0,
            "avg_risk_score": 0.0,
            "feedback_distribution": {},
            "hallucination_trend": [],
            "thumbs_down_trend": [],
            "model_metrics": [],
            "chat_score_count": 0,
            "chat_avg_trust_score": 0.0,
            "chat_hallucination_rate": 0.0,
            "chat_overconfidence_rate": 0.0,
            "chat_citation_rate": 0.0,
            "chat_trust_trend": [],
        }

    @classmethod
    def _build_report_from_trace_items(cls, traces: list[dict]) -> dict:
        total_results = len(traces)
        hallucination_values = [
            float(item["hallucination_risk"])
            for item in traces
            if item.get("hallucination_risk") is not None
        ]
        thumbs_down_count = sum(int(item.get("thumbs_down_count") or 0) for item in traces)
        chat_traces = [item for item in traces if item.get("source_type") == "chat"]
        trust_values = [
            float(item["trust_score"])
            for item in chat_traces
            if item.get("trust_score") is not None
        ]
        overconfidence_values = [
            float(item["overconfidence"])
            for item in chat_traces
            if item.get("overconfidence") is not None
        ]
        citation_values = [
            bool(item["has_citation"])
            for item in chat_traces
            if item.get("has_citation") is not None
        ]

        model_groups: dict[str, list[dict]] = defaultdict(list)
        for item in traces:
            model_groups[str(item.get("model_key") or "unknown")].append(item)

        model_metrics = []
        for model_key, items in sorted(model_groups.items()):
            result_count = len(items)
            pass_count = sum(1 for item in items if item.get("verdict") == "pass")
            model_hallucination_values = [
                float(item["hallucination_risk"])
                for item in items
                if item.get("hallucination_risk") is not None
            ]
            model_metrics.append({
                "model_key": model_key,
                "result_count": result_count,
                "pass_rate": round(pass_count / result_count, 4) if result_count else 0.0,
                "hallucination_rate": round(
                    sum(1 for value in model_hallucination_values if value >= 0.6) / len(model_hallucination_values),
                    4,
                ) if model_hallucination_values else 0.0,
                "thumbs_down_rate": round(
                    sum(int(item.get("thumbs_down_count") or 0) for item in items) / result_count,
                    4,
                ) if result_count else 0.0,
            })

        return {
            "total_results": total_results,
            "hallucination_rate": round(
                sum(1 for value in hallucination_values if value >= 0.6) / len(hallucination_values),
                4,
            ) if hallucination_values else 0.0,
            "thumbs_down_rate": round(thumbs_down_count / total_results, 4) if total_results else 0.0,
            "avg_risk_score": 0.0,
            "feedback_distribution": {},
            "hallucination_trend": cls._build_trace_value_trend(traces, "hallucination_risk", threshold=0.6),
            "thumbs_down_trend": cls._build_trace_count_trend(traces, "thumbs_down_count"),
            "model_metrics": model_metrics,
            "chat_score_count": len(trust_values),
            "chat_avg_trust_score": round(sum(trust_values) / len(trust_values), 4) if trust_values else 0.0,
            "chat_hallucination_rate": round(
                sum(1 for value in hallucination_values if value >= 0.6) / len(hallucination_values),
                4,
            ) if hallucination_values else 0.0,
            "chat_overconfidence_rate": round(
                sum(1 for value in overconfidence_values if value >= 0.6) / len(overconfidence_values),
                4,
            ) if overconfidence_values else 0.0,
            "chat_citation_rate": round(sum(1 for value in citation_values if value) / len(citation_values), 4)
            if citation_values else 0.0,
            "chat_trust_trend": cls._build_trace_average_trend(chat_traces, "trust_score"),
        }

    @classmethod
    def build_overview_quality_from_trace_items(cls, traces: list[dict]) -> dict:
        report = cls._build_report_from_trace_items(traces)
        total_results = int(report["total_results"])
        pass_count = sum(1 for item in traces if item.get("verdict") == "pass")
        model_metrics = []
        for metric in report["model_metrics"]:
            model_items = [item for item in traces if str(item.get("model_key") or "unknown") == metric["model_key"]]
            result_count = len(model_items)
            total_tokens = sum(int(item.get("total_tokens") or 0) for item in model_items)
            total_cost = round(sum(float(item.get("total_cost") or 0.0) for item in model_items), 4)
            model_metrics.append({
                "model_key": metric["model_key"],
                "result_count": metric["result_count"],
                "pass_rate": metric["pass_rate"],
                "hallucination_rate": metric["hallucination_rate"],
                "avg_tokens": round(total_tokens / result_count, 2) if result_count else 0.0,
                "total_cost": total_cost,
            })
        return {
            "total_results": total_results,
            "total_cost": round(sum(float(item.get("total_cost") or 0.0) for item in traces), 4),
            "pass_rate": round(pass_count / total_results, 4) if total_results else 0.0,
            "hallucination_rate": report["hallucination_rate"],
            "pass_rate_trend": cls._build_trace_verdict_trend(traces),
            "hallucination_trend": report["hallucination_trend"],
            "model_metrics": model_metrics,
        }

    @staticmethod
    def _trace_bucket(item: dict) -> str | None:
        raw = item.get("created_at")
        if isinstance(raw, datetime):
            return raw.strftime("%Y-%m-%d")
        if isinstance(raw, str) and raw:
            return raw[:10]
        return None

    @classmethod
    def _build_trace_average_trend(cls, traces: list[dict], attr: str):
        buckets: dict[str, list[float]] = defaultdict(list)
        for item in traces:
            bucket = cls._trace_bucket(item)
            value = item.get(attr)
            if not bucket or value is None:
                continue
            buckets[bucket].append(float(value))
        return [
            {"bucket": bucket, "value": round(sum(values) / len(values), 4)}
            for bucket, values in sorted(buckets.items())
        ]

    @classmethod
    def _build_trace_value_trend(cls, traces: list[dict], attr: str, *, threshold: float):
        buckets: dict[str, list[float]] = defaultdict(list)
        for item in traces:
            bucket = cls._trace_bucket(item)
            value = item.get(attr)
            if not bucket or value is None:
                continue
            buckets[bucket].append(float(value))
        return [
            {"bucket": bucket, "value": round(sum(1 for value in values if value >= threshold) / len(values), 4)}
            for bucket, values in sorted(buckets.items())
        ]

    @classmethod
    def _build_trace_count_trend(cls, traces: list[dict], attr: str):
        buckets: dict[str, list[int]] = defaultdict(list)
        for item in traces:
            bucket = cls._trace_bucket(item)
            if not bucket:
                continue
            buckets[bucket].append(int(item.get(attr) or 0))
        return [
            {"bucket": bucket, "value": float(sum(values))}
            for bucket, values in sorted(buckets.items())
        ]

    @classmethod
    def _build_trace_verdict_trend(cls, traces: list[dict]):
        buckets: dict[str, list[bool]] = defaultdict(list)
        for item in traces:
            bucket = cls._trace_bucket(item)
            if not bucket or item.get("verdict") is None:
                continue
            buckets[bucket].append(item.get("verdict") == "pass")
        return [
            {"bucket": bucket, "value": round(sum(1 for value in values if value) / len(values), 4)}
            for bucket, values in sorted(buckets.items())
        ]

    @staticmethod
    def _build_quality_traces(
        results,
        feedbacks,
        ledger_items,
        limit: int = 100,
        chat_scores=None,
        chat_messages=None,
        langfuse_trace_exists=None,
        build_trace_url=None,
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

            trace_url = None
            if callable(build_trace_url):
                trace_url = build_trace_url(trace_id)
            if not trace_url:
                trace_url = trace_meta.get("trace_url")

            traces.append(
                {
                    "source_type": "inspection",
                    "trace_id": trace_id,
                    "trace_url": trace_url,
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
            trace_url = None
            if callable(build_trace_url):
                trace_url = build_trace_url(trace_id)
            if not trace_url:
                trace_url = score.trace_url
            traces.append(
                {
                    "source_type": "chat",
                    "trace_id": trace_id,
                    "trace_url": trace_url,
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

    async def delete_trace(self, trace_id: str) -> dict:
        api_client = LangfuseApiClient()
        detail: dict = {
            "trace_id": trace_id,
            "deleted": False,
            "status": "pending",
            "message": "",
            "langfuse_deleted": False,
            "local_cleaned": False,
        }

        if api_client.enabled:
            try:
                await api_client.delete_trace(trace_id)
                detail["langfuse_deleted"] = True
            except LangfuseApiError as exc:
                logger.warning("Failed to delete trace %s from Langfuse: %s", trace_id, exc)
                detail["status"] = "langfuse_failed"
                detail["message"] = str(exc)
                return detail
        else:
            detail["status"] = "langfuse_disabled"
            detail["message"] = "Langfuse is disabled; only local data can be cleaned."

        ledger_entries = await self._token_ledger_repo.find_by_trace_id(trace_id)
        result_ids = list({e.result_id for e in ledger_entries if e.result_id})
        for result_id in result_ids:
            await self._result_repo.soft_delete(result_id)
        detail["local_results_removed"] = len(result_ids)

        chat_scores = await self._chat_score_repo.find_by_trace_id(trace_id)
        for score in chat_scores:
            await self._chat_score_repo.soft_delete(score.id)
        detail["local_scores_removed"] = len(chat_scores)

        detail["local_cleaned"] = True
        detail["deleted"] = bool(detail["langfuse_deleted"] or result_ids or chat_scores)
        detail["status"] = "deleted" if detail["deleted"] else "not_found"
        detail["message"] = "Trace deleted" if detail["deleted"] else "Trace not found in Langfuse or local records"
        return detail
