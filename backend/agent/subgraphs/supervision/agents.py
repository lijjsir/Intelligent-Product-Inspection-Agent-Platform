"""Four business agents; calculations are deterministic tools, semantic claims need evidence."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Awaitable, Callable, TypedDict

from langgraph.graph import END, StateGraph

ModelCall = Callable[[str, dict], Awaitable[dict]]


def parse_model_json(response: dict) -> dict:
    text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    text = str(text).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("模型结果必须为对象")
    return result


def trust_review(output: dict, snapshot: dict) -> dict:
    evidence = snapshot.get("data", {}).get("evidence", [])
    actual = {x["evidence_id"] for x in evidence if x.get("nature") == "observed"}
    cited = set(output.get("evidence_ids", []))
    issues = list(output.get("missing_inputs", []))
    if not cited or not cited.issubset(actual):
        issues.append("结论缺少可定位的真实证据")
    if output.get("conflicts"):
        issues.append("存在尚未解决的证据冲突")
    if output.get("status") in {"manual_review_required", "insufficient_evidence"}:
        issues.append("分析未满足业务完成条件")
    return {
        "decision": "request_evidence" if issues else "awaiting_human_review",
        "issues": list(dict.fromkeys(issues)),
        "probability": None,
        "score_version": "evidence-gates-v1",
    }


def standard_applicability(snapshot: dict) -> list[str]:
    standard = snapshot.get("standard")
    if not standard:
        return ["缺少可核验的标准原文"]
    app = standard.get("applicability") or {}
    data = snapshot["data"]
    issues = []
    if not app.get("clause_version") or not app.get("effective_from"):
        issues.append("标准生效时间或条款版本未明确")
    if not standard.get("clauses"):
        issues.append("缺少可定位标准条款")
    at = (
        datetime.fromisoformat(data["occurred_at"]).replace(tzinfo=None)
        if data.get("occurred_at")
        else None
    )
    if at:
        if app.get("effective_from") and at < datetime.fromisoformat(app["effective_from"]).replace(
            tzinfo=None
        ):
            issues.append("标准尚未生效，需要仲裁适用版本")
        if app.get("effective_to") and at > datetime.fromisoformat(app["effective_to"]).replace(
            tzinfo=None
        ):
            issues.append("标准已失效，需要仲裁适用版本")
    region = data.get("sampling_region_id") or data.get("complaint_region_id")
    if app.get("region_ids") and region not in app["region_ids"]:
        issues.append("标准适用地域尚未匹配")
    produced = snapshot.get("production_date")
    for field, direction in (("production_from", -1), ("production_to", 1)):
        if app.get(field):
            if not produced:
                issues.append("缺少生产日期，无法确认标准适用条件")
            elif (
                str(produced)[:10] < app[field][:10]
                if direction == -1
                else str(produced)[:10] > app[field][:10]
            ):
                issues.append("生产日期不符合该标准适用条件，需要仲裁")
    return list(dict.fromkeys(issues))


class PublicOpinionMonitoringAgent:
    """Normalize complaints and public-opinion clues into evidence-bound risk signals."""

    name = "public_opinion_monitoring"

    async def run(self, snapshot: dict, model_call: ModelCall | None = None) -> dict:
        async def analyze(state: dict) -> dict:
            data = state["snapshot"]["data"]
            evidence = [e for e in data.get("evidence", []) if e.get("nature") == "observed"]
            public_sources = [
                e
                for e in evidence
                if e.get("source_type") in {"complaint", "public_opinion", "image"}
            ]
            missing = [
                k
                for k in ("enterprise_id", "product_sku_id", "inspection_standard_id")
                if not data.get(k)
            ]
            missing.extend(standard_applicability(state["snapshot"]))
            if not evidence:
                missing.append("真实来源证据")
            if not public_sources:
                missing.append("投诉、舆情或图像线索")
            output = {
                "status": "insufficient_evidence",
                "risk_level": "unknown",
                "probability": None,
                "evidence_ids": [e["evidence_id"] for e in evidence],
                "missing_inputs": missing,
                "conflicts": [],
                "source_coverage": dict(Counter(e.get("source_type", "unknown") for e in evidence)),
                "normalized_signals": [],
                "sentiment_is_risk": False,
                "limitations": ["风险概率尚未经过校准"],
                "summary": "需要补齐证据后进行风险研判",
            }
            if model_call and evidence:
                try:
                    raw = await model_call(
                        "risk_case.assess",
                        {
                            "snapshot": state["snapshot"],
                            "instruction": "仅依据observed证据，从投诉、舆情和图像中识别企业、产品、缺陷与风险线索，区分情绪强度和质量事实。不得推断不可观察的内部缺陷。返回JSON：summary、risk_level(low/medium/high/critical/unknown)、evidence_ids、normalized_signals(string[])、conflicts(string[])、missing_inputs(string[])、limitations(string[])。每个判断必须引用给定证据编号。",
                        },
                    )
                    allowed = {e["evidence_id"] for e in evidence}
                    citations = raw.get("evidence_ids", [])
                    if not citations or not set(citations).issubset(allowed):
                        raise ValueError("风险判断引用了未知证据")
                    level = raw.get("risk_level", "unknown")
                    if level not in {"low", "medium", "high", "critical", "unknown"}:
                        raise ValueError("无效风险等级")
                    output.update(
                        summary=str(raw.get("summary", ""))[:8000],
                        risk_level=level,
                        evidence_ids=citations,
                        conflicts=list(raw.get("conflicts") or []),
                        normalized_signals=list(raw.get("normalized_signals") or []),
                        missing_inputs=list(
                            dict.fromkeys(missing + list(raw.get("missing_inputs") or []))
                        ),
                        limitations=list(raw.get("limitations") or []) + ["风险概率尚未经过校准"],
                        status="awaiting_review"
                        if not missing and not raw.get("missing_inputs")
                        else "insufficient_evidence",
                    )
                    # Independent semantic review sees original evidence plus output, not analyst reasoning.
                    review = await model_call(
                        "trust.review",
                        {
                            "evidence": evidence,
                            "standard": snapshot.get("standard"),
                            "assessment": output,
                            "instruction": "独立检查原始证据是否支持判断、是否把情绪等同风险、是否存在标准适用冲突。返回JSON：supported(boolean)、issues(string[])。不得仅依据作者的自信表述同意结论。",
                        },
                    )
                    if review.get("supported") is not True or review.get("issues"):
                        output["conflicts"].extend(
                            list(review.get("issues") or ["独立复核未确认支持关系"])
                        )
                        output["status"] = "manual_review_required"
                except Exception:
                    output.update(
                        status="manual_review_required",
                        summary="模型分析或独立复核未完成，请人工复核原始证据",
                    )
            elif evidence:
                output.update(
                    status="manual_review_required",
                    summary="已登记证据；当前无可用风险分析模型，请人工复核",
                )
            return {"output": output}

        async def review(state: dict) -> dict:
            out = dict(state["output"])
            out["trust_review"] = trust_review(out, state["snapshot"])
            return {"output": out}

        return await _graph(snapshot, analyze, review)


class MarketMonitoringAgent:
    """Monitor domestic market risk signals by time, source, product, enterprise and region."""

    name = "market_monitoring"

    async def run(self, snapshot: dict, model_call: ModelCall | None = None) -> dict:
        async def calculate(state: dict) -> dict:
            now = datetime.fromisoformat(snapshot["as_of"])
            cases = snapshot.get("cases", [])
            current, previous = [], []
            for case in cases:
                at = datetime.fromisoformat(case["data"]["occurred_at"]).replace(tzinfo=None)
                delta = (now.replace(tzinfo=None) - at).days
                if 0 <= delta < 30:
                    current.append(case)
                elif 30 <= delta < 60:
                    previous.append(case)
            dimensions = {}
            for key in (
                "complaint_region_id",
                "sampling_region_id",
                "enterprise_id",
                "product_category",
            ):
                dimensions[key] = dict(
                    Counter(str(c["data"].get(key) or "未登记") for c in current)
                )
            source_distribution = dict(
                Counter(
                    evidence.get("source_type", "unknown")
                    for case in current
                    for evidence in case.get("data", {}).get("evidence", [])
                    if evidence.get("nature") == "observed"
                )
            )
            risk_distribution = dict(
                Counter(
                    case.get("data", {}).get("analysis", {}).get("risk_level", "unknown")
                    for case in current
                )
            )
            change = len(current) - len(previous)
            return {
                "output": {
                    "status": "completed",
                    "summary": f"最近30天记录{len(current)}个案件，前30天{len(previous)}个",
                    "current_count": len(current),
                    "previous_count": len(previous),
                    "dimensions": dimensions,
                    "source_distribution": source_distribution,
                    "risk_distribution": risk_distribution,
                    "signal_change": change,
                    "monitoring_alert": change > 0 and bool(current),
                    "period_days": 30,
                    "probability": None,
                    "exposures": snapshot.get("exposures", []),
                    "limitations": [
                        "案件数量变化不等于实际产品失效率",
                        "缺少匹配的暴露量时不估计总体风险概率",
                    ],
                    "scenario": "若新增线索持续增加，优先补充样本与使用条件，再安排代表性抽查",
                }
            }

        return await _graph(snapshot, calculate)


class SupervisionSamplingAgent:
    """Turn confirmed domestic risk signals into an auditable supervision sampling plan."""

    name = "supervision_sampling"

    async def run(self, snapshot: dict, model_call: ModelCall | None = None) -> dict:
        async def optimize(state: dict) -> dict:
            data = snapshot["data"]
            cases = {x["id"]: x for x in snapshot.get("cases", [])}
            devices = {x["id"]: x for x in snapshot.get("devices", [])}
            ranks = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}
            candidates = data.get("candidates", [])

            def category(c):
                return (
                    cases.get(c["case_id"], {}).get("data", {}).get("product_category") or "未登记"
                )

            def rank(c):
                return ranks.get(
                    cases.get(c["case_id"], {})
                    .get("data", {})
                    .get("analysis", {})
                    .get("risk_level"),
                    0,
                )

            # Cover required categories first, then risk ordering; stable ties for reproducibility.
            required = set(data.get("required_categories", []))
            ordered = []
            for cat in sorted(required):
                group = sorted(
                    [c for c in candidates if category(c) == cat],
                    key=lambda c: (-rank(c), c["case_id"]),
                )
                if group:
                    ordered.append(group[0])
            ordered += [
                c
                for c in sorted(candidates, key=lambda c: (-rank(c), c["case_id"]))
                if c not in ordered
            ]
            selected, rejected, used = [], [], Counter()
            cost, count, hours = 0.0, 0, 0.0
            for c in ordered:
                n = c["sample_count"]
                dc = devices.get(c.get("device_id"))
                reason = None
                if cases.get(c["case_id"], {}).get("status") != "risk_assessed":
                    reason = "风险评估尚未确认"
                elif not c.get("test_items") or any(
                    not t.get("standard_ref") for t in c["test_items"]
                ):
                    reason = "缺少检测项目或标准依据"
                elif c.get("device_id") and (
                    not dc
                    or dc["status"] != "active"
                    or used[c["device_id"]] + n > dc["data"].get("capacity", 0)
                ):
                    reason = "设备未启用或容量不足"
                elif c.get("device_id") and any(
                    t["item"] not in dc["data"].get("capabilities", [])
                    for t in c.get("test_items", [])
                ):
                    reason = "设备检测能力与计划项目不匹配"
                elif (
                    cost + n * c["unit_cost"] > data["budget"]
                    or count + n > data["max_samples"]
                    or hours + n * data["hours_per_sample"] > data["max_staff_hours"]
                ):
                    reason = "预算、样本或人员工时约束不足"
                if reason:
                    rejected.append({"case_id": c["case_id"], "reason": reason})
                    continue
                selected.append({**c, "category": category(c), "reason": "类别覆盖与风险排序"})
                cost += n * c["unit_cost"]
                count += n
                hours += n * data["hours_per_sample"]
                used[c.get("device_id")] += n
            uncovered = sorted(required - {x["category"] for x in selected})
            return {
                "output": {
                    "status": "completed" if selected and not uncovered else "infeasible",
                    "summary": f"拟抽查{count}个样本，成本{cost:g}，工时{hours:g}",
                    "selected": selected,
                    "rejected": rejected,
                    "uncovered_categories": uncovered,
                    "total_cost": cost,
                    "sample_count": count,
                    "staff_hours": hours,
                    "probability": None,
                    "limitations": ["使用确定性覆盖与排序策略，不保证全局最优"],
                }
            }

        return await _graph(snapshot, optimize)


class LaboratoryTestingAgent:
    """Coordinate laboratory samples, devices, measurements, baselines and re-tests."""

    name = "laboratory_testing"

    async def run(self, snapshot: dict, model_call: ModelCall | None = None) -> dict:
        async def compute(state: dict) -> dict:
            data = snapshot["data"]
            if data.get("input_mode") == "image":
                return {
                    "output": data.get("image_assessment")
                    or {
                        "status": "insufficient_evidence",
                        "summary": "尚无图片分析草稿",
                        "missing_inputs": ["图片分析"],
                        "probability": None,
                    }
                }
            measurements = snapshot.get("measurements", [])
            devices = {d["id"]: d for d in snapshot.get("devices", [])}
            expected = {
                (sid, t["item"]): t
                for sid in data.get("sample_ids", [])
                for t in data["test_items"]
            }
            latest = {}
            for m in measurements:
                key = (m["sample_id"], m["item"])
                if key not in latest or m["measured_at"] > latest[key]["measured_at"]:
                    latest[key] = m
            findings, valid, missing_limits = [], set(), []
            for key, m in latest.items():
                t = expected.get(key)
                if not t:
                    continue
                dev = devices.get(m["device_id"], {})
                expiry = dev.get("data", {}).get("calibration_expires_at")
                expired = expiry and datetime.fromisoformat(expiry).replace(
                    tzinfo=None
                ) < datetime.fromisoformat(m["measured_at"]).replace(tzinfo=None)
                if (
                    m["quality_flag"] != "valid"
                    or dev.get("data", {}).get("calibration_status") != "valid"
                    or expired
                ):
                    findings.append(
                        {
                            "type": "instrument_suspected",
                            "event_id": m["event_id"],
                            "item": m["item"],
                            "value": m["value"],
                        }
                    )
                    continue
                valid.add(key)
                if not t.get("standard_ref") or (
                    t.get("lower_limit") is None and t.get("upper_limit") is None
                ):
                    missing_limits.append(m["item"])
                if (t.get("lower_limit") is not None and m["value"] < t["lower_limit"]) or (
                    t.get("upper_limit") is not None and m["value"] > t["upper_limit"]
                ):
                    findings.append(
                        {
                            "type": "product_abnormal",
                            "event_id": m["event_id"],
                            "item": m["item"],
                            "value": m["value"],
                            "standard_ref": t.get("standard_ref"),
                        }
                    )
                if (t.get("normal_lower") is not None and m["value"] < t["normal_lower"]) or (
                    t.get("normal_upper") is not None and m["value"] > t["normal_upper"]
                ):
                    findings.append(
                        {"type": "baseline_deviation", "event_id": m["event_id"], "item": m["item"]}
                    )
            missing = [f"{sid}:{item}" for sid, item in expected if (sid, item) not in valid]
            for source in snapshot.get("related_sources", []):
                if source["data"].get("knowledge_status") == "needs_reassessment":
                    missing.append("关联案件或计划依据已失效，需要重评估")
            complete = bool(expected) and not missing and not missing_limits
            visual = snapshot.get("visual_inspection_result")
            visual_verdict = str(
                (visual or {}).get("verdict") or (visual or {}).get("draft_verdict") or "unknown"
            )
            if data.get("input_mode") == "mixed":
                if not visual or visual_verdict not in {"pass", "fail"}:
                    missing.append("图片风险与标准校核")
                    complete = False
                if visual_verdict == "fail":
                    findings.append(
                        {
                            "type": "visual_abnormal",
                            "item": "图片可观察缺陷",
                            "evidence": visual.get("summary"),
                        }
                    )
            return {
                "output": {
                    "status": "awaiting_review" if complete else "insufficient_evidence",
                    "summary": f"有效完成{len(valid)}/{len(expected)}项，发现{len(findings)}个异常信号",
                    "data_completeness": len(valid) / len(expected) if expected else 0,
                    "findings": findings,
                    "missing_inputs": missing + [f"标准限值:{x}" for x in missing_limits],
                    "early_warning": any(f["type"] == "product_abnormal" for f in findings),
                    "probability": None,
                    "can_make_final_verdict": False,
                    "suggested_verdict": "fail"
                    if any(f["type"] in {"product_abnormal", "visual_abnormal"} for f in findings)
                    else "pass"
                    if complete and not findings
                    else "manual_required",
                    "consumed_event_ids": [m["event_id"] for m in latest.values()],
                    "visual_defects": (visual or {}).get("defects", []),
                    "limitations": ["提前提示不替代完整检测及人工结果签发"],
                }
            }

        return await _graph(snapshot, compute)


async def _graph(snapshot: dict, analyze, review=None) -> dict:
    class State(TypedDict):
        snapshot: dict
        output: dict

    graph = StateGraph(State)
    graph.add_node("analyze", analyze)
    graph.set_entry_point("analyze")
    if review:
        graph.add_node("review", review)
        graph.add_edge("analyze", "review")
        graph.add_edge("review", END)
    else:
        graph.add_edge("analyze", END)
    result = await graph.compile().ainvoke({"snapshot": snapshot})
    return result["output"]


AGENTS = {
    x.name: x()
    for x in (
        PublicOpinionMonitoringAgent,
        MarketMonitoringAgent,
        SupervisionSamplingAgent,
        LaboratoryTestingAgent,
    )
}
