import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.permissions import ROLE_ADMIN, ROLE_EXPERT, ROLE_USER
from app.models.task import InspectionTask
from app.repositories.alert_repo import AlertRepository
from app.repositories.inspection_standard_library_repo import InspectionStandardLibraryRepository
from app.repositories.inspection_spec_repo import InspectionSpecRepository
from app.repositories.organization_repo import OrganizationRepository
from app.repositories.product_master_repo import ProductMasterRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.stability_repo import StabilityRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.task_execution_event_repo import TaskExecutionEventRepository
from app.services.audit_service import AuditService
from app.services.product_master_service import ProductMasterService
from app.schemas.task import ImageItem


logger = logging.getLogger(__name__)


def _duplicate_image_item_groups(items: list[ImageItem]) -> list[list[ImageItem]]:
    groups: dict[str, list[ImageItem]] = {}
    for item in items:
        groups.setdefault(item.hash, []).append(item)
    return [group for group in groups.values() if len(group) > 1]


def _format_image_item_label(item: ImageItem) -> str:
    if item.sample_number is not None:
        return f"样品{item.sample_number}"
    return f"图片{item.index + 1}"


def _format_image_item_labels(items: list[ImageItem]) -> str:
    labels: list[str] = []
    for item in items:
        label = _format_image_item_label(item)
        if label not in labels:
            labels.append(label)
    return "、".join(labels)


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
        self._standard_repo = InspectionStandardLibraryRepository(session)
        self._product_repo = ProductMasterRepository(session)
        self._product_service = ProductMasterService(session, org_id)
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
        product_sku_id: str | None = None,
        batch_id: str | None = None,
        inspection_standard_id: str | None = None,
    ) -> InspectionTask:
        standard = None
        line = sku = batch = None
        normalized_product_id = str(product_id or "").strip()
        normalized_spec_code = str(spec_code or "").strip()

        if product_sku_id or batch_id or inspection_standard_id:
            if not product_sku_id or not batch_id or not inspection_standard_id:
                raise ValidationError("product_sku_id, batch_id and inspection_standard_id are required")
            line, sku, batch = await self._product_service.require_active_sku_and_batch(
                str(product_sku_id),
                str(batch_id),
            )
            standard = await self._standard_repo.get_active(self._org_id, str(inspection_standard_id))
            if not standard:
                raise ValidationError("inspection standard not found or inactive")
            self._ensure_standard_applicable(standard, line_id=str(line.id), sku_id=str(sku.id))
            normalized_product_id = str(sku.code)
            normalized_spec_code = str(getattr(standard, "spec_code", None) or normalized_spec_code or "").strip()
        else:
            # Legacy internal materialization path: keep chat/result backfills alive while
            # public task creation moves to the master-data closure.
            if not normalized_product_id:
                normalized_product_id = "unknown-product"
            line, sku, batch = await self._product_service.ensure_legacy_defaults(normalized_product_id)
            if normalized_spec_code:
                standard = await self._standard_repo.get_active_by_spec_code(self._org_id, normalized_spec_code)
            if standard is not None:
                inspection_standard_id = str(standard.id)
                normalized_spec_code = str(getattr(standard, "spec_code", None) or normalized_spec_code).strip()

        spec = await self._resolve_spec_from_standard(standard, normalized_spec_code)
        if standard is not None and not spec:
            raise ValidationError("selected inspection standard is missing a valid quality threshold binding")
        if spec and not normalized_spec_code:
            normalized_spec_code = str(spec.spec_code)
        if not normalized_spec_code:
            raise ValidationError("检测标准编码不能为空")
        if not spec:
            raise ValidationError(f"检测标准 {normalized_spec_code} 不存在或未启用")

        normalized_items = list(image_items or [ImageItem.from_url(i, url) for i, url in enumerate(image_urls)])
        if not normalized_items:
            raise ValidationError("请至少提供一张图片")

        duplicate_groups = _duplicate_image_item_groups(normalized_items)
        if duplicate_groups:
            duplicate_desc = "；".join(
                _format_image_item_labels(group) for group in duplicate_groups
            )
            raise ValidationError(f"检测到重复图片：{duplicate_desc}，请删除重复图片后重试")

        # Re-check hashes against recent tasks in this org to prevent cross-task duplicates.
        find_recent_image_hashes = getattr(self._repo, "find_recent_image_hashes", None)
        if callable(find_recent_image_hashes):
            try:
                existing_hashes = await find_recent_image_hashes(
                    self._org_id, [item.hash for item in normalized_items]
                )
            except Exception as exc:
                logger.warning(
                    "task image history duplicate check skipped: %s",
                    exc,
                    exc_info=True,
                )
                existing_hashes = set()
        else:
            existing_hashes = set()
        if existing_hashes:
            duplicate_items = [item for item in normalized_items if item.hash in existing_hashes]
            raise ValidationError(
                f"检测到重复图片：{_format_image_item_labels(duplicate_items)} 已在历史任务中上传，请更换后重试"
            )

        normalized_items = [
            ImageItem(
                index=i,
                url=item.url,
                hash=item.hash,
                sample_number=item.sample_number,
            )
            for i, item in enumerate(normalized_items)
        ]
        normalized_urls = [item.url for item in normalized_items]
        task_metadata = dict(metadata or {})
        task_metadata.update(
            {
                "product_line_id": str(line.id) if line else None,
                "product_line_code": str(line.code) if line else None,
                "product_line_name": str(line.name) if line else None,
                "product_sku_id": str(sku.id) if sku else str(product_sku_id or "") or None,
                "product_sku_code": str(sku.code) if sku else normalized_product_id,
                "product_sku_name": str(sku.name) if sku else None,
                "batch_id": str(batch.id) if batch else str(batch_id or "") or None,
                "batch_no": str(batch.batch_no) if batch else None,
                "batch_name": str(batch.name) if batch else None,
                "inspection_standard_id": str(standard.id) if standard else str(inspection_standard_id or "") or None,
                "inspection_standard_name": str(standard.name) if standard else None,
                "product_family": str(getattr(standard, "product_family", "") or getattr(spec, "product_family", "") or ""),
                "standard_rag_space_ids": list(getattr(standard, "rag_space_ids", None) or []),
                "system_rag_space_ids": list(getattr(standard, "rag_space_ids", None) or []),
                "spec_code": normalized_spec_code,
            }
        )

        task = InspectionTask(
            org_id=self._org_id,
            created_by=created_by,
            product_id=normalized_product_id,
            spec_code=normalized_spec_code,
            product_sku_id=str(sku.id) if sku else product_sku_id,
            batch_id=str(batch.id) if batch else batch_id,
            inspection_standard_id=str(standard.id) if standard else inspection_standard_id,
            image_urls=normalized_urls,
            image_items=[item.model_dump() for item in normalized_items],
            priority=priority,
            meta_data=task_metadata,
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

    async def _resolve_spec_from_standard(self, standard, spec_code: str):
        if standard is not None:
            standard_spec_id = str(getattr(standard, "inspection_spec_id", "") or "").strip()
            if standard_spec_id:
                spec = await self._spec_repo.get(self._org_id, standard_spec_id)
                if spec and bool(getattr(spec, "is_active", False)):
                    return spec
            standard_spec_code = str(getattr(standard, "spec_code", "") or spec_code).strip()
            if standard_spec_code:
                return await self._spec_repo.get_active_spec(self._org_id, standard_spec_code)
            return None
        return await self._spec_repo.get_active_spec(self._org_id, spec_code)

    @staticmethod
    def _ensure_standard_applicable(standard, *, line_id: str, sku_id: str) -> None:
        applicable_sku_ids = {str(item) for item in list(getattr(standard, "applicable_product_sku_ids", None) or [])}
        applicable_line_ids = {str(item) for item in list(getattr(standard, "applicable_product_line_ids", None) or [])}
        if applicable_sku_ids and sku_id not in applicable_sku_ids:
            raise ValidationError("inspection standard is not applicable to selected product SKU")
        if not applicable_sku_ids and applicable_line_ids and line_id not in applicable_line_ids:
            raise ValidationError("inspection standard is not applicable to selected product line")

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
            event_repo = TaskExecutionEventRepository(self._session)
            if not await event_repo.has_failed_event(self._task_scope_org_id, task_id):
                raise ValidationError("运行中的任务不能删除")
            metadata = dict(task.meta_data or {})
            metadata["execution"] = {
                **dict(metadata.get("execution") or {}),
                "error": metadata.get("execution", {}).get("error") or "任务事件流已失败，自动解除 running 状态以允许删除",
            }
            await self._repo.update_status(self._task_scope_org_id, task_id, "failed")
            await self._repo.patch_metadata(self._task_scope_org_id, task_id, metadata)

        result_repo = ResultRepository(self._session)
        stability_repo = StabilityRepository(self._session)
        alert_repo = AlertRepository(self._session)

        result = await result_repo.get_by_task(self._org_id, task_id)
        stability = await stability_repo.get_by_task(self._org_id, task_id)

        if result:
            await result_repo.soft_delete(str(result.id))
        if stability:
            await stability_repo.soft_delete(str(stability.id))
            alerts = await alert_repo.list_by_stability(self._org_id, str(stability.id))
            for alert in alerts:
                await alert_repo.soft_delete(self._org_id, str(alert.id))

        deleted = await self._repo.soft_delete(
            org_id=self._task_scope_org_id,
            task_id=task_id,
            owner_user_id=self._owner_user_id,
        )
        return deleted

    @property
    def _owner_user_id(self) -> str | None:
        if self._actor_role == ROLE_USER:
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
            await self._annotate_task_master_labels(task, meta)
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

    async def _annotate_task_master_labels(self, task: InspectionTask, meta: dict) -> None:
        product_line_code = meta.get("product_line_code")
        product_line_name = meta.get("product_line_name")
        product_sku_code = meta.get("product_sku_code") or meta.get("product_code")
        product_name = meta.get("product_sku_name") or meta.get("product_name")
        batch_no = meta.get("batch_no")
        standard_name = meta.get("inspection_standard_name") or meta.get("standard_name")

        sku_id = str(getattr(task, "product_sku_id", "") or "").strip()
        if sku_id and not (product_line_code and product_line_name and product_sku_code and product_name):
            sku = await self._product_repo.get_sku(str(task.org_id), sku_id)
            if sku:
                product_sku_code = product_sku_code or str(sku.code)
                product_name = product_name or str(sku.name)
                line = await self._product_repo.get_line(str(task.org_id), str(sku.product_line_id))
                if line:
                    product_line_code = product_line_code or str(line.code)
                    product_line_name = product_line_name or str(line.name)

        current_batch_id = str(getattr(task, "batch_id", "") or "").strip()
        if current_batch_id and not batch_no:
            batch = await self._product_repo.get_batch(str(task.org_id), current_batch_id)
            if batch:
                batch_no = str(batch.batch_no)

        current_standard_id = str(getattr(task, "inspection_standard_id", "") or "").strip()
        if current_standard_id and not standard_name:
            standard = await self._standard_repo.get(str(task.org_id), current_standard_id)
            if standard:
                standard_name = str(standard.name)

        setattr(task, "product_line_code", str(product_line_code or "") or None)
        setattr(task, "product_line_name", str(product_line_name or "") or None)
        setattr(task, "product_sku_code", str(product_sku_code or "") or None)
        setattr(task, "product_name", str(product_name or "") or None)
        setattr(task, "batch_no", str(batch_no or "") or None)
        setattr(task, "standard_name", str(standard_name or "") or None)
