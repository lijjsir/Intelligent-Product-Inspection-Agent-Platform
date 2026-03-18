from sqlalchemy.ext.asyncio import AsyncSession


class AnalyticsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_overview(self, org_id: str) -> dict:
        return {"pass_rate": 0.0, "hallucination_rate": 0.0, "risk_yellow_rate": 0.0}
