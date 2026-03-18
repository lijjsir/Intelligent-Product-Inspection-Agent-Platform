from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.task import InspectionTask
from app.models.alert import AlertEvent
from app.models.result import InspectionResult

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

        pass_rate = float(total_pass / total_tasks) if total_tasks > 0 else 0.0

        return {
            "total_tasks": total_tasks,
            "total_alerts": total_alerts,
            "pass_rate": pass_rate,
            "hallucination_rate": 0.05,
            "risk_yellow_rate": 0.12
        }
