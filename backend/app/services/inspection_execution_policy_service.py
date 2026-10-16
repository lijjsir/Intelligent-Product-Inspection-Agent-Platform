"""Input completeness gates, separate from confirmed standard product limits."""
from app.services.inspection_execution_context_service import task_image_inputs

FIELD_LABELS={"product_category":"产品类别","production_date":"实际生产日期","sample_ids":"样品",
    "session_id":"检测会话","quality_product_id":"具体产品","production_batch_ref":"生产批次","unit_serial_ref":"单件标识"}


def evaluate_policy_inputs(task,scope,payload,policy):
    issues=[];meta=task.meta_data or {};images=task_image_inputs(task)
    by_hash={image["image_hash"]:image for image in images}
    declared={}
    for item in payload.get("image_view_assignments",[]):
        key=item["image_hash"]
        if key not in by_hash:issues.append("视角标注引用的图片不属于本任务");continue
        if key in declared and declared[key]!=item["view"]:issues.append("同一图片不能充当多个独立视角")
        declared[key]=item["view"]
    for image in images:
        image["view"]=declared.get(image["image_hash"],image["view"])
    if scope["input_mode"] in policy.get("image_requirements_apply_to",["image","mixed"]):
        count=int(policy.get("required_image_count") or 0)
        if len(images)<count:issues.append(f"策略要求至少{count}张独立图片，当前{len(images)}张")
        missing=set(policy.get("required_views") or [])-{image["view"] for image in images}
        if missing:issues.append("策略要求的图片视角尚未补齐："+"、".join(sorted(missing)))
    fields={**scope,"product_category":payload["product_category"],"production_date":payload["production_date"],
        "sample_ids":payload["sample_ids"],"session_id":payload.get("session_id")}
    for field in policy.get("required_fields",[]):
        value=fields.get(field) if field in FIELD_LABELS else meta.get(field.removeprefix("metadata:"))
        if value is None or (isinstance(value,str) and not value.strip()) or value==[] or value=={}:
            issues.append("任务缺少策略要求字段："+FIELD_LABELS.get(field,field))
    return {"input_mode":scope["input_mode"],"images":images,"required_fields":{f:fields.get(f,meta.get(f.removeprefix("metadata:"))) for f in policy.get("required_fields",[])},
        "issues":list(dict.fromkeys(issues)),"notice":"视角为任务材料的人工标注，输入完整不代表产品符合标准。"}
