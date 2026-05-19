from __future__ import annotations

import json
import math
import re
import asyncio
from datetime import datetime
from typing import Any

import httpx

from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from agent.llm.langfuse_tracer import LangfuseTracer
from app.core.config import settings
from app.services.model_config_service import ModelConfigService

CERTAINTY_PATTERNS = [
    r"\b(always|never|definitely|absolutely|certainly|guaranteed|100%|undoubtedly)\b",
    r"100\s*%",
    r"(一定|必然|肯定|绝对|毫无疑问|完全正确|从不|总是|百分之百)",
]
HEDGE_PATTERNS = [
    r"\b(may|might|possibly|probably|likely|uncertain|depends|appears|seems)\b",
    r"(可能|也许|大概|或许|不确定|看起来|似乎|需要进一步确认|取决于)",
]
CITATION_PATTERNS = [
    r"https?://[^\s)）]+",
    r"\[\s*\d+\s*\]",
    r"【\s*\d+\s*】",
    r"(来源|引用|依据|标准|文档|source|reference)\s*[:：]",
]
DIGIT_RE = re.compile(r"\d")
SCORE_VERSION = "trust_v1"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _round3(value: float) -> float:
    return float(round(float(value), 3))


def _count_any(patterns: list[str], text: str) -> int:
    return sum(len(re.findall(pattern, text, flags=re.I)) for pattern in patterns)


def _has_citation(output_text: str, citations: list[dict[str, Any]] | None) -> int:
    if citations:
        return 1
    return 1 if any(re.search(pattern, output_text, flags=re.I) for pattern in CITATION_PATTERNS) else 0


def score_output_rule(
    *,
    input_text: str,
    output_text: str,
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    text = str(output_text or "").strip()
    if not text:
        return {
            "hallucination_risk": 1.0,
            "overconfidence": 1.0,
            "has_citation": 0,
            "debug": {"empty": True, "input_len": len(str(input_text or "")), "output_len": 0},
        }

    certainty_hits = _count_any(CERTAINTY_PATTERNS, text)
    hedge_hits = _count_any(HEDGE_PATTERNS, text)
    digits = len(re.findall(DIGIT_RE, text))
    length = max(1, len(text))
    numeric_density = digits / length
    has_citation = _has_citation(text, citations)

    certainty_score = 1.0 - math.exp(-certainty_hits / 3.0) if certainty_hits else 0.0
    hedge_score = 1.0 - math.exp(-hedge_hits / 3.0) if hedge_hits else 0.0
    overconfidence = _clamp01(0.12 + 0.8 * certainty_score - 0.3 * hedge_score)
    hallucination_risk = _clamp01(
        0.2
        + 0.45 * certainty_score
        + 0.25 * (0.0 if has_citation else 1.0)
        + 0.1 * _clamp01(numeric_density * 30.0)
    )
    hallucination_risk = _clamp01(hallucination_risk * (1.0 - 0.25 * hedge_score))
    overconfidence = _clamp01(overconfidence * (1.0 - 0.35 * hedge_score))

    return {
        "hallucination_risk": float(hallucination_risk),
        "overconfidence": float(overconfidence),
        "has_citation": int(has_citation),
        "debug": {
            "certainty_hits": certainty_hits,
            "hedge_hits": hedge_hits,
            "digits": digits,
            "length": length,
            "numeric_density": numeric_density,
            "has_citation": has_citation,
        },
    }


def extract_json_object(text: str) -> dict[str, Any]:
    candidates = [str(text or "").strip()]
    for block in re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", str(text or ""), flags=re.I):
        candidates.insert(0, block.strip())
    raw = re.search(r"\{[\s\S]*\}", str(text or ""))
    if raw:
        candidates.append(raw.group(0))

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("reviewer output did not contain a JSON object")


def normalize_llm_score(obj: dict[str, Any] | None) -> dict[str, Any]:
    obj = dict(obj or {})
    reasons = obj.get("reasons") or []
    if isinstance(reasons, str):
        reasons_list = [reasons]
    elif isinstance(reasons, list):
        reasons_list = [str(item) for item in reasons if str(item).strip()]
    else:
        reasons_list = []
    if not reasons_list:
        reasons_list = ["Reviewer returned no explicit reason."]
    cite_raw = obj.get("has_citation_llm", 0)
    citation = 1 if str(cite_raw).strip().lower() in {"1", "true", "yes", "y"} else 0
    return {
        "hallucination_risk_llm": _clamp01(float(obj.get("hallucination_risk_llm", 0.5))),
        "overconfidence_llm": _clamp01(float(obj.get("overconfidence_llm", 0.5))),
        "has_citation_llm": citation,
        "reasons": reasons_list[:3],
    }


def combine_trust_scores(*, rule_score: dict[str, Any], llm_score: dict[str, Any]) -> dict[str, Any]:
    hallucination = _round3(
        (float(rule_score["hallucination_risk"]) + float(llm_score["hallucination_risk_llm"])) / 2.0
    )
    overconfidence = _round3(
        (float(rule_score["overconfidence"]) + float(llm_score["overconfidence_llm"])) / 2.0
    )
    citation_confidence = _clamp01(
        (float(rule_score["has_citation"]) + float(llm_score["has_citation_llm"])) / 2.0
    )
    has_citation = 1 if citation_confidence >= 0.5 else 0
    risk = _clamp01((hallucination + overconfidence + (1.0 - citation_confidence)) / 3.0)
    trust_score = _round3(1.0 - risk)
    if trust_score >= 0.75:
        risk_level = "low"
    elif trust_score >= 0.5:
        risk_level = "medium"
    elif trust_score >= 0.25:
        risk_level = "high"
    else:
        risk_level = "critical"
    return {
        "trust_score": trust_score,
        "trust_pct": _round3(trust_score * 100.0),
        "risk_level": risk_level,
        "hallucination_risk": hallucination,
        "overconfidence": overconfidence,
        "has_citation": has_citation,
    }


def build_pending_trust_score(
    *,
    org_id: str,
    session_id: str,
    user_id: str | None,
    assistant_message_id: str,
    input_text: str,
    output_text: str,
    citations: list[dict[str, Any]] | None,
    trace_id: str | None,
    observation_id: str | None,
    model_key: str | None,
) -> dict[str, Any]:
    rule_score = score_output_rule(input_text=input_text, output_text=output_text, citations=citations)
    trace_url_getter = getattr(LangfuseTracer(), "get_trace_url", None)
    trace_url = trace_url_getter(trace_id) if trace_id and callable(trace_url_getter) else None
    return {
        "org_id": org_id,
        "session_id": session_id,
        "user_id": user_id,
        "assistant_message_id": assistant_message_id,
        "score_version": SCORE_VERSION,
        "trace_id": trace_id,
        "observation_id": observation_id,
        "trace_url": trace_url,
        "model_key": model_key,
        "review_model": None,
        "rule_scores": rule_score,
        "llm_scores": None,
        "combined_scores": None,
        "trust_score": None,
        "hallucination_risk": None,
        "overconfidence": None,
        "has_citation": None,
        "status": "reviewing",
        "langfuse_synced_at": None,
    }


class ChatTrustScoringService:
    def __init__(
        self,
        *,
        review_provider: str | None = None,
        review_model: str | None = None,
        review_base_url: str | None = None,
        review_api_key: str | None = None,
        input_price_per_million: float | None = None,
        output_price_per_million: float | None = None,
        review_disabled_reason: str | None = None,
    ) -> None:
        self._review_provider = review_provider
        self._review_model = review_model
        self._review_base_url = review_base_url
        self._review_api_key = review_api_key
        self._input_price_per_million = input_price_per_million
        self._output_price_per_million = output_price_per_million
        self._review_disabled_reason = review_disabled_reason

    @staticmethod
    async def resolve_review_model(db_session, org_id: str) -> dict[str, Any]:
        runtime_models = await ModelConfigService(db_session, org_id).list_runtime_models()
        runtime = await LLMGateway().select_runtime(
            runtime_models,
            model_types={"chat", "llm"},
            reserve=False,
        )
        if runtime:
            return {
                "review_provider": str(runtime.get("provider") or ""),
                "review_model": str(runtime.get("model_id") or ""),
                "review_base_url": str(runtime.get("base_url") or ""),
                "review_api_key": runtime.get("api_key"),
                "input_price_per_million": runtime.get("input_price_per_million"),
                "output_price_per_million": runtime.get("output_price_per_million"),
            }
        return {
            "review_provider": None,
            "review_model": None,
            "review_base_url": None,
            "review_api_key": None,
            "input_price_per_million": None,
            "output_price_per_million": None,
            "review_disabled_reason": "no active chat model configured in model config page",
        }

    async def score_answer(
        self,
        *,
        org_id: str,
        session_id: str,
        user_id: str | None,
        assistant_message_id: str,
        input_text: str,
        output_text: str,
        citations: list[dict[str, Any]] | None,
        trace_id: str | None,
        observation_id: str | None,
        model_key: str | None,
    ) -> dict[str, Any]:
        rule_score = score_output_rule(
            input_text=input_text,
            output_text=output_text,
            citations=citations,
        )
        status = "scored"
        try:
            llm_score = await asyncio.wait_for(
                self._call_reviewer(input_text=input_text, output_text=output_text),
                timeout=max(1, int(settings.trust_review_timeout_sec or 30)),
            )
        except Exception as exc:
            status = "rule_only"
            llm_score = {
                "hallucination_risk_llm": float(rule_score["hallucination_risk"]),
                "overconfidence_llm": float(rule_score["overconfidence"]),
                "has_citation_llm": int(rule_score["has_citation"]),
                "reasons": [str(exc)],
            }

        combined = combine_trust_scores(rule_score=rule_score, llm_score=llm_score)
        trace_url, synced_at = self._sync_langfuse_scores(
            trace_id=trace_id,
            observation_id=observation_id,
            model_key=model_key,
            review_model=self._review_model,
            rule_score=rule_score,
            llm_score=llm_score,
            combined=combined,
            status=status,
        )
        scored = status == "scored"
        return {
            "org_id": org_id,
            "session_id": session_id,
            "user_id": user_id,
            "assistant_message_id": assistant_message_id,
            "score_version": SCORE_VERSION,
            "trace_id": trace_id,
            "observation_id": observation_id,
            "trace_url": trace_url,
            "model_key": model_key,
            "review_model": self._review_model,
            "rule_scores": rule_score,
            "llm_scores": llm_score,
            "combined_scores": combined if scored else None,
            "trust_score": combined["trust_score"] if scored else None,
            "hallucination_risk": combined["hallucination_risk"] if scored else None,
            "overconfidence": combined["overconfidence"] if scored else None,
            "has_citation": bool(combined["has_citation"]) if scored else None,
            "status": status,
            "langfuse_synced_at": synced_at,
        }

    async def _call_reviewer(self, *, input_text: str, output_text: str) -> dict[str, Any]:
        if self._review_disabled_reason:
            raise RuntimeError(self._review_disabled_reason)
        if not self._review_provider or not self._review_model:
            raise RuntimeError("no active chat model configured in model config page")
        prompt = self._build_rubric_prompt(input_text=input_text, output_text=output_text)
        client = LLMClient(
            provider=self._review_provider,
            model_id=self._review_model,
            base_url=self._review_base_url,
            api_key=self._review_api_key,
            input_price_per_million=self._input_price_per_million,
            output_price_per_million=self._output_price_per_million,
        )
        try:
            response = await client.chat(
                [
                    {"role": "system", "content": "You are a strict evaluator. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                observation_name="chat.trust_review",
                observation_metadata={"pipeline": SCORE_VERSION},
            )
            if {"hallucination_risk_llm", "overconfidence_llm", "has_citation_llm"} <= set(response):
                return normalize_llm_score(response)
            if "text" in response:
                return normalize_llm_score(extract_json_object(str(response["text"])))
            return normalize_llm_score(response)
        except httpx.HTTPError:
            raise

    @staticmethod
    def _build_rubric_prompt(*, input_text: str, output_text: str) -> str:
        return (
            "Evaluate an assistant answer for quality risk. Return one JSON object only.\n"
            "Fields:\n"
            "- hallucination_risk_llm: number 0..1, higher means likely unsupported or fabricated.\n"
            "- overconfidence_llm: number 0..1, higher means overly certain without caveats.\n"
            "- has_citation_llm: 0 or 1, whether the answer includes clear source/citation evidence.\n"
            "- reasons: 1 to 3 short strings.\n\n"
            f"User question:\n{input_text}\n\nAssistant answer:\n{output_text}\n"
        )

    @staticmethod
    def _sync_langfuse_scores(
        *,
        trace_id: str | None,
        observation_id: str | None,
        model_key: str | None,
        review_model: str | None,
        rule_score: dict[str, Any],
        llm_score: dict[str, Any],
        combined: dict[str, Any],
        status: str,
    ) -> tuple[str | None, datetime | None]:
        tracer = LangfuseTracer()
        if not trace_id:
            return None, None
        trace_url_getter = getattr(tracer, "get_trace_url", None)
        trace_url = trace_url_getter(trace_id) if callable(trace_url_getter) else None
        if status != "scored":
            return trace_url, None
        comment = json.dumps(
            {
                "source": "piap-chat-trust-scoring",
                "score_version": SCORE_VERSION,
                "status": status,
                "answer_model": model_key,
                "review_model": review_model,
                "rule_debug": rule_score.get("debug", {}),
                "llm_reasons": llm_score.get("reasons", []),
                "combined": combined,
            },
            ensure_ascii=False,
            default=str,
        )
        score_defs = [
            ("hallucination_risk", combined["hallucination_risk"], "NUMERIC"),
            ("overconfidence", combined["overconfidence"], "NUMERIC"),
            ("has_citation", float(combined["has_citation"]), "BOOLEAN"),
            ("trust_score", combined["trust_score"], "NUMERIC"),
        ]
        synced = False
        for name, value, data_type in score_defs:
            payload = tracer.score(
                trace_id=trace_id,
                observation_id=observation_id,
                name=name,
                value=float(value),
                data_type=data_type,
                comment=comment,
                metadata={"score_version": SCORE_VERSION, "source": "chat"},
            )
            synced_payload = tracer.sync_score(payload)
            synced = bool(synced_payload.get("synced")) or synced
            trace_url = synced_payload.get("trace_url") or trace_url
        return trace_url, datetime.utcnow() if synced else None


def trust_payload_from_score(score: dict[str, Any] | None) -> dict[str, Any] | None:
    if not score:
        return None
    return {
        "status": score.get("status"),
        "trust_score": score.get("trust_score"),
        "risk_level": (score.get("combined_scores") or {}).get("risk_level"),
        "hallucination_risk": score.get("hallucination_risk"),
        "overconfidence": score.get("overconfidence"),
        "has_citation": score.get("has_citation"),
        "trace_url": score.get("trace_url"),
        "review_model": score.get("review_model"),
    }
