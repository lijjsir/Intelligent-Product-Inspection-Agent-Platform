from __future__ import annotations

import json
from typing import Any

from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from agent.subgraphs.lab_detection.contracts import (
    LabAnomalyFeature,
    LabEarlyRiskAssessment,
    LabPartialDataContext,
)
from agent.subgraphs.lab_detection.normalizers import (
    compute_data_completeness,
    normalize_lab_measurements,
)
from agent.subgraphs.lab_detection.parsers import (
    parse_lower_limit,
    parse_numeric_range,
    parse_upper_limit,
)
from agent.subgraphs.lab_detection.prompts import (
    LAB_EARLY_RISK_SYSTEM_PROMPT,
    build_lab_early_risk_user_prompt,
)
from agent.subgraphs.lab_detection.validators import enforce_lab_safety
from app.services.model_config_service import ModelConfigService
from infra.database.session import get_session


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _has_truthy_signal(payload: dict[str, Any], keywords: tuple[str, ...]) -> bool:
    for key, value in payload.items():
        key_text = str(key).lower()
        value_text = str(value).lower()
        if not any(keyword in key_text or keyword in value_text for keyword in keywords):
            continue
        if isinstance(value, bool):
            return value
        if value not in (None, "", 0, "0", "false", "False", "normal", "ok"):
            return True
    return False


def _manual_review_feature_present(features: list[dict[str, Any]]) -> bool:
    return any(
        feature.get("deviation_type")
        in {"instrument_suspected", "environment_suspected"}
        for feature in features
    )


def _assessment(
    *,
    state: str,
    completeness: float,
    risk_level: str = "low",
    abnormal_probability: float = 0.0,
    early_warning: bool = False,
    features: list[dict[str, Any]] | None = None,
    explanation: str,
    requires_manual_review: bool = False,
    confidence: float = 0.0,
    raw_llm_output: dict[str, Any] | None = None,
    deterministic_summary: dict[str, Any] | None = None,
    next_test_priority: list[dict[str, Any]] | None = None,
    suggested_action: str | None = None,
) -> dict[str, Any]:
    assessment = LabEarlyRiskAssessment(
        assessment_state=state,  # type: ignore[arg-type]
        abnormal_probability=abnormal_probability,
        risk_level=risk_level,  # type: ignore[arg-type]
        data_completeness=completeness,
        early_warning=early_warning,
        can_make_final_verdict=False,
        abnormal_indicators=list(features or []),
        suggested_action=suggested_action,
        next_test_priority=list(next_test_priority or []),
        explanation=explanation,
        requires_manual_review=requires_manual_review,
        confidence=confidence,
        raw_llm_output=dict(raw_llm_output or {}),
        deterministic_summary=dict(deterministic_summary or {}),
    )
    assessment.can_make_final_verdict = False
    return assessment.model_dump()


async def input_adapter(state: dict[str, Any]) -> dict[str, Any]:
    raw = dict(state.get("input_context") or {})
    try:
        context = LabPartialDataContext.model_validate(raw)
        state["normalized_context"] = context.model_dump()
        state["validation_errors"] = []
    except Exception as exc:
        state["validation_errors"] = [f"LabPartialDataContext parse failed: {exc}"]
        state["blocked_reason"] = "invalid_lab_context"
    return state


async def validate_lab_context(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("validation_errors"):
        return state

    context = LabPartialDataContext.model_validate(state["normalized_context"])
    errors: list[str] = []

    if not str(context.sample_id or "").strip():
        errors.append("missing sample_id")
    if not context.partial_measurements:
        errors.append("missing partial_measurements")
    if context.test_plan.total_items <= 0:
        errors.append("missing test_plan.total_items")
    if context.test_plan.completed_items < 0:
        errors.append("completed_items cannot be negative")
    if context.test_plan.completed_items > context.test_plan.total_items:
        errors.append("completed_items cannot exceed total_items")

    state["validation_errors"] = errors
    if errors:
        state["blocked_reason"] = "insufficient_data"
    return state


async def normalize_measurements(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("validation_errors"):
        return state

    context = LabPartialDataContext.model_validate(state["normalized_context"])
    normalized = normalize_lab_measurements(context.partial_measurements)

    payload = context.model_dump()
    payload["partial_measurements"] = [item.model_dump() for item in normalized]
    state["normalized_context"] = payload
    return state


async def load_reference_context(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("validation_errors"):
        return state

    context = LabPartialDataContext.model_validate(state["normalized_context"])
    limits: list[dict[str, Any]] = []

    for item in context.partial_measurements:
        if item.standard_limit:
            limits.append(
                {
                    "item": item.item,
                    "standard_limit": item.standard_limit,
                    "source": "input.partial_measurements.standard_limit",
                }
            )

    for item in context.standard_context:
        if isinstance(item, dict) and item.get("standard_limit"):
            limits.append({**item, "source": item.get("source") or "input.standard_context"})

    state["standard_limits"] = limits
    state["normal_profile"] = context.historical_baseline.model_dump()
    return state


async def compute_anomaly_features(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("validation_errors"):
        return state

    context = LabPartialDataContext.model_validate(state["normalized_context"])
    features: list[LabAnomalyFeature] = []
    instrument_keywords = ("instrument", "drift", "calibration", "suspect", "invalid", "error")

    for measurement in context.partial_measurements:
        try:
            numeric_value = float(measurement.value)  # type: ignore[arg-type]
        except Exception:
            numeric_value = None

        upper = parse_upper_limit(measurement.standard_limit)
        lower = parse_lower_limit(measurement.standard_limit)

        if numeric_value is not None and upper is not None and numeric_value > upper:
            features.append(
                LabAnomalyFeature(
                    item=measurement.item,
                    value=numeric_value,
                    unit=measurement.unit,
                    expected_range=measurement.normal_range,
                    standard_limit=measurement.standard_limit,
                    deviation_type="above_limit",
                    severity="high",
                    evidence=f"{measurement.item}={numeric_value}{measurement.unit or ''} exceeds {measurement.standard_limit}",
                    confidence=0.9,
                )
            )

        if numeric_value is not None and lower is not None and numeric_value < lower:
            features.append(
                LabAnomalyFeature(
                    item=measurement.item,
                    value=numeric_value,
                    unit=measurement.unit,
                    expected_range=measurement.normal_range,
                    standard_limit=measurement.standard_limit,
                    deviation_type="below_limit",
                    severity="high",
                    evidence=f"{measurement.item}={numeric_value}{measurement.unit or ''} is below {measurement.standard_limit}",
                    confidence=0.9,
                )
            )

        normal_range = parse_numeric_range(measurement.normal_range)
        if numeric_value is not None and normal_range is not None:
            low, high = normal_range
            if numeric_value < low or numeric_value > high:
                features.append(
                    LabAnomalyFeature(
                        item=measurement.item,
                        value=numeric_value,
                        unit=measurement.unit,
                        expected_range=measurement.normal_range,
                        standard_limit=measurement.standard_limit,
                        deviation_type="out_of_normal_range",
                        severity="medium",
                        evidence=f"{measurement.item}={numeric_value}{measurement.unit or ''} is outside normal range {measurement.normal_range}",
                        confidence=0.75,
                    )
                )

        quality_payload = {
            "quality_flag": measurement.quality_flag,
            "instrument_id": measurement.instrument_id,
        }
        baseline = context.historical_baseline.instrument_baseline
        if measurement.instrument_id and isinstance(baseline.get(measurement.instrument_id), dict):
            quality_payload.update(baseline[measurement.instrument_id])
        if _has_truthy_signal(quality_payload, instrument_keywords):
            features.append(
                LabAnomalyFeature(
                    item=measurement.item,
                    value=measurement.value,
                    unit=measurement.unit,
                    expected_range=measurement.normal_range,
                    standard_limit=measurement.standard_limit,
                    deviation_type="instrument_suspected",
                    severity="medium",
                    evidence=f"{measurement.item} has instrument or data-quality anomaly signals",
                    confidence=0.65,
                )
            )

    environment_keywords = (
        "alarm",
        "abnormal",
        "drift",
        "fluctuat",
        "temperature",
        "humidity",
        "contamination",
        "power",
    )
    if _has_truthy_signal(context.environment, environment_keywords):
        features.append(
            LabAnomalyFeature(
                item="environment",
                deviation_type="environment_suspected",
                severity="medium",
                evidence="Environment metadata contains anomaly signals",
                confidence=0.65,
            )
        )

    completeness = compute_data_completeness(context.test_plan)
    feature_payloads = [item.model_dump() for item in features]
    state["anomaly_features"] = feature_payloads
    state["deterministic_summary"] = {
        "data_completeness": completeness,
        "feature_count": len(features),
        "limit_violation_count": len(
            [
                item
                for item in features
                if item.deviation_type in {"above_limit", "below_limit"}
            ]
        ),
        "normal_range_deviation_count": len(
            [item for item in features if item.deviation_type == "out_of_normal_range"]
        ),
        "instrument_suspected_count": len(
            [item for item in features if item.deviation_type == "instrument_suspected"]
        ),
        "environment_suspected_count": len(
            [item for item in features if item.deviation_type == "environment_suspected"]
        ),
        "critical_indicator_triggered": any(
            str(item.severity) in {"high", "critical"} for item in features
        ),
    }

    if completeness < 0.2 and not features:
        state["blocked_reason"] = "insufficient_data"

    return state


async def llm_early_risk_reasoning(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("validation_errors"):
        return state

    if state.get("blocked_reason") == "insufficient_data":
        return state

    context = LabPartialDataContext.model_validate(state["normalized_context"])
    user_prompt = build_lab_early_risk_user_prompt(
        context=context,
        anomaly_features=list(state.get("anomaly_features") or []),
        deterministic_summary=dict(state.get("deterministic_summary") or {}),
        standard_limits=list(state.get("standard_limits") or []),
        normal_profile=dict(state.get("normal_profile") or {}),
    )

    state["llm_prompt"] = {
        "system": LAB_EARLY_RISK_SYSTEM_PROMPT,
        "user": user_prompt,
    }

    try:
        async with get_session() as session:
            runtime_models = await ModelConfigService(
                session, str(state.get("org_id") or "")
            ).list_runtime_models()

        runtime = await LLMGateway().select_runtime(runtime_models)
    except Exception as exc:
        state["blocked_reason"] = "model_unavailable"
        state["llm_error"] = f"runtime model lookup failed: {exc}"
        return state

    if not runtime:
        state["blocked_reason"] = "model_unavailable"
        state["llm_error"] = "no runtime model available"
        return state

    llm = LLMClient(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        model_id=runtime.get("model_id"),
        trace_id=str(state.get("workflow_run_id") or state.get("request_id") or ""),
        task_id=str(state.get("session_id") or ""),
        org_id=str(state.get("org_id") or ""),
        provider=str(runtime.get("provider") or ""),
        input_price_per_million=runtime.get("input_price_per_million"),
        output_price_per_million=runtime.get("output_price_per_million"),
    )

    try:
        response = await llm.chat(
            [
                {"role": "system", "content": LAB_EARLY_RISK_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            observation_name="lab_detection.early_risk_reasoning",
            observation_metadata={
                "agent": "lab_detection",
                "workflow_version": "lab_detection_v1",
                "source": "standalone_subgraph",
            },
        )
        state["llm_result"] = response
    except Exception as exc:
        state["blocked_reason"] = "llm_reasoning_failed"
        state["llm_error"] = str(exc)

    return state


async def recommend_next_tests(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("validation_errors"):
        return state

    context = LabPartialDataContext.model_validate(state["normalized_context"])
    llm_result = _as_dict(state.get("llm_result") or {})

    priority = list(llm_result.get("next_test_priority") or [])
    if not priority:
        priority = [
            {
                "item": item,
                "priority": "medium",
                "reason": "This test is still pending; continue testing before any final laboratory conclusion.",
            }
            for item in list(context.test_plan.pending_items or [])[:3]
        ]

    state["next_test_priority"] = priority
    return state


async def finalize_assessment(state: dict[str, Any]) -> dict[str, Any]:
    context_payload = dict(state.get("normalized_context") or {})
    test_plan = context_payload.get("test_plan") or {}

    if test_plan.get("total_items"):
        completeness = float(test_plan.get("completed_items") or 0) / max(
            float(test_plan.get("total_items") or 1), 1.0
        )
    else:
        completeness = 0.0

    features = list(state.get("anomaly_features") or [])
    deterministic_summary = dict(state.get("deterministic_summary") or {})

    if state.get("validation_errors") or state.get("blocked_reason") == "insufficient_data":
        state["assessment"] = _assessment(
            state="insufficient_data",
            completeness=completeness,
            explanation="Insufficient laboratory input data for early risk assessment.",
            deterministic_summary=deterministic_summary,
        )
        return state

    if state.get("blocked_reason") == "model_unavailable":
        state["assessment"] = _assessment(
            state="manual_review_required",
            completeness=completeness,
            risk_level="medium",
            features=features,
            explanation="No runtime model is available; manual review is required.",
            requires_manual_review=True,
            deterministic_summary=deterministic_summary,
        )
        return state

    if state.get("blocked_reason") == "llm_reasoning_failed":
        state["assessment"] = _assessment(
            state="manual_review_required",
            completeness=completeness,
            risk_level="medium",
            abnormal_probability=0.5 if features else 0.0,
            early_warning=bool(features),
            features=features,
            explanation=(
                f"LLM reasoning failed: {state.get('llm_error', 'unknown error')}. "
                f"The rule layer found {len(features)} anomaly feature(s); manual review is required."
            ),
            requires_manual_review=True,
            raw_llm_output=_as_dict(state.get("llm_result") or {}),
            deterministic_summary=deterministic_summary,
        )
        return state

    llm_result = enforce_lab_safety(_as_dict(state.get("llm_result") or {}))
    manual_review = bool(llm_result.get("requires_manual_review")) or _manual_review_feature_present(features)
    assessment_state = llm_result.get("assessment_state") or "uncertain_continue"
    if manual_review and assessment_state == "normal_so_far":
        assessment_state = "manual_review_required"

    state["assessment"] = _assessment(
        state=assessment_state,
        abnormal_probability=float(llm_result.get("abnormal_probability") or 0.0),
        risk_level=llm_result.get("risk_level") or "medium",
        completeness=completeness,
        early_warning=bool(llm_result.get("early_warning") or False),
        features=features,
        suggested_action=llm_result.get("suggested_action"),
        next_test_priority=list(
            state.get("next_test_priority") or llm_result.get("next_test_priority") or []
        ),
        explanation=str(
            llm_result.get("explanation")
            or "Early laboratory risk assessment completed; it does not replace the final laboratory conclusion."
        ),
        requires_manual_review=manual_review,
        confidence=float(llm_result.get("confidence") or 0.0),
        raw_llm_output=llm_result,
        deterministic_summary=deterministic_summary,
    )
    return state
