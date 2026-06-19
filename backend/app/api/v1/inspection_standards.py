from fastapi import APIRouter, Depends, Query, status

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.inspection_standard_library import (
    InspectionStandardCreate,
    InspectionStandardResponse,
    InspectionStandardUpdate,
    PaginatedDocuments,
    PaginatedInspectionStandards,
    StandardDocumentChunkResponse,
    StandardDocumentResponse,
    StandardDocumentUpdate,
    StandardLibraryIndexResult,
    StandardLibraryScanResult,
    StandardRetrieveRequest,
    StandardRetrieveResponse,
)
from app.schemas.user import CurrentUser
from app.services.inspection_standard_library_service import InspectionStandardLibraryService

router = APIRouter()
standards_router = APIRouter()
standard_documents_router = APIRouter()


@router.get("", response_model=ResponseEnvelope[PaginatedInspectionStandards])
async def list_inspection_standards(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_items(page=page, size=size))


@router.get("/{library_id}", response_model=ResponseEnvelope[InspectionStandardResponse])
async def get_inspection_standard(
    library_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.get_item(library_id))


@router.post("", response_model=ResponseEnvelope[InspectionStandardResponse], status_code=status.HTTP_201_CREATED)
async def create_inspection_standard(
    payload: InspectionStandardCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.create_item(payload.model_dump()))


@router.patch("/{library_id}", response_model=ResponseEnvelope[InspectionStandardResponse])
async def update_inspection_standard(
    library_id: str,
    payload: InspectionStandardUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.update_item(library_id, payload.model_dump(exclude_unset=True)))


@router.delete("/{library_id}", response_model=ResponseEnvelope[dict[str, bool]])
async def delete_inspection_standard(
    library_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    await service.delete_item(library_id)
    return ResponseEnvelope(data={"success": True})


@router.post("/{library_id}/scan", response_model=ResponseEnvelope[StandardLibraryScanResult])
async def scan_inspection_standard(
    library_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.scan_library(library_id))


@router.post("/{library_id}/index", response_model=ResponseEnvelope[StandardLibraryIndexResult])
async def index_inspection_standard(
    library_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.index_library(library_id, reindex=False))


@router.post("/{library_id}/reindex", response_model=ResponseEnvelope[StandardLibraryIndexResult])
async def reindex_inspection_standard(
    library_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.index_library(library_id, reindex=True))


@router.get("/{library_id}/documents", response_model=ResponseEnvelope[PaginatedDocuments])
async def list_inspection_standard_documents(
    library_id: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_documents(library_id, page=page, size=size))


@standard_documents_router.get("/{document_id}", response_model=ResponseEnvelope[StandardDocumentResponse])
async def get_standard_document(
    document_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.get_document(document_id))


@standard_documents_router.patch("/{document_id}", response_model=ResponseEnvelope[StandardDocumentResponse])
async def update_standard_document(
    document_id: str,
    payload: StandardDocumentUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.update_document(document_id, payload.model_dump(exclude_unset=True)))


@standard_documents_router.delete("/{document_id}", response_model=ResponseEnvelope[dict[str, bool]])
async def delete_standard_document(
    document_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    await service.delete_document(document_id)
    return ResponseEnvelope(data={"success": True})


@standard_documents_router.post("/{document_id}/index", response_model=ResponseEnvelope[StandardLibraryIndexResult])
async def index_standard_document(
    document_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.index_document(document_id, reindex=False))


@standard_documents_router.post("/{document_id}/reindex", response_model=ResponseEnvelope[StandardLibraryIndexResult])
async def reindex_standard_document(
    document_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.index_document(document_id, reindex=True))


@standard_documents_router.get("/{document_id}/chunks", response_model=ResponseEnvelope[list[StandardDocumentChunkResponse]])
async def list_standard_document_chunks(
    document_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_chunks(document_id))


@standards_router.post("/retrieve", response_model=ResponseEnvelope[StandardRetrieveResponse])
async def retrieve_standards(
    payload: StandardRetrieveRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.retrieve(payload.model_dump()))
