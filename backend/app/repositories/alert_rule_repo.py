from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_rule import AlertRule


class AlertRuleRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, org_id: str | None, rule_id: str) -> AlertRule | None:
        stmt = select(AlertRule).where(AlertRule.id == rule_id)
        if org_id:
            stmt = stmt.where(AlertRule.org_id == org_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, payload: dict) -> AlertRule:
        rule = AlertRule(**payload)
        self._session.add(rule)
        await self._session.flush()
        return rule

    async def list_rules(
        self,
        org_id: str | None,
        skip: int = 0,
        limit: int = 20,
        severity: str | None = None,
        enabled: bool | None = None,
    ):
        stmt = select(AlertRule)
        if org_id:
            stmt = stmt.where(AlertRule.org_id == org_id)
        if severity:
            stmt = stmt.where(AlertRule.severity == severity)
        if enabled is not None:
            stmt = stmt.where(AlertRule.enabled == enabled)

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total_res = await self._session.execute(total_stmt)
        total = total_res.scalar_one()

        stmt = stmt.order_by(AlertRule.created_at.desc()).offset(skip).limit(limit)
        items_res = await self._session.execute(stmt)
        items = items_res.scalars().all()
        return total, list(items)

    async def update(self, org_id: str | None, rule_id: str, values: dict) -> bool:
        stmt = update(AlertRule).where(AlertRule.id == rule_id)
        if org_id:
            stmt = stmt.where(AlertRule.org_id == org_id)
        stmt = stmt.values(**values)
        res = await self._session.execute(stmt)
        return res.rowcount > 0

    async def delete(self, org_id: str | None, rule_id: str) -> bool:
        stmt = delete(AlertRule).where(AlertRule.id == rule_id)
        if org_id:
            stmt = stmt.where(AlertRule.org_id == org_id)
        res = await self._session.execute(stmt)
        return res.rowcount > 0

    async def find_enabled_by_type(self, org_id: str, alert_type: str) -> list[AlertRule]:
        """Return all enabled rules for the given org and alert_type, ordered by severity desc."""
        stmt = (
            select(AlertRule)
            .where(
                AlertRule.org_id == org_id,
                AlertRule.alert_type == alert_type,
                AlertRule.enabled == True,
            )
            .order_by(AlertRule.severity.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
