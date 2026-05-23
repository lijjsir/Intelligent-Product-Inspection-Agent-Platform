from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import ROLE_ADMIN, require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.rag_space import (
    RagDocumentResponse,
    RagNodeCreateRequest,
    RagNodeResponse,
    RagNodeUpdateRequest,
    RagSpaceCreateRequest,
    RagSpaceDocumentListItem,
    RagSpaceResponse,
    RagSpaceUpdateRequest,
)
from app.schemas.user import CurrentUser
from app.services.rag_space_service import RagSpaceService


router = APIRouter(prefix="/rag-spaces", tags=["rag-spaces"])


def _require_rag_space_access(current: CurrentUser) -> None:
    if current.role == ROLE_ADMIN:
        return
    require_role("chat", current.role)


def _owner_user_id(current: CurrentUser) -> str | None:
    return None if current.role == ROLE_ADMIN else current.user_id


@router.get("", response_model=ResponseEnvelope[list[RagSpaceResponse]])
async def list_rag_spaces(
    limit: int = Query(default=200, ge=1, le=500),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    return ResponseEnvelope(data=await service.list_spaces(limit=limit))


@router.get("/{rag_space_id}/tree", response_model=ResponseEnvelope[list[RagNodeResponse]])
async def get_rag_space_tree(
    rag_space_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    return ResponseEnvelope(data=await service.get_tree(rag_space_id=rag_space_id))


@router.get("/{rag_space_id}/documents", response_model=ResponseEnvelope[list[RagSpaceDocumentListItem]])
async def list_rag_documents(
    rag_space_id: str,
    limit: int = Query(default=1000, ge=1, le=5000),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    return ResponseEnvelope(data=await service.list_documents(rag_space_id=rag_space_id, limit=limit))


@router.post("", response_model=ResponseEnvelope[RagSpaceResponse])
async def create_rag_space(
    body: RagSpaceCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    return ResponseEnvelope(data=await service.create_space(name=body.name, description=body.description))


@router.patch("/{rag_space_id}", response_model=ResponseEnvelope[RagSpaceResponse])
async def update_rag_space(
    rag_space_id: str,
    body: RagSpaceUpdateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    return ResponseEnvelope(data=await service.update_space(rag_space_id=rag_space_id, name=body.name, description=body.description))


@router.post("/{rag_space_id}/nodes", response_model=ResponseEnvelope[RagNodeResponse])
async def create_rag_node(
    rag_space_id: str,
    body: RagNodeCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    return ResponseEnvelope(
        data=await service.create_node(
            rag_space_id=rag_space_id,
            parent_id=body.parent_id,
            node_type=body.node_type,
            name=body.name,
        )
    )


@router.patch("/{rag_space_id}/nodes/{node_id}", response_model=ResponseEnvelope[RagNodeResponse])
async def update_rag_node(
    rag_space_id: str,
    node_id: str,
    body: RagNodeUpdateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    return ResponseEnvelope(
        data=await service.update_node(
            rag_space_id=rag_space_id,
            node_id=node_id,
            parent_id=body.parent_id,
            name=body.name,
        )
    )


@router.post("/{rag_space_id}/nodes/{node_id}/documents", response_model=ResponseEnvelope[list[RagNodeResponse]])
async def upload_rag_documents_to_node(
    rag_space_id: str,
    node_id: str,
    files: list[UploadFile] = File(...),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    return ResponseEnvelope(data=await service.upload_documents(rag_space_id=rag_space_id, files=files, parent_node_id=node_id))


@router.post("/{rag_space_id}/documents", response_model=ResponseEnvelope[list[RagNodeResponse]])
async def upload_rag_documents(
    rag_space_id: str,
    files: list[UploadFile] = File(...),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    return ResponseEnvelope(data=await service.upload_documents(rag_space_id=rag_space_id, files=files, parent_node_id=None))


@router.delete("/{rag_space_id}/nodes/{node_id}", response_model=ResponseEnvelope[dict])
async def delete_rag_node(
    rag_space_id: str,
    node_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    await service.delete_node(rag_space_id=rag_space_id, node_id=node_id)
    return ResponseEnvelope(data={"deleted": True})


@router.delete("/{rag_space_id}", response_model=ResponseEnvelope[dict])
async def delete_rag_space(
    rag_space_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    await service.delete_space(rag_space_id=rag_space_id)
    return ResponseEnvelope(data={"deleted": True})


@router.delete("/{rag_space_id}/documents/{file_id}", response_model=ResponseEnvelope[dict])
async def delete_rag_document(
    rag_space_id: str,
    file_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _require_rag_space_access(current)
    service = RagSpaceService(db, org_id=current.org_id, user_id=_owner_user_id(current))
    await service.delete_document(rag_space_id=rag_space_id, file_id=file_id)
    return ResponseEnvelope(data={"deleted": True})
