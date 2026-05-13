import pytest

from app.api.v1 import inspection_specs as specs_api
from app.core.exceptions import ForbiddenError
from app.schemas.user import CurrentUser


def current_user(role: str) -> CurrentUser:
    return CurrentUser(user_id=f"{role}-1", org_id="org-1", role=role, roles=[role])


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["user", "expert"])
async def test_user_and_expert_can_read_inspection_specs(monkeypatch, role):
    calls = []

    class FakeInspectionSpecService:
        def __init__(self, db, org_id):
            calls.append((db, org_id))

        async def list_specs(self):
            return [{"id": "spec-1", "org_id": "org-1", "spec_code": "STD-1"}]

    monkeypatch.setattr(specs_api, "InspectionSpecService", FakeInspectionSpecService)

    response = await specs_api.list_inspection_specs(current=current_user(role), db=object())

    assert response.data[0]["spec_code"] == "STD-1"
    assert calls[0][1] == "org-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["user", "expert"])
async def test_user_and_expert_cannot_write_inspection_specs(role):
    with pytest.raises(ForbiddenError):
        await specs_api.delete_inspection_spec("spec-1", current=current_user(role), db=object())
