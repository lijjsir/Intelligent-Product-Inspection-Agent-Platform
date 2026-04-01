from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.task import InspectionTask
from app.repositories.inspection_spec_repo import InspectionSpecRepository
from app.repositories.task_repo import TaskRepository
from app.services.audit_service import AuditService


class TaskService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = TaskRepository(session)
        self._spec_repo = InspectionSpecRepository(session)

    async def create_task(
        self,
        created_by: str,
        product_id: str,
        spec_code: str,
        image_urls: list[str],
        priority: int,
        metadata: dict | None,
    ) -> InspectionTask:
        normalized_spec_code = str(spec_code).strip()
        if not normalized_spec_code:
            raise ValidationError("检测标准编码不能为空")

        spec = await self._spec_repo.get_active_spec(self._org_id, normalized_spec_code)
        if not spec:
            raise ValidationError(f"检测标准 {normalized_spec_code} 不存在或未启用")

        task = InspectionTask(
            org_id=self._org_id,
            created_by=created_by,
            product_id=product_id,
            spec_code=normalized_spec_code,
            image_urls=image_urls,
            priority=priority,
            meta_data=metadata,
            status="pending",
        )
        task = await self._repo.create(task)
        audit = AuditService(self._session)
        await audit.write_outbox(
            {
                "org_id": self._org_id,
                "actor_id": created_by,
                "resource_type": "task",
                "resource_id": str(task.id),
                "action": "create",
            }
        )
        refresh = getattr(self._session, "refresh", None)
        if callable(refresh):
            await refresh(task)
        return task

    async def get_task(self, task_id: str) -> InspectionTask | None:
        return await self._repo.get(self._org_id, task_id)

    async def list_tasks(self, query) -> tuple[list[InspectionTask], int]:
        return await self._repo.list_paged(
            org_id=self._org_id,
            filters=query.to_filters(),
            page=query.page,
            size=query.size,
        )
