from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.core.datetime import utcnow
from app.models.task import InspectionTask


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, task: InspectionTask) -> InspectionTask:
        self._session.add(task)
        await self._session.flush()
        await self._session.refresh(task, attribute_names=["created_at", "updated_at"])
        return task

    async def get(self, org_id: str | None, task_id: str) -> InspectionTask | None:
        stmt = select(InspectionTask).where(
            InspectionTask.id == task_id,
            InspectionTask.deleted_at.is_(None),
        )
        if org_id:
            stmt = stmt.where(InspectionTask.org_id == org_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_user(
        self,
        org_id: str | None,
        task_id: str,
        owner_user_id: str | None = None,
    ) -> InspectionTask | None:
        stmt = select(InspectionTask).where(
            InspectionTask.id == task_id,
            InspectionTask.deleted_at.is_(None),
        )
        if org_id:
            stmt = stmt.where(InspectionTask.org_id == org_id)
        if owner_user_id:
            stmt = stmt.where(InspectionTask.created_by == owner_user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(self, org_id: str, task_id: str, status: str) -> bool:
        values: dict = {"status": status}
        if status == "running":
            values["started_at"] = utcnow()
        if status in {"done", "failed"}:
            values["finished_at"] = utcnow()

        res = await self._session.execute(
            update(InspectionTask)
            .where(InspectionTask.org_id == org_id, InspectionTask.id == task_id)
            .values(**values)
        )
        return bool(res.rowcount and res.rowcount > 0)

    async def patch_metadata(self, org_id: str, task_id: str, patch: dict) -> bool:
        task = await self.get(org_id, task_id)
        if task is None:
            return False
        task.meta_data = {**dict(task.meta_data or {}), **patch}
        await self._session.flush()
        return True

    async def list_paged(
        self,
        org_id: str | None,
        filters: dict,
        page: int,
        size: int,
        owner_user_id: str | None = None,
    ) -> tuple[list[InspectionTask], int]:
        from sqlalchemy import func
        base = (
            select(InspectionTask)
            .options(
                load_only(
                    InspectionTask.id,
                    InspectionTask.org_id,
                    InspectionTask.product_id,
                    InspectionTask.spec_code,
                    InspectionTask.status,
                    InspectionTask.priority,
                    InspectionTask.meta_data,
                    InspectionTask.created_at,
                    InspectionTask.updated_at,
                )
            )
            .where(InspectionTask.deleted_at.is_(None))
        )
        if org_id:
            base = base.where(InspectionTask.org_id == org_id)
        if owner_user_id:
            base = base.where(InspectionTask.created_by == owner_user_id)
        base = base.where(
            InspectionTask.product_id != "chat_quality",
            InspectionTask.spec_code != "CHAT-QUALITY-QA",
        )
        if "status" in filters:
            base = base.where(InspectionTask.status == filters["status"])
        if "product_id" in filters:
            base = base.where(InspectionTask.product_id == filters["product_id"])
        if "ids" in filters and filters["ids"]:
            base = base.where(InspectionTask.id.in_(filters["ids"]))

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        
        items = await self._session.execute(
            base.order_by(InspectionTask.priority.desc(), InspectionTask.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(items.scalars().all()), int(total or 0)

    async def get_by_chat_materialization_key(
        self,
        org_id: str,
        workflow_run_id: str,
        assistant_message_id: str,
    ) -> InspectionTask | None:
        stmt = (
            select(InspectionTask)
            .where(
                InspectionTask.org_id == org_id,
                InspectionTask.deleted_at.is_(None),
                func.json_unquote(
                    func.json_extract(InspectionTask.meta_data, "$.workflow_run_id")
                )
                == workflow_run_id,
                func.json_unquote(
                    func.json_extract(InspectionTask.meta_data, "$.assistant_message_id")
                )
                == assistant_message_id,
            )
            .order_by(InspectionTask.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def find_recent_image_hashes(self, org_id: str, hashes: list[str]) -> set[str]:
        """Return the subset of `hashes` that already appear in recent (non-deleted) tasks."""
        if not hashes:
            return set()
        from sqlalchemy import text as sa_text
        hash_list = ", ".join(f":h{i}" for i in range(len(hashes)))
        params = {f"h{i}": h for i, h in enumerate(hashes)}
        params["org_id"] = org_id
        rows = await self._session.execute(
            sa_text(
                f"SELECT DISTINCT jt.hash_val FROM inspection_tasks AS t "
                f"CROSS JOIN JSON_TABLE(t.image_items, '$[*]' COLUMNS(hash_val VARCHAR(128) PATH '$.hash')) AS jt "
                f"WHERE t.org_id = :org_id AND t.deleted_at IS NULL AND jt.hash_val IN ({hash_list})"
            ),
            params,
        )
        return {row[0] for row in rows.fetchall()}

    async def soft_delete(
        self,
        org_id: str | None,
        task_id: str,
        owner_user_id: str | None = None,
    ) -> InspectionTask | None:
        obj = await self.get_for_user(org_id=org_id, task_id=task_id, owner_user_id=owner_user_id)
        if obj is None:
            return None
        obj.deleted_at = utcnow()
        await self._session.flush()
        return obj
