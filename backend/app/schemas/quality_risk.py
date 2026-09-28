from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RECORD_TYPES = {
    "consumer_complaint",
    "supervision_inspection",
    "enforcement_case",
    "enterprise_information",
    "public_opinion",
    "policy_document",
    "standard_document",
    "inspection_report",
    "production_data",
    "image",
    "video",
    "device_observation",
    "expert_opinion",
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LocationRef(Strict):
    province_code: str | None = Field(default=None, max_length=12)
    city_code: str | None = Field(default=None, max_length=12)
    district_code: str | None = Field(default=None, max_length=12)
    formatted_address: str | None = Field(default=None, max_length=500)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    location_method: Literal["manual", "browser", "imported", "source", "unknown"] = "unknown"
    accuracy_meters: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ProductRef(Strict):
    category_id: str | None = None
    product_id: str | None = None
    production_batch_ref: str | None = Field(default=None, max_length=128)
    unit_serial_ref: str | None = Field(default=None, max_length=255)
    source_product_id: str | None = Field(default=None, max_length=255)


class EnterpriseRef(Strict):
    enterprise_id: str | None = None
    name: str | None = Field(default=None, max_length=255)
    credit_code: str | None = Field(default=None, max_length=32)
    role: str | None = Field(default=None, max_length=32)


class ProductCategoryCreate(Strict):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    parent_id: str | None = None
    description: str | None = None
    is_active: bool = True


class ProductCategoryUpdate(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: str | None = None
    description: str | None = None
    is_active: bool | None = None


class ProductCategoryResponse(ProductCategoryCreate):
    id: str
    org_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductIdentifierInput(Strict):
    identifier_type: Literal["model_code", "sku", "barcode", "source_product_id"]
    identifier_value: str = Field(min_length=1, max_length=255)
    source_id: str | None = None


class ProductCreate(Strict):
    category_id: str
    name: str = Field(min_length=1, max_length=255)
    model: str | None = Field(default=None, max_length=128)
    brand: str | None = Field(default=None, max_length=128)
    manufacturer_enterprise_id: str | None = None
    attributes: dict = Field(default_factory=dict)
    identifiers: list[ProductIdentifierInput] = Field(default_factory=list, max_length=100)
    is_active: bool = True


class ProductUpdate(Strict):
    category_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    model: str | None = Field(default=None, max_length=128)
    brand: str | None = Field(default=None, max_length=128)
    manufacturer_enterprise_id: str | None = None
    attributes: dict | None = None
    identifiers: list[ProductIdentifierInput] | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class ProductResponse(Strict):
    id: str
    org_id: str
    category_id: str
    category_name: str | None = None
    name: str
    model: str | None = None
    brand: str | None = None
    manufacturer_enterprise_id: str | None = None
    attributes: dict = Field(default_factory=dict)
    identifiers: list[dict] = Field(default_factory=list)
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProductCatalogResponse(Strict):
    categories: list[ProductCategoryResponse]
    products: list[ProductResponse]


class DataSourceCreate(Strict):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    source_type: str = Field(min_length=1, max_length=48)
    connector_type: Literal["manual", "file", "api", "webhook", "database_sync"]
    config: dict = Field(default_factory=dict)
    status: Literal["active", "inactive"] = "active"


class DataSourceUpdate(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    source_type: str | None = Field(default=None, min_length=1, max_length=48)
    connector_type: Literal["manual", "file", "api", "webhook", "database_sync"] | None = None
    config: dict | None = None
    status: Literal["active", "inactive"] | None = None


class DataSourceResponse(DataSourceCreate):
    id: str
    org_id: str
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class QualityEventCreate(Strict):
    source_id: str
    external_record_id: str | None = Field(default=None, max_length=255)
    record_type: str
    occurred_at: datetime
    content: dict = Field(default_factory=dict)
    enterprise_ref: EnterpriseRef = Field(default_factory=EnterpriseRef)
    product_ref: ProductRef = Field(default_factory=ProductRef)
    location: LocationRef = Field(default_factory=LocationRef)
    attachment_ids: list[str] = Field(default_factory=list, max_length=100)
    provenance: dict = Field(default_factory=dict)
    authorization_scope: str = Field(default="organization", max_length=64)
    data_nature: Literal["observed", "inferred", "synthetic"] = "observed"
    ingestion_job_id: str | None = None

    @field_validator("record_type")
    @classmethod
    def known_record_type(cls, value: str) -> str:
        if value not in RECORD_TYPES:
            raise ValueError("unsupported quality record type")
        return value


class QualitySourceRecordResponse(Strict):
    id: str
    org_id: str
    source_id: str
    ingestion_job_id: str | None = None
    external_record_id: str | None = None
    record_type: str
    occurred_at: datetime
    received_at: datetime
    content: dict
    content_hash: str
    enterprise_ref: dict
    product_ref: dict
    location: dict
    attachment_ids: list[str]
    provenance: dict
    authorization_scope: str
    data_nature: str
    normalization_status: str
    normalization_errors: list
    created_by: str
    created_at: datetime | None = None


class QualityAttachmentResponse(Strict):
    id: str
    file_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    download_url: str


class IngestionPreviewResponse(Strict):
    id: str
    source_id: str
    request_key: str
    import_batch_code: str
    status: str
    file_name: str | None = None
    total_count: int
    valid_count: int
    error_count: int
    errors: list
    preview_rows: list[dict] = Field(default_factory=list)


class RiskCaseCreate(Strict):
    title: str = Field(min_length=1, max_length=255)
    scope_type: Literal["category", "enterprise", "product", "production_batch", "individual_unit", "mixed"]
    scope: dict = Field(default_factory=dict)
    source_record_ids: list[str] = Field(default_factory=list, min_length=1, max_length=500)
    evidence_ids: list[str] = Field(default_factory=list, max_length=1000)
    assigned_to: str | None = None


class RiskCaseResponse(Strict):
    id: str
    org_id: str
    code: str
    title: str
    scope_type: str
    scope: dict
    status: str
    evidence_ids: list[str]
    source_record_ids: list[str]
    assigned_to: str | None = None
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RiskAnalyzeRequest(Strict):
    policy_id: str | None = None


class RiskAssessmentResponse(Strict):
    id: str
    org_id: str
    risk_case_id: str
    version: int
    risk_type: str | None = None
    risk_level: str
    scope: dict
    evidence_ids: list[str]
    standard_matches: list
    conflicts: list
    missing_inputs: list
    possible_causes: list
    recommendations: list
    trust_status: str
    probability: float | None = None
    model_versions: dict
    policy_version: str | None = None
    knowledge_snapshot_id: str | None = None
    status: str
    submitted_by: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None
    created_at: datetime | None = None


class RiskReviewRequest(Strict):
    decision: Literal["accept", "request_evidence", "revise"]
    comment: str = Field(min_length=1, max_length=4000)
    risk_type: str | None = Field(default=None, max_length=128)
    risk_level: Literal["low", "medium", "high", "critical"] | None = None
    possible_causes: list[str] | None = None
    recommendations: list[str] | None = None


class RiskPolicyCreate(Strict):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=32)
    rules: dict

    @model_validator(mode="after")
    def validate_rules(self):
        required = {"severity", "likelihood", "exposure", "evidence_sufficiency", "level_mapping"}
        missing = sorted(required - set(self.rules))
        if missing:
            raise ValueError(f"risk policy rules missing: {', '.join(missing)}")
        return self


class RiskPolicyResponse(RiskPolicyCreate):
    id: str
    org_id: str
    status: str
    created_by: str
    published_by: str | None = None
    published_at: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class StandardExecutionRuleCreate(Strict):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=32)
    standard_id: str
    clause_ref: str = Field(min_length=1, max_length=255)
    page_ref: str | None = Field(default=None, max_length=64)
    category_id: str | None = None
    product_id: str | None = None
    indicator: str = Field(min_length=1, max_length=128)
    method: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, max_length=32)
    condition: dict
    decision_action: Literal["pass", "fail", "warn", "manual_review"]
    review_policy: dict = Field(default_factory=dict)


class StandardExecutionRuleResponse(StandardExecutionRuleCreate):
    id: str
    org_id: str
    status: str
    created_by: str
    reviewed_by: str | None = None
    published_by: str | None = None
    published_at: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PhysicalSampleCreate(Strict):
    sampling_plan_id: str
    product_id: str | None = None
    production_batch_ref: str | None = Field(default=None, max_length=128)
    external_sample_code: str | None = Field(default=None, max_length=128)
    unit_serial_ref: str | None = Field(default=None, max_length=255)
    sampled_at: datetime | None = None
    sampling_location: LocationRef = Field(default_factory=LocationRef)


class PhysicalSampleResponse(PhysicalSampleCreate):
    id: str
    org_id: str
    custody_status: str
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
