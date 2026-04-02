from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.rag_space import RagSpaceCreateRequest, RagSpaceFileResponse, RagSpaceResponse
from app.schemas.user import CurrentUser
from app.services.rag_space_service import RagSpaceService


router = APIRouter(prefix="/rag-spaces", tags=["rag-spaces"])


@router.get("", response_model=ResponseEnvelope[list[RagSpaceResponse]])
async def list_rag_spaces(
    limit: int = Query(default=200, ge=1, le=500),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("chat", current.role)
    service = RagSpaceService(db, org_id=current.org_id, user_id=current.user_id)
    return ResponseEnvelope(data=await service.list_spaces(limit=limit))


@router.get("/{rag_space_id}/documents", response_model=ResponseEnvelope[list[RagSpaceFileResponse]])
async def list_rag_documents(
    rag_space_id: str,
    limit: int = Query(default=1000, ge=1, le=5000),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("chat", current.role)
    service = RagSpaceService(db, org_id=current.org_id, user_id=current.user_id)
    return ResponseEnvelope(data=await service.list_documents(rag_space_id=rag_space_id, limit=limit))


@router.post("", response_model=ResponseEnvelope[RagSpaceResponse])
async def create_rag_space(
    body: RagSpaceCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("chat", current.role)
    service = RagSpaceService(db, org_id=current.org_id, user_id=current.user_id)
    return ResponseEnvelope(data=await service.create_space(name=body.name, description=body.description))


@router.post("/{rag_space_id}/documents", response_model=ResponseEnvelope[list[RagSpaceFileResponse]])
async def upload_rag_documents(
    rag_space_id: str,
    files: list[UploadFile] = File(...),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("chat", current.role)
    service = RagSpaceService(db, org_id=current.org_id, user_id=current.user_id)
    return ResponseEnvelope(data=await service.upload_documents(rag_space_id=rag_space_id, files=files))
