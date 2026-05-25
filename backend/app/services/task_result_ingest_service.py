from __future__ import annotations

import base64
import binascii
import hashlib
import json
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.dataset_modality import dataset_supports_sample_type
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import ROLE_ADMIN, ROLE_USER
from app.repositories.dataset_repo import DatasetAsyncJobRepository, DatasetRepository, DatasetSampleRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.task import TaskResultIngestRequest, TaskResultIngestResponse
from app.services.object_storage.factory import build_object_storage
from app.services.rag_space_service import RagSpaceService


@dataclass(slots=True)
class _TaskImageRef:
    index: int
    url: str
    image_hash: str
    sample_number: int | None = None


class TaskResultIngestService:
    def __init__(
        self,
        session,
        org_id: str,
        *,
        actor_user_id: str,
        actor_role: str,
    ) -> None:
        self._session = session
        self._org_id = org_id
        self._actor_user_id = actor_user_id
        self._actor_role = actor_role or ""
        self._tasks = TaskRepository(session)
        self._results = ResultRepository(session)
        self._stability = StabilityRepository(session)
        self._datasets = DatasetRepository(session)
        self._dataset_samples = DatasetSampleRepository(session)
        self._dataset_jobs = DatasetAsyncJobRepository(session)
        self._storage = build_object_storage()
        self._dataset_bucket = settings.dataset_storage_bucket

    async def ingest_task_result(self, *, task_id: str, payload: TaskResultIngestRequest) -> TaskResultIngestResponse:
        task_id = self._require_uuid(task_id, "task_id")
        task = await self._tasks.get_for_user(
            org_id=self._task_scope_org_id,
            task_id=task_id,
            owner_user_id=self._task_owner_user_id,
        )
        if task is None:
            raise NotFoundError(f"Task {task_id} not found")
        if str(getattr(task, "status", "") or "") != "done":
            raise ValidationError("only completed tasks can be ingested")

        result = await self._results.get_by_task(str(task.org_id), str(task.id))
        if result is None:
            raise ValidationError("task result not found")
        stability = await self._stability.get_by_task(str(task.org_id), str(task.id))

        created_document_count = 0
        created_sample_count = 0
        skipped_count = 0
        warnings: list[str] = []
        resolved_dataset_id: str | None = None
        resolved_dataset_name: str | None = None

        if payload.target in {"rag", "both"}:
            if not payload.rag_space_id:
                raise ValidationError("rag_space_id is required when target includes rag")
            rag_space_id = self._require_uuid(payload.rag_space_id, "rag_space_id")
            created, skipped, rag_warnings = await self._ingest_to_rag(
                task=task,
                result=result,
                stability=stability,
                rag_space_id=rag_space_id,
            )
            created_document_count += created
            skipped_count += skipped
            warnings.extend(rag_warnings)

        if payload.target in {"dataset", "both"}:
            if payload.mode != "candidate":
                raise ValidationError("only candidate mode is supported")
            resolved_dataset_id, resolved_dataset_name = await self._resolve_dataset_target(
                dataset_id=payload.dataset_id,
                dataset_name=payload.dataset_name,
            )
            created, skipped, dataset_warnings = await self._ingest_to_dataset_candidates(
                task=task,
                result=result,
                dataset_id=resolved_dataset_id,
            )
            created_sample_count += created
            skipped_count += skipped
            warnings.extend(dataset_warnings)

        return TaskResultIngestResponse(
            task_id=str(task.id),
            target=payload.target,
            mode=payload.mode,
            rag_space_id=payload.rag_space_id if payload.rag_space_id else None,
            dataset_id=resolved_dataset_id,
            dataset_name=resolved_dataset_name,
            created_document_count=created_document_count,
            created_sample_count=created_sample_count,
            skipped_count=skipped_count,
            warnings=warnings,
        )

    @staticmethod
    def _require_uuid(value: str, field_name: str) -> str:
        try:
            return str(uuid.UUID(str(value).strip()))
        except ValueError as exc:
            raise ValidationError(f"{field_name} must be a valid UUID") from exc

    async def _resolve_dataset_target(self, *, dataset_id: str | None, dataset_name: str | None) -> tuple[str, str]:
        normalized_name = str(dataset_name or "").strip()
        if normalized_name:
            dataset = await self._datasets.get_by_name(
                org_id=self._org_id,
                owner_user_id=self._actor_user_id,
                name=normalized_name,
            )
            if dataset is None:
                raise NotFoundError(f"dataset named {normalized_name} not found")
            return str(dataset.id), str(dataset.name)

        normalized_id = str(dataset_id or "").strip()
        if normalized_id:
            resolved_id = self._require_uuid(normalized_id, "dataset_id")
            dataset = await self._datasets.get(
                org_id=self._org_id,
                dataset_id=resolved_id,
                owner_user_id=self._actor_user_id,
            )
            if dataset is None:
                raise NotFoundError("dataset not found")
            return str(dataset.id), str(dataset.name)

        raise ValidationError("dataset_name is required when target includes dataset")

    async def _ingest_to_rag(self, *, task, result, stability, rag_space_id: str) -> tuple[int, int, list[str]]:
        service = RagSpaceService(
            self._session,
            org_id=self._org_id,
            user_id=self._rag_owner_user_id,
        )
        existing_docs = await service.list_documents(rag_space_id=rag_space_id, limit=5000)
        file_name = f"inspection-task-{task.id}.jsonl"
        if any(str(item.file_name) == file_name for item in existing_docs):
            return 0, 1, [f"RAG document already exists for task {task.id} in space {rag_space_id}"]

        records = self._build_rag_records(task=task, result=result, stability=stability)
        content = "\n".join(json.dumps(record, ensure_ascii=False) for record in records).encode("utf-8")
        await service.create_generated_document(
            rag_space_id=rag_space_id,
            file_name=file_name,
            content=content,
            content_type="application/x-ndjson",
        )
        return 1, 0, []

    async def _ingest_to_dataset_candidates(self, *, task, result, dataset_id: str) -> tuple[int, int, list[str]]:
        dataset = await self._datasets.get(
            org_id=self._org_id,
            dataset_id=dataset_id,
            owner_user_id=self._actor_user_id,
        )
        if dataset is None:
            raise NotFoundError("dataset not found")
        if str(getattr(dataset, "status", "") or "") != "active":
            raise ValidationError("dataset must be active")
        if not dataset_supports_sample_type(getattr(dataset, "modality", None), "image"):
            raise ValidationError(f"dataset modality {dataset.modality} does not support image samples")

        warnings: list[str] = []
        image_refs = self._extract_task_images(task)
        if not image_refs:
            return 0, 0, ["task has no image evidence to import into dataset candidates"]

        existing_rows = await self._dataset_samples.list_for_dataset_all(
            org_id=self._org_id,
            dataset_id=dataset_id,
            owner_user_id=self._actor_user_id,
        )
        existing_ingest_keys = {
            str((row.source_metadata or {}).get("ingest_key") or "")
            for row in existing_rows
            if isinstance(getattr(row, "source_metadata", None), dict)
        }

        defects_by_image, defects_warnings = self._group_defects_by_image(
            image_count=len(image_refs),
            defects=list(getattr(result, "defects", None) or []),
        )
        warnings.extend(defects_warnings)

        created = 0
        skipped = 0
        for image_ref in image_refs:
            ingest_key = f"result_import:{task.id}:{image_ref.image_hash or image_ref.index}"
            if ingest_key in existing_ingest_keys:
                skipped += 1
                continue

            image_defects = defects_by_image.get(image_ref.index, [])
            labels = sorted({str(item.get("type") or "unknown") for item in image_defects if str(item.get("type") or "").strip()})
            annotation_data = {
                "label": str(getattr(result, "verdict", "") or "unknown"),
                "verdict": str(getattr(result, "verdict", "") or "unknown"),
                "overall_score": float(getattr(result, "overall_score", 0.0) or 0.0),
                "product_id": str(getattr(task, "product_id", "") or ""),
                "spec_code": str(getattr(task, "spec_code", "") or ""),
                "labels": labels,
                "defects": image_defects,
            }
            source_metadata = {
                "source": "result_import",
                "ingest_status": "candidate_created",
                "review_status": "pending_review",
                "task_id": str(task.id),
                "result_id": str(result.id),
                "image_index": image_ref.index,
                "image_hash": image_ref.image_hash,
                "sample_number": image_ref.sample_number,
                "ingest_key": ingest_key,
            }
            sample_name = self._build_dataset_sample_name(task_id=str(task.id), image_ref=image_ref)
            media_payload = self._build_dataset_media_payload(
                task_id=str(task.id),
                dataset_id=dataset_id,
                image_ref=image_ref,
                sample_name=sample_name,
            )
            try:
                await self._dataset_samples.create(
                    {
                        "org_id": self._org_id,
                        "dataset_id": dataset_id,
                        "created_by": self._actor_user_id,
                        "sample_type": "image",
                        "sample_name": sample_name,
                        "annotation_data": annotation_data,
                        "quality_score": float(getattr(result, "overall_score", 0.0) or 0.0),
                        "related_entities": labels or None,
                        "source_metadata": source_metadata,
                        "preview_text": sample_name,
                        **media_payload,
                    }
                )
            except Exception:
                self._cleanup_dataset_media_payload(media_payload)
                raise
            existing_ingest_keys.add(ingest_key)
            created += 1

        if created > 0:
            await self._datasets.recalculate_counters(dataset_id=dataset_id)
        await self._dataset_jobs.create(
            {
                "org_id": self._org_id,
                "dataset_id": dataset_id,
                "created_by": self._actor_user_id,
                "job_type": "task_result_candidate_ingest",
                "status": "completed",
                "payload_json": {
                    "task_id": str(task.id),
                    "result_id": str(result.id),
                    "mode": "candidate",
                },
                "result_summary": {
                    "created": created,
                    "skipped": skipped,
                    "sample_type": "image",
                    "source": "result_import",
                    "warnings": warnings,
                },
            }
        )
        return created, skipped, warnings

    def _extract_task_images(self, task) -> list[_TaskImageRef]:
        image_urls = [str(item).strip() for item in list(getattr(task, "image_urls", None) or []) if str(item).strip()]
        item_rows = [item for item in list(getattr(task, "image_items", None) or []) if isinstance(item, dict)]
        refs: list[_TaskImageRef] = []
        for index, url in enumerate(image_urls):
            item = next((row for row in item_rows if int(row.get("index", -1)) == index), None)
            image_hash = str((item or {}).get("hash") or "").strip()
            if not image_hash:
                image_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
            sample_number = (item or {}).get("sample_number")
            refs.append(
                _TaskImageRef(
                    index=index,
                    url=url,
                    image_hash=image_hash,
                    sample_number=int(sample_number) if sample_number is not None else None,
                )
            )
        return refs

    def _group_defects_by_image(self, *, image_count: int, defects: list[dict[str, Any]]) -> tuple[dict[int, list[dict[str, Any]]], list[str]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        unassigned: list[dict[str, Any]] = []
        for raw in defects:
            if not isinstance(raw, dict):
                continue
            payload = {
                "type": str(raw.get("type") or "unknown"),
                "confidence": float(raw.get("confidence") or 0.0),
                "bbox": list(raw.get("bbox") or []) if isinstance(raw.get("bbox"), list) else [],
                "description": str(raw.get("description") or ""),
                "image_index": raw.get("image_index"),
            }
            image_index = raw.get("image_index")
            if isinstance(image_index, int) and 0 <= image_index < image_count:
                grouped.setdefault(image_index, []).append(payload)
                continue
            unassigned.append(payload)

        warnings: list[str] = []
        if unassigned:
            if image_count == 1:
                grouped.setdefault(0, []).extend(unassigned)
            elif image_count > 1:
                grouped.setdefault(0, []).extend(unassigned)
                warnings.append(
                    f"{len(unassigned)} defects missing image_index were attached to the first image sample"
                )
        return grouped, warnings

    def _build_rag_records(self, *, task, result, stability) -> list[dict[str, str]]:
        citations = []
        if isinstance(getattr(result, "citations", None), dict):
            citations = [item for item in list(result.citations.get("items") or []) if isinstance(item, dict)]
        defects = [item for item in list(getattr(result, "defects", None) or []) if isinstance(item, dict)]

        summary_text = (
            f"任务 {task.id} 的产品 {task.product_id} 按标准 {task.spec_code} 完成检测。"
            f"最终判定为 {result.verdict}，综合评分 {float(result.overall_score or 0.0):.4f}。"
        )
        if stability is not None:
            summary_text += (
                f" 风险等级 {stability.risk_level}，证据评分 {float(stability.evidence_score or 0.0):.4f}，"
                f"溯源评分 {float(stability.traceability_score or 0.0):.4f}。"
            )

        records: list[dict[str, str]] = [
            {
                "title": f"检测结论 {task.product_id}",
                "source": f"inspection-task://{task.id}/summary",
                "text": summary_text,
            }
        ]
        if defects:
            defect_lines = []
            for index, defect in enumerate(defects, start=1):
                bbox = defect.get("bbox") if isinstance(defect.get("bbox"), list) else []
                bbox_text = json.dumps(bbox, ensure_ascii=False) if bbox else "[]"
                image_index = defect.get("image_index")
                image_hint = f" 图像索引 {image_index}。" if image_index is not None else ""
                defect_lines.append(
                    f"缺陷 {index}：类型 {defect.get('type') or 'unknown'}，置信度 {float(defect.get('confidence') or 0.0):.4f}，"
                    f"框 {bbox_text}。{image_hint} {str(defect.get('description') or '').strip()}".strip()
                )
            records.append(
                {
                    "title": f"缺陷清单 {task.product_id}",
                    "source": f"inspection-task://{task.id}/defects",
                    "text": "\n".join(defect_lines),
                }
            )
        if citations:
            evidence_lines = []
            for index, citation in enumerate(citations[:8], start=1):
                quote = str(citation.get("quote") or "").strip()
                source = str(citation.get("source") or citation.get("title") or "unknown")
                evidence_lines.append(f"证据 {index}：来源 {source}。摘要 {quote}")
            records.append(
                {
                    "title": f"证据摘要 {task.product_id}",
                    "source": f"inspection-task://{task.id}/evidence",
                    "text": "\n".join(evidence_lines),
                }
            )
        return records

    @staticmethod
    def _build_dataset_sample_name(*, task_id: str, image_ref: _TaskImageRef) -> str:
        suffix = Path(image_ref.url.split("?", 1)[0]).suffix.lower()
        if not suffix and image_ref.url.startswith("data:"):
            content_type = TaskResultIngestService._content_type_from_data_url(image_ref.url)
            guessed = mimetypes.guess_extension(content_type or "")
            if guessed == ".jpe":
                guessed = ".jpg"
            suffix = (guessed or "").lower()
        if not suffix or len(suffix) > 10:
            suffix = ".img"
        return f"task-{task_id}-image-{image_ref.index + 1}{suffix}"

    def _build_dataset_media_payload(
        self,
        *,
        task_id: str,
        dataset_id: str,
        image_ref: _TaskImageRef,
        sample_name: str,
    ) -> dict[str, Any]:
        if image_ref.url.startswith("data:"):
            content, content_type = self._decode_data_url(image_ref.url)
            object_key = f"datasets/{self._org_id}/{dataset_id}/{image_ref.image_hash[:12]}-{sample_name}"
            self._storage.ensure_bucket(self._dataset_bucket)
            stored = self._storage.put_bytes(
                bucket=self._dataset_bucket,
                object_key=object_key,
                data=content,
                content_type=content_type or "application/octet-stream",
            )
            return {
                "text_content": None,
                "content_type": stored.get("content_type") or content_type or None,
                "size_bytes": int(stored.get("size_bytes") or len(content)),
                "checksum_sha256": image_ref.image_hash or hashlib.sha256(content).hexdigest(),
                "storage_backend": self._storage.backend_name,
                "bucket": stored.get("bucket") or self._dataset_bucket,
                "object_key": stored.get("object_key") or object_key,
                "file_url": stored.get("url"),
            }

        content_type, _ = mimetypes.guess_type(sample_name)
        return {
            "text_content": None,
            "content_type": content_type,
            "size_bytes": 0,
            "checksum_sha256": image_ref.image_hash,
            "storage_backend": "external_url",
            "bucket": None,
            "object_key": None,
            "file_url": image_ref.url,
        }

    def _cleanup_dataset_media_payload(self, payload: dict[str, Any]) -> None:
        if str(payload.get("storage_backend") or "") != self._storage.backend_name:
            return
        bucket = str(payload.get("bucket") or "")
        object_key = str(payload.get("object_key") or "")
        if bucket and object_key:
            self._storage.delete_object(bucket=bucket, object_key=object_key)

    @staticmethod
    def _content_type_from_data_url(url: str) -> str | None:
        header, _, _payload = str(url).partition(",")
        if not header.startswith("data:"):
            return None
        meta = header[5:]
        return (meta.split(";", 1)[0] or "application/octet-stream").strip() or "application/octet-stream"

    @classmethod
    def _decode_data_url(cls, url: str) -> tuple[bytes, str | None]:
        header, sep, payload = str(url).partition(",")
        if not sep or not header.startswith("data:") or ";base64" not in header:
            raise ValidationError("unsupported task image data URL")
        try:
            return base64.b64decode(payload, validate=True), cls._content_type_from_data_url(url)
        except (binascii.Error, ValueError) as exc:
            raise ValidationError("invalid task image data URL") from exc

    @property
    def _task_owner_user_id(self) -> str | None:
        if self._actor_role == ROLE_USER:
            return self._actor_user_id
        return None

    @property
    def _task_scope_org_id(self) -> str | None:
        if self._actor_role == ROLE_ADMIN:
            return None
        return self._org_id

    @property
    def _rag_owner_user_id(self) -> str | None:
        if self._actor_role == ROLE_ADMIN:
            return None
        return self._actor_user_id
