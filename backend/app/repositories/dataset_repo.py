from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.dataset import Dataset, DatasetAsyncJob, DatasetSample, DatasetUploadSession


class DatasetRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, payload: dict) -> Dataset:
        obj = Dataset(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def list_for_owner(
        self,
        *,
        org_id: str,
        owner_user_id: str,
        page: int,
        size: int,
        keyword: str | None = None,
        modality: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Dataset], int]:
        conditions = [
            Dataset.org_id == org_id,
            Dataset.created_by == owner_user_id,
            Dataset.deleted_at.is_(None),
        ]
        if keyword:
            like = f"%{keyword.strip()}%"
            conditions.append(or_(Dataset.name.ilike(like), Dataset.description.ilike(like)))
        if modality:
            conditions.append(Dataset.modality == modality)
        if status:
            conditions.append(Dataset.status == status)

        total = int(
            await self._session.scalar(
                select(func.count(Dataset.id)).where(*conditions)
            )
            or 0
        )
        stmt = (
            select(Dataset)
            .where(*conditions)
            .order_by(Dataset.updated_at.desc(), Dataset.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def get(self, *, org_id: str, dataset_id: str, owner_user_id: str) -> Dataset | None:
        result = await self._session.execute(
            select(Dataset).where(
                Dataset.id == dataset_id,
                Dataset.org_id == org_id,
                Dataset.created_by == owner_user_id,
                Dataset.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        *,
        org_id: str,
        owner_user_id: str,
        name: str,
        exclude_dataset_id: str | None = None,
    ) -> Dataset | None:
        conditions = [
            Dataset.org_id == org_id,
            Dataset.created_by == owner_user_id,
            Dataset.name == name,
            Dataset.deleted_at.is_(None),
        ]
        if exclude_dataset_id:
            conditions.append(Dataset.id != exclude_dataset_id)
        result = await self._session.execute(select(Dataset).where(*conditions).limit(1))
        return result.scalar_one_or_none()

    async def get_deleted_by_name(
        self,
        *,
        org_id: str,
        owner_user_id: str,
        name: str,
        exclude_dataset_id: str | None = None,
    ) -> Dataset | None:
        conditions = [
            Dataset.org_id == org_id,
            Dataset.created_by == owner_user_id,
            Dataset.name == name,
            Dataset.deleted_at.is_not(None),
        ]
        if exclude_dataset_id:
            conditions.append(Dataset.id != exclude_dataset_id)
        result = await self._session.execute(
            select(Dataset)
            .where(*conditions)
            .order_by(Dataset.deleted_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save(self, obj: Dataset, payload: dict) -> Dataset:
        for key, value in payload.items():
            setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["updated_at"])
        return obj

    async def soft_delete(self, obj: Dataset) -> Dataset:
        obj.deleted_at = utcnow()
        obj.name = f"{obj.name}__deleted__{obj.id[:8]}"
        await self._session.flush()
        return obj

    async def recalculate_counters(self, *, dataset_id: str) -> Dataset | None:
        obj = await self._session.get(Dataset, dataset_id)
        if obj is None or obj.deleted_at is not None:
            return obj
        counts = await self._session.execute(
            select(
                func.count(DatasetSample.id).label("sample_count"),
                func.sum(func.if_(DatasetSample.sample_type == "image", 1, 0)).label("image_count"),
                func.sum(func.if_(DatasetSample.sample_type == "video", 1, 0)).label("video_count"),
                func.sum(func.if_(DatasetSample.sample_type == "text", 1, 0)).label("text_count"),
                func.coalesce(func.sum(DatasetSample.size_bytes), 0).label("uploaded_bytes"),
            ).where(
                DatasetSample.dataset_id == dataset_id,
                DatasetSample.deleted_at.is_(None),
            )
        )
        sample_count, image_count, video_count, text_count, uploaded_bytes = counts.one()
        obj.sample_count = int(sample_count or 0)
        obj.image_sample_count = int(image_count or 0)
        obj.video_sample_count = int(video_count or 0)
        obj.text_sample_count = int(text_count or 0)
        obj.uploaded_bytes = int(uploaded_bytes or 0)
        await self._session.flush()
        return obj


class DatasetSampleRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, payload: dict) -> DatasetSample:
        obj = DatasetSample(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def list_for_dataset(
        self,
        *,
        org_id: str,
        dataset_id: str,
        owner_user_id: str,
        page: int,
        size: int,
        sample_type: str | None = None,
    ) -> tuple[list[DatasetSample], int]:
        conditions = [
            DatasetSample.org_id == org_id,
            DatasetSample.dataset_id == dataset_id,
            DatasetSample.created_by == owner_user_id,
            DatasetSample.deleted_at.is_(None),
        ]
        if sample_type:
            conditions.append(DatasetSample.sample_type == sample_type)
        total = int(
            await self._session.scalar(
                select(func.count(DatasetSample.id)).where(*conditions)
            )
            or 0
        )
        stmt = (
            select(DatasetSample)
            .where(*conditions)
            .order_by(DatasetSample.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def get(self, *, org_id: str, dataset_id: str, sample_id: str, owner_user_id: str) -> DatasetSample | None:
        result = await self._session.execute(
            select(DatasetSample).where(
                DatasetSample.id == sample_id,
                DatasetSample.org_id == org_id,
                DatasetSample.dataset_id == dataset_id,
                DatasetSample.created_by == owner_user_id,
                DatasetSample.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_dataset_all(self, *, org_id: str, dataset_id: str, owner_user_id: str) -> list[DatasetSample]:
        result = await self._session.execute(
            select(DatasetSample).where(
                DatasetSample.org_id == org_id,
                DatasetSample.dataset_id == dataset_id,
                DatasetSample.created_by == owner_user_id,
                DatasetSample.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def soft_delete(self, obj: DatasetSample) -> DatasetSample:
        obj.deleted_at = utcnow()
        await self._session.flush()
        return obj

    async def soft_delete_many(self, *, dataset_id: str) -> None:
        result = await self._session.execute(
            select(DatasetSample).where(
                DatasetSample.dataset_id == dataset_id,
                DatasetSample.deleted_at.is_(None),
            )
        )
        for row in result.scalars().all():
            row.deleted_at = utcnow()
        await self._session.flush()


class DatasetAsyncJobRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, payload: dict) -> DatasetAsyncJob:
        obj = DatasetAsyncJob(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def list_recent_for_dataset(self, *, org_id: str, dataset_id: str, owner_user_id: str, limit: int = 10) -> list[DatasetAsyncJob]:
        result = await self._session.execute(
            select(DatasetAsyncJob).where(
                DatasetAsyncJob.org_id == org_id,
                DatasetAsyncJob.dataset_id == dataset_id,
                DatasetAsyncJob.created_by == owner_user_id,
                DatasetAsyncJob.deleted_at.is_(None),
            ).order_by(DatasetAsyncJob.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get(self, *, org_id: str, dataset_id: str, job_id: str, owner_user_id: str) -> DatasetAsyncJob | None:
        result = await self._session.execute(
            select(DatasetAsyncJob).where(
                DatasetAsyncJob.id == job_id,
                DatasetAsyncJob.org_id == org_id,
                DatasetAsyncJob.dataset_id == dataset_id,
                DatasetAsyncJob.created_by == owner_user_id,
                DatasetAsyncJob.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


class DatasetUploadSessionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, payload: dict) -> DatasetUploadSession:
        obj = DatasetUploadSession(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(self, *, org_id: str, dataset_id: str, session_id: str, owner_user_id: str) -> DatasetUploadSession | None:
        result = await self._session.execute(
            select(DatasetUploadSession).where(
                DatasetUploadSession.id == session_id,
                DatasetUploadSession.org_id == org_id,
                DatasetUploadSession.dataset_id == dataset_id,
                DatasetUploadSession.created_by == owner_user_id,
                DatasetUploadSession.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def save(self, obj: DatasetUploadSession, payload: dict) -> DatasetUploadSession:
        for key, value in payload.items():
            setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["updated_at"])
        return obj

    async def list_parts(self, obj: DatasetUploadSession) -> list[int]:
        raw = obj.uploaded_parts_json or []
        if isinstance(raw, dict):
            raw = raw.get("parts") or raw.get("uploaded_parts") or []
        return sorted({int(item) for item in raw if str(item).isdigit()})
