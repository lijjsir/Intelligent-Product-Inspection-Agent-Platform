"""Evidence requirements for document review, separate from live regulatory decisions."""
from app.core.exceptions import ValidationError

HISTORICAL = "historical_review"
CURRENT = "current_supervision"
RULES_VERSION = "risk-purpose-v1"
HISTORY_BOUNDARY = "仅复盘所列时期、对象和原始资料；原报告结论与平台分析分别保留，不代表当前在售产品状态，也不构成本平台重新检测或抽查执行结论。"


def purpose(scope):
    scope = scope or {}
    return scope.get("assessment_purpose") or (HISTORICAL if scope.get("case_mode") == "public_historical_review" else CURRENT)


def canonical_scope(scope, requested=None):
    value = purpose(scope)
    if requested is not None and (scope.get("assessment_purpose") or scope.get("case_mode")) and requested != value:
        raise ValidationError("研判用途与对象范围中的用途不一致")
    value = requested or value
    if value not in {CURRENT, HISTORICAL}:
        raise ValidationError("不支持的研判用途")
    return {**scope, "assessment_purpose": value}


def historical_requirements(scope, records):
    """Only source facts determine prerequisites. Model prose never relaxes these."""
    required = []
    if not str(scope.get("historical_period") or "").strip():
        required.append("明确历史复盘的时间范围")
    if not any(scope.get(key) for key in ("product_id", "category_id", "enterprise_id", "name", "category_name")):
        required.append("明确历史复盘的对象范围")
    official = [r for r in records if r.data_nature == "observed" and r.record_type in {
        "inspection_report", "supervision_inspection", "enforcement_case"}]
    if not official:
        required.append("可追溯的原始检测报告、抽查通报或执法事实")
    for record in official:
        content, provenance = record.content or {}, record.provenance or {}
        if not (provenance.get("source_url") or provenance.get("url") or record.attachment_ids):
            required.append("原始资料的出处链接或原件")
        if record.record_type == "inspection_report":
            if not record.attachment_ids:
                required.append("所引用检测报告的原件")
            if not content.get("report_no") or not content.get("issued_date"):
                required.append("原报告编号及出具日期")
            if not any(content.get(key) for key in ("documentary_verdict", "conclusion", "findings")):
                required.append("原报告记载的结论及适用范围")
        if scope.get("product_id") and (record.product_ref or {}).get("product_id") != scope["product_id"]:
            required.append("原始资料的产品对象与复盘范围一致")
    return list(dict.fromkeys(required))


def review_requirements(scope, records, model_missing, limitations):
    historical = purpose(scope) == HISTORICAL
    source_limits = [value for record in records for value in (record.content or {}).get("limitations", []) if isinstance(value, str)]
    return {"rules_version": RULES_VERSION, "purpose": purpose(scope),
        "required_inputs": historical_requirements(scope, records) if historical else list(model_missing),
        "limitations": list(dict.fromkeys([*source_limits, *limitations, *model_missing, HISTORY_BOUNDARY])) if historical else list(limitations),
        "model_suggestions": list(model_missing),
        "boundary": HISTORY_BOUNDARY if historical else "当前监管研判；涉及新检测时须完成样品、标准、设备、测量和独立复核核验。"}


def require_current_purpose(case):
    if purpose(case.scope) == HISTORICAL:
        raise ValidationError("历史资料复盘不能直接作为当前抽查或新检测依据；请另建当前监管事项并核对现有对象及证据")
