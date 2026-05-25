import pytest

from app.services.alert_rule_service import AlertRuleService


class FakeSession:
    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True


class FakeRepo:
    def __init__(self):
        self.created_payload = None

    async def create(self, payload):
        self.created_payload = payload
        return payload


@pytest.mark.asyncio
async def test_create_rule_generates_uuid_when_missing():
    session = FakeSession()
    service = AlertRuleService(session, "org-1")
    repo = FakeRepo()
    service._repo = repo

    payload = {
        "org_id": "org-1",
        "name": "test",
        "alert_type": "quality_review",
        "severity": "warning",
        "enabled": True,
        "cooldown_seconds": 60,
    }

    result = await service.create_rule(payload)

    assert "id" in repo.created_payload
    assert isinstance(repo.created_payload["id"], str)
    assert len(repo.created_payload["id"]) == 36
    assert result["id"] == repo.created_payload["id"]
    assert session.committed is True
