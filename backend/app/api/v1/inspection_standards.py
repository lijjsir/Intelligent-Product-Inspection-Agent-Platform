from fastapi import APIRouter, Depends, File, Query, UploadFile, status, Response
from urllib.parse import quote
import asyncio

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
    StandardUploadResult,
)
from app.schemas.user import CurrentUser
from app.services.inspection_standard_library_service import InspectionStandardLibraryService
from app.services.standard_admission_service import StandardAdmissionService
from app.schemas.standard_admission import CandidateEdit, CandidateReview, ReviewAssignment, RevisionAction, RevisionMetadata, RevisionReview
from app.services.standard_review_service import StandardReviewService
from app.core.permissions import has_permission
from app.schemas.standard_applicability import StandardApplicabilityCheck

router = APIRouter()
standards_router = APIRouter()
standard_documents_router = APIRouter()


@standards_router.get("/review-queue", response_model=ResponseEnvelope[dict])
async def review_queue(scope: str="pending", keyword: str="", domain: str="", page: int=Query(1,ge=1), size: int=Query(30,ge=1,le=100),
                       current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("inspection_standard_library_read", current.role)
    return ResponseEnvelope(data=await StandardReviewService(db,current).queue(scope=scope,keyword=keyword,domain=domain,page=page,size=size))


@standards_router.get("/reviewers", response_model=ResponseEnvelope[list[dict]])
async def standard_reviewers(current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("standard_review_assign",current.role)
    return ResponseEnvelope(data=await StandardReviewService(db,current).reviewers())


@standard_documents_router.post("/{document_id}/revisions/{revision_id}/assignment", response_model=ResponseEnvelope[dict])
async def assign_standard_review(document_id: str, revision_id: str, payload: ReviewAssignment,
                                current: CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("inspection_standard_library_read",current.role)
    return ResponseEnvelope(data=await StandardReviewService(db,current).assign(document_id,revision_id,payload.model_dump()))


@standard_documents_router.post("/{document_id}/revisions/{revision_id}/candidate-review", response_model=ResponseEnvelope[dict])
async def review_standard_candidate(document_id: str, revision_id: str, payload: CandidateReview,
                                   current: CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("standard_admission_review",current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id,current.user_id).candidate_review(
        document_id,revision_id,payload.model_dump(),can_confirm=str(current.role)=="expert"))


@standard_documents_router.post("/{document_id}/revisions/{revision_id}/requirements-draft", response_model=ResponseEnvelope[dict])
async def draft_standard_requirements(document_id: str, revision_id: str, payload: RevisionAction,
                                      current: CurrentUser=Depends(get_current_user),db=Depends(get_db)):
    require_role("standard_admission_submit",current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id,current.user_id).draft_requirements(
        document_id,revision_id,payload.model_dump()))


@router.get("", response_model=ResponseEnvelope[PaginatedInspectionStandards])
async def list_inspection_standards(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library_read", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_items(page=page, size=size))


@router.get("/{library_id}", response_model=ResponseEnvelope[InspectionStandardResponse])
async def get_inspection_standard(
    library_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library_read", current.role)
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
    result = await service.update_item(library_id, payload.model_dump(exclude_unset=True))
    from app.services.supervision_service import SupervisionService
    await SupervisionService(db,current).invalidate_external(library_id)
    return ResponseEnvelope(data=result)


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


@router.post("/{library_id}/upload", response_model=ResponseEnvelope[StandardUploadResult])
async def upload_standard_pdfs(
    library_id: str,
    files: list[UploadFile] = File(...),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Receive immutable PDFs; parse candidates asynchronously, never auto-publish."""
    require_role("standard_admission_submit", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    uploaded_files: list[tuple[str, bytes, str | None]] = []
    if len(files)>20:
        from app.core.exceptions import ValidationError
        raise ValidationError("每次最多接收20份PDF")
    for f in files:
        content = await f.read(50*1024*1024+1)
        if len(content)>50*1024*1024:
            from app.core.exceptions import ValidationError
            raise ValidationError("单份PDF不超过50MB")
        uploaded_files.append((f.filename or "unknown.pdf", content, f.content_type))
    result = await StandardAdmissionService(db, current.org_id, current.user_id).receive(library_id, uploaded_files)
    return ResponseEnvelope(data=result)


@router.get("/{library_id}/documents", response_model=ResponseEnvelope[PaginatedDocuments])
async def list_inspection_standard_documents(
    library_id: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library_read", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_documents(library_id, page=page, size=size))


@standard_documents_router.get("/{document_id}", response_model=ResponseEnvelope[StandardDocumentResponse])
async def get_standard_document(
    document_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library_read", current.role)
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
    require_role("inspection_standard_library_read", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_chunks(document_id))


@standards_router.post("/retrieve", response_model=ResponseEnvelope[StandardRetrieveResponse])
async def retrieve_standards(
    payload: StandardRetrieveRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library_read", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.retrieve(payload.model_dump()))


@standards_router.get("/requirements", response_model=ResponseEnvelope[list[dict]])
async def requirements_overview(current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("inspection_standard_library_read",current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id).requirements())


@standard_documents_router.get("/{document_id}/revisions", response_model=ResponseEnvelope[list[dict]])
async def list_revisions(document_id: str, current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("inspection_standard_library_read", current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id).list_revisions(document_id))


@standard_documents_router.get("/{document_id}/revisions/{revision_id}", response_model=ResponseEnvelope[dict])
async def revision_detail(document_id: str, revision_id: str, current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("inspection_standard_library_read", current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id).detail(document_id,revision_id))


@standard_documents_router.get("/{document_id}/revisions/{revision_id}/file")
async def revision_file(document_id: str, revision_id: str, current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("inspection_standard_library_read", current.role)
    service=StandardAdmissionService(db,current.org_id)
    _,rev=await service.revision(document_id,revision_id)
    content=await asyncio.to_thread(service.read_original,rev)
    return Response(content,media_type="application/pdf",headers={"Content-Disposition":f"inline; filename*=UTF-8''{quote(rev.snapshot['file_name'])}"})


@standard_documents_router.get("/{document_id}/revisions/{revision_id}/pages/{page_number}/preview")
async def revision_page_preview(document_id: str, revision_id: str, page_number: int,
    current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("inspection_standard_library_read", current.role)
    service=StandardAdmissionService(db,current.org_id)
    _,rev=await service.revision(document_id,revision_id)
    content=await asyncio.to_thread(service.read_original,rev)
    from app.services.standard_pdf_reading_text import render_standard_page
    image=await asyncio.to_thread(render_standard_page,content,page_number)
    return Response(image,media_type='image/png',headers={'Cache-Control':'private, no-store'})


@standard_documents_router.post("/{document_id}/revisions", response_model=ResponseEnvelope[dict])
async def amend_revision(document_id: str, payload: RevisionMetadata, current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("standard_admission_submit", current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id,current.user_id).amend(document_id,payload.model_dump()))


@standard_documents_router.post("/{document_id}/revisions/{revision_id}/review", response_model=ResponseEnvelope[dict])
async def review_revision(document_id: str, revision_id: str, payload: RevisionReview, current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("standard_admission_review", current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id,current.user_id).review(document_id,revision_id,payload.model_dump(),actor_role=current.role))


@standard_documents_router.post("/{document_id}/revisions/{revision_id}/candidates", response_model=ResponseEnvelope[dict])
async def edit_candidate(document_id: str, revision_id: str, payload: CandidateEdit, current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("standard_admission_submit", current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id,current.user_id).candidate(document_id,revision_id,payload.model_dump(),
        can_confirm=str(current.role)=="expert" and has_permission("standard_admission_review",current.role),actor_role=current.role))


@standard_documents_router.post("/{document_id}/revisions/{revision_id}/publish", response_model=ResponseEnvelope[dict])
async def publish_revision(document_id: str, revision_id: str, payload: RevisionAction, current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("standard_admission_publish", current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id,current.user_id).publish(document_id,revision_id,payload.model_dump()))


@standard_documents_router.post("/{document_id}/revisions/{revision_id}/withdraw", response_model=ResponseEnvelope[dict])
async def withdraw_revision(document_id: str, revision_id: str, payload: RevisionAction, current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("standard_admission_publish", current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id,current.user_id).withdraw(document_id,revision_id,payload.model_dump()))


@standard_documents_router.post("/{document_id}/revisions/{revision_id}/retry", response_model=ResponseEnvelope[dict])
async def retry_revision(document_id: str, revision_id: str, payload: RevisionAction, current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("standard_admission_submit", current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id,current.user_id).retry(document_id,revision_id,payload.model_dump()))


@standard_documents_router.post("/{document_id}/revisions/{revision_id}/applicability", response_model=ResponseEnvelope[dict])
async def check_standard_applicability(document_id: str, revision_id: str, payload: StandardApplicabilityCheck,
    current: CurrentUser=Depends(get_current_user), db=Depends(get_db)):
    require_role("inspection_standard_library_read",current.role)
    return ResponseEnvelope(data=await StandardAdmissionService(db,current.org_id).check_applicability(document_id,revision_id,payload.model_dump()))
