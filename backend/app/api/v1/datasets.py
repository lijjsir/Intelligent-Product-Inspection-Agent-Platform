from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.dataset import (
    DatasetCreateRequest,
    DatasetDetailResponse,
    DatasetJobResponse,
    DatasetUploadCompleteRequest,
    DatasetUploadCompleteResponse,
    DatasetUploadInitRequest,
    DatasetUploadInitResponse,
    DatasetUploadPartResponse,
    DatasetSampleCreateRequest,
    DatasetSampleResponse,
    DatasetUpdateRequest,
)
from app.schemas.user import CurrentUser
from app.services.dataset_service import DatasetService


router = APIRouter()


@router.get("", response_model=ResponseEnvelope)
async def list_datasets(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    modality: str | None = Query(default=None),
    status_text: str | None = Query(default=None, alias="status"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    return ResponseEnvelope(
        data=await service.list_datasets(
            page=page,
            size=size,
            keyword=keyword,
            modality=modality,
            status=status_text,
        )
    )


@router.post("", response_model=ResponseEnvelope[DatasetDetailResponse], status_code=status.HTTP_201_CREATED)
async def create_dataset(
    payload: DatasetCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    data = await service.create_dataset(payload)
    await db.commit()
    return ResponseEnvelope(data=data)


@router.get("/{dataset_id}", response_model=ResponseEnvelope[DatasetDetailResponse])
async def get_dataset(
    dataset_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    return ResponseEnvelope(data=await service.get_dataset(dataset_id))


@router.patch("/{dataset_id}", response_model=ResponseEnvelope[DatasetDetailResponse])
async def update_dataset(
    dataset_id: str,
    payload: DatasetUpdateRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    data = await service.update_dataset(dataset_id, payload)
    await db.commit()
    return ResponseEnvelope(data=data)


@router.delete("/{dataset_id}", response_model=ResponseEnvelope[dict])
async def delete_dataset(
    dataset_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    await service.delete_dataset(dataset_id)
    await db.commit()
    return ResponseEnvelope(data={"deleted": True})


@router.get("/{dataset_id}/samples", response_model=ResponseEnvelope)
async def list_dataset_samples(
    dataset_id: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=24, ge=1, le=100),
    sample_type: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    return ResponseEnvelope(data=await service.list_samples(dataset_id=dataset_id, page=page, size=size, sample_type=sample_type))


@router.post("/{dataset_id}/samples/text", response_model=ResponseEnvelope[DatasetSampleResponse], status_code=status.HTTP_201_CREATED)
async def create_text_sample(
    dataset_id: str,
    payload: DatasetSampleCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    data = await service.create_text_sample(dataset_id=dataset_id, payload=payload)
    await db.commit()
    return ResponseEnvelope(data=data)


@router.post("/{dataset_id}/samples/images", response_model=ResponseEnvelope[list[DatasetSampleResponse]], status_code=status.HTTP_201_CREATED)
async def upload_image_samples(
    dataset_id: str,
    files: list[UploadFile] = File(...),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    data = await service.upload_image_samples(dataset_id=dataset_id, files=files)
    await db.commit()
    return ResponseEnvelope(data=data)


@router.post("/{dataset_id}/samples/videos", response_model=ResponseEnvelope[list[DatasetSampleResponse]], status_code=status.HTTP_201_CREATED)
async def upload_video_samples(
    dataset_id: str,
    files: list[UploadFile] = File(...),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    data = await service.upload_video_samples(dataset_id=dataset_id, files=files)
    await db.commit()
    return ResponseEnvelope(data=data)


@router.post("/{dataset_id}/upload/init", response_model=ResponseEnvelope[DatasetUploadInitResponse], status_code=status.HTTP_201_CREATED)
async def init_dataset_upload(
    dataset_id: str,
    payload: DatasetUploadInitRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    data = await service.init_upload_session(dataset_id=dataset_id, payload=payload)
    await db.commit()
    return ResponseEnvelope(data=data)


@router.put("/{dataset_id}/upload/{session_id}/parts/{part_number}", response_model=ResponseEnvelope[DatasetUploadPartResponse])
async def upload_dataset_part(
    dataset_id: str,
    session_id: str,
    part_number: int,
    chunk: bytes = File(...),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    data = await service.upload_part(dataset_id=dataset_id, session_id=session_id, part_number=part_number, content=chunk)
    await db.commit()
    return ResponseEnvelope(data=data)


@router.post("/{dataset_id}/upload/complete", response_model=ResponseEnvelope[DatasetUploadCompleteResponse], status_code=status.HTTP_201_CREATED)
async def complete_dataset_upload(
    dataset_id: str,
    payload: DatasetUploadCompleteRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    data = await service.complete_upload_session(dataset_id=dataset_id, payload=payload)
    await db.commit()
    return ResponseEnvelope(data=data)


@router.get("/{dataset_id}/jobs/{job_id}", response_model=ResponseEnvelope[DatasetJobResponse])
async def get_dataset_job(
    dataset_id: str,
    job_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    job = await service.get_job(dataset_id=dataset_id, job_id=job_id)
    return ResponseEnvelope(data=job)


@router.delete("/{dataset_id}/samples/{sample_id}", response_model=ResponseEnvelope[dict])
async def delete_dataset_sample(
    dataset_id: str,
    sample_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_role("dataset", current.role)
    service = DatasetService(db, current.org_id, current.user_id)
    await service.delete_sample(dataset_id=dataset_id, sample_id=sample_id)
    await db.commit()
    return ResponseEnvelope(data={"deleted": True})
