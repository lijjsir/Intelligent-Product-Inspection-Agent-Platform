from types import SimpleNamespace

import pytest

from app.core.exceptions import ForbiddenError, ValidationError
from app.schemas.approval import ApprovalCreate
from app.schemas.memory import RollbackAction
from app.services.approval_service import ApprovalService
from app.services.memory_governance_service import MemoryRollbackService


class FakeApprovalRepo:
    def __init__(self):
        self.created = []
        self.items = {}

    async def create(self, approval):
        self.created.append(approval)
        self.items[approval.id] = approval
        return approval

    async def get_by_id(self, approval_id):
        return self.items.get(approval_id)

    async def list_approvals(self, **kwargs):
        requester_id = kwargs.get("requester_id")
        items = list(self.items.values())
        if requester_id:
            items = [item for item in items if item.requester_id == requester_id]
        return items, len(items)

    async def update(self, approval):
        self.items[approval.id] = approval
        return approval


class FakeAuditRepo:
    def __init__(self):
        self.records = []

    async def write(self, audit):
        self.records.append(audit)
        return audit


@pytest.mark.asyncio
async def test_approval_service_restricts_non_admin_to_own_items():
    service = ApprovalService(None, "org-1")
    repo = FakeApprovalRepo()
    service._repo = repo
    service._audit_repo = FakeAuditRepo()

    own = await service.create_approval("user-1", "platform_operator", ApprovalCreate(
        source_module="memory_governance",
        operation_summary="own",
    ))
    await service.create_approval("user-2", "app_developer", ApprovalCreate(
        source_module="memory_governance",
        operation_summary="other",
    ))

    items, total = await service.list_approvals(page=1, size=20, current_role="platform_operator", current_user_id="user-1")
    assert total == 1
    assert items[0].id == own.id

    with pytest.raises(ForbiddenError):
        await service.get_approval(list(repo.items.keys())[1], current_role="platform_operator", current_user_id="user-1")


@pytest.mark.asyncio
async def test_approval_service_rejects_repeated_review():
    service = ApprovalService(None, "org-1")
    repo = FakeApprovalRepo()
    audit_repo = FakeAuditRepo()
    service._repo = repo
    service._audit_repo = audit_repo

    approval = await service.create_approval("user-1", "platform_operator", ApprovalCreate(
        source_module="memory_governance",
        operation_summary="first",
    ))
    await service.approve(approval.id, "admin-1", "ok")

    with pytest.raises(ValidationError):
        await service.reject(approval.id, "admin-1", "again")

    assert len(audit_repo.records) == 1


@pytest.mark.asyncio
async def test_memory_rollback_service_creates_followup_approval_for_high_risk():
    service = MemoryRollbackService(None, "org-1", None)
    repo = FakeApprovalRepo()
    service._approval_repo = repo

    approval_id = await service._create_followup_approval(
        rollback_id="rb-1",
        root_memory_id="mem-root",
        operator_id="user-1",
        operator_role="platform_operator",
        workspace="governance",
        action=RollbackAction.DELETE,
        target_memory_ids=["m1", "m2"],
        reason="containment",
        propagation_graph={"nodes": 2},
        affected_count=2,
        require_human_review=False,
    )

    assert approval_id is not None
    assert repo.created[0].source_module == "memory_governance"
    assert repo.created[0].risk_level == "high"


@pytest.mark.asyncio
async def test_memory_rollback_service_skips_followup_approval_for_low_risk():
    service = MemoryRollbackService(None, "org-1", None)
    repo = FakeApprovalRepo()
    service._approval_repo = repo

    approval_id = await service._create_followup_approval(
        rollback_id="rb-1",
        root_memory_id="mem-root",
        operator_id="user-1",
        operator_role="platform_operator",
        workspace="governance",
        action=RollbackAction.DEGRADE,
        target_memory_ids=["m1"],
        reason="containment",
        propagation_graph=None,
        affected_count=1,
        require_human_review=False,
    )

    assert approval_id is None
    assert repo.created == []
