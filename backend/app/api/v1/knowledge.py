from fastapi import APIRouter,Depends
from app.api.v1.deps import get_current_user,get_db
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.schemas.knowledge_admission import KnowledgeSubmit,KnowledgeReview,KnowledgeShare,KnowledgeAction,KnowledgePublish,SpaceShare,KnowledgeSourceRequest
from app.core.permissions import require_role
from app.core.exceptions import ForbiddenError,ValidationError
from app.services.knowledge_admission_service import KnowledgeAdmissionService
from app.services.knowledge_workspace_service import KnowledgeWorkspaceService
from app.schemas.task import TaskCreate
from app.services.material_task_service import MaterialTaskService
from app.schemas.inspection_standard_library import StandardRetrieveRequest

router=APIRouter(prefix="/knowledge",tags=["knowledge"])


@router.post("/search",response_model=ResponseEnvelope[dict])
async def grouped_search(payload:StandardRetrieveRequest,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_read",current.role)
    from app.services.knowledge_retrieval_service import KnowledgeRetrievalService
    return ResponseEnvelope(data=await KnowledgeRetrievalService(db,current).search(payload.query,payload.top_k))


@router.post("/materials/{record_id}/task-draft",response_model=ResponseEnvelope[dict])
async def material_task(record_id:str,payload:TaskCreate,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("task",current.role)
    if payload.image_urls or payload.image_items:raise ValidationError("材料任务使用原附件引用，无需再传图片")
    return ResponseEnvelope(data=await MaterialTaskService(db,current).draft(record_id,payload))


@router.get("/candidates",response_model=ResponseEnvelope[list[dict]])
async def candidates(current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_candidate_submit",current.role)
    return ResponseEnvelope(data=await KnowledgeAdmissionService(db,current).list())


@router.post("/candidates",response_model=ResponseEnvelope[dict])
async def submit(payload:KnowledgeSubmit,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_candidate_submit",current.role)
    return ResponseEnvelope(data=await KnowledgeAdmissionService(db,current).submit(payload.model_dump()))


@router.get("/published",response_model=ResponseEnvelope[list[dict]])
async def published(current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_read",current.role)
    return ResponseEnvelope(data=await KnowledgeAdmissionService(db,current).list(published=True))


@router.get("/candidates/{admission_id}",response_model=ResponseEnvelope[dict])
async def detail(admission_id:str,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_candidate_submit",current.role)
    service=KnowledgeAdmissionService(db,current)
    item=await service.get(admission_id)
    return ResponseEnvelope(data=await service.serialize(item,detail=True))


@router.post("/candidates/{admission_id}/review",response_model=ResponseEnvelope[dict])
async def review(admission_id:str,payload:KnowledgeReview,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_review",current.role)
    return ResponseEnvelope(data=await KnowledgeAdmissionService(db,current).review(admission_id,payload.model_dump()))


@router.post("/candidates/{admission_id}/sharing",response_model=ResponseEnvelope[dict])
async def sharing(admission_id:str,payload:KnowledgeShare,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_share_decide",current.role)
    return ResponseEnvelope(data=await KnowledgeAdmissionService(db,current).sharing(admission_id,payload.model_dump()))


@router.post("/candidates/{admission_id}/publish",response_model=ResponseEnvelope[dict])
async def publish(admission_id:str,payload:KnowledgePublish,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_publish",current.role)
    return ResponseEnvelope(data=await KnowledgeAdmissionService(db,current).publish(admission_id,payload.model_dump()))


@router.post("/candidates/{admission_id}/mapping-preview",response_model=ResponseEnvelope[dict])
async def mapping_preview(admission_id:str,payload:KnowledgePublish,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_candidate_submit",current.role)
    service=KnowledgeAdmissionService(db,current);item=await service.get(admission_id)
    return ResponseEnvelope(data=service.mapping(item,payload.model_dump()))


@router.post("/candidates/{admission_id}/withdraw",response_model=ResponseEnvelope[dict])
async def withdraw(admission_id:str,payload:KnowledgeAction,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_candidate_submit",current.role)
    return ResponseEnvelope(data=await KnowledgeAdmissionService(db,current).withdraw(admission_id,payload.model_dump()))


@router.post("/candidates/{admission_id}/retry",response_model=ResponseEnvelope[dict])
async def retry(admission_id:str,payload:KnowledgeAction,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_publish",current.role)
    return ResponseEnvelope(data=await KnowledgeAdmissionService(db,current).retry(admission_id,payload.model_dump()))


@router.post("/source-preview",response_model=ResponseEnvelope[dict])
async def source_preview(payload:KnowledgeSourceRequest,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_candidate_submit",current.role)
    return ResponseEnvelope(data=await KnowledgeAdmissionService(db,current).sources.resolve(payload.kind,payload.id,preview=True))


@router.get("/share-targets",response_model=ResponseEnvelope[list[dict]])
async def share_targets(current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_read",current.role)
    return ResponseEnvelope(data=await KnowledgeWorkspaceService(db,current).targets())


@router.get("/spaces/{space_id}/grants",response_model=ResponseEnvelope[list[dict]])
async def grants(space_id:str,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_read",current.role)
    return ResponseEnvelope(data=await KnowledgeWorkspaceService(db,current).grants(space_id))


@router.post("/spaces/{space_id}/share",response_model=ResponseEnvelope[list[dict]])
async def share(space_id:str,payload:SpaceShare,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_read",current.role)
    return ResponseEnvelope(data=await KnowledgeWorkspaceService(db,current).share(space_id,payload.model_dump()))


@router.post("/spaces/{space_id}/revoke",response_model=ResponseEnvelope[list[dict]])
async def revoke(space_id:str,payload:SpaceShare,current:CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("knowledge_read",current.role)
    return ResponseEnvelope(data=await KnowledgeWorkspaceService(db,current).share(space_id,payload.model_dump(),revoke=True))
