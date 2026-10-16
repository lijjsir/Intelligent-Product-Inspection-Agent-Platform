from sqlalchemy import select
from app.models.standard_admission import StandardDocumentRevision
from app.models.inspection_standard_library import StandardDocument,InspectionStandardLibrary


def agent_execution_context(snapshot: dict) -> dict:
    """Return the shared, read-only standard/evidence view consumed by agents."""
    evaluation = snapshot.get("standard_execution_evaluation") or snapshot.get("standard_execution")
    sources = snapshot.get("standard_execution_sources") or snapshot.get("source_refs") or []
    observations = snapshot.get("observations") or snapshot.get("measurements") or []
    evidence = []
    for item in observations:
        evidence.append({
            "evidence_id": item.get("evidence_id") or item.get("event_id") or item.get("id"),
            "kind": item.get("kind") or "measurement",
            "measurement_key": item.get("measurement_key") or item.get("item"),
            "sample_id": item.get("sample_id"),
            "validation_status": item.get("validation_status"),
            "quality_flag": item.get("quality_flag"),
        })
    for item in snapshot.get("data", {}).get("evidence", []) if isinstance(snapshot.get("data"), dict) else []:
        evidence.append({
            "evidence_id": item.get("evidence_id"),
            "kind": item.get("source_type") or "observed",
            "measurement_key": None,
            "sample_id": None,
            "validation_status": "observed" if item.get("nature") == "observed" else item.get("nature"),
            "quality_flag": None,
        })
    if evaluation:
        status = "evaluated"
        missing = list(evaluation.get("missing_inputs") or [])
    elif snapshot.get("standard"):
        status = "standard_reference_only"
        missing = ["尚未形成标准要求执行快照"]
    else:
        status = "missing"
        missing = ["缺少已发布标准执行上下文"]
    return {
        "status": status,
        "evaluation": evaluation or {"item_verdict": "incomplete", "product_verdict": "not_assessed", "risk_level": "unknown"},
        "standard_sources": sources,
        "evidence": evidence,
        "missing_inputs": list(dict.fromkeys(missing)),
        "boundary": "仅供各 Agent 共享依据与证据索引；不生成标准限值，不替代专业复核。",
    }


async def published_standard_context(session,org_id,*,library_id=None,product_category=None):
    q=select(StandardDocumentRevision,StandardDocument).join(StandardDocument,StandardDocument.published_revision_id==StandardDocumentRevision.id)
    q=q.join(InspectionStandardLibrary,InspectionStandardLibrary.id==StandardDocument.library_id).where(StandardDocumentRevision.org_id==org_id,
        StandardDocument.org_id==org_id,InspectionStandardLibrary.org_id==org_id,StandardDocumentRevision.publication_status=="published",
        StandardDocumentRevision.review_status=="approved",StandardDocument.deleted_at.is_(None),InspectionStandardLibrary.deleted_at.is_(None),InspectionStandardLibrary.is_active.is_(True))
    if library_id:q=q.where(StandardDocument.library_id==library_id)
    rows=(await session.execute(q)).all();result=[]
    for revision,document in rows:
        meta=revision.snapshot
        if product_category and meta.get("product_category")!=product_category:continue
        result.append({"revision_id":revision.id,"document_id":document.id,"library_id":document.library_id,"standard_no":meta["standard_no"],
            "standard_status":meta.get("standard_status"),"file_hash":revision.file_hash,"applicability":meta.get("scope_notes"),
            "product_category":meta.get("product_category"),"effective_from":meta.get("effective_from"),"effective_to":meta.get("effective_to"),
            "requirements":[c for c in revision.candidates_json or [] if c.get("status")=="confirmed"],
            "clauses":[{"page_number":p["page_number"],"text":p["text"][:2500]} for p in revision.pages_json or [] if p.get("text")][:40]})
    return result
