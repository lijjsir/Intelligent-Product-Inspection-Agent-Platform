from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inspection_spec import InspectionSpec, InspectionSpecItem
from app.repositories.inspection_spec_repo import InspectionSpecRepository


VALID_DISPOSITIONS = {"pass", "fail", "uncertain", "manual_required"}


class InspectionStandardService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._repo = InspectionSpecRepository(session)
        self._org_id = org_id

    async def evaluate(
        self,
        spec_code: str,
        image_urls: list[str],
        defects: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        reasoning_chain: dict[str, Any],
        model_verdict: str,
        overall_score: float,
    ) -> dict[str, Any]:
        spec = await self._repo.get_active_spec(self._org_id, spec_code)
        if not spec:
            return {
                "verdict": "manual_required",
                "summary": "未找到有效检测标准，按 QS-009 禁止自动放行。",
                "reasons": ["missing_spec"],
                "matched_rules": [],
                "unmatched_defects": [str(item.get("type") or "unknown") for item in defects],
                "ai_gate": self._build_ai_gate(None, citations, reasoning_chain, defects, overall_score),
                "spec": None,
            }

        items = await self._repo.list_items(spec.id)
        return self._evaluate_loaded_spec(
            spec=spec,
            items=items,
            image_urls=image_urls,
            defects=defects,
            citations=citations,
            reasoning_chain=reasoning_chain,
            model_verdict=model_verdict,
            overall_score=overall_score,
        )

    @classmethod
    def _evaluate_loaded_spec(
        cls,
        spec: InspectionSpec,
        items: list[InspectionSpecItem],
        image_urls: list[str],
        defects: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        reasoning_chain: dict[str, Any],
        model_verdict: str,
        overall_score: float,
    ) -> dict[str, Any]:
        if len(image_urls) < int(spec.required_image_count or 1):
            ai_gate = cls._build_ai_gate(spec, citations, reasoning_chain, defects, overall_score)
            ai_gate["reasons"].append("insufficient_required_views")
            return {
                "verdict": "manual_required",
                "summary": "图像视角或数量不足，不能自动放行。",
                "reasons": ["insufficient_required_views"],
                "matched_rules": [],
                "unmatched_defects": [str(item.get("type") or "unknown") for item in defects],
                "ai_gate": ai_gate,
                "spec": cls._serialize_spec(spec),
            }

        matched_rules: list[dict[str, Any]] = []
        unmatched_defects: list[str] = []
        counts: dict[str, int] = {}

        for defect in defects:
            defect_type = str(defect.get("type") or "unknown")
            confidence = float(defect.get("confidence") or 0.0)
            counts[defect_type] = counts.get(defect_type, 0) + 1
            matched = False
            for item in items:
                if item.defect_type != defect_type:
                    continue
                if confidence < float(item.confidence_threshold or 0.0):
                    continue
                if item.max_count is not None and counts[defect_type] > int(item.max_count):
                    continue
                matched = True
                matched_rules.append(
                    {
                        "defect_type": defect_type,
                        "confidence": round(confidence, 4),
                        "severity": item.severity,
                        "disposition": item.disposition,
                        "zone_name": item.zone_name,
                        "description": item.description,
                    }
                )
            if not matched:
                unmatched_defects.append(defect_type)

        ai_gate = cls._build_ai_gate(spec, citations, reasoning_chain, defects, overall_score)
        dispositions = {str(rule.get("disposition") or "manual_required") for rule in matched_rules}
        reasons: list[str] = []
        verdict = "uncertain"

        if "fail" in dispositions:
            verdict = "fail"
            reasons.append("matched_reject_rule")
        elif "manual_required" in dispositions:
            verdict = "manual_required"
            reasons.append("matched_manual_review_rule")
        elif defects and unmatched_defects:
            verdict = "manual_required"
            reasons.append("unmapped_detected_defects")
        else:
            normalized_model_verdict = str(model_verdict or "uncertain").lower()
            if normalized_model_verdict not in VALID_DISPOSITIONS:
                normalized_model_verdict = "uncertain"
            if normalized_model_verdict == "fail":
                verdict = "fail"
                reasons.append("model_reject")
            elif normalized_model_verdict == "pass":
                if bool(spec.auto_pass_enabled) and ai_gate["passed"]:
                    verdict = "pass"
                else:
                    verdict = "manual_required"
                    reasons.append("ai_gate_blocked_auto_pass")
            else:
                verdict = normalized_model_verdict
                if not ai_gate["passed"]:
                    reasons.append("ai_gate_warning")

        summary = cls._build_summary(verdict, spec.spec_code, matched_rules, unmatched_defects, ai_gate["reasons"])
        return {
            "verdict": verdict,
            "summary": summary,
            "reasons": reasons,
            "matched_rules": matched_rules,
            "unmatched_defects": unmatched_defects,
            "ai_gate": ai_gate,
            "spec": cls._serialize_spec(spec),
        }

    @staticmethod
    def _build_ai_gate(
        spec: InspectionSpec | None,
        citations: list[dict[str, Any]],
        reasoning_chain: dict[str, Any],
        defects: list[dict[str, Any]],
        overall_score: float,
    ) -> dict[str, Any]:
        evidence_score = 1.0 if not defects else min(1.0, len(citations) / max(len(defects), 1))
        traceability_score = 1.0 if reasoning_chain and citations else 0.6 if reasoning_chain else 0.0
        confidence_threshold = float(spec.ai_gate_confidence_threshold) if spec else 0.72
        evidence_threshold = float(spec.ai_gate_evidence_threshold) if spec else 0.5
        traceability_threshold = float(spec.ai_gate_traceability_threshold) if spec else 0.5
        reasons: list[str] = []
        if float(overall_score or 0.0) < confidence_threshold:
            reasons.append("confidence_below_threshold")
        if evidence_score < evidence_threshold:
            reasons.append("evidence_below_threshold")
        if traceability_score < traceability_threshold:
            reasons.append("traceability_below_threshold")
        return {
            "passed": not reasons,
            "confidence_score": round(float(overall_score or 0.0), 4),
            "evidence_score": round(evidence_score, 4),
            "traceability_score": round(traceability_score, 4),
            "thresholds": {
                "confidence": round(confidence_threshold, 4),
                "evidence": round(evidence_threshold, 4),
                "traceability": round(traceability_threshold, 4),
            },
            "reasons": reasons,
        }

    @staticmethod
    def _serialize_spec(spec: InspectionSpec) -> dict[str, Any]:
        return {
            "spec_code": spec.spec_code,
            "name": spec.name,
            "version": spec.version,
            "product_id": spec.product_id,
            "product_family": spec.product_family,
            "applicable_skus": list(spec.applicable_skus or []),
            "required_views": list(spec.required_views or []),
            "effective_from": spec.effective_from,
            "effective_to": spec.effective_to,
            "required_image_count": int(spec.required_image_count or 1),
            "aggregation_rules": dict(spec.aggregation_rules or {}),
            "ai_gate_rules": dict(spec.ai_gate_rules or {}),
            "manual_review_policies": dict(spec.manual_review_policies or {}),
            "auto_pass_enabled": bool(spec.auto_pass_enabled),
        }

    @staticmethod
    def _build_summary(
        verdict: str,
        spec_code: str,
        matched_rules: list[dict[str, Any]],
        unmatched_defects: list[str],
        ai_gate_reasons: list[str],
    ) -> str:
        if verdict == "pass":
            return f"按标准 {spec_code} 校验通过，且 AI 门禁满足自动放行条件。"
        if verdict == "fail":
            return f"按标准 {spec_code} 命中拒收规则，结果判定为 FAIL。"
        details = []
        if unmatched_defects:
            details.append("存在未映射缺陷")
        if ai_gate_reasons:
            details.append("AI 门禁未全部通过")
        if matched_rules and verdict == "manual_required":
            details.append("命中人工复核规则")
        suffix = "；".join(details) if details else "需要人工复核"
        return f"按标准 {spec_code} 不能自动放行，{suffix}。"
