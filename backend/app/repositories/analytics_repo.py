from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.task import InspectionTask
from app.models.alert import AlertEvent
from app.models.result import InspectionResult
from app.models.stability import StabilityReport

class AnalyticsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_overview(self, org_id: str) -> dict:
        stmt_tasks = select(func.count()).where(InspectionTask.org_id == org_id)
        total_tasks = (await self._session.execute(stmt_tasks)).scalar_one()

        stmt_alerts = select(func.count()).where(AlertEvent.org_id == org_id, AlertEvent.status == 'open')
        total_alerts = (await self._session.execute(stmt_alerts)).scalar_one()

        stmt_pass = select(func.count()).where(InspectionResult.org_id == org_id, InspectionResult.verdict == 'pass')
        total_pass = (await self._session.execute(stmt_pass)).scalar_one()

        stmt_results = select(func.count()).where(InspectionResult.org_id == org_id)
        total_results = (await self._session.execute(stmt_results)).scalar_one()

        # "幻觉率"近似口径：缺少引证来源（citations 为空/空结构）的结果占比
        # 使用 Python 侧判定，避免不同 MySQL 版本 JSON 函数兼容问题导致接口失败。
        stmt_citations = select(InspectionResult.citations).where(InspectionResult.org_id == org_id)
        citations_rows = (await self._session.execute(stmt_citations)).scalars().all()
        hallucination_count = sum(1 for citations in citations_rows if self._is_empty_citations(citations))

        stmt_stability = select(func.count()).where(StabilityReport.org_id == org_id)
        total_stability = (await self._session.execute(stmt_stability)).scalar_one()

        # "置信告警率"口径：中风险（risk_level=medium）稳定性报告占比
        stmt_risk_yellow = select(func.count()).where(
            StabilityReport.org_id == org_id,
            StabilityReport.risk_level == "medium",
        )
        risk_yellow_count = (await self._session.execute(stmt_risk_yellow)).scalar_one()

        pass_rate = float(total_pass / total_tasks) if total_tasks > 0 else 0.0
        hallucination_rate = float(hallucination_count / total_results) if total_results > 0 else 0.0
        risk_yellow_rate = float(risk_yellow_count / total_stability) if total_stability > 0 else 0.0

        return {
            "total_tasks": total_tasks,
            "total_alerts": total_alerts,
            "pass_rate": pass_rate,
            "hallucination_rate": hallucination_rate,
            "risk_yellow_rate": risk_yellow_rate,
        }

    @staticmethod
    def _is_empty_citations(citations: object) -> bool:
        if citations is None:
            return True
        if isinstance(citations, (list, tuple, dict, set)):
            return len(citations) == 0
        text = str(citations).strip().lower()
        return text in {"", "null", "[]", "{}"}
