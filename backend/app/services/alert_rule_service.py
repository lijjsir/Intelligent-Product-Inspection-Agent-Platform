from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.alert_rule_repo import AlertRuleRepository


class AlertRuleService:
    def __init__(self, session: AsyncSession, org_id: str | None):
        self._session = session
        self._org_id = org_id
        self._repo = AlertRuleRepository(session)

    async def get(self, rule_id: str):
        return await self._repo.get(self._org_id, rule_id)

    async def list_rules(self, skip: int = 0, limit: int = 20, severity: str | None = None, enabled: bool | None = None):
        return await self._repo.list_rules(self._org_id, skip, limit, severity, enabled)

    async def create_rule(self, payload: dict) -> dict:
        rule = await self._repo.create(payload)
        await self._session.commit()
        return rule

    async def update_rule(self, rule_id: str, payload: dict):
        existing = await self._repo.get(self._org_id, rule_id)
        if not existing:
            raise NotFoundError("Alert rule not found")
        payload.pop("org_id", None)
        await self._repo.update(self._org_id, rule_id, payload)
        await self._session.commit()
        return await self._repo.get(self._org_id, rule_id)

    async def delete_rule(self, rule_id: str):
        existing = await self._repo.get(self._org_id, rule_id)
        if not existing:
            raise NotFoundError("Alert rule not found")
        from app.repositories.alert_repo import AlertRepository
        alert_repo = AlertRepository(self._session)
        await alert_repo.nullify_rule_id(self._org_id, rule_id)
        deleted = await self._repo.delete(self._org_id, rule_id)
        await self._session.commit()
        return deleted
