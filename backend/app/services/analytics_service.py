from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.analytics_repo import AnalyticsRepository


class AnalyticsService:
    def __init__(self, session: AsyncSession, org_id: str | None):
        self._session = session
        self._org_id = org_id
        self._repo = AnalyticsRepository(session)

    async def overview(self, start_date=None, end_date=None) -> dict:
        return await self._repo.get_overview(self._org_id, start_date=start_date, end_date=end_date)

    async def product_line_drilldown(self, product_line: str, start_date=None, end_date=None, page: int = 1, size: int = 8) -> dict:
        return await self._repo.get_product_line_drilldown(
            self._org_id,
            product_line=product_line,
            start_date=start_date,
            end_date=end_date,
            page=page,
            size=size,
        )

    async def model_drilldown(self, model_key: str, start_date=None, end_date=None, page: int = 1, size: int = 8) -> dict:
        return await self._repo.get_model_drilldown(
            self._org_id,
            model_key=model_key,
            start_date=start_date,
            end_date=end_date,
            page=page,
            size=size,
        )

    async def task_drilldown(self, task_id: str) -> dict:
        stats = await self._repo.get_task_drilldown(self._org_id, task_id=task_id)
        if not stats:
            raise NotFoundError(f"Task {task_id} not found")
        return stats
