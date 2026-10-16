from fastapi import APIRouter,Depends,Query
from sqlalchemy import select
from app.api.v1.deps import get_db,get_current_user
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.schemas.inspection_execution import InspectionExecutionCreate,InspectionExecutionReview,PolicyPublish,TaskReportLink
from app.schemas.standard_admission import RevisionAction
from app.services.inspection_execution_service import InspectionExecutionService
from app.models.standard_admission import StandardDocumentRevision
from app.models.inspection_standard_library import StandardDocument,InspectionStandardLibrary

router=APIRouter(prefix="/inspection-execution",tags=["inspection-execution"])


@router.get("/tasks/{task_id}/case-workflow",response_model=ResponseEnvelope[dict|None])
async def case_workflow(task_id:str,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role('inspection_execution',current.role);require_role('result',current.role)
    from app.services.inspection_case_workflow_service import InspectionCaseWorkflowService
    return ResponseEnvelope(data=await InspectionCaseWorkflowService(db,current).read(task_id))


@router.get("/tasks/{task_id}/context",response_model=ResponseEnvelope[dict])
async def task_context(task_id:str,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_execution",current.role)
    from app.services.inspection_execution_context_service import InspectionExecutionContextService
    task=await InspectionExecutionService(db,current).task(task_id)
    return ResponseEnvelope(data=await InspectionExecutionContextService(db,current).context(task))


@router.get("/tasks/{task_id}/report-candidates",response_model=ResponseEnvelope[list[dict]])
async def report_candidates(task_id:str,keyword:str=Query(default="",max_length=200),current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_execution",current.role)
    from app.services.inspection_execution_context_service import InspectionExecutionContextService
    task=await InspectionExecutionService(db,current).task(task_id)
    return ResponseEnvelope(data=await InspectionExecutionContextService(db,current).report_candidates(task,keyword))


@router.get("/tasks/{task_id}/reports/{attachment_id}")
async def task_report_file(task_id:str,attachment_id:str,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_execution",current.role)
    from app.services.inspection_execution_context_service import InspectionExecutionContextService
    from app.services.execution_evidence_service import ExecutionEvidenceService
    from app.core.exceptions import NotFoundError
    task=await InspectionExecutionService(db,current).task(task_id)
    link=next((l for l in (((task.meta_data or {}).get("execution_inputs") or {}).get("report_links",[])) if l["attachment_id"]==attachment_id),None)
    if not link:raise NotFoundError("报告未关联到本任务")
    context_service=InspectionExecutionContextService(db,current)
    await context_service.source_report(task,link,await context_service.scope(task))
    row,content,_=await ExecutionEvidenceService(db,current,review_owner=task.created_by,review_attachment_ids=[attachment_id]).file(attachment_id,pdf=True)
    from fastapi.responses import Response
    from urllib.parse import quote
    return Response(content,media_type="application/pdf",headers={"Content-Disposition":f"inline; filename*=UTF-8''{quote(row.file_name)}",
        "Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})


@router.post("/tasks/{task_id}/report-links",response_model=ResponseEnvelope[dict])
async def link_report(task_id:str,payload:TaskReportLink,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_execution",current.role)
    from app.services.inspection_execution_context_service import InspectionExecutionContextService
    task=await InspectionExecutionService(db,current).task(task_id,lock=True)
    return ResponseEnvelope(data=await InspectionExecutionContextService(db,current).link_report(task,payload.model_dump()))


@router.get("/runs/{run_id}/reports/{attachment_id}")
async def report_file(run_id:str,attachment_id:str,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_execution",current.role)
    row,content,_=await InspectionExecutionService(db,current).report_file(run_id,attachment_id)
    from fastapi.responses import Response
    from urllib.parse import quote
    return Response(content,media_type="application/pdf",headers={"Content-Disposition":f"inline; filename*=UTF-8''{quote(row.file_name)}",
        "Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})


@router.get("/requirements",response_model=ResponseEnvelope[list[dict]])
async def requirements(task_id:str,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_execution",current.role)
    await InspectionExecutionService(db,current).task(task_id)
    rows=(await db.execute(select(StandardDocumentRevision).join(StandardDocument,StandardDocument.published_revision_id==StandardDocumentRevision.id)
        .join(InspectionStandardLibrary,InspectionStandardLibrary.id==StandardDocument.library_id).where(StandardDocumentRevision.org_id==current.org_id,
            StandardDocumentRevision.review_status=="approved",StandardDocumentRevision.publication_status=="published",
            StandardDocument.org_id==current.org_id,InspectionStandardLibrary.org_id==current.org_id,
            StandardDocument.deleted_at.is_(None),InspectionStandardLibrary.deleted_at.is_(None),InspectionStandardLibrary.is_active.is_(True)))).scalars().all()
    return ResponseEnvelope(data=[{**c,"revision_id":r.id,"standard_no":r.snapshot["standard_no"],"product_category":r.snapshot.get("product_category")}
        for r in rows for c in r.candidates_json or [] if c.get("status")=="confirmed"])


@router.get("/policies",response_model=ResponseEnvelope[list[dict]])
async def policies(current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_spec_read",current.role)
    return ResponseEnvelope(data=await InspectionExecutionService(db,current).policies())


@router.post("/policies/{spec_id}/publish",response_model=ResponseEnvelope[dict])
async def publish_policy(spec_id:str,payload:PolicyPublish,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_spec",current.role)
    return ResponseEnvelope(data=await InspectionExecutionService(db,current).publish_policy(spec_id,payload.model_dump()))


@router.post("/policies/{policy_id}/withdraw",response_model=ResponseEnvelope[dict])
async def withdraw_policy(policy_id:str,payload:RevisionAction,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_spec",current.role)
    return ResponseEnvelope(data=await InspectionExecutionService(db,current).withdraw_policy(policy_id,payload.model_dump()))


@router.post("/runs",response_model=ResponseEnvelope[dict])
async def create(payload:InspectionExecutionCreate,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_execution",current.role)
    return ResponseEnvelope(data=await InspectionExecutionService(db,current).create(payload.model_dump()))


@router.get("/runs",response_model=ResponseEnvelope[list[dict]])
async def list_runs(task_id:str,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_execution",current.role)
    return ResponseEnvelope(data=await InspectionExecutionService(db,current).list(task_id))


@router.get("/runs/{run_id}",response_model=ResponseEnvelope[dict])
async def detail(run_id:str,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_execution",current.role)
    service=InspectionExecutionService(db,current)
    return ResponseEnvelope(data=await service.serialize(await service.get(run_id)))


@router.post("/runs/{run_id}/review",response_model=ResponseEnvelope[dict])
async def review(run_id:str,payload:InspectionExecutionReview,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_execution_review",current.role)
    return ResponseEnvelope(data=await InspectionExecutionService(db,current).review(run_id,payload.model_dump()))
