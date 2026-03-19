from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import InspectionTask
from app.repositories.task_repo import TaskRepository
from app.services.audit_service import AuditService


class TaskService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = TaskRepository(session)

    async def create_task(
        self, created_by: str, product_id: str, spec_id: str, image_urls: list[str], priority: int, metadata: dict | None
    ) -> InspectionTask:
        task = InspectionTask(
            org_id=self._org_id,
            created_by=created_by,
            product_id=product_id,
            spec_id=spec_id,
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
