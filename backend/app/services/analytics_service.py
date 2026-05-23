from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.analytics_repo import AnalyticsRepository
from app.services.langfuse_api_client import LangfuseApiClient
from app.services.quality_report_service import QualityReportService


class AnalyticsService:
    def __init__(self, session: AsyncSession, org_id: str | None):
        self._session = session
        self._org_id = org_id
        self._repo = AnalyticsRepository(session)

    async def overview(self, start_date=None, end_date=None, product_lines: list[str] | None = None) -> dict:
        overview = await self._repo.get_overview(self._org_id, start_date=start_date, end_date=end_date, product_lines=product_lines)
        api_client = LangfuseApiClient()
        if not api_client.enabled:
            return overview

        quality_service = QualityReportService(self._session, self._org_id)
        traces, error = await quality_service._fetch_traces_from_langfuse(
            source="all",
            limit=1000,
            api_client=api_client,
            start_date=start_date,
            end_date=end_date,
        )
        quality = QualityReportService.build_overview_quality_from_trace_items([] if error else traces)
        for key in ("hallucination_rate", "hallucination_trend"):
            if quality.get(key):
                overview[key] = quality[key]
        if quality.get("model_metrics") and overview.get("model_metrics"):
            db_cost_map = {m["model_key"]: m.get("total_cost", 0.0) for m in overview["model_metrics"]}
            for m in quality["model_metrics"]:
                m["total_cost"] = db_cost_map.get(m["model_key"], m.get("total_cost", 0.0))
            overview["model_metrics"] = quality["model_metrics"]
        return overview

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
