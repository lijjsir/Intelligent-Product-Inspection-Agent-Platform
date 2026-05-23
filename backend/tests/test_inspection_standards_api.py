import pytest

from app.api.v1 import inspection_standards as standards_api
from app.core.exceptions import ForbiddenError
from app.schemas.user import CurrentUser


def current_user(role: str) -> CurrentUser:
    return CurrentUser(user_id=f"{role}-1", org_id="org-1", role=role, roles=[role])


@pytest.mark.asyncio
async def test_admin_can_list_inspection_standards(monkeypatch):
    class FakeService:
        def __init__(self, db, org_id):
            self.db = db
            self.org_id = org_id

        async def list_items(self):
            return [{
                "id": "std-1",
                "org_id": "org-1",
                "name": "食品国家标准库",
                "product_family": "food",
                "description": None,
                "rag_space_ids": ["space-1"],
                "rag_spaces": [],
                "total_document_count": 0,
                "is_active": True,
                "created_at": None,
                "updated_at": None,
            }]

    monkeypatch.setattr(standards_api, "InspectionStandardLibraryService", FakeService)
    response = await standards_api.list_inspection_standards(current=current_user("admin"), db=object())
    assert response.data[0]["product_family"] == "food"


@pytest.mark.asyncio
async def test_non_admin_cannot_access_inspection_standards():
    with pytest.raises(ForbiddenError):
        await standards_api.list_inspection_standards(current=current_user("platform_operator"), db=object())
