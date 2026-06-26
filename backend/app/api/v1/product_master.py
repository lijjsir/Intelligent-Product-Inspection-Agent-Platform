from fastapi import APIRouter, Depends, status

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.product_master import (
    ProductBatchCreate,
    ProductBatchResponse,
    ProductBatchUpdate,
    ProductLineCreate,
    ProductLineResponse,
    ProductLineUpdate,
    ProductMasterCatalogResponse,
    ProductSkuCreate,
    ProductSkuResponse,
    ProductSkuUpdate,
)
from app.schemas.user import CurrentUser
from app.services.product_master_service import ProductMasterService

router = APIRouter()


@router.get("/catalog", response_model=ResponseEnvelope[ProductMasterCatalogResponse])
async def get_product_catalog(
    include_inactive: bool = True,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("product_master_read", current.role)
    service = ProductMasterService(db, current.org_id)
    return ResponseEnvelope(data=await service.catalog(include_inactive=include_inactive))


@router.post("/lines", response_model=ResponseEnvelope[ProductLineResponse], status_code=status.HTTP_201_CREATED)
async def create_product_line(
    payload: ProductLineCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("product_master", current.role)
    service = ProductMasterService(db, current.org_id)
    return ResponseEnvelope(data=await service.create_line(payload.model_dump()))


@router.patch("/lines/{line_id}", response_model=ResponseEnvelope[ProductLineResponse])
async def update_product_line(
    line_id: str,
    payload: ProductLineUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("product_master", current.role)
    service = ProductMasterService(db, current.org_id)
    return ResponseEnvelope(data=await service.update_line(line_id, payload.model_dump(exclude_unset=True)))


@router.delete("/lines/{line_id}", response_model=ResponseEnvelope[dict[str, bool]])
async def delete_product_line(
    line_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("product_master", current.role)
    service = ProductMasterService(db, current.org_id)
    await service.delete_line(line_id)
    return ResponseEnvelope(data={"success": True})


@router.post("/skus", response_model=ResponseEnvelope[ProductSkuResponse], status_code=status.HTTP_201_CREATED)
async def create_product_sku(
    payload: ProductSkuCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("product_master", current.role)
    service = ProductMasterService(db, current.org_id)
    return ResponseEnvelope(data=await service.create_sku(payload.model_dump()))


@router.patch("/skus/{sku_id}", response_model=ResponseEnvelope[ProductSkuResponse])
async def update_product_sku(
    sku_id: str,
    payload: ProductSkuUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("product_master", current.role)
    service = ProductMasterService(db, current.org_id)
    return ResponseEnvelope(data=await service.update_sku(sku_id, payload.model_dump(exclude_unset=True)))


@router.delete("/skus/{sku_id}", response_model=ResponseEnvelope[dict[str, bool]])
async def delete_product_sku(
    sku_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("product_master", current.role)
    service = ProductMasterService(db, current.org_id)
    await service.delete_sku(sku_id)
    return ResponseEnvelope(data={"success": True})


@router.post("/batches", response_model=ResponseEnvelope[ProductBatchResponse], status_code=status.HTTP_201_CREATED)
async def create_product_batch(
    payload: ProductBatchCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("product_master", current.role)
    service = ProductMasterService(db, current.org_id)
    return ResponseEnvelope(data=await service.create_batch(payload.model_dump()))


@router.patch("/batches/{batch_id}", response_model=ResponseEnvelope[ProductBatchResponse])
async def update_product_batch(
    batch_id: str,
    payload: ProductBatchUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("product_master", current.role)
    service = ProductMasterService(db, current.org_id)
    return ResponseEnvelope(data=await service.update_batch(batch_id, payload.model_dump(exclude_unset=True)))


@router.delete("/batches/{batch_id}", response_model=ResponseEnvelope[dict[str, bool]])
async def delete_product_batch(
    batch_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("product_master", current.role)
    service = ProductMasterService(db, current.org_id)
    await service.delete_batch(batch_id)
    return ResponseEnvelope(data={"success": True})
