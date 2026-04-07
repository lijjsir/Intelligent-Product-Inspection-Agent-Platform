from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.billing_service import BillingService


class FakeLedgerRepo:
    def __init__(self, _session):
        self.aggregate_calls = []

    async def aggregate(self, org_id, granularity, start_date=None, end_date=None, model_key=None, product_line=None):
        self.aggregate_calls.append(
            {
                "org_id": org_id,
                "granularity": granularity,
                "start_date": start_date,
                "end_date": end_date,
                "model_key": model_key,
                "product_line": product_line,
            }
        )
        return (
            [
                SimpleNamespace(total_tokens=120, cost_amount=Decimal("1.2300")),
                SimpleNamespace(total_tokens=80, cost_amount=Decimal("0.7700")),
            ],
            [{"bucket": "2026-04-03", "total_tokens": 200, "total_cost": 2.0, "request_count": 2}],
        )


class FakeUserSummaryRepo:
    def __init__(self, _session):
        self.list_calls = []
        self.get_calls = []

    async def list_with_users(self, *, org_id=None):
        self.list_calls.append(org_id)
        return [
            {
                "user_id": "user-1",
                "org_id": "org-1",
                "username": "user",
                "role": "user",
                "total_prompt_tokens": 120,
                "total_completion_tokens": 80,
                "total_tokens": 200,
                "total_cost": 2.0,
                "request_count": 2,
                "last_ledger_at": datetime(2026, 4, 3, 9, 0, 0),
                "updated_at": datetime(2026, 4, 3, 9, 0, 0),
            }
        ]

    async def get_for_user(self, *, user_id, org_id=None):
        self.get_calls.append({"user_id": user_id, "org_id": org_id})
        if user_id == "missing":
            return None
        return SimpleNamespace(
            user_id=user_id,
            total_prompt_tokens=120,
            total_completion_tokens=80,
            total_tokens=200,
            total_cost=Decimal("2.0000"),
            request_count=2,
            last_ledger_at=datetime(2026, 4, 3, 9, 0, 0),
        )


class FakeQuery:
    granularity = "day"
    start_date = None
    end_date = None
    model_key = None
    product_line = None


@pytest.mark.asyncio
async def test_admin_summary_ignores_org_scope(monkeypatch):
    ledger_repo = FakeLedgerRepo(None)
    user_repo = FakeUserSummaryRepo(None)
    monkeypatch.setattr("app.services.billing_service.TokenLedgerRepository", lambda session: ledger_repo)
    monkeypatch.setattr("app.services.billing_service.UserTokenUsageSummaryRepository", lambda session: user_repo)

    service = BillingService(session=object(), org_id="org-1", actor_role="admin")
    data = await service.get_summary(FakeQuery())

    assert ledger_repo.aggregate_calls[0]["org_id"] is None
    assert user_repo.list_calls == [None]
    assert data["total_tokens"] == 200
    assert data["total_cost"] == 2.0
    assert data["user_summaries"][0]["username"] == "user"


@pytest.mark.asyncio
async def test_current_user_summary_returns_zero_when_missing(monkeypatch):
    monkeypatch.setattr("app.services.billing_service.TokenLedgerRepository", FakeLedgerRepo)
    monkeypatch.setattr("app.services.billing_service.UserTokenUsageSummaryRepository", FakeUserSummaryRepo)

    service = BillingService(session=object(), org_id="org-1", actor_role="user")
    data = await service.get_current_user_summary(user_id="missing")

    assert data == {
        "user_id": "missing",
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "request_count": 0,
        "last_ledger_at": None,
    }
