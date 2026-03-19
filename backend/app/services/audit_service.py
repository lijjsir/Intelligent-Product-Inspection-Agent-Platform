from __future__ import annotations

from datetime import date, datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditOutbox
from app.core.ids import uuid7


def _json_safe(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return value


class AuditService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def write_outbox(self, payload: dict) -> AuditOutbox:
        outbox = AuditOutbox(id=str(uuid7()), payload=_json_safe(payload), processed=False)
        self._session.add(outbox)
        await self._session.flush()
        return outbox
