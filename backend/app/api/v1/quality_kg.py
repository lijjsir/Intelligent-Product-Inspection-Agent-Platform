from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_current_user
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.quality_kg_schema import (
    QualityKgNodeDelete,
    QualityKgRelationshipDelete,
    QualityKnowledgeChain,
    QualityKnowledgeChainBatch,
)
from app.services.quality_kg_service import QualityKnowledgeGraphService

router = APIRouter()


def _service(current: CurrentUser) -> QualityKnowledgeGraphService:
    return QualityKnowledgeGraphService(org_id=current.org_id)


@router.post("/chains", response_model=ResponseEnvelope[dict])
async def create_quality_chain(
    payload: QualityKnowledgeChain,
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality", current.role)
    await _service(current).ingest_chain(payload)
    return ResponseEnvelope(
        data={"success": True, "message": "quality knowledge chain ingested"}
    )


@router.post("/chains/batch", response_model=ResponseEnvelope[dict])
async def create_quality_chains_batch(
    payload: QualityKnowledgeChainBatch,
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality", current.role)
    await _service(current).ingest_chains(payload.items)
    return ResponseEnvelope(data={"success": True, "ingested": len(payload.items)})


@router.get("/products/{product_category}/standards", response_model=ResponseEnvelope[dict])
async def get_standards_by_product(
    product_category: str,
    domain: str = Query(..., min_length=1),
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality", current.role)
    standards = await _service(current).search_standards_by_product(
        domain=domain,
        product_category=product_category,
    )
    return ResponseEnvelope(data={"standards": standards})


@router.get("/standards/{standard}/clauses", response_model=ResponseEnvelope[dict])
async def get_clauses_by_standard(
    standard: str,
    domain: str = Query(..., min_length=1),
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality", current.role)
    clauses = await _service(current).search_clauses_by_standard(
        domain=domain,
        standard=standard,
    )
    return ResponseEnvelope(data={"clauses": clauses})


@router.get("/clauses/{standard_clause}/items", response_model=ResponseEnvelope[dict])
async def get_items_by_clause(
    standard_clause: str,
    domain: str = Query(..., min_length=1),
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality", current.role)
    items = await _service(current).search_items_by_clause(
        domain=domain,
        standard_clause=standard_clause,
    )
    return ResponseEnvelope(data={"items": items})


@router.get("/items/{inspection_item}/metrics", response_model=ResponseEnvelope[dict])
async def get_metrics_by_item(
    inspection_item: str,
    domain: str = Query(..., min_length=1),
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality", current.role)
    metrics = await _service(current).search_metrics_by_item(
        domain=domain,
        inspection_item=inspection_item,
    )
    return ResponseEnvelope(data={"metrics": metrics})


@router.get("/metrics/{metric}/defects", response_model=ResponseEnvelope[dict])
async def get_defects_by_metric(
    metric: str,
    domain: str = Query(..., min_length=1),
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality", current.role)
    defects = await _service(current).search_defects_by_metric(
        domain=domain,
        metric=metric,
    )
    return ResponseEnvelope(data={"defects": defects})


@router.get("/actions", response_model=ResponseEnvelope[dict])
async def get_actions_by_metric(
    domain: str = Query(..., min_length=1),
    metric: str = Query(..., min_length=1),
    product_category: str = Query(default=""),
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality", current.role)
    actions = await _service(current).search_actions_by_product_and_metric(
        domain=domain,
        product_category=product_category,
        metric=metric,
    )
    return ResponseEnvelope(data={"actions": actions})


@router.get("/defects/{defect_type}/actions", response_model=ResponseEnvelope[dict])
async def get_defect_actions(
    defect_type: str,
    domain: str = Query(..., min_length=1),
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality", current.role)
    service = _service(current)
    risks = await service.search_risks_by_defect(domain=domain, defect_type=defect_type)
    actions = await service.search_actions_by_defect(domain=domain, defect_type=defect_type)
    return ResponseEnvelope(data={"risks": risks, "actions": actions})


@router.get("/defects/{defect_type}/causes", response_model=ResponseEnvelope[dict])
async def get_causes_by_defect(
    defect_type: str,
    domain: str = Query(..., min_length=1),
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality", current.role)
    causes = await _service(current).search_causes_by_defect(
        domain=domain,
        defect_type=defect_type,
    )
    return ResponseEnvelope(data={"causes": causes})


@router.get("/products/{product_category}/paths", response_model=ResponseEnvelope[dict])
async def get_chain_paths_by_product(
    product_category: str,
    domain: str = Query(..., min_length=1),
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality", current.role)
    paths = await _service(current).search_chain_paths_by_product(
        domain=domain,
        product_category=product_category,
    )
    return ResponseEnvelope(data={"paths": paths})


@router.delete("/relationships", response_model=ResponseEnvelope[dict])
async def delete_quality_relationship(
    payload: QualityKgRelationshipDelete,
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality_delete", current.role)
    deleted = await _service(current).delete_relationship(payload)
    return ResponseEnvelope(data={"deleted": deleted})


@router.delete("/nodes", response_model=ResponseEnvelope[dict])
async def delete_quality_node(
    payload: QualityKgNodeDelete,
    current: CurrentUser = Depends(get_current_user),
):
    require_role("quality_delete", current.role)
    deleted = await _service(current).delete_node(payload)
    return ResponseEnvelope(data={"deleted": deleted})
