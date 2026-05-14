from __future__ import annotations

from typing import Any

from app.core.exceptions import NotFoundError
from app.core.ids import uuid7
from app.core.permissions import ROLE_ANALYST, normalize_role
from app.repositories.inspection_spec_repo import InspectionSpecRepository
from app.services.base import TenantAwareService


GLOBAL_SPEC_RAW_ROLES = {"super_admin", "platform_admin"}


class InspectionSpecService(TenantAwareService):
    def __init__(self, session, org_id: str):
        super().__init__(session, org_id)
        self._repo = InspectionSpecRepository(session)

    async def list_specs(self) -> list[dict[str, Any]]:
        specs = await self._repo.list_all(self._org_id)
        items_map = await self._repo.list_items_map([spec.id for spec in specs])
        return [self._serialize_spec(spec, items_map.get(spec.id, [])) for spec in specs]

    async def get_spec(self, inspection_spec_row_id: str) -> dict[str, Any]:
        spec = await self._repo.get(self._org_id, inspection_spec_row_id)
        if not spec:
            raise NotFoundError("inspection spec not found")
        items = await self._repo.list_items(spec.id)
        return self._serialize_spec(spec, items)

    async def create_spec(self, payload: dict[str, Any], actor_role: str) -> dict[str, Any]:
        body = dict(payload)
        items = body.pop("items", [])
        can_manage_global = self._can_manage_global(actor_role)
        target_org_id = self._resolve_target_org_id(body.pop("org_id", None), can_manage_global)
        body["id"] = str(uuid7())
        body["org_id"] = target_org_id
        item_rows = [self._build_item_payload(body["id"], item) for item in items]
        spec = await self._repo.create_spec(body, item_rows)
        return self._serialize_spec(spec, await self._repo.list_items(spec.id))

    async def update_spec(self, inspection_spec_row_id: str, payload: dict[str, Any], actor_role: str) -> dict[str, Any]:
        spec = await self._get_writable_spec(inspection_spec_row_id, self._can_manage_global(actor_role))
        body = dict(payload)
        items = body.pop("items", None)
        body.pop("org_id", None)
        updates = body
        if updates:
            await self._repo.save_spec(spec, updates)
        if items is not None:
            await self._repo.replace_items(spec.id, [self._build_item_payload(spec.id, item) for item in items])
        return self._serialize_spec(spec, await self._repo.list_items(spec.id))

    async def delete_spec(self, inspection_spec_row_id: str, actor_role: str) -> None:
        spec = await self._get_writable_spec(inspection_spec_row_id, self._can_manage_global(actor_role))
        await self._repo.delete_spec(spec)

    async def _get_writable_spec(self, inspection_spec_row_id: str, can_manage_global: bool):
        spec = await self._repo.get_for_write(
            self._org_id,
            inspection_spec_row_id,
            include_global=can_manage_global,
        )
        if not spec:
            raise NotFoundError("inspection spec not found")
        return spec

    def _resolve_target_org_id(self, requested_org_id: str | None, can_manage_global: bool) -> str | None:
        if can_manage_global:
            if requested_org_id is None:
                return None
            if str(requested_org_id).strip():
                return requested_org_id
        return self._org_id

    @staticmethod
    def _can_manage_global(actor_role: str) -> bool:
        return actor_role in GLOBAL_SPEC_RAW_ROLES or normalize_role(actor_role) == ROLE_ANALYST

    @staticmethod
    def _build_item_payload(spec_row_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = dict(payload)
        row["id"] = str(uuid7())
        row["spec_row_id"] = spec_row_id
        return row

    @staticmethod
    def _serialize_spec(spec, items: list[Any]) -> dict[str, Any]:
        return {
            "id": spec.id,
            "org_id": spec.org_id,
            "spec_code": spec.spec_code,
            "name": spec.name,
            "version": spec.version,
            "product_id": spec.product_id,
            "required_image_count": int(spec.required_image_count or 1),
            "ai_gate_confidence_threshold": float(spec.ai_gate_confidence_threshold),
            "ai_gate_evidence_threshold": float(spec.ai_gate_evidence_threshold),
            "ai_gate_traceability_threshold": float(spec.ai_gate_traceability_threshold),
            "auto_pass_enabled": bool(spec.auto_pass_enabled),
            "is_active": bool(spec.is_active),
            "items": [
                {
                    "id": item.id,
                    "defect_type": item.defect_type,
                    "severity": item.severity,
                    "disposition": item.disposition,
                    "confidence_threshold": float(item.confidence_threshold),
                    "zone_name": item.zone_name,
                    "max_count": item.max_count,
                    "description": item.description,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
                for item in items
            ],
            "created_at": spec.created_at,
            "updated_at": spec.updated_at,
        }
