from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.result import InspectionResult
from app.models.task import InspectionTask


class ResultRepository:
    def __init__(self, session: AsyncSession):
        """封装检测结果表的查询和按任务幂等写入操作。"""
        self._session = session

    async def get_by_task(self, org_id: str, task_id: str) -> InspectionResult | None:
        """按任务查询结果，供同任务重复执行时覆盖更新。"""
        result = await self._session.execute(
            select(InspectionResult).where(
                InspectionResult.org_id == org_id, InspectionResult.task_id == task_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, org_id: str, result_id: str) -> InspectionResult | None:
        """按结果 ID 查询单条检测结果。"""
        result = await self._session.execute(
            select(InspectionResult).where(
                InspectionResult.org_id == org_id, InspectionResult.id == result_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_range(self, org_id: str, start_date=None, end_date=None) -> list[InspectionResult]:
        """按时间范围查询结果列表，供统计分析场景使用。"""
        stmt = select(InspectionResult).where(InspectionResult.org_id == org_id)
        if start_date:
            stmt = stmt.where(InspectionResult.created_at >= __import__("datetime").datetime.combine(start_date, __import__("datetime").datetime.min.time()))
        if end_date:
            stmt = stmt.where(InspectionResult.created_at <= __import__("datetime").datetime.combine(end_date, __import__("datetime").datetime.max.time()))
        result = await self._session.execute(stmt.order_by(InspectionResult.created_at.asc()))
        return list(result.scalars().all())

    async def list_paged(
        self,
        org_id: str,
        *,
        verdict: str | None = None,
        product_id: str | None = None,
        model_key: str | None = None,
        task_id: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[tuple[InspectionResult, str]], int]:
        """联表任务信息后返回分页结果列表，支持 verdict、产品和模型等维度筛选。"""
        stmt = (
            select(InspectionResult, InspectionTask.product_id)
            .join(InspectionTask, InspectionTask.id == InspectionResult.task_id)
            .where(InspectionResult.org_id == org_id, InspectionTask.org_id == org_id)
        )
        if verdict:
            stmt = stmt.where(InspectionResult.verdict == verdict)
        if product_id:
            stmt = stmt.where(InspectionTask.product_id == product_id)
        if model_key:
            stmt = stmt.where(InspectionResult.llm_model == model_key)
        if task_id:
            stmt = stmt.where(InspectionResult.task_id == task_id)

        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.execute(
            stmt.order_by(InspectionResult.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(rows.all()), int(total or 0)

    async def upsert_by_task(self, payload: dict) -> InspectionResult:
        """按 task_id 幂等写入结果，存在则覆盖更新，不存在则创建。"""
        existing = await self.get_by_task(payload["org_id"], payload["task_id"])
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
            await self._session.flush()
            return existing

        obj = InspectionResult(**payload)
        self._session.add(obj)
        await self._session.flush()
        return obj
