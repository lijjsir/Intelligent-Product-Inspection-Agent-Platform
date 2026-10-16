"""Deterministic evaluation of explicit, reviewed requirements.

No extraction of thresholds from natural language and no product-wide pass
inferred from an incomplete list of selected inspection items.
"""
import math
import json
from decimal import Decimal

ENGINE_VERSION="confirmed-requirements-v2"
UNIT_ALIASES={"dB(A)":"dBA","db(a)":"dBA","℃":"°C","度":"°C","毫伏":"mV","伏":"V"}
UNIT_GROUPS={"mm":("length",Decimal("0.001")),"cm":("length",Decimal("0.01")),"m":("length",Decimal(1)),
    "km/h":("speed",Decimal(1)),"m/s":("speed",Decimal("3.6")),"V":("voltage",Decimal(1)),"mV":("voltage",Decimal("0.001")),
    "Ω":("resistance",Decimal(1)),"MΩ":("resistance",Decimal(1000000)),"g":("mass",Decimal("0.001")),"kg":("mass",Decimal(1))}


def numeric(value):
    if isinstance(value,bool) or value is None:return None
    try:result=Decimal(str(value))
    except Exception:return None
    return result if result.is_finite() else None


def convert(value,source,target):
    value=numeric(value)
    if value is None:return None
    source=UNIT_ALIASES.get(source,source);target=UNIT_ALIASES.get(target,target)
    if source==target:return value
    a,b=UNIT_GROUPS.get(source),UNIT_GROUPS.get(target)
    if not a or not b or a[0]!=b[0]:return None
    return value*a[1]/b[1]


def evaluate_requirement(rule,observations):
    base={"candidate_id":rule["id"],"indicator":rule["indicator"],"measurement_key":rule["measurement_key"],
        "revision_id":rule.get("revision_id"),"standard_no":rule.get("standard_no"),"clause_no":rule.get("clause_no"),
        "page_number":rule.get("page_number"),"candidate_type":rule.get("candidate_type") or "unclassified","unit":rule["unit"],"method":rule["method"],"evidence_ids":[],"findings":[],"missing_inputs":[],
        "duplicate_evidence_ids":[],"conflicting_evidence_ids":[],"independent_observation_count":0}
    if rule.get("execution_mode")!="numeric":return {**base,"status":"manual_required","missing_inputs":["该要求尚未确认可执行数值字段或需要人工文字核验"]}
    operator=rule.get("operator");low=numeric(rule.get("numeric_lower"));high=numeric(rule.get("numeric_upper"));target=numeric(rule.get("numeric_target"))
    if operator not in {"le","ge","range","eq"} or (operator=="le" and high is None) or (operator=="ge" and low is None) or (operator=="range" and (low is None or high is None or low>high)) or (operator=="eq" and target is None):
        return {**base,"status":"manual_required","missing_inputs":["标准数值要求不完整，不能从文字中的数字推断限值"]}
    if not observations:return {**base,"status":"missing","missing_inputs":["缺少该样品与检测项目的观测"]}
    valid=[];issues=[];identities={};unique=[]
    for obs in observations:
        identity=obs.get("observation_identity") or obs.get("evidence_id")
        if not identity:
            issues.append("观测缺少可追溯身份");continue
        # Identity is supplied by the source validator, never by the execution request.
        # Compare before filtering invalid readings: a contradictory copy cannot vanish.
        signature=json.dumps({key:obs.get(key) for key in ["value","unit","method","conditions","uncertainty",
            "quality_flag","validation_status","sample_id","measurement_key","source_version"]},sort_keys=True,default=str)
        if identity in identities:
            base["duplicate_evidence_ids"].append(obs.get("evidence_id"))
            if identities[identity]!=signature:
                base["conflicting_evidence_ids"].append(obs.get("evidence_id"))
                issues.append("同一观测身份存在不同数值、条件或来源状态，需核对冲突")
            continue
        identities[identity]=signature;unique.append(obs)
    for obs in unique:
        if obs.get("validation_status") not in {"accepted","reported"} or obs.get("quality_flag")!="valid":
            issues.append("测量质量、校准或来源状态未通过核验");continue
        if obs.get("method")!=rule["method"]:issues.append("检测方法与确认要求不匹配");continue
        expected=rule.get("expected_conditions") or {}
        if any((obs.get("conditions") or {}).get(key)!=value for key,value in expected.items()):issues.append("试验条件或规格分支缺失/不匹配");continue
        value=convert(obs.get("value"),obs.get("unit"),rule["unit"])
        if value is None:issues.append("数值无效或单位不兼容");continue
        uncertainty=None
        if rule.get("decision_mode")=="interval":
            uncertainty=convert(obs.get("uncertainty"),obs.get("unit"),rule["unit"])
            if uncertainty is None or uncertainty<0:issues.append("区间判定缺少有效测量不确定度");continue
        valid.append((obs,value,uncertainty or Decimal(0)))
    base["evidence_ids"]=[o.get("evidence_id") for o,_,_ in valid]
    base["independent_observation_count"]=len(valid)
    if issues or len(valid)<int(rule.get("minimum_observations") or 1):
        return {**base,"status":"uncertain","missing_inputs":list(dict.fromkeys(issues or ["有效观测次数不足"]))}
    if rule.get("numeric_aggregation","all")=="mean":
        if rule.get("decision_mode")=="interval":return {**base,"status":"manual_required","missing_inputs":["均值与不确定度的组合规则尚未实现，需专业核验"]}
        valid=[({"evidence_id":"mean","validation_status":"accepted"},sum(v for _,v,_ in valid)/len(valid),Decimal(0))]
    states=[]
    for obs,value,uncertainty in valid:
        lower,upper=value-uncertainty,value+uncertainty
        if operator=="le":status="pass" if upper<=high else "fail" if lower>high else "uncertain"
        elif operator=="ge":status="pass" if lower>=low else "fail" if upper<low else "uncertain"
        elif operator=="range":status="pass" if lower>=low and upper<=high else "fail" if upper<low or lower>high else "uncertain"
        else:status="pass" if lower==upper==target else "fail" if target<lower or target>upper else "uncertain"
        states.append(status);base["findings"].append({"evidence_id":obs.get("evidence_id"),"value":str(value),"status":status,
            "lower":str(low) if low is not None else None,"upper":str(high) if high is not None else None,"target":str(target) if target is not None else None})
    status="fail" if "fail" in states else "uncertain" if "uncertain" in states else "pass"
    return {**base,"status":status,"missing_inputs":["观测区间与限值重叠，需要复核"] if status=="uncertain" else []}


def evaluate_plan(requirements,samples,observations,*,source_issues=None,policy=None):
    source_issues=list(source_issues or [])
    checks=[]
    for sample in samples:
        for rule in requirements:
            matched=[o for o in observations if o.get("sample_id")==sample and o.get("measurement_key")==rule["measurement_key"]]
            checks.append({"sample_id":sample,**evaluate_requirement(rule,matched)})
    missing=list(dict.fromkeys([*source_issues,*[m for c in checks for m in c["missing_inputs"]]]))
    if not checks:missing.append("没有可执行检测项目")
    failures=[c for c in checks if c["status"]=="fail"]
    unknown=[c for c in checks if c["status"] not in {"pass","fail"}]
    verdict="incomplete" if missing or unknown else "fail" if failures else "pass"
    policy=policy or {}
    review=["选定项目结论需独立专业复核"]
    if failures and policy.get("review_on_fail",True):review.append("存在不符合项目")
    if any(o.get("validation_status")=="reported" for o in observations):review.append("使用了报告转录值，需逐项核对原文")
    groups={}
    for kind in ["inspection_requirement","method_condition","body_clause","unclassified"]:
        group=[c for c in checks if c["candidate_type"]==kind]
        groups[kind]={"count":len(group),"verdict":"not_assessed" if not group else "incomplete" if any(c["status"] not in {"pass","fail"} for c in group) else "fail" if any(c["status"]=="fail" for c in group) else "pass"}
    return {"engine_version":ENGINE_VERSION,"scope":"selected_confirmed_requirements","requirement_groups":groups,"item_verdict":verdict,"product_verdict":"not_assessed",
        "checks":checks,"missing_inputs":missing,"failed_count":len(failures),"complete_count":sum(c["status"] in {"pass","fail"} for c in checks),
        "expected_count":len(checks),"consumed_evidence_ids":list(dict.fromkeys(e for c in checks for e in c["evidence_ids"] if e)),
        "review_status":"required","review_reasons":review,"risk_level":"unknown","score_status":"not_calibrated",
        "boundary":"仅判定本次选定项目；不代表整份标准、全部样品或产品整体合格，也不直接等同风险等级。"}
