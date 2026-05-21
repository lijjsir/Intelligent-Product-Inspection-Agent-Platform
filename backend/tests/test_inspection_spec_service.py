from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
import uuid

import pytest

from app.services import inspection_spec_service as spec_mod


def make_spec(inspection_spec_row_id: str, org_id: str | None, spec_code: str = "STD-1", name: str = "默认标准"):
    now = datetime(2026, 3, 24, 10, 0, 0)
    return SimpleNamespace(
        id=inspection_spec_row_id,
        org_id=org_id,
        spec_code=spec_code,
        name=name,
        version="v1",
        product_id="prod-a",
        required_image_count=2,
        ai_gate_confidence_threshold=0.72,
        ai_gate_evidence_threshold=0.5,
        ai_gate_traceability_threshold=0.5,
        auto_pass_enabled=False,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def make_item(item_id: str, spec_row_id: str, defect_type: str = "scratch"):
    now = datetime(2026, 3, 24, 10, 0, 0)
    return SimpleNamespace(
        id=item_id,
        spec_row_id=spec_row_id,
        defect_type=defect_type,
        severity="major",
        disposition="fail",
        confidence_threshold=0.66,
        zone_name="edge",
        max_count=1,
        description="rule",
        created_at=now,
        updated_at=now,
    )


class FakeInspectionSpecRepo:
    def __init__(self, _session):
        self.specs: dict[str, SimpleNamespace] = {}
        self.items: dict[str, list[SimpleNamespace]] = {}

    async def list_all(self, org_id: str):
        visible = [spec for spec in self.specs.values() if spec.org_id in {None, org_id}]
        return sorted(visible, key=lambda spec: (spec.org_id is None, spec.spec_code, spec.version))

    async def get(self, org_id: str, inspection_spec_row_id: str):
        spec = self.specs.get(inspection_spec_row_id)
        if not spec or spec.org_id not in {None, org_id}:
            return None
        return spec

    async def get_for_write(self, org_id: str, inspection_spec_row_id: str, include_global: bool = False):
        spec = self.specs.get(inspection_spec_row_id)
        if not spec:
            return None
        if spec.org_id == org_id:
            return spec
        if include_global and spec.org_id is None:
            return spec
        return None

    async def list_items(self, spec_row_id: str):
        return list(self.items.get(spec_row_id, []))

    async def list_items_map(self, spec_row_ids: list[str]):
        return {spec_row_id: list(self.items.get(spec_row_id, [])) for spec_row_id in spec_row_ids}

    async def create_spec(self, payload: dict, items: list[dict]):
        spec = make_spec(
            inspection_spec_row_id=payload["id"],
            org_id=payload.get("org_id"),
            spec_code=payload["spec_code"],
            name=payload["name"],
        )
        spec.version = payload["version"]
        spec.product_id = payload.get("product_id")
        spec.required_image_count = payload["required_image_count"]
        spec.ai_gate_confidence_threshold = payload["ai_gate_confidence_threshold"]
        spec.ai_gate_evidence_threshold = payload["ai_gate_evidence_threshold"]
        spec.ai_gate_traceability_threshold = payload["ai_gate_traceability_threshold"]
        spec.auto_pass_enabled = payload["auto_pass_enabled"]
        spec.is_active = payload["is_active"]
        self.specs[spec.id] = spec
        self.items[spec.id] = [
            make_item(row["id"], spec.id, row["defect_type"])
            for row in items
        ]
        for item, row in zip(self.items[spec.id], items):
            item.severity = row["severity"]
            item.disposition = row["disposition"]
            item.confidence_threshold = row["confidence_threshold"]
            item.zone_name = row.get("zone_name")
            item.max_count = row.get("max_count")
            item.description = row.get("description")
        return spec

    async def save_spec(self, model, payload: dict):
        for key, value in payload.items():
            setattr(model, key, value)
        return model

    async def replace_items(self, spec_row_id: str, items: list[dict]):
        self.items[spec_row_id] = [
            make_item(row["id"], spec_row_id, row["defect_type"])
            for row in items
        ]
        for item, row in zip(self.items[spec_row_id], items):
            item.severity = row["severity"]
            item.disposition = row["disposition"]
            item.confidence_threshold = row["confidence_threshold"]
            item.zone_name = row.get("zone_name")
            item.max_count = row.get("max_count")
            item.description = row.get("description")

    async def delete_spec(self, model):
        self.specs.pop(model.id, None)
        self.items.pop(model.id, None)


def patch_uuid(monkeypatch):
    counter = iter(range(1, 20))
    monkeypatch.setattr(spec_mod, "uuid7", lambda: uuid.UUID(int=next(counter)))


@pytest.mark.asyncio
async def test_create_spec_allows_global_scope_for_admin(monkeypatch):
    repo = FakeInspectionSpecRepo(None)
    monkeypatch.setattr(spec_mod, "InspectionSpecRepository", lambda session: repo)
    patch_uuid(monkeypatch)

    svc = spec_mod.InspectionSpecService(None, "org-1")
    created = await svc.create_spec(
        {
            "org_id": None,
            "spec_code": "STD-ORG",
            "name": "组织标准",
            "version": "v2",
            "product_id": "prod-1",
            "required_image_count": 3,
            "ai_gate_confidence_threshold": 0.81,
            "ai_gate_evidence_threshold": 0.62,
            "ai_gate_traceability_threshold": 0.58,
            "auto_pass_enabled": True,
            "is_active": True,
            "items": [
                {
                    "defect_type": "scratch",
                    "severity": "major",
                    "disposition": "fail",
                    "confidence_threshold": 0.7,
                    "zone_name": "front",
                    "max_count": 1,
                    "description": "front scratch",
                }
            ],
        },
        "admin",
    )

    assert created["org_id"] is None
    assert created["spec_code"] == "STD-ORG"
    assert len(created["items"]) == 1
    assert created["items"][0]["defect_type"] == "scratch"


@pytest.mark.asyncio
async def test_create_spec_scopes_algorithm_engineer_to_current_org(monkeypatch):
    repo = FakeInspectionSpecRepo(None)
    monkeypatch.setattr(spec_mod, "InspectionSpecRepository", lambda session: repo)
    patch_uuid(monkeypatch)

    svc = spec_mod.InspectionSpecService(None, "org-1")
    created = await svc.create_spec(
        {
            "org_id": None,
            "spec_code": "STD-GLOBAL",
            "name": "全局标准",
            "version": "v1",
            "product_id": "prod-1",
            "required_image_count": 2,
            "ai_gate_confidence_threshold": 0.72,
            "ai_gate_evidence_threshold": 0.5,
            "ai_gate_traceability_threshold": 0.5,
            "auto_pass_enabled": False,
            "is_active": True,
            "items": [
                {
                    "defect_type": "dent",
                    "severity": "major",
                    "disposition": "manual_required",
                    "confidence_threshold": 0.6,
                    "zone_name": None,
                    "max_count": None,
                    "description": "dent rule",
                }
            ],
        },
        "algorithm_engineer",
    )

    assert created["org_id"] == "org-1"
    assert created["items"][0]["disposition"] == "manual_required"


@pytest.mark.asyncio
async def test_update_spec_replaces_rule_items(monkeypatch):
    repo = FakeInspectionSpecRepo(None)
    repo.specs["spec-1"] = make_spec("spec-1", "org-1", spec_code="STD-1", name="旧标准")
    repo.items["spec-1"] = [make_item("item-1", "spec-1", "scratch")]
    monkeypatch.setattr(spec_mod, "InspectionSpecRepository", lambda session: repo)
    patch_uuid(monkeypatch)

    svc = spec_mod.InspectionSpecService(None, "org-1")
    updated = await svc.update_spec(
        "spec-1",
        {
            "name": "新标准",
            "items": [
                {
                    "defect_type": "dent",
                    "severity": "critical",
                    "disposition": "fail",
                    "confidence_threshold": 0.82,
                    "zone_name": "rear",
                    "max_count": 2,
                    "description": "rear dent",
                }
            ],
        },
        "admin",
    )

    assert updated["name"] == "新标准"
    assert [item["defect_type"] for item in updated["items"]] == ["dent"]
    assert updated["items"][0]["zone_name"] == "rear"


@pytest.mark.asyncio
async def test_admin_can_modify_global_spec(monkeypatch):
    repo = FakeInspectionSpecRepo(None)
    repo.specs["spec-global"] = make_spec("spec-global", None, spec_code="STD-G", name="全局标准")
    repo.items["spec-global"] = [make_item("item-1", "spec-global", "dent")]
    monkeypatch.setattr(spec_mod, "InspectionSpecRepository", lambda session: repo)

    svc = spec_mod.InspectionSpecService(None, "org-1")
    await svc.delete_spec("spec-global", "admin")

    assert "spec-global" not in repo.specs


@pytest.mark.asyncio
async def test_list_specs_returns_org_and_global_items(monkeypatch):
    repo = FakeInspectionSpecRepo(None)
    repo.specs["spec-org"] = make_spec("spec-org", "org-1", spec_code="STD-ORG", name="组织标准")
    repo.specs["spec-global"] = make_spec("spec-global", None, spec_code="STD-BASE", name="基线标准")
    repo.items["spec-org"] = [make_item("item-1", "spec-org", "scratch")]
    repo.items["spec-global"] = [make_item("item-2", "spec-global", "dent")]
    monkeypatch.setattr(spec_mod, "InspectionSpecRepository", lambda session: repo)

    svc = spec_mod.InspectionSpecService(None, "org-1")
    items = await svc.list_specs()

    assert [item["spec_code"] for item in items] == ["STD-ORG", "STD-BASE"]
    assert items[0]["items"][0]["defect_type"] == "scratch"
    assert items[1]["items"][0]["defect_type"] == "dent"
