from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.models.approval import Approval
from app.models.audit import AuditLog
from app.repositories.approval_repo import ApprovalRepository
from app.repositories.audit_repo import AuditRepository
from app.schemas.approval import ApprovalCreate


class ApprovalService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = ApprovalRepository(session)
        self._audit_repo = AuditRepository(session)

    async def list_approvals(
        self,
        page: int,
        size: int,
        status: str | None = None,
        source_module: str | None = None,
        risk_level: str | None = None,
        requester_id: str | None = None,
        current_role: str | None = None,
        current_user_id: str | None = None,
    ) -> tuple[list[Approval], int]:
        effective_requester_id = requester_id
        if current_role != "admin":
            effective_requester_id = current_user_id
        return await self._repo.list_approvals(
            org_id=self._org_id,
            page=page,
            size=size,
            status=status,
            source_module=source_module,
            risk_level=risk_level,
            requester_id=effective_requester_id,
        )

    async def get_approval(self, approval_id: str, current_role: str | None = None, current_user_id: str | None = None) -> Approval:
        approval = await self._repo.get_by_id(approval_id)
        if not approval or approval.org_id != self._org_id:
            raise NotFoundError("approval not found")
        if current_role != "admin" and approval.requester_id != current_user_id:
            raise ForbiddenError("approval not found")
        return approval

    async def create_approval(
        self,
        requester_id: str,
        requester_role: str,
        payload: ApprovalCreate,
    ) -> Approval:
        approval = Approval(
            id=str(uuid7()),
            org_id=self._org_id,
            source_module=payload.source_module.strip(),
            source_id=payload.source_id.strip() if payload.source_id else None,
            operation_summary=payload.operation_summary.strip(),
            risk_level=payload.risk_level,
            payload_json=payload.payload_json or {},
            requester_id=requester_id,
            requester_role=requester_role,
            status="pending",
        )
        return await self._repo.create(approval)

    async def approve(self, approval_id: str, reviewer_id: str, comment: str | None = None) -> Approval:
        approval = await self.get_approval(approval_id, current_role="admin", current_user_id=reviewer_id)
        self._ensure_pending(approval)
        approval.status = "approved"
        approval.reviewer_id = reviewer_id
        approval.review_comment = (comment or "").strip() or None
        approval.reviewed_at = datetime.now(timezone.utc)
        await self._repo.update(approval)

        # If memory governance approval, trigger rollback apply
        if approval.source_module == "memory_governance":
            try:
                from app.services.memory_governance_service import MemoryRollbackService
                rollback_svc = MemoryRollbackService(self._session, self._org_id)
                await rollback_svc.apply_rollback(approval.source_id)
            except Exception:
                pass
        elif approval.source_module == "agent_tool":
            await self._execute_agent_tool_approval(approval)

        await self._write_audit_log(approval, reviewer_id, "approve")
        return approval

    async def reject(self, approval_id: str, reviewer_id: str, comment: str | None = None) -> Approval:
        approval = await self.get_approval(approval_id, current_role="admin", current_user_id=reviewer_id)
        self._ensure_pending(approval)
        approval.status = "rejected"
        approval.reviewer_id = reviewer_id
        approval.review_comment = (comment or "").strip() or None
        approval.reviewed_at = datetime.now(timezone.utc)
        self._discard_agent_tool_arguments(approval)
        await self._repo.update(approval)
        await self._write_audit_log(approval, reviewer_id, "reject")
        return approval

    async def cancel(self, approval_id: str, requester_id: str) -> Approval:
        approval = await self.get_approval(approval_id, current_role="admin", current_user_id=requester_id)
        self._ensure_pending(approval)
        if approval.requester_id != requester_id:
            raise ForbiddenError("only requester can cancel approval")
        approval.status = "cancelled"
        approval.reviewed_at = datetime.now(timezone.utc)
        self._discard_agent_tool_arguments(approval)
        await self._repo.update(approval)
        return approval

    async def _execute_agent_tool_approval(self, approval: Approval) -> None:
        payload = dict(approval.payload_json or {})
        execution: dict = {"status": "failed", "error": "tool approval payload is invalid"}

        try:
            from agent.integrations.bk_aidev.approval_bridge import decrypt_tool_arguments
            from agent.tools import get_registry
            from agent.tools.contracts import ToolContext
            from agent.tools.invoker import ToolInvoker

            tool_name = str(payload.get("tool_name") or "").strip()
            encrypted_arguments = str(payload.get("arguments_encrypted") or "").strip()
            if not tool_name or not encrypted_arguments:
                raise ValidationError("tool approval payload is incomplete")

            arguments = decrypt_tool_arguments(encrypted_arguments)
            result = await ToolInvoker(get_registry(), db_session=self._session).invoke(
                tool_name=tool_name,
                arguments=arguments,
                context=ToolContext(
                    org_id=self._org_id,
                    request_id=str(payload.get("request_id") or approval.source_id or approval.id),
                    agent=str(payload.get("agent") or ""),
                    surface=str(payload.get("surface") or ""),
                    user_id=approval.requester_id,
                    workflow_run_id=str(payload.get("workflow_run_id") or "") or None,
                    session_id=str(payload.get("session_id") or "") or None,
                    trace_id=str(payload.get("trace_id") or "") or None,
                    allowed_modes=[str(item) for item in payload.get("allowed_modes") or []],
                    confirmed_actions=[tool_name],
                    metadata={
                        "approval_id": approval.id,
                        "requester_role": approval.requester_role,
                    },
                ),
            )
            execution = {
                "status": result.status,
                "data": result.data,
                "error": result.error,
                "execution_id": result.execution_id,
                "latency_ms": result.latency_ms,
            }
        except Exception as exc:
            execution = {"status": "failed", "error": str(exc)}

        payload.pop("arguments_encrypted", None)
        payload["execution"] = execution
        approval.payload_json = payload
        await self._repo.update(approval)

    @staticmethod
    def _discard_agent_tool_arguments(approval: Approval) -> None:
        if approval.source_module != "agent_tool":
            return
        payload = dict(approval.payload_json or {})
        payload.pop("arguments_encrypted", None)
        approval.payload_json = payload

    def _ensure_pending(self, approval: Approval) -> None:
        if approval.status != "pending":
            raise ValidationError("approval is not pending")

    async def _write_audit_log(self, approval: Approval, actor_id: str, action: str) -> None:
        audit = AuditLog(
            id=str(uuid7()),
            org_id=self._org_id,
            actor_id=actor_id,
            actor_role="admin",
            resource_type="approval",
            resource_id=approval.id,
            action=action,
            payload_hash=None,
            request_id=f"approval-{uuid.uuid4().hex[:12]}",
            ip_address=None,
            user_agent=None,
            result_code=200,
            occurred_at=datetime.now(timezone.utc),
        )
        await self._audit_repo.write(audit)
