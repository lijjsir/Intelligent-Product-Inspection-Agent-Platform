from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def write(self, audit: AuditLog) -> AuditLog:
        self._session.add(audit)
        await self._session.flush()
        return audit
