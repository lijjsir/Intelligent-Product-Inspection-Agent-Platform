import pytest

from app.api.v1 import product_master as product_api
from app.core.exceptions import ForbiddenError
from app.schemas.user import CurrentUser


def current_user(role: str) -> CurrentUser:
    return CurrentUser(user_id=f"{role}-1", org_id="org-1", role=role, roles=[role])


@pytest.mark.asyncio
async def test_user_can_read_product_catalog(monkeypatch):
    class FakeService:
        def __init__(self, db, org_id):
            self.db = db
            self.org_id = org_id

        async def catalog(self, *, include_inactive: bool = True):
            assert include_inactive is False
            return {"product_lines": [], "product_skus": [], "product_batches": []}

    monkeypatch.setattr(product_api, "ProductMasterService", FakeService)
    response = await product_api.get_product_catalog(
        include_inactive=False,
        current=current_user("user"),
        db=object(),
    )

    assert response.data["product_lines"] == []


@pytest.mark.asyncio
async def test_non_admin_cannot_write_product_master():
    with pytest.raises(ForbiddenError):
        await product_api.create_product_line(
            payload=product_api.ProductLineCreate(code="line-a", name="Line A"),
            current=current_user("user"),
            db=object(),
        )
