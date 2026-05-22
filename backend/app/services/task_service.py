from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.permissions import ROLE_ADMIN, ROLE_EXPERT, ROLE_USER
from app.models.task import InspectionTask
from app.repositories.alert_repo import AlertRepository
from app.repositories.inspection_spec_repo import InspectionSpecRepository
from app.repositories.organization_repo import OrganizationRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.chat_score_repo import ChatMessageScoreRepository
from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.services.audit_service import AuditService
from app.schemas.task import ImageItem


def _dedup_image_items(items: list[ImageItem]) -> list[ImageItem]:
    """Remove duplicate images by hash, keeping first occurrence."""
    seen: set[str] = set()
    result: list[ImageItem] = []
    for item in items:
        if item.hash not in seen:
            seen.add(item.hash)
            result.append(item)
    return result


class TaskService:
    def __init__(
        self,
        session: AsyncSession,
        org_id: str,
        *,
        actor_user_id: str | None = None,
        actor_role: str | None = None,
    ):
        self._session = session
        self._org_id = org_id
        self._actor_user_id = actor_user_id
        self._actor_role = actor_role or ""
        self._repo = TaskRepository(session)
        self._spec_repo = InspectionSpecRepository(session)
        self._org_repo = OrganizationRepository(session)
        self._result_repo = ResultRepository(session)
        self._stability_repo = StabilityRepository(session)

    async def create_task(
        self,
        created_by: str,
        product_id: str,
        spec_code: str,
        image_urls: list[str],
        priority: int,
        metadata: dict | None,
        image_items: list[ImageItem] | None = None,
    ) -> InspectionTask:
        normalized_spec_code = str(spec_code).strip()
        if not normalized_spec_code:
            raise ValidationError("检测标准编码不能为空")

        spec = await self._spec_repo.get_active_spec(self._org_id, normalized_spec_code)
        if not spec:
            raise ValidationError(f"检测标准 {normalized_spec_code} 不存在或未启用")

        # Build or normalize image_items with hash-based dedup.
        if image_items:
            deduped = _dedup_image_items(image_items)
            deduped_urls = [item.url for item in deduped]
        else:
            deduped = [ImageItem.from_url(i, url) for i, url in enumerate(image_urls)]
            deduped_urls = image_urls

        # Re-check hashes against recent tasks in this org to prevent cross-task duplicates.
        existing_hashes = await self._repo.find_recent_image_hashes(
            self._org_id, [item.hash for item in deduped]
        )
        if existing_hashes:
            deduped_items = [item for item in deduped if item.hash not in existing_hashes]
            deduped_urls = [item.url for item in deduped_items]
        else:
            deduped_items = deduped

        # Re-index remaining images sequentially.
        deduped_items = [
            ImageItem(index=i, url=item.url, hash=item.hash)
            for i, item in enumerate(deduped_items)
        ]
        deduped_urls = [item.url for item in deduped_items]

        task = InspectionTask(
            org_id=self._org_id,
            created_by=created_by,
            product_id=product_id,
            spec_code=normalized_spec_code,
            image_urls=deduped_urls,
            image_items=[item.model_dump() for item in deduped_items],
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
        task = await self._repo.get_for_user(
            self._task_scope_org_id,
            task_id,
            owner_user_id=self._owner_user_id,
        )
        await self._annotate_tasks([task] if task else [])
        return task

    async def list_tasks(self, query) -> tuple[list[InspectionTask], int]:
        items, total = await self._repo.list_paged(
            org_id=self._task_scope_org_id,
            filters=query.to_filters(),
            page=query.page,
            size=query.size,
            owner_user_id=self._owner_user_id,
        )
        await self._annotate_tasks(items)
        return items, total

    async def delete_task(self, task_id: str) -> InspectionTask | None:
        task = await self._repo.get_for_user(
            org_id=self._task_scope_org_id,
            task_id=task_id,
            owner_user_id=self._owner_user_id,
        )
        if task is None:
            return None
        if str(task.status) == "running":
            raise ValidationError("运行中的任务不能删除")

        # Cascade soft-delete related records.
        from app.repositories.chat_repo import ChatMessageRepository, ChatSessionRepository
        from sqlalchemy import text

        result_repo = ResultRepository(self._session)
        stability_repo = StabilityRepository(self._session)
        alert_repo = AlertRepository(self._session)
        chat_score_repo = ChatMessageScoreRepository(self._session)
        token_repo = TokenLedgerRepository(self._session)

        result = await result_repo.get_by_task(self._org_id, task_id)
        stability = await stability_repo.get_by_task(self._org_id, task_id)

        if result:
            await result_repo.soft_delete(str(result.id))
        if stability:
            await stability_repo.soft_delete(str(stability.id))
            # Also soft-delete alerts linked to this stability report.
            alerts = await alert_repo.list_by_stability(self._org_id, str(stability.id))
            for alert in alerts:
                await alert_repo.soft_delete(self._org_id, str(alert.id))
        # Soft-delete chat scores tied to this task.
        await self._session.execute(
            text(
                "UPDATE chat_message_scores SET deleted_at = NOW() "
                "WHERE task_id = :task_id AND deleted_at IS NULL"
            ),
            {"task_id": task_id},
        )

        deleted = await self._repo.soft_delete(
            org_id=self._task_scope_org_id,
            task_id=task_id,
            owner_user_id=self._owner_user_id,
        )
        return deleted

    @property
    def _owner_user_id(self) -> str | None:
        if self._actor_role in (ROLE_USER, ROLE_EXPERT):
            return self._actor_user_id
        return None

    @property
    def _task_scope_org_id(self) -> str | None:
        if self._actor_role == ROLE_ADMIN:
            return None
        return self._org_id

    async def _annotate_tasks(self, tasks: list[InspectionTask]) -> None:
        valid_tasks = [task for task in tasks if task is not None]
        if not valid_tasks:
            return

        org_map = {}
        if hasattr(self._session, "execute"):
            org_map = {
                str(item.id): item
                for item in await self._org_repo.list_by_ids(
                    list({str(task.org_id) for task in valid_tasks if task.org_id})
                )
            }
        for task in valid_tasks:
            meta = dict(getattr(task, "meta_data", None) or {})
            org = org_map.get(str(task.org_id))
            setattr(task, "org_slug", getattr(org, "slug", None))
            setattr(task, "source_kind", str(meta.get("source") or "unknown"))
            setattr(task, "source_graph", str(meta.get("source_graph") or meta.get("source_subgraph") or ""))
            execution = meta.get("execution") if isinstance(meta.get("execution"), dict) else None
            setattr(task, "execution", execution)
            try:
                result = await self._result_repo.get_by_task(str(task.org_id), str(task.id))
                stability = await self._stability_repo.get_by_task(str(task.org_id), str(task.id))
            except AttributeError:
                result = None
                stability = None
            setattr(task, "has_result", result is not None)
            setattr(task, "has_stability", stability is not None)
            setattr(task, "result_id", str(result.id) if result is not None else None)
            setattr(task, "stability_id", str(stability.id) if stability is not None else None)
