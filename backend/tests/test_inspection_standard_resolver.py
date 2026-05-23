import pytest

from app.services.inspection_standard_resolver_service import InspectionStandardResolverService


class FakeLibraryService:
    def __init__(self, session, org_id):
        self.session = session
        self.org_id = org_id

    async def resolve_active_binding(self, *, product_family: str | None):
        if product_family != "food":
            return None
        return {
            "id": "binding-1",
            "name": "食品标准库",
            "product_family": "food",
            "rag_space_ids": ["space-1", "space-2"],
            "rag_spaces": [{"name": "食品国标 A"}, {"name": "食品国标 B"}],
        }


@pytest.mark.asyncio
async def test_resolver_returns_system_rag_binding(monkeypatch):
    monkeypatch.setattr(
        "app.services.inspection_standard_resolver_service.InspectionStandardLibraryService",
        FakeLibraryService,
    )
    resolver = InspectionStandardResolverService(object(), "org-1")
    result = await resolver.resolve(spec_code="FOOD-1", product_id="FOOD-1", product_family="food")
    assert result is not None
    assert result["system_rag_space_ids"] == ["space-1", "space-2"]
    assert result["system_rag_space_names"] == ["食品国标 A", "食品国标 B"]


@pytest.mark.asyncio
async def test_resolver_infers_product_family_from_product_id(monkeypatch):
    monkeypatch.setattr(
        "app.services.inspection_standard_resolver_service.InspectionStandardLibraryService",
        FakeLibraryService,
    )
    resolver = InspectionStandardResolverService(object(), "org-1")
    result = await resolver.resolve(spec_code=None, product_id="FOOD-RAW-001", product_family=None)
    assert result is not None
    assert result["product_family"] == "food"


@pytest.mark.asyncio
async def test_resolver_returns_none_when_family_cannot_be_inferred(monkeypatch):
    monkeypatch.setattr(
        "app.services.inspection_standard_resolver_service.InspectionStandardLibraryService",
        FakeLibraryService,
    )
    resolver = InspectionStandardResolverService(object(), "org-1")
    result = await resolver.resolve(spec_code=None, product_id="UNKNOWN-1", product_family=None)
    assert result is None
