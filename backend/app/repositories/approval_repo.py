from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval


class ApprovalRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, approval: Approval) -> Approval:
        self._session.add(approval)
        await self._session.flush()
        return approval

    async def get_by_id(self, approval_id: str) -> Approval | None:
        result = await self._session.execute(select(Approval).where(Approval.id == approval_id))
        return result.scalar_one_or_none()

    def _apply_filters(
        self,
        stmt,
        org_id: str,
        status: str | None = None,
        source_module: str | None = None,
        risk_level: str | None = None,
        requester_id: str | None = None,
    ):
        stmt = stmt.where(Approval.org_id == org_id)
        if status:
            stmt = stmt.where(Approval.status == status)
        if source_module:
            stmt = stmt.where(Approval.source_module == source_module)
        if risk_level:
            stmt = stmt.where(Approval.risk_level == risk_level)
        if requester_id:
            stmt = stmt.where(Approval.requester_id == requester_id)
        return stmt

    async def list_approvals(
        self,
        org_id: str,
        page: int,
        size: int,
        status: str | None = None,
        source_module: str | None = None,
        risk_level: str | None = None,
        requester_id: str | None = None,
    ) -> tuple[list[Approval], int]:
        offset = (page - 1) * size
        stmt = self._apply_filters(
            select(Approval),
            org_id=org_id,
            status=status,
            source_module=source_module,
            risk_level=risk_level,
            requester_id=requester_id,
        )
        result = await self._session.execute(
            stmt.order_by(Approval.created_at.desc()).offset(offset).limit(size)
        )
        count_stmt = self._apply_filters(
            select(func.count()).select_from(Approval),
            org_id=org_id,
            status=status,
            source_module=source_module,
            risk_level=risk_level,
            requester_id=requester_id,
        )
        count_result = await self._session.execute(count_stmt)
        return list(result.scalars().all()), int(count_result.scalar() or 0)

    async def update(self, approval: Approval) -> Approval:
        self._session.add(approval)
        await self._session.flush()
        return approval
