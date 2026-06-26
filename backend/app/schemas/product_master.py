from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ProductLineCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class ProductLineUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class ProductSkuCreate(BaseModel):
    product_line_id: str
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class ProductSkuUpdate(BaseModel):
    product_line_id: str | None = None
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class ProductBatchCreate(BaseModel):
    product_sku_id: str
    batch_no: str = Field(..., min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=128)
    production_date: date | None = None
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class ProductBatchUpdate(BaseModel):
    product_sku_id: str | None = None
    batch_no: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=128)
    production_date: date | None = None
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class ProductLineResponse(BaseModel):
    id: str
    org_id: str
    code: str
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProductSkuResponse(BaseModel):
    id: str
    org_id: str
    product_line_id: str
    product_line_code: str | None = None
    product_line_name: str | None = None
    code: str
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProductBatchResponse(BaseModel):
    id: str
    org_id: str
    product_sku_id: str
    product_sku_code: str | None = None
    product_sku_name: str | None = None
    product_line_id: str | None = None
    product_line_code: str | None = None
    product_line_name: str | None = None
    batch_no: str
    name: str
    production_date: date | None = None
    description: str | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProductMasterCatalogResponse(BaseModel):
    product_lines: list[ProductLineResponse]
    product_skus: list[ProductSkuResponse]
    product_batches: list[ProductBatchResponse]
