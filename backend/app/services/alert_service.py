from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.core.exceptions import ValidationError, NotFoundError
from app.repositories.alert_repo import AlertRepository
from app.schemas.alert import AlertAction


# 状态机：允许的 (当前状态, 动作) 组合
_TRANSITIONS: dict[tuple[str, AlertAction], str] = {
    ("open", AlertAction.acknowledge): "acknowledged",
    ("open", AlertAction.suppress): "suppressed",
    ("open", AlertAction.resolve): "resolved",
    ("acknowledged", AlertAction.suppress): "suppressed",
    ("acknowledged", AlertAction.resolve): "resolved",
}


class AlertService:
    def __init__(self, session: AsyncSession, org_id: str | None):
        self._session = session
        self._org_id = org_id
        self._repo = AlertRepository(session)

    async def get(self, alert_id: str):
        return await self._repo.get(self._org_id, alert_id)

    async def list_alerts(self, skip: int = 0, limit: int = 20, status: str | None = None, severity: str | None = None):
        return await self._repo.list_alerts(self._org_id, skip, limit, status, severity)

    async def handle_alert(self, alert_id: str, action: AlertAction, user_id: str, action_note: str | None = None):
        alert = await self.get(alert_id)
        if not alert:
            raise NotFoundError("Alert not found")

        target_status = _TRANSITIONS.get((alert.status, action))
        if target_status is None:
            raise ValidationError(f"无法从 {alert.status} 执行 {action.value} 操作")

        now = utcnow()
        values: dict = {"status": target_status, "action_note": action_note}

        if action == AlertAction.acknowledge:
            values["ack_by"] = user_id
            values["ack_at"] = now
        elif action == AlertAction.suppress:
            values["suppressed_by"] = user_id
            values["suppressed_at"] = now
        elif action == AlertAction.resolve:
            values["resolved_by"] = user_id
            values["resolved_at"] = now

        await self._repo.handle_alert(self._org_id, alert_id, values)
        await self._session.commit()
        return await self.get(alert_id)

    async def resolve_alert(self, alert_id: str, user_id: str):
        """兼容旧 PUT /resolve 接口，内部转调 handle_alert"""
        return await self.handle_alert(alert_id, AlertAction.resolve, user_id)
