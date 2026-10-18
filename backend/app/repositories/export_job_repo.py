from sqlalchemy import JSON, case, select, func, type_coerce, or_
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
        *,
        actor_id: str | None = None,
        task_id: str | None = None,
        risk_actor_id: str | None = None,
    ) -> tuple[int, list[ExportJob]]:
        stmt = select(ExportJob).where(ExportJob.org_id == org_id, ExportJob.deleted_at.is_(None))
        stmt = stmt.where(or_(ExportJob.report_type != 'risk_assessment', ExportJob.actor_id == risk_actor_id))
        if actor_id:
            stmt = stmt.where(ExportJob.actor_id == actor_id)
        if status:
            stmt = stmt.where(ExportJob.status == status)
        if report_type:
            stmt = stmt.where(ExportJob.report_type == report_type)
        if task_id:
            configured_task = case((func.json_valid(ExportJob.config_json) == 1,
                                    type_coerce(ExportJob.config_json, JSON)["task_id"].as_string()), else_=None)
            stmt = stmt.where(configured_task == task_id)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar() or 0
        # Immutable evidence bundles can be large: sort only job IDs, not their content.
        ids = list((await self._session.scalars(stmt.with_only_columns(ExportJob.id)
            .order_by(ExportJob.created_at.desc()).offset((page - 1) * size).limit(size))).all())
        rows = (await self._session.scalars(select(ExportJob).where(ExportJob.org_id == org_id,
            ExportJob.deleted_at.is_(None), ExportJob.id.in_(ids)))).all() if ids else []
        by_id = {row.id: row for row in rows}
        return total, [by_id[job_id] for job_id in ids if job_id in by_id]

    async def update_status(self, job_id: str, status: str, file_url: str | None = None, file_size: int | None = None, error_message: str | None = None, expires_at=None) -> ExportJob | None:
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
        if expires_at is not None:
            job.expires_at = expires_at
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
