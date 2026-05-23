from __future__ import annotations

from typing import Any

from app.services.inspection_standard_library_service import InspectionStandardLibraryService


def _infer_product_family(product_family: str | None, product_id: str | None, spec_code: str | None) -> str | None:
    explicit = str(product_family or "").strip().lower()
    if explicit:
        return explicit
    product_candidate = str(product_id or "").strip().lower()
    if product_candidate.startswith("food"):
        return "food"
    if product_candidate.startswith("elec") or product_candidate in {"electronics", "electronic"}:
        return "electronics"
    if product_candidate == "screw":
        return "screw"
    spec_candidate = str(spec_code or "").strip().lower()
    if spec_candidate.startswith("food"):
        return "food"
    if spec_candidate.startswith("elec"):
        return "electronics"
    if spec_candidate.startswith("screw"):
        return "screw"
    return None


class InspectionStandardResolverService:
    def __init__(self, session, org_id: str):
        self._service = InspectionStandardLibraryService(session, org_id)

    async def resolve(
        self,
        *,
        spec_code: str | None = None,
        product_id: str | None = None,
        product_family: str | None = None,
    ) -> dict[str, Any] | None:
        resolved_family = _infer_product_family(product_family, product_id, spec_code)
        binding = await self._service.resolve_active_binding(product_family=resolved_family)
        if not binding:
            return None
        return {
            "binding_id": binding["id"],
            "binding_name": binding["name"],
            "product_family": binding["product_family"],
            "system_rag_space_ids": list(binding.get("rag_space_ids") or []),
            "system_rag_space_names": [str(item.get("name") or "") for item in list(binding.get("rag_spaces") or []) if str(item.get("name") or "").strip()],
            "spec_code": spec_code,
            "product_id": product_id,
        }
