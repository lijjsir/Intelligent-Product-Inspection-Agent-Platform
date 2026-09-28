# FastAPI dependency declarations intentionally call Depends/File/Form in signatures.
# ruff: noqa: B008

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.api.v1.deps import get_current_user, get_db
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.quality_risk import (
    DataSourceCreate,
    DataSourceResponse,
    DataSourceUpdate,
    IngestionPreviewResponse,
    PhysicalSampleCreate,
    PhysicalSampleResponse,
    ProductCatalogResponse,
    ProductCategoryCreate,
    ProductCategoryResponse,
    ProductCategoryUpdate,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    QualityAttachmentResponse,
    QualityEventCreate,
    QualitySourceRecordResponse,
    RiskAnalyzeRequest,
    RiskAssessmentResponse,
    RiskCaseCreate,
    RiskCaseResponse,
    RiskPolicyCreate,
    RiskPolicyResponse,
    RiskReviewRequest,
    StandardExecutionRuleCreate,
    StandardExecutionRuleResponse,
)
from app.schemas.user import CurrentUser
from app.services.quality_risk_service import QualityRiskService

router = APIRouter()


def service(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return QualityRiskService(db, current)


@router.get("/quality-products/catalog", response_model=ResponseEnvelope[ProductCatalogResponse])
async def product_catalog(include_inactive: bool = False, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.product_catalog(include_inactive=include_inactive))


@router.post("/quality-products/categories", response_model=ResponseEnvelope[ProductCategoryResponse], status_code=status.HTTP_201_CREATED)
async def create_category(payload: ProductCategoryCreate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.create_category(payload))


@router.patch("/quality-products/categories/{category_id}", response_model=ResponseEnvelope[ProductCategoryResponse])
async def update_category(category_id: str, payload: ProductCategoryUpdate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.update_category(category_id, payload))


@router.post("/quality-products", response_model=ResponseEnvelope[ProductResponse], status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.create_product(payload))


@router.patch("/quality-products/{product_id}", response_model=ResponseEnvelope[ProductResponse])
async def update_product(product_id: str, payload: ProductUpdate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.update_product(product_id, payload))


@router.get("/quality-data/sources", response_model=ResponseEnvelope[list[DataSourceResponse]])
async def list_sources(svc=Depends(service)):
    return ResponseEnvelope(data=await svc.list_sources())


@router.post("/quality-data/sources", response_model=ResponseEnvelope[DataSourceResponse], status_code=status.HTTP_201_CREATED)
async def create_source(payload: DataSourceCreate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.create_source(payload))


@router.patch("/quality-data/sources/{source_id}", response_model=ResponseEnvelope[DataSourceResponse])
async def update_source(source_id: str, payload: DataSourceUpdate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.update_source(source_id, payload))


@router.post("/quality-data/events", response_model=ResponseEnvelope[QualitySourceRecordResponse], status_code=status.HTTP_201_CREATED)
async def create_event(payload: QualityEventCreate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.create_event(payload))


@router.post("/quality-data/attachments", response_model=ResponseEnvelope[list[QualityAttachmentResponse]], status_code=status.HTTP_201_CREATED)
async def upload_attachments(files: list[UploadFile] = File(...), svc=Depends(service)):
    return ResponseEnvelope(data=[await svc.upload_attachment(file) for file in files])


@router.post("/quality-data/imports", response_model=ResponseEnvelope[IngestionPreviewResponse], status_code=status.HTTP_201_CREATED)
async def create_import(
    source_id: str = Form(...),
    request_key: str = Form(...),
    mapping: str = Form("{}"),
    file: UploadFile = File(...),
    svc=Depends(service),
):
    try:
        mapping_value = json.loads(mapping)
        if not isinstance(mapping_value, dict):
            raise TypeError()
    except (TypeError, ValueError, json.JSONDecodeError):
        from app.core.exceptions import ValidationError

        raise ValidationError("字段映射必须为JSON对象") from None
    return ResponseEnvelope(data=await svc.preview_import(source_id=source_id, request_key=request_key, file=file, mapping=mapping_value))


@router.get("/quality-data/import-template")
async def import_template(svc=Depends(service)):
    svc.require_role({"admin", "user", "expert"})
    content = (
        "external_record_id,record_type,occurred_at,text,production_batch_ref,"
        "unit_serial_ref,formatted_address\n"
        "CASE-001,consumer_complaint,2026-09-27T10:00:00,原始投诉内容,,,重庆市\n"
    )
    return Response(
        content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=quality-data-template.csv"},
    )


@router.get("/quality-data/imports/{job_id}", response_model=ResponseEnvelope[IngestionPreviewResponse])
async def get_import(job_id: str, svc=Depends(service)):
    return ResponseEnvelope(data=svc.ingestion_response(await svc.ingestion_job(job_id)))


@router.post("/quality-data/imports/{job_id}/confirm", response_model=ResponseEnvelope[IngestionPreviewResponse])
async def confirm_import(job_id: str, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.confirm_import(job_id))


@router.post("/quality-data/imports/{job_id}/cancel", response_model=ResponseEnvelope[IngestionPreviewResponse])
async def cancel_import(job_id: str, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.cancel_import(job_id))


@router.get("/quality-data/records", response_model=ResponseEnvelope[PagedResponse[QualitySourceRecordResponse]])
async def list_records(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    record_type: str | None = None,
    keyword: str | None = None,
    svc=Depends(service),
):
    return ResponseEnvelope(data=await svc.list_records(page=page, size=size, record_type=record_type, keyword=keyword))


@router.get("/quality-data/records/{record_id}", response_model=ResponseEnvelope[QualitySourceRecordResponse])
async def get_record(record_id: str, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.get_record(record_id))


@router.get("/quality-data/records/{record_id}/evidence", response_model=ResponseEnvelope[list[dict]])
async def get_record_evidence(record_id: str, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.record_evidence(record_id))


@router.get("/risk-cases", response_model=ResponseEnvelope[PagedResponse[RiskCaseResponse]])
async def list_risk_cases(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    status_text: str | None = Query(default=None, alias="status"),
    keyword: str | None = None,
    svc=Depends(service),
):
    return ResponseEnvelope(data=await svc.list_risk_cases(page=page, size=size, status=status_text, keyword=keyword))


@router.post("/risk-cases", response_model=ResponseEnvelope[RiskCaseResponse], status_code=status.HTTP_201_CREATED)
async def create_risk_case(payload: RiskCaseCreate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.create_risk_case(payload))


@router.get("/risk-cases/{risk_case_id}", response_model=ResponseEnvelope[RiskCaseResponse])
async def get_risk_case(risk_case_id: str, svc=Depends(service)):
    return ResponseEnvelope(data=svc.risk_case_response(await svc.risk_case(risk_case_id)))


@router.post("/risk-cases/{risk_case_id}/analyze", response_model=ResponseEnvelope[RiskAssessmentResponse])
async def analyze_risk(risk_case_id: str, payload: RiskAnalyzeRequest, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.analyze_risk(risk_case_id, payload))


@router.post("/risk-cases/{risk_case_id}/reviews", response_model=ResponseEnvelope[RiskAssessmentResponse])
async def review_risk(risk_case_id: str, payload: RiskReviewRequest, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.review_risk(risk_case_id, payload))


@router.get("/risk-assessments/{assessment_id}", response_model=ResponseEnvelope[RiskAssessmentResponse])
async def get_assessment(assessment_id: str, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.get_assessment(assessment_id))


@router.get("/risk-policies", response_model=ResponseEnvelope[list[RiskPolicyResponse]])
async def list_policies(svc=Depends(service)):
    return ResponseEnvelope(data=await svc.list_policies())


@router.post("/risk-policies", response_model=ResponseEnvelope[RiskPolicyResponse], status_code=status.HTTP_201_CREATED)
async def create_policy(payload: RiskPolicyCreate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.create_policy(payload))


@router.post("/risk-policies/{policy_id}/publish", response_model=ResponseEnvelope[RiskPolicyResponse])
async def publish_policy(policy_id: str, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.publish_policy(policy_id))


@router.get("/standard-execution-rules", response_model=ResponseEnvelope[list[StandardExecutionRuleResponse]])
async def list_standard_rules(svc=Depends(service)):
    return ResponseEnvelope(data=await svc.list_standard_rules())


@router.post("/standard-execution-rules", response_model=ResponseEnvelope[StandardExecutionRuleResponse], status_code=status.HTTP_201_CREATED)
async def create_standard_rule(payload: StandardExecutionRuleCreate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.create_standard_rule(payload))


@router.post("/standard-execution-rules/{rule_id}/publish", response_model=ResponseEnvelope[StandardExecutionRuleResponse])
async def publish_standard_rule(rule_id: str, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.publish_standard_rule(rule_id))


@router.get("/physical-samples", response_model=ResponseEnvelope[list[PhysicalSampleResponse]])
async def list_physical_samples(sampling_plan_id: str | None = None, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.list_physical_samples(sampling_plan_id))


@router.post("/physical-samples", response_model=ResponseEnvelope[PhysicalSampleResponse], status_code=status.HTTP_201_CREATED)
async def create_physical_sample(payload: PhysicalSampleCreate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.create_physical_sample(payload))
