from __future__ import annotations

from agent.subgraphs.lab_detection.contracts import LabMeasurement, LabTestPlan


ITEM_ALIASES = {
    "moisture": "水分",
    "water": "水分",
    "ph": "pH",
    "PH": "pH",
}


def normalize_item_name(name: str) -> str:
    key = str(name or "").strip()
    return ITEM_ALIASES.get(key, key)


def normalize_lab_measurements(items: list[LabMeasurement]) -> list[LabMeasurement]:
    normalized: list[LabMeasurement] = []
    for item in items:
        payload = item.model_dump()
        payload["item"] = normalize_item_name(payload.get("item") or "")
        normalized.append(LabMeasurement.model_validate(payload))
    return normalized


def compute_data_completeness(test_plan: LabTestPlan) -> float:
    if test_plan.total_items <= 0:
        return 0.0
    return max(0.0, min(1.0, test_plan.completed_items / test_plan.total_items))
