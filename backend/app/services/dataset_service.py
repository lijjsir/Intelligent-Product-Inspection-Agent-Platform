from __future__ import annotations

import asyncio
import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.core.config import settings
from app.core.datetime import utcnow, utcnow_iso
from app.core.exceptions import NotFoundError, ValidationError
from app.models.dataset import Dataset, DatasetSample
from app.repositories.dataset_repo import DatasetAsyncJobRepository, DatasetRepository, DatasetSampleRepository, DatasetUploadSessionRepository
from app.schemas.common import PagedResponse
from app.schemas.dataset import (
    AsyncJobResponse,
    DatasetUploadCompleteRequest,
    DatasetUploadCompleteResponse,
    DatasetUploadInitRequest,
    DatasetUploadInitResponse,
    DatasetUploadPartResponse,
    DatasetCreateRequest,
    DatasetDetailResponse,
    DatasetListItem,
    DatasetSampleCreateRequest,
    DatasetSampleResponse,
    DatasetUpdateRequest,
)
from app.services.base import TenantAwareService
from app.services.object_storage.factory import build_object_storage
from app.services.task_execution_service import has_active_celery_worker
from infra.database.session import get_session


ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/bmp",
}
TEXT_SIDECAR_EXTENSIONS = {".txt"}
ANNOTATION_SIDECAR_EXTENSIONS = {".json"}
IGNORED_TEXT_EXTENSIONS = {".txt", ".md", ".jsonl", ".json"}


class DatasetService(TenantAwareService):
    def __init__(self, session, org_id: str, user_id: str):
        super().__init__(session, org_id)
        self._user_id = user_id
        self._datasets = DatasetRepository(session)
        self._samples = DatasetSampleRepository(session)
        self._jobs = DatasetAsyncJobRepository(session)
        self._uploads = DatasetUploadSessionRepository(session)
        self._storage = build_object_storage()
        self._dataset_bucket = settings.dataset_storage_bucket

    async def list_datasets(
        self,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        modality: str | None = None,
        status: str | None = None,
    ) -> PagedResponse[DatasetListItem]:
        rows, total = await self._datasets.list_for_owner(
            org_id=self._org_id,
            owner_user_id=self._user_id,
            page=page,
            size=size,
            keyword=keyword,
            modality=modality,
            status=status,
        )
        return PagedResponse(
            items=[self._serialize_dataset_list_item(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def create_dataset(self, payload: DatasetCreateRequest) -> DatasetDetailResponse:
        body = payload.model_dump()
        body["name"] = body["name"].strip()
        body["description"] = (body.get("description") or "").strip() or None
        body["tags"] = [str(item).strip() for item in body.get("tags") or [] if str(item).strip()]
        body["org_id"] = self._org_id
        body["created_by"] = self._user_id
        created = await self._datasets.create(body)
        return await self._build_detail(created)

    async def get_dataset(self, dataset_id: str) -> DatasetDetailResponse:
        dataset = await self._require_dataset(dataset_id)
        return await self._build_detail(dataset)

    async def update_dataset(self, dataset_id: str, payload: DatasetUpdateRequest) -> DatasetDetailResponse:
        dataset = await self._require_dataset(dataset_id)
        updates = payload.model_dump(exclude_unset=True)
        if "name" in updates:
            updates["name"] = str(updates["name"]).strip()
        if "description" in updates:
            updates["description"] = (updates["description"] or "").strip() or None
        if "tags" in updates and updates["tags"] is not None:
            updates["tags"] = [str(item).strip() for item in updates["tags"] if str(item).strip()]
        await self._datasets.save(dataset, updates)
        return await self._build_detail(dataset)

    async def delete_dataset(self, dataset_id: str) -> None:
        dataset = await self._require_dataset(dataset_id)
        samples = await self._samples.list_for_dataset_all(
            org_id=self._org_id,
            dataset_id=dataset_id,
            owner_user_id=self._user_id,
        )
        for sample in samples:
            self._delete_sample_object(sample)
        await self._samples.soft_delete_many(dataset_id=dataset_id)
        await self._datasets.soft_delete(dataset)

    async def list_samples(
        self,
        *,
        dataset_id: str,
        page: int,
        size: int,
        sample_type: str | None = None,
    ) -> PagedResponse[DatasetSampleResponse]:
        await self._require_dataset(dataset_id)
        rows, total = await self._samples.list_for_dataset(
            org_id=self._org_id,
            dataset_id=dataset_id,
            owner_user_id=self._user_id,
            page=page,
            size=size,
            sample_type=sample_type,
        )
        return PagedResponse(
            items=[self._serialize_sample(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def create_text_sample(self, *, dataset_id: str, payload: DatasetSampleCreateRequest) -> DatasetSampleResponse:
        dataset = await self._require_dataset(dataset_id)
        self._ensure_dataset_supports(dataset, "text")
        text_content = payload.text_content.strip()
        if not text_content:
            raise ValidationError("text_content cannot be empty")
        preview = text_content[:200]
        created = await self._samples.create(
            {
                "org_id": self._org_id,
                "dataset_id": dataset_id,
                "created_by": self._user_id,
                "sample_type": "text",
                "sample_name": (payload.sample_name or "").strip() or None,
                "text_content": text_content,
                "content_type": "text/plain",
                "size_bytes": len(text_content.encode("utf-8")),
                "checksum_sha256": hashlib.sha256(text_content.encode("utf-8")).hexdigest(),
                "annotation_data": payload.annotation_data,
                "quality_score": payload.quality_score,
                "related_entities": payload.related_entities,
                "source_metadata": payload.source_metadata,
                "preview_text": preview,
            }
        )
        await self._datasets.recalculate_counters(dataset_id=dataset_id)
        await self._jobs.create(
            {
                "org_id": self._org_id,
                "dataset_id": dataset_id,
                "created_by": self._user_id,
                "job_type": "text_sample_ingest",
                "status": "completed",
                "payload_json": {"sample_id": created.id},
                "result_summary": {"created": 1, "sample_type": "text"},
            }
        )
        return self._serialize_sample(created)

    async def upload_image_samples(self, *, dataset_id: str, files: list[UploadFile]) -> list[DatasetSampleResponse]:
        dataset = await self._require_dataset(dataset_id)
        self._ensure_dataset_supports(dataset, "image")
        if not files:
            raise ValidationError("no files uploaded")

        created_rows: list[DatasetSample] = []
        total_bytes = 0
        for upload in files:
            raw_name = Path(upload.filename or "image.bin").name
            suffix = Path(raw_name).suffix.lower()
            if suffix not in ALLOWED_IMAGE_EXTENSIONS:
                raise ValidationError(f"unsupported image file: {raw_name}")
            content = await upload.read()
            if not content:
                raise ValidationError(f"empty image file: {raw_name}")
            content_type = upload.content_type or ""
            if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
                raise ValidationError(f"unsupported content type: {content_type}")

            checksum = hashlib.sha256(content).hexdigest()
            object_key = f"datasets/{self._org_id}/{dataset_id}/{checksum[:12]}-{raw_name}"
            self._storage.ensure_bucket(self._dataset_bucket)
            stored = self._storage.put_bytes(
                bucket=self._dataset_bucket,
                object_key=object_key,
                data=content,
                content_type=content_type or None,
            )
            try:
                created_rows.append(
                    await self._samples.create(
                        {
                            "org_id": self._org_id,
                            "dataset_id": dataset_id,
                            "created_by": self._user_id,
                            "sample_type": "image",
                            "sample_name": raw_name,
                            "text_content": None,
                            "content_type": stored.get("content_type") or content_type or None,
                            "size_bytes": int(stored.get("size_bytes") or len(content)),
                            "checksum_sha256": checksum,
                            "storage_backend": self._storage.backend_name,
                            "bucket": stored.get("bucket") or self._dataset_bucket,
                            "object_key": stored.get("object_key") or object_key,
                            "file_url": stored.get("url"),
                            "annotation_data": None,
                            "source_metadata": {"original_filename": raw_name},
                            "preview_text": raw_name,
                        }
                    )
                )
            except Exception:
                self._storage.delete_object(
                    bucket=stored.get("bucket") or self._dataset_bucket,
                    object_key=stored.get("object_key") or object_key,
                )
                raise
            total_bytes += len(content)

        await self._datasets.recalculate_counters(dataset_id=dataset_id)
        await self._jobs.create(
            {
                "org_id": self._org_id,
                "dataset_id": dataset_id,
                "created_by": self._user_id,
                "job_type": "image_batch_upload",
                "status": "completed",
                "payload_json": {"file_count": len(created_rows)},
                "result_summary": {"created": len(created_rows), "sample_type": "image", "uploaded_bytes": total_bytes},
            }
        )
        return [self._serialize_sample(row) for row in created_rows]

    async def init_upload_session(self, *, dataset_id: str, payload: DatasetUploadInitRequest) -> DatasetUploadInitResponse:
        dataset = await self._require_dataset(dataset_id)
        if Path(payload.file_name).suffix.lower() != ".zip":
            raise ValidationError("only zip uploads are supported")
        bucket = self._dataset_bucket
        self._storage.ensure_bucket(bucket)
        object_key = f"datasets/{self._org_id}/{dataset_id}/uploads/{hashlib.sha256(f'{payload.file_name}:{utcnow_iso()}'.encode()).hexdigest()[:16]}-{Path(payload.file_name).name}"
        expires_at = utcnow() + timedelta(hours=24)
        session_row = await self._uploads.create(
            {
                "org_id": self._org_id,
                "dataset_id": dataset_id,
                "created_by": self._user_id,
                "file_name": Path(payload.file_name).name,
                "content_type": payload.content_type or "application/zip",
                "file_size": payload.file_size,
                "chunk_size": payload.chunk_size,
                "total_chunks": payload.total_chunks,
                "bucket": bucket,
                "object_key": object_key,
                "uploaded_parts_json": [],
                "status": "pending",
                "expires_at": expires_at,
            }
        )
        return DatasetUploadInitResponse(
            session_id=session_row.id,
            bucket=bucket,
            object_key=object_key,
            chunk_size=payload.chunk_size,
            total_chunks=payload.total_chunks,
            expires_at=expires_at,
        )

    async def upload_part(
        self,
        *,
        dataset_id: str,
        session_id: str,
        part_number: int,
        content: bytes,
    ) -> DatasetUploadPartResponse:
        await self._require_dataset(dataset_id)
        upload = await self._uploads.get(
            org_id=self._org_id,
            dataset_id=dataset_id,
            session_id=session_id,
            owner_user_id=self._user_id,
        )
        if upload is None:
            raise NotFoundError("upload session not found")
        if upload.status not in {"pending", "uploading"}:
            raise ValidationError("upload session cannot accept more parts")
        if part_number < 1 or part_number > int(upload.total_chunks or 0):
            raise ValidationError("invalid part number")

        bucket = upload.bucket or self._dataset_bucket
        self._storage.ensure_bucket(bucket)
        raw_parts = upload.uploaded_parts_json or []
        uploaded_parts = sorted({int(item) for item in raw_parts if str(item).isdigit()})
        if part_number not in uploaded_parts:
            uploaded_parts.append(part_number)
        uploaded_parts.sort()
        part_key = f"{upload.object_key}.part-{part_number:05d}"
        self._storage.put_bytes(
            bucket=bucket,
            object_key=part_key,
            data=content,
            content_type=upload.content_type or "application/octet-stream",
        )
        await self._uploads.save(
            upload,
            {
                "status": "uploading",
                "uploaded_parts_json": uploaded_parts,
                "error_message": None,
            },
        )
        await self._commit()
        return DatasetUploadPartResponse(
            session_id=upload.id,
            part_number=part_number,
            uploaded_parts=uploaded_parts,
            uploaded_count=len(uploaded_parts),
        )

    async def complete_upload_session(self, *, dataset_id: str, payload: DatasetUploadCompleteRequest) -> DatasetUploadCompleteResponse:
        dataset = await self._require_dataset(dataset_id)
        upload = await self._uploads.get(
            org_id=self._org_id,
            dataset_id=dataset_id,
            session_id=payload.session_id,
            owner_user_id=self._user_id,
        )
        if upload is None:
            raise NotFoundError("upload session not found")
        bucket = upload.bucket or self._dataset_bucket
        object_key = upload.object_key or ""
        if not object_key:
            raise ValidationError("upload object key missing")
        expected_parts = set(range(1, int(upload.total_chunks or 0) + 1))
        provided_parts = set(int(item) for item in payload.uploaded_parts or [])
        stored_parts = set(await self._uploads.list_parts(upload))
        uploaded_parts = provided_parts or stored_parts
        if uploaded_parts != expected_parts:
            raise ValidationError("uploaded parts are incomplete")
        part_bytes: list[bytes] = []
        for part_number in sorted(expected_parts):
            stored = self._storage.get_bytes(bucket=bucket, object_key=f"{object_key}.part-{part_number:05d}")
            if stored is None:
                raise ValidationError(f"missing uploaded part {part_number}")
            part_bytes.append(stored[0])
        content = b"".join(part_bytes)
        if not zipfile.is_zipfile(io.BytesIO(content)):
            raise ValidationError("upload payload must be a zip archive")
        self._storage.put_bytes(
            bucket=bucket,
            object_key=object_key,
            data=content,
            content_type=upload.content_type or "application/zip",
        )
        await self._uploads.save(
            upload,
            {
                "status": "completed",
                "completed_at": utcnow(),
                "uploaded_parts_json": sorted(expected_parts),
            },
        )
        job = await self._jobs.create(
            {
                "org_id": self._org_id,
                "dataset_id": dataset_id,
                "created_by": self._user_id,
                "job_type": "data_import",
                "status": "queued",
                "payload_json": {"upload_session_id": upload.id, "bucket": upload.bucket, "object_key": upload.object_key},
                "result_summary": {"status": "queued", "warnings": []},
            }
        )
        await self._commit()
        if await self._resolve_execution_mode() == "celery":
            from worker.tasks.dataset_pipeline_task import run_dataset_import

            run_dataset_import.delay(
                {
                    "dataset_id": dataset_id,
                    "job_id": job.id,
                    "upload_session_id": upload.id,
                    "bucket": bucket,
                    "object_key": object_key,
                    "org_id": self._org_id,
                    "user_id": self._user_id,
                }
            )
        else:
            asyncio.create_task(
                self._run_data_import(
                    dataset_id=dataset_id,
                    job_id=job.id,
                    upload_session_id=upload.id,
                    bucket=bucket,
                    object_key=object_key,
                )
            )
        return DatasetUploadCompleteResponse(
            session_id=upload.id,
            job=AsyncJobResponse.model_validate(job),
            dataset=await self._build_detail(dataset),
        )

    async def _run_data_import(self, *, dataset_id: str, job_id: str, upload_session_id: str, bucket: str, object_key: str) -> None:
        await asyncio.sleep(0)
        async with get_session() as session:
            service = DatasetService(session, self._org_id, self._user_id)
            job = await service._jobs.get(
                org_id=self._org_id,
                dataset_id=dataset_id,
                job_id=job_id,
                owner_user_id=self._user_id,
            )
            upload = await service._uploads.get(
                org_id=self._org_id,
                dataset_id=dataset_id,
                session_id=upload_session_id,
                owner_user_id=self._user_id,
            )
            if job is None or upload is None:
                return
            job.status = "running"
            job.result_summary = {"status": "running", "warnings": []}
            upload.status = "running"
            await session.commit()

        warnings: list[str] = []
        created_sample_count = 0
        created_image_count = 0
        created_text_count = 0
        text_sidecar_attached = 0
        annotation_sidecar_attached = 0
        total_bytes = 0
        skipped_files = 0

        async with get_session() as session:
            service = DatasetService(session, self._org_id, self._user_id)
            job = await service._jobs.get(
                org_id=self._org_id,
                dataset_id=dataset_id,
                job_id=job_id,
                owner_user_id=self._user_id,
            )
            upload = await service._uploads.get(
                org_id=self._org_id,
                dataset_id=dataset_id,
                session_id=upload_session_id,
                owner_user_id=self._user_id,
            )
            if job is None or upload is None:
                return
            stored = service._storage.get_bytes(bucket=bucket, object_key=object_key)
            if stored is None:
                job.status = "failed"
                job.error_message = "uploaded archive not found"
                job.result_summary = {"status": "failed", "warnings": ["uploaded archive not found"]}
                upload.status = "failed"
                upload.error_message = "uploaded archive not found"
                await session.commit()
                return

            content, _ = stored
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    members = [info for info in archive.infolist() if not info.is_dir()]
                    image_entries: dict[str, tuple[Any, bytes]] = {}
                    sidecar_entries: list[Any] = []
                    for info in members:
                        filename = Path(info.filename).name
                        suffix = Path(filename).suffix.lower()
                        stem = Path(filename).stem
                        if suffix in ALLOWED_IMAGE_EXTENSIONS:
                            image_entries[stem] = (info, archive.read(info))
                            continue
                        sidecar_entries.append(info)

                    for stem, (info, sample_bytes) in image_entries.items():
                        filename = Path(info.filename).name
                        if not sample_bytes:
                            warnings.append(f"skipped empty image file: {info.filename}")
                            skipped_files += 1
                            continue
                        text_content = None
                        preview_text = filename
                        annotation_data = None
                        sidecar_text_filename = None
                        sidecar_annotation_filename = None
                        for sidecar in sidecar_entries:
                            sidecar_name = Path(sidecar.filename).name
                            sidecar_stem = Path(sidecar_name).stem
                            sidecar_suffix = Path(sidecar_name).suffix.lower()
                            if sidecar_stem != stem:
                                continue
                            raw_sidecar = archive.read(sidecar)
                            if sidecar_suffix in TEXT_SIDECAR_EXTENSIONS:
                                try:
                                    parsed_text = raw_sidecar.decode("utf-8").strip()
                                except UnicodeDecodeError:
                                    warnings.append(f"skipped invalid text sidecar: {sidecar.filename}")
                                    skipped_files += 1
                                    continue
                                if parsed_text:
                                    text_content = parsed_text
                                    preview_text = parsed_text[:200]
                                    sidecar_text_filename = sidecar.filename
                                    text_sidecar_attached += 1
                                continue
                            if sidecar_suffix in ANNOTATION_SIDECAR_EXTENSIONS:
                                try:
                                    parsed_annotation = json.loads(raw_sidecar.decode("utf-8"))
                                except (UnicodeDecodeError, json.JSONDecodeError):
                                    warnings.append(f"skipped invalid annotation sidecar: {sidecar.filename}")
                                    skipped_files += 1
                                    continue
                                if not isinstance(parsed_annotation, (dict, list)):
                                    warnings.append(f"skipped unsupported annotation sidecar payload: {sidecar.filename}")
                                    skipped_files += 1
                                    continue
                                annotation_data = parsed_annotation
                                sidecar_annotation_filename = sidecar.filename
                                annotation_sidecar_attached += 1

                        checksum = hashlib.sha256(sample_bytes).hexdigest()
                        object_key_item = f"datasets/{self._org_id}/{dataset_id}/{checksum[:12]}-{filename}"
                        service._storage.ensure_bucket(service._dataset_bucket)
                        stored_image = service._storage.put_bytes(
                            bucket=service._dataset_bucket,
                            object_key=object_key_item,
                            data=sample_bytes,
                            content_type="image/*",
                        )
                        await service._samples.create(
                            {
                                "org_id": self._org_id,
                                "dataset_id": dataset_id,
                                "created_by": self._user_id,
                                "sample_type": "image",
                                "sample_name": filename,
                                "text_content": text_content,
                                "content_type": stored_image.get("content_type") or "image/*",
                                "size_bytes": int(stored_image.get("size_bytes") or len(sample_bytes)),
                                "checksum_sha256": checksum,
                                "storage_backend": service._storage.backend_name,
                                "bucket": stored_image.get("bucket") or service._dataset_bucket,
                                "object_key": stored_image.get("object_key") or object_key_item,
                                "file_url": stored_image.get("url"),
                                "annotation_data": annotation_data,
                                "source_metadata": {
                                    "original_filename": info.filename,
                                    "upload_session_id": upload.id,
                                    "sidecar_text_filename": sidecar_text_filename,
                                    "sidecar_annotation_filename": sidecar_annotation_filename,
                                },
                                "preview_text": preview_text,
                            }
                        )
                        created_sample_count += 1
                        created_image_count += 1
                        total_bytes += len(sample_bytes)

                    for sidecar in sidecar_entries:
                        sidecar_name = Path(sidecar.filename).name
                        sidecar_suffix = Path(sidecar_name).suffix.lower()
                        sidecar_stem = Path(sidecar_name).stem
                        if sidecar_stem in image_entries:
                            continue
                        if sidecar_suffix in IGNORED_TEXT_EXTENSIONS:
                            warnings.append(f"skipped orphan sidecar file: {sidecar.filename}")
                            skipped_files += 1
                            continue
                        warnings.append(f"skipped unsupported file: {sidecar.filename}")
                        skipped_files += 1
                dataset = await service._datasets.get(org_id=self._org_id, dataset_id=dataset_id, owner_user_id=self._user_id)
                if dataset is None:
                    raise NotFoundError("dataset not found")
                await service._datasets.recalculate_counters(dataset_id=dataset_id)
                job.status = "completed"
                job.result_summary = {
                    "status": "completed",
                    "created_samples": created_sample_count,
                    "image_samples": created_image_count,
                    "text_samples": created_text_count,
                    "text_sidecar_attached": text_sidecar_attached,
                    "annotation_sidecar_attached": annotation_sidecar_attached,
                    "skipped_files": skipped_files,
                    "uploaded_bytes": total_bytes,
                    "warnings": warnings,
                }
                upload.status = "completed"
                upload.completed_at = utcnow()
                upload.error_message = None
            except zipfile.BadZipFile:
                job.status = "failed"
                job.error_message = "upload payload must be a zip archive"
                job.result_summary = {"status": "failed", "warnings": ["upload payload must be a zip archive"]}
                upload.status = "failed"
                upload.error_message = "upload payload must be a zip archive"
            except Exception as exc:
                job.status = "failed"
                job.error_message = str(exc)
                job.result_summary = {"status": "failed", "warnings": warnings + [str(exc)]}
                upload.status = "failed"
                upload.error_message = str(exc)
            await session.commit()

    async def delete_sample(self, *, dataset_id: str, sample_id: str) -> None:
        await self._require_dataset(dataset_id)
        sample = await self._samples.get(
            org_id=self._org_id,
            dataset_id=dataset_id,
            sample_id=sample_id,
            owner_user_id=self._user_id,
        )
        if sample is None:
            raise NotFoundError("dataset sample not found")
        self._delete_sample_object(sample)
        await self._samples.soft_delete(sample)
        await self._datasets.recalculate_counters(dataset_id=dataset_id)

    async def get_job(self, *, dataset_id: str, job_id: str) -> AsyncJobResponse:
        await self._require_dataset(dataset_id)
        job = await self._jobs.get(
            org_id=self._org_id,
            dataset_id=dataset_id,
            job_id=job_id,
            owner_user_id=self._user_id,
        )
        if job is None:
            raise NotFoundError("dataset job not found")
        return AsyncJobResponse.model_validate(job)

    async def _build_detail(self, dataset: Dataset) -> DatasetDetailResponse:
        jobs = await self._jobs.list_recent_for_dataset(
            org_id=self._org_id,
            dataset_id=dataset.id,
            owner_user_id=self._user_id,
            limit=10,
        )
        payload = self._serialize_dataset_list_item(dataset).model_dump()
        payload["recent_jobs"] = [AsyncJobResponse.model_validate(job) for job in jobs]
        return DatasetDetailResponse(**payload)

    async def _require_dataset(self, dataset_id: str) -> Dataset:
        dataset = await self._datasets.get(
            org_id=self._org_id,
            dataset_id=dataset_id,
            owner_user_id=self._user_id,
        )
        if dataset is None:
            raise NotFoundError("dataset not found")
        return dataset

    async def _commit(self) -> None:
        commit = getattr(self._session, "commit", None)
        if commit is None:
            return
        result = commit()
        if asyncio.iscoroutine(result):
            await result

    async def _resolve_execution_mode(self) -> str:
        result = has_active_celery_worker()
        if hasattr(result, "__await__"):
            result = await result
        return "celery" if result else "local_background"

    @staticmethod
    def _ensure_dataset_supports(dataset: Dataset, sample_type: str) -> None:
        modality = str(dataset.modality or "image_text")
        if modality == "image_text":
            return
        if modality != sample_type:
            raise ValidationError(f"dataset modality {modality} does not support {sample_type} samples")

    def _delete_sample_object(self, sample: DatasetSample) -> None:
        if sample.sample_type != "image":
            return
        bucket = sample.bucket or self._dataset_bucket
        object_key = sample.object_key or ""
        if not object_key:
            return
        self._storage.delete_object(bucket=bucket, object_key=object_key)

    @staticmethod
    def _serialize_dataset_list_item(row: Dataset) -> DatasetListItem:
        return DatasetListItem(
            id=row.id,
            org_id=row.org_id,
            created_by=row.created_by,
            name=row.name,
            description=row.description,
            modality=row.modality,
            tags=list(row.tags or []),
            status=row.status,
            sample_count=int(row.sample_count or 0),
            image_sample_count=int(row.image_sample_count or 0),
            text_sample_count=int(row.text_sample_count or 0),
            uploaded_bytes=int(row.uploaded_bytes or 0),
            knowledge_graph_status=row.knowledge_graph_status,
            alignment_status=row.alignment_status,
            augmentation_status=row.augmentation_status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _serialize_sample(self, row: DatasetSample) -> DatasetSampleResponse:
        payload = DatasetSampleResponse.model_validate(row).model_dump()
        download_url = None
        if row.bucket and row.object_key:
            download_url = self._storage.presign_download_url(bucket=row.bucket, object_key=row.object_key)
        payload["download_url"] = download_url
        return DatasetSampleResponse(**payload)


async def run_dataset_import_pipeline(
    *,
    dataset_id: str,
    job_id: str,
    upload_session_id: str,
    bucket: str,
    object_key: str,
    org_id: str,
    user_id: str,
) -> dict[str, str]:
    async with get_session() as session:
        service = DatasetService(session, org_id, user_id)
        await service._run_data_import(
            dataset_id=dataset_id,
            job_id=job_id,
            upload_session_id=upload_session_id,
            bucket=bucket,
            object_key=object_key,
        )
    return {"status": "ok"}
