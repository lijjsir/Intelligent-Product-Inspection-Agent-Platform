from sqlalchemy.ext.asyncio import AsyncSession


class TenantAwareService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
