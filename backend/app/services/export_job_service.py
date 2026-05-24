from __future__ import annotations

import json

from app.core.exceptions import NotFoundError
from app.core.ids import uuid7
from app.repositories.export_job_repo import ExportJobRepository
from app.services.base import TenantAwareService


class ExportJobService(TenantAwareService):
    def __init__(self, session, org_id: str):
        super().__init__(session, org_id)
        self._repo = ExportJobRepository(session)

    async def create_job(self, actor_id: str, payload: dict):
        from app.core.datetime import utcnow
        now = utcnow()
        config_json = payload.get("config_json")
        if isinstance(config_json, dict):
            config_json = json.dumps(config_json, ensure_ascii=False)
        job = await self._repo.create({
            "id": str(uuid7()),
            "org_id": self._org_id,
            "actor_id": actor_id,
            "report_name": payload["report_name"],
            "report_type": payload["report_type"],
            "format": payload.get("format", "pdf"),
            "template": payload.get("template", "standard"),
            "config_json": config_json,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        })

        import asyncio
        from worker.tasks.report_generate_task import generate_report_task

        task_payload = {"job_id": job.id, "org_id": self._org_id}
        try:
            generate_report_task.delay(task_payload)
        except Exception:
            from app.services.report_generation_service import generate_report as _run
            asyncio.create_task(_run(job_id=job.id, org_id=self._org_id))

        return job

    async def get_detail(self, job_id: str):
        job = await self._repo.get_by_id(job_id)
        if not job or job.org_id != self._org_id:
            raise NotFoundError("export job not found")
        return job

    async def list_jobs(self, page: int, size: int, status: str | None = None, report_type: str | None = None):
        return await self._repo.list_jobs(self._org_id, page, size, status, report_type)

    async def delete_job(self, job_id: str):
        deleted = await self._repo.soft_delete(job_id)
        if not deleted:
            raise NotFoundError("export job not found")
