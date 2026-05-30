from __future__ import annotations

from datetime import datetime

from fastapi import Request
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.core.exceptions import ServiceUnavailableError
from app.models.auth_log import AuthLog
from app.repositories.auth_log_repo import AuthLogRepository

AUTH_LOGS_MISSING_MESSAGE = "登录日志尚未初始化，请先完成数据库迁移。"


def _is_auth_logs_table_missing(exc: Exception) -> bool:
    if not isinstance(exc, (ProgrammingError, OperationalError)):
        return False
    message = str(exc).lower()
    if "doesn't exist" not in message and "does not exist" not in message:
        return False
    return "auth_logs" in message


class AuthLogService:
    def __init__(self, session: AsyncSession):
        self._repo = AuthLogRepository(session)

    async def record_login(
        self,
        org_id: str,
        username: str,
        request: Request | None,
        success: bool,
        user_id: str | None = None,
        detail: str | None = None,
    ) -> AuthLog:
        log = AuthLog(
            id=str(uuid7()),
            org_id=org_id,
            user_id=user_id,
            username=username,
            event_type="login" if success else "login_failed",
            ip_address=self._get_ip_address(request),
            user_agent=self._get_user_agent(request),
            success=success,
            detail=detail,
        )
        try:
            return await self._repo.write(log)
        except Exception as exc:
            if _is_auth_logs_table_missing(exc):
                await self._rollback_repo_session()
                return log
            raise

    async def list_logs(
        self,
        org_id: str,
        page: int,
        size: int,
        user_id: str | None = None,
        event_type: str | None = None,
        ip_address: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        try:
            return await self._repo.list_logs(
                org_id=org_id,
                page=page,
                size=size,
                user_id=user_id,
                event_type=event_type,
                ip_address=ip_address,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            if _is_auth_logs_table_missing(exc):
                await self._rollback_repo_session()
                raise ServiceUnavailableError(AUTH_LOGS_MISSING_MESSAGE) from exc
            raise

    async def _rollback_repo_session(self) -> None:
        session = getattr(self._repo, "_session", None)
        rollback = getattr(session, "rollback", None)
        if callable(rollback):
            await rollback()

    @staticmethod
    def _get_ip_address(request: Request | None) -> str | None:
        if not request:
            return None
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return None

    @staticmethod
    def _get_user_agent(request: Request | None) -> str | None:
        if not request:
            return None
        return request.headers.get("User-Agent")
