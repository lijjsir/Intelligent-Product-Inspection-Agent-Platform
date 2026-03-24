from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.result_repo import ResultRepository


class ResultService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = ResultRepository(session)

    async def get_by_task(self, task_id: str):
        return await self._repo.get_by_task(self._org_id, task_id)

    async def list_results(self, query):
        return await self._repo.list_paged(
            self._org_id,
            verdict=query.verdict,
            product_id=query.product_id,
            model_key=query.model_key,
            page=query.page,
            size=query.size,
        )
