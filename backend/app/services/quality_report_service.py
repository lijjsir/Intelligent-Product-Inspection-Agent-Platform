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
import json

import logging

from agent.llm.langfuse_tracer import LangfuseTracer
from agent.llm.pricing import ModelPricing
from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.repositories.feedback_repo import FeedbackRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.repositories.chat_score_repo import ChatMessageScoreRepository
from app.repositories.chat_repo import ChatMessageRepository
from app.services.base import TenantAwareService
from app.services.chat_trust_scoring_service import combine_trust_scores, score_output_rule
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
    def _extract_trust_risk(reasoning_chain) -> float | None:
        if not isinstance(reasoning_chain, dict):
            return None
        trust = reasoning_chain.get("trust_scoring")
        if not isinstance(trust, dict):
            return None
        risk = trust.get("hallucination_risk")
        if risk is None:
            return None
        try:
            return float(risk)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _has_citations(citations, reasoning_chain=None) -> bool:
        trust_risk = QualityReportService._extract_trust_risk(reasoning_chain)
        if trust_risk is not None:
            return trust_risk < 0.6
        if not citations:
            return False
        if isinstance(citations, dict):
            items = citations.get("items")
            return bool(items)
        if isinstance(citations, list):
            return bool(citations)
        return True

    @staticmethod
    def _is_chat_origin_result_feedback(item) -> bool:
        category = str(getattr(item, "category", "") or "").strip().lower()
        comment = str(getattr(item, "comment", "") or "").strip().lower()
        source_type = str(getattr(item, "source_type", "") or "").strip().lower()
        if category in {"chat_helpful", "chat_not_helpful"}:
            return True
        if comment.startswith("from_chat_message:"):
            return True
        return source_type == "chat"

    @classmethod
    def _normalize_result_feedbacks_for_quality(cls, feedbacks) -> list:
        return [
            item
            for item in list(feedbacks or [])
            if not cls._is_chat_origin_result_feedback(item)
        ]

    @staticmethod
    def _safe_float(value) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _first_float(cls, *values, default: float = 0.5) -> float:
        for value in values:
            parsed = cls._safe_float(value)
            if parsed is not None:
                return parsed
        return default

    @staticmethod
    def _safe_bool(value) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
        return bool(value)

    @classmethod
    def _chat_score_values_from_payload(cls, payload: dict | None) -> dict:
        payload = dict(payload or {})
        return {
            "trust_score": cls._safe_float(payload.get("trust_score")),
            "hallucination_risk": cls._safe_float(payload.get("hallucination_risk")),
            "overconfidence": cls._safe_float(payload.get("overconfidence")),
            "has_citation": cls._safe_bool(payload.get("has_citation")),
        }

    @classmethod
    def _chat_score_values_from_row(cls, score) -> dict:
        values = cls._chat_score_values_from_payload(
            {
                "trust_score": getattr(score, "trust_score", None),
                "hallucination_risk": getattr(score, "hallucination_risk", None),
                "overconfidence": getattr(score, "overconfidence", None),
                "has_citation": getattr(score, "has_citation", None),
            }
        )
        if values["trust_score"] is not None:
            return values

        combined = getattr(score, "combined_scores", None)
        if isinstance(combined, dict):
            values = cls._chat_score_values_from_payload(combined)
            if values["trust_score"] is not None:
                return values

        rule_score = getattr(score, "rule_scores", None)
        llm_score = getattr(score, "llm_scores", None)
        if not isinstance(rule_score, dict):
            return values
        if not isinstance(llm_score, dict):
            llm_score = {}
        llm_score = {
            "hallucination_risk_llm": cls._first_float(
                llm_score.get("hallucination_risk_llm"),
                rule_score.get("hallucination_risk"),
            ),
            "overconfidence_llm": cls._first_float(
                llm_score.get("overconfidence_llm"),
                rule_score.get("overconfidence"),
            ),
            "has_citation_llm": 1 if cls._safe_bool(llm_score.get("has_citation_llm", rule_score.get("has_citation"))) else 0,
        }
        try:
            combined = combine_trust_scores(rule_score=rule_score, llm_score=llm_score)
        except Exception:
            return values
        return cls._chat_score_values_from_payload(combined)

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
    def _build_feedback_trend(feedbacks, feedback_type: str = "down"):
        totals: dict[str, dict[str, int]] = defaultdict(lambda: {"all": 0, "target": 0})
        for item in feedbacks:
            bucket = item.created_at.strftime("%Y-%m-%d")
            totals[bucket]["all"] += 1
            if item.feedback_type == feedback_type:
                totals[bucket]["target"] += 1
        return [
            {"bucket": bucket, "value": round(values["target"] / values["all"], 4) if values["all"] else 0.0}
            for bucket, values in sorted(totals.items())
        ]

    async def list_traces(self, limit: int = 100, source: str = "all", include_remote: bool = True) -> list[dict]:
        result = await self.list_traces_with_meta(limit=limit, source=source, include_remote=include_remote)
        return result["items"]

    async def list_traces_with_meta(self, limit: int = 100, source: str = "all", include_remote: bool = True) -> dict:
        api_client = LangfuseApiClient()
        meta: dict = {
            "langfuse_enabled": api_client.enabled,
            "langfuse_status": "disabled" if not api_client.enabled else "unknown",
            "langfuse_error": None,
            "source": source,
            "canonical_source": "local",
        }
        if api_client.enabled and include_remote:
            meta["canonical_source"] = "langfuse"
            traces, error = await self._fetch_traces_from_langfuse(source=source, limit=limit, api_client=api_client)
            local_traces = await self._list_traces_from_mysql(
                limit=limit,
                source=source,
                api_client=api_client,
                langfuse_available=False,
            )
            if error:
                meta["langfuse_status"] = "error"
                meta["langfuse_error"] = str(error)
                meta["canonical_source"] = "local_fallback"
                meta["item_count"] = len(local_traces)
                return {"items": local_traces, "meta": meta}

            meta["langfuse_status"] = "ok"
            merged_traces = self._merge_trace_items(traces, local_traces)
            meta["canonical_source"] = "hybrid" if local_traces else "langfuse"
            meta["item_count"] = len(merged_traces)
            return {"items": merged_traces, "meta": meta}

        if api_client.enabled:
            traces = await self._list_traces_from_mysql(
                limit=limit,
                source=source,
                api_client=api_client,
                langfuse_available=False,
            )
            meta["langfuse_status"] = "ok"
            meta["canonical_source"] = "local_fast"
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
        limit: int | None,
        source: str,
        api_client: LangfuseApiClient,
        langfuse_available: bool,
        start_date=None,
        end_date=None,
    ) -> list[dict]:
        results = await self._result_repo.list_by_range(self._org_id, start_date, end_date)
        feedbacks = await self._feedback_repo.list_by_range(self._org_id, start_date, end_date)
        message_feedbacks = await self._feedback_repo.list_message_by_range(
            self._org_id,
            start_date,
            end_date,
            target_type="chat",
        )
        ledger_items = await self._token_ledger_repo.list_filtered(self._org_id)
        chat_scores = await self._chat_score_repo.list_by_range(self._org_id, start_date, end_date, limit=limit)
        chat_messages = await self._chat_message_repo.list_assistant_for_org(
            self._org_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        if source == "inspection":
            chat_scores, chat_messages, message_feedbacks = [], [], []
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
            chat_scores=chat_scores, chat_messages=chat_messages, message_feedbacks=message_feedbacks,
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

    @classmethod
    def _first_optional_float(cls, *values) -> float | None:
        for value in values:
            parsed = cls._safe_float(value)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _safe_int(value) -> int:
        if value is None:
            return 0
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _langfuse_usage_tokens(cls, observation: dict) -> dict[str, int]:
        usage = observation.get("usage") if isinstance(observation.get("usage"), dict) else {}
        usage_details = observation.get("usageDetails") if isinstance(observation.get("usageDetails"), dict) else {}

        prompt_tokens = max(
            cls._safe_int(usage.get("prompt_tokens")),
            cls._safe_int(usage.get("promptTokens")),
            cls._safe_int(usage.get("input_tokens")),
            cls._safe_int(usage.get("input")),
            cls._safe_int(usage_details.get("prompt_tokens")),
            cls._safe_int(usage_details.get("promptTokens")),
            cls._safe_int(usage_details.get("input_tokens")),
            cls._safe_int(usage_details.get("input")),
        )
        completion_tokens = max(
            cls._safe_int(usage.get("completion_tokens")),
            cls._safe_int(usage.get("completionTokens")),
            cls._safe_int(usage.get("output_tokens")),
            cls._safe_int(usage.get("output")),
            cls._safe_int(usage_details.get("completion_tokens")),
            cls._safe_int(usage_details.get("completionTokens")),
            cls._safe_int(usage_details.get("output_tokens")),
            cls._safe_int(usage_details.get("output")),
        )
        total_tokens = max(
            cls._safe_int(usage.get("total")),
            cls._safe_int(usage.get("total_tokens")),
            cls._safe_int(usage.get("totalTokens")),
            cls._safe_int(usage_details.get("total")),
            cls._safe_int(usage_details.get("total_tokens")),
            cls._safe_int(usage_details.get("totalTokens")),
            prompt_tokens + completion_tokens,
        )
        if total_tokens > 0 and prompt_tokens + completion_tokens <= 0:
            prompt_tokens = total_tokens
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    @classmethod
    def _langfuse_observation_cost(cls, observation: dict, *, model_key: str, usage: dict[str, int]) -> float:
        cost_details = observation.get("costDetails") if isinstance(observation.get("costDetails"), dict) else {}
        direct_cost = cls._first_optional_float(
            observation.get("totalCost"),
            observation.get("calculatedTotalCost"),
            observation.get("cost"),
            cost_details.get("total"),
            cost_details.get("totalCost"),
            cost_details.get("total_cost"),
        )
        if direct_cost is not None and direct_cost > 0:
            return float(direct_cost)

        split_cost = sum(
            float(value or 0.0)
            for value in (
                cls._safe_float(cost_details.get("input")),
                cls._safe_float(cost_details.get("output")),
                cls._safe_float(cost_details.get("prompt")),
                cls._safe_float(cost_details.get("completion")),
            )
            if value is not None
        )
        if split_cost > 0:
            return round(split_cost, 6)

        return ModelPricing.estimate_cost(
            model_key,
            usage["prompt_tokens"],
            usage["completion_tokens"],
        )

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
        thumbs_up_count = 0
        last_score_value = None
        last_score_at = None
        latest_feedback_by_actor: dict[str, dict] = {}

        for s in score_dicts:
            name = s.get("name", "")
            value = float(s.get("value", 0))
            comment = s.get("comment")
            if name == "trust_score":
                trust_score = value
                if isinstance(comment, str):
                    try:
                        comment_payload = json.loads(comment)
                    except json.JSONDecodeError:
                        comment_payload = None
                    if isinstance(comment_payload, dict):
                        review_model = str(comment_payload.get("review_model") or "").strip() or review_model
            elif name == "hallucination_risk":
                hallucination_risk = value
            elif name == "overconfidence":
                overconfidence = value
            elif name == "has_citation":
                has_citation = bool(value)
            elif name == "user_feedback":
                score_meta = s.get("metadata") or {}
                actor_key = str(
                    score_meta.get("actor_id")
                    or s.get("userId")
                    or s.get("id")
                    or f"feedback:{len(latest_feedback_by_actor)}"
                )
                current_ts = str(s.get("timestamp") or s.get("createdAt") or "")
                previous = latest_feedback_by_actor.get(actor_key)
                previous_ts = str((previous or {}).get("timestamp") or (previous or {}).get("createdAt") or "")
                if previous is None or current_ts >= previous_ts:
                    latest_feedback_by_actor[actor_key] = s

        for s in latest_feedback_by_actor.values():
            value = float(s.get("value", 0))
            feedback_count += 1
            if value < 0.5:
                thumbs_down_count += 1
            else:
                thumbs_up_count += 1
            scored_at = s.get("timestamp") or s.get("createdAt")
            if last_score_at is None or str(scored_at or "") >= str(last_score_at or ""):
                last_score_value = value
                last_score_at = scored_at

        generation_observations = [o for o in observation_dicts if o.get("type") == "GENERATION"]
        model_key = ""
        for o in generation_observations:
            if o.get("model"):
                model_key = str(o["model"])
                break
        if not model_key:
            model_key = str(metadata.get("model_key", "") or "")
        if not model_key and observation_dicts:
            for o in observation_dicts:
                if o.get("model"):
                    model_key = str(o["model"])
                    break

        usage_items = [QualityReportService._langfuse_usage_tokens(o) for o in generation_observations]
        total_tokens = sum(item["total_tokens"] for item in usage_items)
        trace_cost = QualityReportService._first_optional_float(
            trace.get("totalCost"),
            trace.get("total_cost"),
            trace.get("totalCostUsd"),
        )
        total_cost = float(trace_cost or 0.0)
        if total_cost <= 0:
            total_cost = round(
                sum(
                    QualityReportService._langfuse_observation_cost(
                        observation,
                        model_key=str(observation.get("model") or model_key or ""),
                        usage=usage,
                    )
                    for observation, usage in zip(generation_observations, usage_items)
                ),
                6,
            )

        trace_url = None
        if api_client and api_client.enabled:
            trace_url = api_client.build_trace_url(tid)

        return {
            "source_type": metadata.get("source_type", "inspection"),
            "trace_id": tid,
            "trace_url": trace_url,
            "result_id": metadata.get("result_id") or metadata.get("task_id"),
            "task_id": metadata.get("task_id"),
            "assistant_message_id": None,
            "session_id": trace.get("sessionId"),
            "observation_id": observation_ids[0] if observation_ids else None,
            "verdict": metadata.get("verdict"),
            "model_key": model_key,
            "total_tokens": total_tokens,
            "feedback_count": feedback_count,
            "thumbs_down_count": thumbs_down_count,
            "thumbs_up_count": thumbs_up_count,
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
            "total_cost": total_cost,
        }

    async def build_report(self, start_date=None, end_date=None, source: str = "all", include_remote: bool = False):
        api_client = LangfuseApiClient()
        stabilities = await self._stability_repo.list_by_range(self._org_id, start_date, end_date)
        result_feedbacks = await self._feedback_repo.list_by_range(self._org_id, start_date, end_date)
        message_feedbacks = await self._feedback_repo.list_message_by_range(
            self._org_id,
            start_date,
            end_date,
            target_type="chat",
        )
        if source == "inspection":
            message_feedbacks = []
        elif source == "chat":
            stabilities = []
            result_feedbacks = []
        result_feedbacks = self._normalize_result_feedbacks_for_quality(result_feedbacks)

        local_traces = await self._list_traces_from_mysql(
            limit=None,
            source=source,
            api_client=api_client,
            langfuse_available=False,
            start_date=start_date,
            end_date=end_date,
        )
        local_chat_message_count = len(
            {
                str(item.get("assistant_message_id") or "")
                for item in local_traces
                if item.get("source_type") == "chat" and item.get("assistant_message_id")
            }
        )
        if include_remote and api_client.enabled:
            traces, error = await self._fetch_traces_from_langfuse(
                source=source,
                limit=1000,
                api_client=api_client,
                start_date=start_date,
                end_date=end_date,
            )
            if not error:
                merged_traces = self._merge_trace_items(traces, local_traces)
                report = self._build_report_from_trace_items(merged_traces)
                report["avg_risk_score"] = round(
                    sum(float(item.risk_score or 0.0) for item in stabilities) / len(stabilities),
                    4,
                ) if stabilities else 0.0
                report.update(
                    self._build_feedback_summary(
                        result_feedbacks,
                        message_feedbacks,
                        fallback_up_count=int(report.get("thumbs_up_count") or 0),
                        fallback_down_count=int(report.get("thumbs_down_count") or 0),
                    )
                )
                report.update(self._build_feedback_rate_summary(
                    total_results=int(report.get("total_results") or 0),
                    thumbs_up_count=int(report.get("thumbs_up_count") or 0),
                    thumbs_down_count=int(report.get("thumbs_down_count") or 0),
                ))
                report.update(
                    self._build_chat_coverage_summary(
                        chat_score_count=int(report.get("chat_score_count") or 0),
                        chat_message_count=max(local_chat_message_count, int(report.get("chat_message_count") or 0)),
                    )
                )
                report["feedback_distribution"] = self._build_feedback_distribution(
                    result_feedbacks,
                    message_feedbacks,
                )
                return report
            logger.warning("Langfuse report source unavailable, falling back to local report: %s", error)

        report = self._build_report_from_trace_items(local_traces)
        report["avg_risk_score"] = round(
            sum(float(item.risk_score or 0.0) for item in stabilities) / len(stabilities),
            4,
        ) if stabilities else 0.0
        report.update(
            self._build_feedback_summary(
                result_feedbacks,
                message_feedbacks,
                fallback_up_count=int(report.get("thumbs_up_count") or 0),
                fallback_down_count=int(report.get("thumbs_down_count") or 0),
            )
        )
        report.update(self._build_feedback_rate_summary(
            total_results=int(report.get("total_results") or 0),
            thumbs_up_count=int(report.get("thumbs_up_count") or 0),
            thumbs_down_count=int(report.get("thumbs_down_count") or 0),
        ))
        report.update(
            self._build_chat_coverage_summary(
                chat_score_count=int(report.get("chat_score_count") or 0),
                chat_message_count=max(local_chat_message_count, int(report.get("chat_message_count") or 0)),
            )
        )
        report["feedback_distribution"] = self._build_feedback_distribution(
            result_feedbacks,
            message_feedbacks,
        )
        return report

    @staticmethod
    def _empty_report() -> dict:
        return {
            "total_results": 0,
            "hallucination_rate": 0.0,
            "thumbs_down_rate": 0.0,
            "thumbs_up_rate": 0.0,
            "thumbs_down_count": 0,
            "thumbs_up_count": 0,
            "feedback_total_count": 0,
            "thumbs_down_share": 0.0,
            "thumbs_up_share": 0.0,
            "avg_risk_score": 0.0,
            "feedback_distribution": {},
            "hallucination_trend": [],
            "thumbs_down_trend": [],
            "thumbs_up_trend": [],
            "model_metrics": [],
            "chat_message_count": 0,
            "chat_score_count": 0,
            "chat_unscored_count": 0,
            "chat_scored_rate": 0.0,
            "chat_avg_trust_score": 0.0,
            "chat_avg_hallucination_risk": 0.0,
            "chat_avg_overconfidence": 0.0,
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
        thumbs_up_count = sum(int(item.get("thumbs_up_count") or 0) for item in traces)
        chat_traces = [item for item in traces if item.get("source_type") == "chat"]
        chat_message_count = max(
            len(
                {
                    str(item.get("assistant_message_id") or "")
                    for item in chat_traces
                    if item.get("assistant_message_id")
                }
            ),
            len(chat_traces),
        )
        chat_hallucination_values = [
            float(item["hallucination_risk"])
            for item in chat_traces
            if item.get("hallucination_risk") is not None
        ]
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
                "thumbs_up_rate": round(
                    sum(int(item.get("thumbs_up_count") or 0) for item in items) / result_count,
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
            "thumbs_up_rate": round(thumbs_up_count / total_results, 4) if total_results else 0.0,
            "thumbs_down_count": thumbs_down_count,
            "thumbs_up_count": thumbs_up_count,
            "feedback_total_count": thumbs_down_count + thumbs_up_count,
            "thumbs_down_share": round(
                thumbs_down_count / (thumbs_down_count + thumbs_up_count),
                4,
            ) if (thumbs_down_count + thumbs_up_count) else 0.0,
            "thumbs_up_share": round(
                thumbs_up_count / (thumbs_down_count + thumbs_up_count),
                4,
            ) if (thumbs_down_count + thumbs_up_count) else 0.0,
            "avg_risk_score": 0.0,
            "feedback_distribution": {},
            "hallucination_trend": cls._build_trace_value_trend(traces, "hallucination_risk", threshold=0.6),
            "thumbs_down_trend": cls._build_trace_feedback_rate_trend(traces, "thumbs_down_count"),
            "thumbs_up_trend": cls._build_trace_feedback_rate_trend(traces, "thumbs_up_count"),
            "model_metrics": model_metrics,
            "chat_message_count": chat_message_count,
            "chat_score_count": len(trust_values),
            "chat_unscored_count": max(chat_message_count - len(trust_values), 0),
            "chat_scored_rate": round(len(trust_values) / chat_message_count, 4) if chat_message_count else 0.0,
            "chat_avg_trust_score": round(sum(trust_values) / len(trust_values), 4) if trust_values else 0.0,
            "chat_avg_hallucination_risk": round(sum(chat_hallucination_values) / len(chat_hallucination_values), 4)
            if chat_hallucination_values else 0.0,
            "chat_avg_overconfidence": round(sum(overconfidence_values) / len(overconfidence_values), 4)
            if overconfidence_values else 0.0,
            "chat_hallucination_rate": round(
                sum(1 for value in chat_hallucination_values if value >= 0.6) / len(chat_hallucination_values),
                4,
            ) if chat_hallucination_values else 0.0,
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
                "call_count": metric.get("call_count", metric["result_count"]),
                "pass_rate": metric["pass_rate"],
                "hallucination_rate": metric["hallucination_rate"],
                "avg_tokens": round(total_tokens / result_count, 2) if result_count else 0.0,
                "total_tokens": total_tokens,
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
    def _trace_sort_key(cls, item: dict) -> str:
        raw = item.get("created_at")
        if isinstance(raw, datetime):
            return raw.isoformat()
        return str(raw or "")

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
    def _build_trace_feedback_rate_trend(cls, traces: list[dict], attr: str):
        buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"all": 0, "feedback": 0})
        for item in traces:
            bucket = cls._trace_bucket(item)
            if not bucket:
                continue
            buckets[bucket]["all"] += 1
            buckets[bucket]["feedback"] += int(item.get(attr) or 0)
        return [
            {
                "bucket": bucket,
                "value": round(values["feedback"] / values["all"], 4) if values["all"] else 0.0,
            }
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
        limit: int | None = 100,
        chat_scores=None,
        chat_messages=None,
        message_feedbacks=None,
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
        for item in QualityReportService._normalize_result_feedbacks_for_quality(feedbacks):
            feedbacks_by_result[item.result_id].append(item)

        feedbacks_by_message: dict[str, list] = defaultdict(list)
        for item in list(message_feedbacks or []):
            feedbacks_by_message[str(item.target_id)].append(item)

        chat_messages_by_id = {
            str(getattr(item, "id", "") or ""): item
            for item in list(chat_messages or [])
            if getattr(item, "id", None)
        }

        traces: list[dict] = []
        for result in sorted(results, key=lambda item: item.created_at, reverse=True):
            reasoning_chain = result.reasoning_chain or {}
            trace_meta = reasoning_chain.get("trace") if isinstance(reasoning_chain, dict) else {}
            score_events = reasoning_chain.get("langfuse_scores") if isinstance(reasoning_chain, dict) else []
            trust_scoring = reasoning_chain.get("trust_scoring") if isinstance(reasoning_chain, dict) else {}
            if not isinstance(trace_meta, dict):
                trace_meta = {}
            if not isinstance(score_events, list):
                score_events = []
            if not isinstance(trust_scoring, dict):
                trust_scoring = {}

            ledger_group = ledger_by_result.get(result.id, [])
            feedback_group = feedbacks_by_result.get(result.id, [])

            latest_score = None
            score_candidates = [item for item in score_events if isinstance(item, dict)]
            if score_candidates:
                latest_score = max(score_candidates, key=lambda item: item.get("scored_at") or "")

            hallucination_risk = QualityReportService._extract_trust_risk(reasoning_chain)
            if hallucination_risk is None:
                hallucination_risk = 0.0 if QualityReportService._has_citations(getattr(result, "citations", None), reasoning_chain) else 1.0
            overconfidence = trust_scoring.get("overconfidence")
            if overconfidence is not None:
                try:
                    overconfidence = float(overconfidence)
                except (TypeError, ValueError):
                    overconfidence = None
            has_citation = QualityReportService._has_citations(getattr(result, "citations", None), reasoning_chain)

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
            thumbs_up_count = sum(1 for item in feedback_group if item.feedback_type == "up")

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
                    "thumbs_up_count": thumbs_up_count,
                    "last_score_value": None if not latest_score else float(latest_score.get("value") or 0.0),
                    "last_score_at": None if not latest_score else latest_score.get("scored_at"),
                    "trust_score": None if not latest_score else float(latest_score.get("value") or 0.0),
                    "hallucination_risk": hallucination_risk,
                    "overconfidence": overconfidence,
                    "has_citation": has_citation,
                    "score_status": None,
                    "review_model": None,
                    "langfuse_status": "local_only",
                    "langfuse_synced": None,
                    "created_at": result.created_at,
                }
            )

        for score in list(chat_scores or []):
            assistant_message_id = str(getattr(score, "assistant_message_id", "") or "")
            linked_message = chat_messages_by_id.get(assistant_message_id)
            linked_payload = dict(getattr(linked_message, "payload", {}) or {})
            linked_llm_meta = dict(linked_payload.get("llm_meta") or {})
            trace_id = str(
                getattr(score, "trace_id", "")
                or linked_llm_meta.get("langfuse", {}).get("trace_id")
                or assistant_message_id
            )
            ledger_group = ledger_by_trace.get(trace_id, [])
            feedback_group = feedbacks_by_message.get(assistant_message_id, [])
            total_tokens = sum(int(item.total_tokens or 0) for item in ledger_group)
            if total_tokens <= 0:
                total_tokens = int(linked_llm_meta.get("usage", {}).get("total_tokens") or 0)
            trace_url = None
            if callable(build_trace_url):
                trace_url = build_trace_url(trace_id)
            if not trace_url:
                trace_url = getattr(score, "trace_url", None)
            score_values = QualityReportService._chat_score_values_from_row(score)
            traces.append(
                {
                    "source_type": "chat",
                    "trace_id": trace_id,
                    "trace_url": trace_url,
                    "result_id": None,
                    "task_id": None,
                    "assistant_message_id": assistant_message_id,
                    "session_id": str(getattr(score, "session_id", "") or ""),
                    "observation_id": getattr(score, "observation_id", None),
                    "verdict": None,
                    "model_key": getattr(score, "model_key", None) or str(linked_llm_meta.get("model") or "chat_model"),
                    "total_tokens": total_tokens,
                    "feedback_count": len(feedback_group),
                    "thumbs_down_count": sum(1 for item in feedback_group if item.feedback_type == "down"),
                    "thumbs_up_count": sum(1 for item in feedback_group if item.feedback_type == "up"),
                    "last_score_value": score_values["trust_score"],
                    "last_score_at": getattr(score, "langfuse_synced_at", None) or getattr(score, "updated_at", None) or getattr(score, "created_at", None),
                    "trust_score": score_values["trust_score"],
                    "hallucination_risk": score_values["hallucination_risk"],
                    "overconfidence": score_values["overconfidence"],
                    "has_citation": score_values["has_citation"],
                    "score_status": getattr(score, "status", None),
                    "review_model": getattr(score, "review_model", None),
                    "langfuse_status": "local_only",
                    "langfuse_synced": getattr(score, "langfuse_synced_at", None) is not None,
                    "created_at": getattr(score, "created_at", None),
                }
            )

        scored_ids = {str(s.assistant_message_id) for s in (chat_scores or []) if s.assistant_message_id}
        for msg in list(chat_messages or []):
            if str(msg.id) in scored_ids:
                continue
            payload = msg.payload or {}
            llm_meta = payload.get("llm_meta") or {}
            trust_payload = dict(payload.get("trust_scoring") or {})
            score_values = QualityReportService._chat_score_values_from_payload(trust_payload)
            score_status = str(trust_payload.get("status") or "unscored")
            if score_values["trust_score"] is None and str(getattr(msg, "content", "") or "").strip():
                citations = [dict(item) for item in list(payload.get("citations") or []) if isinstance(item, dict)]
                rule_score = score_output_rule(
                    input_text="",
                    output_text=str(getattr(msg, "content", "") or ""),
                    citations=citations,
                )
                combined = combine_trust_scores(
                    rule_score=rule_score,
                    llm_score={
                        "hallucination_risk_llm": float(rule_score["hallucination_risk"]),
                        "overconfidence_llm": float(rule_score["overconfidence"]),
                        "has_citation_llm": int(rule_score["has_citation"]),
                    },
                )
                score_values = QualityReportService._chat_score_values_from_payload(combined)
                score_status = "rule_estimate" if score_status == "unscored" else score_status
            trace_id = str(llm_meta.get("langfuse", {}).get("trace_id") or msg.id)
            ledger_group = ledger_by_trace.get(trace_id, [])
            feedback_group = feedbacks_by_message.get(str(msg.id), [])
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
                    "feedback_count": len(feedback_group),
                    "thumbs_down_count": sum(1 for item in feedback_group if item.feedback_type == "down"),
                    "thumbs_up_count": sum(1 for item in feedback_group if item.feedback_type == "up"),
                    "last_score_value": score_values["trust_score"],
                    "last_score_at": None,
                    "trust_score": score_values["trust_score"],
                    "hallucination_risk": score_values["hallucination_risk"],
                    "overconfidence": score_values["overconfidence"],
                    "has_citation": score_values["has_citation"],
                    "score_status": score_status,
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
        return traces if limit is None else traces[:limit]

    @staticmethod
    def _build_feedback_distribution(result_feedbacks, message_feedbacks) -> dict[str, int]:
        counter = Counter()
        for item in list(result_feedbacks or []):
            counter[str(item.category or "uncategorized")] += 1
        for item in list(message_feedbacks or []):
            counter[str(item.category or "uncategorized")] += 1
        return dict(counter)

    @staticmethod
    def _build_feedback_summary(result_feedbacks, message_feedbacks, *, fallback_up_count: int, fallback_down_count: int) -> dict:
        local_feedbacks = list(result_feedbacks or []) + list(message_feedbacks or [])
        if local_feedbacks:
            thumbs_up_count = sum(1 for item in local_feedbacks if item.feedback_type == "up")
            thumbs_down_count = sum(1 for item in local_feedbacks if item.feedback_type == "down")
        else:
            thumbs_up_count = int(fallback_up_count or 0)
            thumbs_down_count = int(fallback_down_count or 0)
        feedback_total_count = thumbs_up_count + thumbs_down_count
        return {
            "thumbs_up_count": thumbs_up_count,
            "thumbs_down_count": thumbs_down_count,
            "feedback_total_count": feedback_total_count,
            "thumbs_up_share": round(thumbs_up_count / feedback_total_count, 4) if feedback_total_count else 0.0,
            "thumbs_down_share": round(thumbs_down_count / feedback_total_count, 4) if feedback_total_count else 0.0,
        }

    @staticmethod
    def _build_feedback_rate_summary(*, total_results: int, thumbs_up_count: int, thumbs_down_count: int) -> dict:
        total = int(total_results or 0)
        return {
            "thumbs_up_rate": round(int(thumbs_up_count or 0) / total, 4) if total else 0.0,
            "thumbs_down_rate": round(int(thumbs_down_count or 0) / total, 4) if total else 0.0,
        }

    @staticmethod
    def _build_chat_coverage_summary(*, chat_score_count: int, chat_message_count: int) -> dict:
        scored = int(chat_score_count or 0)
        total = int(chat_message_count or 0)
        return {
            "chat_message_count": total,
            "chat_score_count": scored,
            "chat_unscored_count": max(total - scored, 0),
            "chat_scored_rate": round(scored / total, 4) if total else 0.0,
        }

    @classmethod
    def _trace_identity_keys(cls, item: dict) -> list[str]:
        source_type = str(item.get("source_type") or "unknown")
        keys: list[str] = []
        if item.get("assistant_message_id"):
            keys.append(f"{source_type}:assistant:{item['assistant_message_id']}")
        if item.get("result_id"):
            keys.append(f"{source_type}:result:{item['result_id']}")
        if item.get("task_id"):
            keys.append(f"{source_type}:task:{item['task_id']}")
        if item.get("trace_id"):
            keys.append(f"{source_type}:trace:{item['trace_id']}")
        return keys

    @classmethod
    def _merge_trace_item(cls, remote: dict, local: dict) -> dict:
        merged = dict(local)
        merged["source_type"] = str(remote.get("source_type") or local.get("source_type") or "unknown")
        merged["trace_id"] = remote.get("trace_id") or local.get("trace_id")
        merged["trace_url"] = remote.get("trace_url") or local.get("trace_url")
        merged["task_id"] = remote.get("task_id") or local.get("task_id")
        merged["assistant_message_id"] = remote.get("assistant_message_id") or local.get("assistant_message_id")
        merged["session_id"] = remote.get("session_id") or local.get("session_id")
        merged["observation_id"] = remote.get("observation_id") or local.get("observation_id")
        merged["verdict"] = remote.get("verdict") or local.get("verdict")
        merged["model_key"] = remote.get("model_key") or local.get("model_key")
        merged["total_tokens"] = int(remote.get("total_tokens") or 0) or int(local.get("total_tokens") or 0)
        merged["total_cost"] = float(remote.get("total_cost") or 0.0) or float(local.get("total_cost") or 0.0)

        local_feedback_count = int(local.get("feedback_count") or 0)
        local_down_count = int(local.get("thumbs_down_count") or 0)
        local_up_count = int(local.get("thumbs_up_count") or 0)
        if local_feedback_count or local_down_count or local_up_count:
            merged["feedback_count"] = local_feedback_count
            merged["thumbs_down_count"] = local_down_count
            merged["thumbs_up_count"] = local_up_count
        else:
            merged["feedback_count"] = int(remote.get("feedback_count") or 0)
            merged["thumbs_down_count"] = int(remote.get("thumbs_down_count") or 0)
            merged["thumbs_up_count"] = int(remote.get("thumbs_up_count") or 0)

        merged["last_score_value"] = remote.get("last_score_value")
        if merged["last_score_value"] is None:
            merged["last_score_value"] = local.get("last_score_value")
        merged["last_score_at"] = remote.get("last_score_at") or local.get("last_score_at")
        merged["trust_score"] = remote.get("trust_score")
        if merged["trust_score"] is None:
            merged["trust_score"] = local.get("trust_score")
        merged["hallucination_risk"] = remote.get("hallucination_risk")
        if merged["hallucination_risk"] is None:
            merged["hallucination_risk"] = local.get("hallucination_risk")
        merged["overconfidence"] = remote.get("overconfidence")
        if merged["overconfidence"] is None:
            merged["overconfidence"] = local.get("overconfidence")
        merged["has_citation"] = remote.get("has_citation")
        if merged["has_citation"] is None:
            merged["has_citation"] = local.get("has_citation")
        merged["score_status"] = remote.get("score_status") or local.get("score_status")
        merged["review_model"] = remote.get("review_model") or local.get("review_model")
        merged["langfuse_status"] = remote.get("langfuse_status") or local.get("langfuse_status")
        merged["langfuse_synced"] = remote.get("langfuse_synced")
        if merged["langfuse_synced"] is None:
            merged["langfuse_synced"] = local.get("langfuse_synced")
        merged["created_at"] = remote.get("created_at") or local.get("created_at")

        remote_result_id = remote.get("result_id")
        local_result_id = local.get("result_id")
        if local_result_id and (not remote_result_id or remote_result_id == remote.get("task_id")):
            merged["result_id"] = local_result_id
        else:
            merged["result_id"] = remote_result_id or local_result_id
        return merged

    @classmethod
    def _keep_local_trace_for_hybrid(cls, item: dict) -> bool:
        if str(item.get("source_type") or "") != "chat":
            return True
        if int(item.get("feedback_count") or 0) > 0:
            return True
        if item.get("trust_score") is not None or item.get("hallucination_risk") is not None:
            return True
        if int(item.get("total_tokens") or 0) > 0:
            return True
        assistant_message_id = str(item.get("assistant_message_id") or "")
        trace_id = str(item.get("trace_id") or "")
        if trace_id and assistant_message_id and trace_id != assistant_message_id:
            return True
        if str(item.get("model_key") or "") not in {"", "chat_model"}:
            return True
        return False

    @classmethod
    def _merge_trace_items(cls, remote_traces: list[dict], local_traces: list[dict]) -> list[dict]:
        merged: list[dict] = []
        key_to_index: dict[str, int] = {}

        local_items = list(local_traces or [])
        if list(remote_traces or []):
            local_items = [item for item in local_items if cls._keep_local_trace_for_hybrid(item)]

        for item in local_items:
            idx = len(merged)
            merged.append(dict(item))
            for key in cls._trace_identity_keys(item):
                key_to_index[key] = idx

        for item in list(remote_traces or []):
            keys = cls._trace_identity_keys(item)
            match_idx = next((key_to_index[key] for key in keys if key in key_to_index), None)
            if match_idx is None:
                match_idx = len(merged)
                merged.append(dict(item))
            else:
                merged[match_idx] = cls._merge_trace_item(item, merged[match_idx])
            for key in cls._trace_identity_keys(merged[match_idx]):
                key_to_index[key] = match_idx

        merged.sort(key=cls._trace_sort_key, reverse=True)
        return merged

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
                trace["langfuse_status"] = "synced" if trace.get("langfuse_synced") else "unknown"
                if trace.get("langfuse_synced") is None:
                    trace["langfuse_synced"] = trace["langfuse_status"] == "synced"

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
