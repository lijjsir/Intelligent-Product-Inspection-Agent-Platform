from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditOutbox
from app.core.ids import uuid7


class AuditService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def write_outbox(self, payload: dict) -> AuditOutbox:
        outbox = AuditOutbox(id=str(uuid7()), payload=payload, processed=False)
        self._session.add(outbox)
        await self._session.flush()
        return outbox
