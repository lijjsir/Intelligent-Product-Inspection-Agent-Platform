from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export_job import ExportJob


class ExportJobRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, payload: dict) -> ExportJob:
        obj = ExportJob(**payload)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def get_by_id(self, job_id: str) -> ExportJob | None:
        result = await self._session.execute(
            select(ExportJob).where(ExportJob.id == job_id, ExportJob.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        org_id: str,
        page: int,
        size: int,
        status: str | None = None,
        report_type: str | None = None,
    ) -> tuple[int, list[ExportJob]]:
        stmt = select(ExportJob).where(ExportJob.org_id == org_id, ExportJob.deleted_at.is_(None))
        if status:
            stmt = stmt.where(ExportJob.status == status)
        if report_type:
            stmt = stmt.where(ExportJob.report_type == report_type)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(ExportJob.created_at.desc()).offset((page - 1) * size).limit(size)
        result = await self._session.execute(stmt)
        return total, list(result.scalars().all())

    async def update_status(self, job_id: str, status: str, file_url: str | None = None, file_size: int | None = None, error_message: str | None = None) -> ExportJob | None:
        job = await self.get_by_id(job_id)
        if not job:
            return None
        job.status = status
        if file_url:
            job.file_url = file_url
        if file_size is not None:
            job.file_size = file_size
        if error_message:
            job.error_message = error_message
        await self._session.flush()
        return job

    async def soft_delete(self, job_id: str) -> bool:
        from app.core.datetime import utcnow
        job = await self.get_by_id(job_id)
        if not job:
            return False
        job.deleted_at = utcnow()
        await self._session.flush()
        return True
