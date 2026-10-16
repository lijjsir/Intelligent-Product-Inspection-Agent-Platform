"""Mixed monitoring pages retain all authorized rows, including unknown event times."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from test_quality_risk_v4 import domain  # noqa: F401 -- isolated database fixture

from app.api.v1.deps import get_current_user, get_db
from app.api.v1.quality_risk import router
from app.core.exceptions import ValidationError
from app.models.quality_risk import QualitySourceRecord
from app.schemas.quality_risk import QualityEventCreate


@pytest_asyncio.fixture
async def monitoring(domain):  # noqa: F811 -- pytest injects the imported fixture
    db, service = domain
    user = service("user")
    seed = await user.create_event(QualityEventCreate(record_type="inspection_report", content={"text": "report seed"}))
    at = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    selected = set()
    for i in range(411):
        kind = "consumer_complaint" if i < 201 else "public_opinion" if i < 406 else "inspection_report"
        record_id = str(UUID(int=i + 100))
        db.add(QualitySourceRecord(id=record_id, org_id=user.org_id, source_id=seed["source_id"],
            record_type=kind, content={"text": f"signal {i}"}, content_hash=f"{i:064x}",
            received_at=at, occurred_at=None, created_by=user.actor, authorization_scope="private"))
        if kind != "inspection_report":
            selected.add(record_id)
    # Another user's private signal and another organization's signal must not leak into this user's pages.
    for i, org, actor in [(1, user.org_id, service("expert").actor), (2, str(uuid4()), user.actor)]:
        db.add(QualitySourceRecord(org_id=org, source_id=seed["source_id"], record_type="public_opinion",
            content={"text": "private other scope"}, content_hash=f"{i + 1000:064x}",
            received_at=at, created_by=actor, authorization_scope="private"))
    await db.commit()
    return db, user, selected


@pytest.mark.asyncio
async def test_mixed_pages_pass_old_200_per_type_cap_without_duplicates(monitoring):
    _, user, selected = monitoring
    seen = []
    for page in range(1, 22):
        result = await user.list_records(page=page, size=20, record_types=["consumer_complaint", "public_opinion"])
        assert result["total"] == 406
        assert result["page"] == page
        seen.extend(r["id"] for r in result["items"])
        assert all(r["occurred_at"] is None for r in result["items"])
    assert len(seen) == len(set(seen)) == 406
    assert set(seen) == selected
    assert seen == sorted(seen, reverse=True)
    complaints = await user.list_records(page=11, size=20, record_types=["consumer_complaint"])
    assert complaints["total"] == 201 and len(complaints["items"]) == 1
    assert (await user.list_records(page=1, size=20, record_types=["public_opinion"], keyword="signal 405"))["total"] == 1
    with pytest.raises(ValidationError):
        await user.list_records(page=1, size=20, record_types=["unknown_type"])


@pytest.mark.asyncio
async def test_api_accepts_repeated_types_and_retains_legacy_filter(monitoring):
    db, user, _ = monitoring
    app = FastAPI()
    app.include_router(router)

    async def session():
        yield db

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_user] = lambda: user.current
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/quality-data/records", params=[("page", 21), ("size", 20),
            ("record_types", "consumer_complaint"), ("record_types", "public_opinion")])
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 406 and len(data["items"]) == 6
        legacy = await client.get("/quality-data/records", params={"record_type": "consumer_complaint"})
        assert legacy.status_code == 200 and legacy.json()["data"]["total"] == 201
