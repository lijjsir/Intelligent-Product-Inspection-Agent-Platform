# FastAPI dependency declarations intentionally call Depends/File/Form in signatures.
# ruff: noqa: B008

from __future__ import annotations

import json
from io import BytesIO
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import has_permission, require_role
from app.core.exceptions import ForbiddenError, NotFoundError
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
    CategoryImportConfirm,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    ProductionBatchCreate,
    ProductionBatchResponse,
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
    RiskWorkspaceResponse,
    RiskSourcesAppend,
    RecordObjectsUpdate,
    StandardExecutionRuleCreate,
    StandardExecutionRuleResponse,
)
from app.schemas.user import CurrentUser
from app.services.quality_risk_service import QualityRiskService
from app.schemas.demo_risk_workflow import DemoDraftCreate, DemoDraftSave, DemoDraftSubmit, DemoDraftReview
from app.schemas.risk_collaboration import RiskCollaborationCreate
from app.schemas.demo_sampling import DemoSamplingCreate, DemoSamplingSave, DemoSamplingConfirm
from app.schemas.risk_completion import LabDecision, LabReturn, LabExecutionReturn, LabExecutionWithdraw, RiskReportCreate, RiskReportExport

router = APIRouter()


def service(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    require_role("quality", current.role)
    return QualityRiskService(db, current)


def intake_service(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return QualityRiskService(db, current)


def catalog_service(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    require_role("product_master_read", current.role)
    return QualityRiskService(db, current)


def product_option_service(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    if not any(has_permission(key, current.role) for key in ("task", "quality_material_submit", "dataset", "quality", "product_master_read")):
        raise ForbiddenError("当前账号没有任务或资料表单的产品选项权限")
    return QualityRiskService(db, current)


def product_maintenance_service(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    require_role("product_master", current.role)
    return QualityRiskService(db, current)


@router.get("/quality-products/options", response_model=ResponseEnvelope[dict])
async def product_form_options(svc=Depends(product_option_service)):
    catalog = await svc.product_catalog(include_inactive=False)
    category_fields = ("id", "org_id", "code", "name", "is_active")
    product_fields = ("id", "org_id", "category_id", "name", "model", "brand", "is_active")
    return ResponseEnvelope(data={
        "categories": [{key: item.get(key) for key in category_fields} for item in catalog["categories"]],
        "products": [{key: item.get(key) for key in product_fields} for item in catalog["products"]],
    })


@router.get("/quality-products/{product_id}/batch-options", response_model=ResponseEnvelope[list[dict]])
async def product_batch_options(product_id: UUID, svc=Depends(product_option_service)):
    product = await svc.product(str(product_id))
    if not product.is_active:
        raise NotFoundError("产品未开放为表单选项")
    rows = await svc.product_batches(str(product_id))
    return ResponseEnvelope(data=[{key: item.get(key) for key in ("id", "product_id", "display_no", "original_batch_no")} for item in rows])


@router.get("/quality-data/locations/reverse-geocode", response_model=ResponseEnvelope[dict])
async def reverse_geocode(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    svc=Depends(service),
):
    return ResponseEnvelope(data=await svc.reverse_geocode(latitude, longitude))


@router.get("/quality-products/catalog", response_model=ResponseEnvelope[ProductCatalogResponse])
async def product_catalog(include_inactive: bool = False, svc=Depends(catalog_service)):
    return ResponseEnvelope(data=await svc.product_catalog(include_inactive=include_inactive, with_batches=True))


@router.post("/quality-products/categories", response_model=ResponseEnvelope[ProductCategoryResponse], status_code=status.HTTP_201_CREATED)
async def create_category(payload: ProductCategoryCreate, svc=Depends(product_maintenance_service)):
    data = await svc.create_category(payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/quality-products/categories/imports/preview", response_model=ResponseEnvelope[dict])
async def preview_category_import(file: UploadFile = File(...), common_basis: str | None = Form(None), svc=Depends(product_maintenance_service)):
    from app.services.quality_category_imports import preview_categories
    return ResponseEnvelope(data=await preview_categories(svc, file.filename or '', await file.read(5 * 1024 * 1024 + 1), common_basis))


@router.post("/quality-products/categories/imports/confirm", response_model=ResponseEnvelope[dict])
async def confirm_category_import(payload: CategoryImportConfirm, svc=Depends(product_maintenance_service)):
    from app.services.quality_category_imports import confirm_categories
    data = await confirm_categories(svc, payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.patch("/quality-products/categories/{category_id}", response_model=ResponseEnvelope[ProductCategoryResponse])
async def update_category(category_id: str, payload: ProductCategoryUpdate, svc=Depends(product_maintenance_service)):
    data = await svc.update_category(category_id, payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/quality-products", response_model=ResponseEnvelope[ProductResponse], status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate, svc=Depends(product_maintenance_service)):
    data = await svc.create_product(payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/quality-products/duplicate-candidates", response_model=ResponseEnvelope[list[dict]])
async def product_duplicate_candidates(category_id: UUID, name: str = Query(..., min_length=1, max_length=255),
    brand: str | None = Query(None, max_length=128), model: str | None = Query(None, max_length=128),
    manufacturer_enterprise_id: UUID | None = None, exclude_id: UUID | None = None, svc=Depends(product_maintenance_service)):
    return ResponseEnvelope(data=await svc.product_candidates(str(category_id), name, brand, model,
        str(manufacturer_enterprise_id) if manufacturer_enterprise_id else None, str(exclude_id) if exclude_id else None))


@router.delete("/quality-products/categories/{category_id}", response_model=ResponseEnvelope[dict])
async def delete_category(category_id: UUID, svc=Depends(product_maintenance_service)):
    data = await svc.delete_foundation("category", str(category_id))
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.delete("/quality-products/{product_id}", response_model=ResponseEnvelope[dict])
async def delete_product(product_id: UUID, svc=Depends(product_maintenance_service)):
    data = await svc.delete_foundation("product", str(product_id))
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.delete("/quality-products/{product_id}/batches/{batch_id}", response_model=ResponseEnvelope[dict])
async def delete_production_batch(product_id: UUID, batch_id: UUID, svc=Depends(product_maintenance_service)):
    data = await svc.delete_foundation("batch", str(batch_id), str(product_id))
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.delete("/enterprises/{enterprise_id}", response_model=ResponseEnvelope[dict])
async def delete_enterprise(enterprise_id: UUID, svc=Depends(service)):
    data = await svc.delete_foundation("enterprise", str(enterprise_id))
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.patch("/quality-products/{product_id}", response_model=ResponseEnvelope[ProductResponse])
async def update_product(product_id: str, payload: ProductUpdate, svc=Depends(product_maintenance_service)):
    data = await svc.update_product(product_id, payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/quality-data/sources", response_model=ResponseEnvelope[list[DataSourceResponse]])
async def list_sources(svc=Depends(service)):
    return ResponseEnvelope(data=await svc.list_sources())


@router.get("/quality-products/{product_id}/batches", response_model=ResponseEnvelope[list[ProductionBatchResponse]])
async def product_batches(product_id: UUID, svc=Depends(catalog_service)):
    return ResponseEnvelope(data=await svc.product_batches(str(product_id)))


@router.post("/quality-products/{product_id}/batches", response_model=ResponseEnvelope[ProductionBatchResponse], status_code=201)
async def create_production_batch(product_id: UUID, payload: ProductionBatchCreate, svc=Depends(product_maintenance_service)):
    data = await svc.save_production_batch(str(product_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.patch("/quality-products/{product_id}/batches/{batch_id}", response_model=ResponseEnvelope[ProductionBatchResponse])
async def update_production_batch(product_id: UUID, batch_id: UUID, payload: ProductionBatchCreate, svc=Depends(product_maintenance_service)):
    data = await svc.save_production_batch(str(product_id), payload, str(batch_id))
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/quality-products/{product_id}/links", response_model=ResponseEnvelope[dict])
async def product_links(product_id: UUID, batch_id: UUID | None = None, svc=Depends(catalog_service)):
    return ResponseEnvelope(data=await svc.product_links(str(product_id), str(batch_id) if batch_id else None))


@router.post("/quality-data/sources", response_model=ResponseEnvelope[DataSourceResponse], status_code=status.HTTP_201_CREATED)
async def create_source(payload: DataSourceCreate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.create_source(payload))


@router.patch("/quality-data/sources/{source_id}", response_model=ResponseEnvelope[DataSourceResponse])
async def update_source(source_id: str, payload: DataSourceUpdate, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.update_source(source_id, payload))


@router.post("/quality-data/events", response_model=ResponseEnvelope[QualitySourceRecordResponse], status_code=status.HTTP_201_CREATED)
async def create_event(payload: QualityEventCreate, svc=Depends(intake_service)):
    data = await svc.create_event(payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/quality-data/attachments", response_model=ResponseEnvelope[list[QualityAttachmentResponse]], status_code=status.HTTP_201_CREATED)
async def upload_attachments(files: list[UploadFile] = File(...), svc=Depends(intake_service)):
    data = [await svc.upload_attachment(file) for file in files]
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/quality-data/imports", response_model=ResponseEnvelope[IngestionPreviewResponse], status_code=status.HTTP_201_CREATED)
async def create_import(
    source_id: str | None = Form(None),
    origin_label: str | None = Form(None),
    record_type: str | None = Form(None),
    request_key: str = Form(...),
    mapping: str = Form("{}"),
    file: UploadFile = File(...),
    svc=Depends(intake_service),
):
    try:
        mapping_value = json.loads(mapping)
        if not isinstance(mapping_value, dict):
            raise TypeError()
    except (TypeError, ValueError, json.JSONDecodeError):
        from app.core.exceptions import ValidationError

        raise ValidationError("字段映射必须为JSON对象") from None
    data = await svc.preview_import(source_id=source_id, request_key=request_key, file=file, mapping=mapping_value, origin_label=origin_label, record_type=record_type)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/quality-data/import-template")
async def import_template(svc=Depends(intake_service)):
    svc.require_intake(write=True)
    content = (
        "external_record_id,record_type,occurred_at,text,origin_label,category_id,product_id,enterprise_id,enterprise_name,enterprise_role,production_batch_ref,"
        "unit_serial_ref,formatted_address\n"
        "CASE-001,consumer_complaint,,原始投诉内容,资料提供方,,,,,,,,重庆市\n"
    )
    return Response(
        content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=quality-data-template.csv"},
    )


@router.get("/quality-data/imports/{job_id}", response_model=ResponseEnvelope[IngestionPreviewResponse])
async def get_import(job_id: str, svc=Depends(intake_service)):
    return ResponseEnvelope(data=svc.ingestion_response(await svc.ingestion_job(job_id)))


@router.post("/quality-data/imports/{job_id}/confirm", response_model=ResponseEnvelope[IngestionPreviewResponse])
async def confirm_import(job_id: str, svc=Depends(intake_service)):
    data = await svc.confirm_import(job_id)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/quality-data/imports/{job_id}/cancel", response_model=ResponseEnvelope[IngestionPreviewResponse])
async def cancel_import(job_id: str, svc=Depends(intake_service)):
    data = await svc.cancel_import(job_id)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/quality-data/records", response_model=ResponseEnvelope[PagedResponse[QualitySourceRecordResponse]])
async def list_records(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    record_type: str | None = None,
    record_types: list[str] | None = Query(None, max_length=13),
    keyword: str | None = None,
    product_id: str | None = None,
    enterprise_id: UUID | None = None,
    production_batch_ref: str | None = None,
    source_id: str | None = None,
    ingestion_job_id: str | None = None,
    svc=Depends(intake_service),
):
    return ResponseEnvelope(data=await svc.list_records(page=page, size=size, record_type=record_type, record_types=record_types, keyword=keyword, product_id=product_id, enterprise_id=str(enterprise_id) if enterprise_id else None, production_batch_ref=production_batch_ref, source_id=source_id, ingestion_job_id=ingestion_job_id))


@router.get("/quality-data/reference-options", response_model=ResponseEnvelope[dict])
async def intake_reference_options(keyword: str = Query("", max_length=100), limit: int = Query(50, ge=1, le=100), svc=Depends(intake_service)):
    return ResponseEnvelope(data=await svc.intake_references(keyword, limit))


@router.get("/quality-data/records/{record_id}/context", response_model=ResponseEnvelope[dict])
async def get_record_context(record_id: UUID, svc=Depends(intake_service)):
    return ResponseEnvelope(data=await svc.record_context(str(record_id)))


@router.patch("/quality-data/records/{record_id}/objects", response_model=ResponseEnvelope[QualitySourceRecordResponse])
async def update_record_objects(record_id: UUID, payload: RecordObjectsUpdate, svc=Depends(intake_service)):
    data = await svc.update_record_objects(str(record_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/quality-data/records/{record_id}", response_model=ResponseEnvelope[QualitySourceRecordResponse])
async def get_record(record_id: str, svc=Depends(intake_service)):
    return ResponseEnvelope(data=await svc.get_record(record_id))


@router.get("/quality-data/records/{record_id}/evidence", response_model=ResponseEnvelope[list[dict]])
async def get_record_evidence(record_id: str, svc=Depends(intake_service)):
    return ResponseEnvelope(data=await svc.record_evidence(record_id))


@router.get("/quality-data/attachments/{attachment_id}", response_model=ResponseEnvelope[QualityAttachmentResponse])
async def get_quality_attachment(attachment_id: str, svc=Depends(intake_service)):
    svc.require_intake()
    return ResponseEnvelope(data=svc.attachment_response(await svc.accessible_attachment(attachment_id)))


@router.get("/quality-data/attachments/{attachment_id}/download")
async def download_quality_attachment(attachment_id: str, svc=Depends(intake_service)):
    svc.require_intake()
    row = await svc.accessible_attachment(attachment_id)
    result = svc.storage.get_bytes(bucket=row.bucket, object_key=row.object_key)
    if result is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("附件文件不存在")
    from urllib.parse import quote
    content, mime_type = result
    return StreamingResponse(BytesIO(content), media_type=mime_type or row.mime_type,
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.file_name)}", "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


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


@router.get("/risk-cases/{risk_case_id}/workspace", response_model=ResponseEnvelope[RiskWorkspaceResponse])
async def get_risk_workspace(risk_case_id: str, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.risk_workspace(risk_case_id))


@router.post("/risk-cases/{risk_case_id}/sources", response_model=ResponseEnvelope[RiskCaseResponse])
async def append_risk_sources(risk_case_id: str, payload: RiskSourcesAppend, svc=Depends(service)):
    data = await svc.append_risk_sources(risk_case_id, payload.source_record_ids)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/risk-cases/{risk_case_id}/reviews", response_model=ResponseEnvelope[RiskAssessmentResponse])
async def review_risk(risk_case_id: str, payload: RiskReviewRequest, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.review_risk(risk_case_id, payload))


@router.get("/risk-assessments/{assessment_id}", response_model=ResponseEnvelope[RiskAssessmentResponse])
async def get_assessment(assessment_id: str, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.get_assessment(assessment_id))


def demo_service(current=Depends(get_current_user), db=Depends(get_db)):
    from app.services.demo_risk_workflow_service import DemoRiskWorkflowService
    return DemoRiskWorkflowService(db, current)


def risk_collaboration_service(current=Depends(get_current_user), db=Depends(get_db)):
    from app.services.risk_collaboration_service import RiskCollaborationService
    return RiskCollaborationService(db, current)


def demo_sampling_service(current=Depends(get_current_user), db=Depends(get_db)):
    from app.services.demo_sampling_service import DemoSamplingService
    return DemoSamplingService(db, current)


def risk_lab_service(current=Depends(get_current_user), db=Depends(get_db)):
    from app.services.risk_lab_service import RiskLabService
    return RiskLabService(db, current)


def risk_report_service(current=Depends(get_current_user), db=Depends(get_db)):
    from app.services.risk_report_service import RiskReportService
    return RiskReportService(db, current)


@router.get("/risk-cases/{case_id}/laboratory-options")
async def risk_lab_options(case_id: UUID, svc=Depends(risk_lab_service)):
    return ResponseEnvelope(data=await svc.options(str(case_id)))


@router.get("/risk-cases/{case_id}/laboratory-verifications")
async def risk_lab_list(case_id: UUID, svc=Depends(risk_lab_service)):
    return ResponseEnvelope(data=await svc.list(str(case_id)))


@router.get('/risk-cases/{case_id}/laboratory-{kind}-options')
async def risk_lab_option_page(case_id: UUID, kind: Literal['tasks', 'records'], page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=50),
    keyword: str = Query('', max_length=200), selected_ids: list[UUID] = Query(default=[], max_length=20), svc=Depends(risk_lab_service)):
    return ResponseEnvelope(data=await svc.option_page(str(case_id), kind, page=page, size=size, keyword=keyword, selected_ids=selected_ids))


@router.post("/risk-cases/{case_id}/laboratory-verifications")
async def risk_lab_decide(case_id: UUID, payload: LabDecision, svc=Depends(risk_lab_service)):
    data = await svc.decide(str(case_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/risk-laboratory-verifications/{link_id}/evidence")
async def risk_lab_return(link_id: UUID, payload: LabReturn, svc=Depends(risk_lab_service)):
    data = await svc.return_records(str(link_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get('/risk-laboratory-verifications/{link_id}/execution-results')
async def risk_lab_execution_candidates(link_id: UUID, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=50), svc=Depends(risk_lab_service)):
    return ResponseEnvelope(data=await svc.execution_candidates(str(link_id), page=page, size=size))


@router.post('/risk-laboratory-verifications/{link_id}/execution-results')
async def risk_lab_execution_return(link_id: UUID, payload: LabExecutionReturn, svc=Depends(risk_lab_service)):
    data = await svc.return_execution(str(link_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post('/risk-laboratory-verifications/{link_id}/execution-results/{return_id}/withdraw')
async def risk_lab_execution_withdraw(link_id: UUID, return_id: UUID, payload: LabExecutionWithdraw, svc=Depends(risk_lab_service)):
    data = await svc.withdraw_execution(str(link_id), str(return_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/risk-reports")
async def risk_report_list(case_id: UUID | None = None, svc=Depends(risk_report_service)):
    return ResponseEnvelope(data=await svc.list(str(case_id) if case_id else None), warnings=[{
        'code':'bounded_legacy_list', 'message':'旧列表最多返回 50 条摘要；完整浏览请使用 /risk-report-pages 分页接口。'}])


@router.get('/risk-report-pages')
async def risk_report_page(case_id: UUID | None = None, size: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None, max_length=2048), keyword: str = Query('', max_length=200), svc=Depends(risk_report_service)):
    return ResponseEnvelope(data=await svc.page(str(case_id) if case_id else None, size=size, cursor=cursor, keyword=keyword))


@router.get("/risk-reports/{report_id}")
async def risk_report_get(report_id: UUID, svc=Depends(risk_report_service)):
    return ResponseEnvelope(data=await svc.get(str(report_id)))


@router.post("/risk-cases/{case_id}/reports")
async def risk_report_create(case_id: UUID, payload: RiskReportCreate, svc=Depends(risk_report_service)):
    data = await svc.create(str(case_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/risk-reports/{report_id}/exports")
async def risk_report_export(report_id: UUID, payload: RiskReportExport, svc=Depends(risk_report_service)):
    from app.services.export_job_service import ExportJobService
    from app.schemas.governance import ExportJobResponse
    item = await ExportJobService(svc.db, svc.org_id, actor_user_id=svc.actor, actor_role=svc.current.role).create_job(svc.actor,
        {"report_type": "risk_assessment", "format": payload.format, "config_json": {"risk_report_id": str(report_id)}})
    return ResponseEnvelope(data=ExportJobResponse.model_validate(item))


@router.get("/demo-sampling/candidates")
@router.get("/risk-sampling/candidates")
async def demo_sampling_candidates(case_id: UUID | None = None, svc=Depends(demo_sampling_service)):
    return ResponseEnvelope(data=await svc.candidates(str(case_id) if case_id else None))


@router.get("/demo-sampling/suggestions")
@router.get("/risk-sampling/suggestions")
async def demo_sampling_list(case_id: UUID | None = None, svc=Depends(demo_sampling_service)):
    return ResponseEnvelope(data=await svc.list(str(case_id) if case_id else None))


@router.get("/demo-sampling/suggestions/{suggestion_id}")
@router.get("/risk-sampling/suggestions/{suggestion_id}")
async def demo_sampling_get(suggestion_id: UUID, svc=Depends(demo_sampling_service)):
    return ResponseEnvelope(data=await svc.get(str(suggestion_id)))


@router.post("/risk-cases/{risk_case_id}/demo-sampling-suggestions")
@router.post("/risk-cases/{risk_case_id}/risk-sampling-suggestions")
async def demo_sampling_create(risk_case_id: UUID, payload: DemoSamplingCreate, svc=Depends(demo_sampling_service)):
    data = await svc.create(str(risk_case_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.patch("/demo-sampling/suggestions/{suggestion_id}")
@router.patch("/risk-sampling/suggestions/{suggestion_id}")
async def demo_sampling_save(suggestion_id: UUID, payload: DemoSamplingSave, svc=Depends(demo_sampling_service)):
    data = await svc.mutate(str(suggestion_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/demo-sampling/suggestions/{suggestion_id}/confirm")
@router.post("/risk-sampling/suggestions/{suggestion_id}/confirm")
async def demo_sampling_confirm(suggestion_id: UUID, payload: DemoSamplingConfirm, svc=Depends(demo_sampling_service)):
    data = await svc.mutate(str(suggestion_id), payload, confirm=True)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/risk-collaborations/participants")
async def risk_collaboration_participants(svc=Depends(risk_collaboration_service)):
    return ResponseEnvelope(data=await svc.candidates())


@router.get("/risk-cases/{risk_case_id}/collaborations")
async def list_risk_collaborations(risk_case_id: UUID, svc=Depends(risk_collaboration_service)):
    return ResponseEnvelope(data=await svc.list_for_case(str(risk_case_id)))


@router.post("/risk-cases/{risk_case_id}/collaborations")
async def create_risk_collaboration(risk_case_id: UUID, payload: RiskCollaborationCreate, svc=Depends(risk_collaboration_service)):
    data = await svc.create(str(risk_case_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.get("/risk-collaborations/{collaboration_id}")
async def get_risk_collaboration(collaboration_id: UUID, svc=Depends(risk_collaboration_service)):
    return ResponseEnvelope(data=await svc.get(str(collaboration_id)))


@router.post("/risk-cases/{risk_case_id}/demo-drafts", response_model=ResponseEnvelope[RiskAssessmentResponse])
async def create_demo_draft(risk_case_id: UUID, payload: DemoDraftCreate, svc=Depends(demo_service)):
    data = await svc.create(str(risk_case_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.patch("/risk-cases/{risk_case_id}/demo-drafts/{assessment_id}", response_model=ResponseEnvelope[RiskAssessmentResponse])
async def save_demo_draft(risk_case_id: UUID, assessment_id: UUID, payload: DemoDraftSave, svc=Depends(demo_service)):
    data = await svc.save(str(risk_case_id), str(assessment_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/risk-cases/{risk_case_id}/demo-drafts/{assessment_id}/submit", response_model=ResponseEnvelope[RiskAssessmentResponse])
async def submit_demo_draft(risk_case_id: UUID, assessment_id: UUID, payload: DemoDraftSubmit, svc=Depends(demo_service)):
    data = await svc.submit(str(risk_case_id), str(assessment_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


@router.post("/risk-cases/{risk_case_id}/demo-drafts/{assessment_id}/review", response_model=ResponseEnvelope[RiskAssessmentResponse])
async def review_demo_draft(risk_case_id: UUID, assessment_id: UUID, payload: DemoDraftReview, svc=Depends(demo_service)):
    data = await svc.review(str(risk_case_id), str(assessment_id), payload)
    await svc.db.commit()
    return ResponseEnvelope(data=data)


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
