from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from sqlalchemy import select

from app.api.v1.deps import get_current_user, get_db
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.supervision import (
    DeviceConnection,
    SupervisionRecord,
    SupervisionRun,
    SupervisionRevision,
)
from app.schemas.common import ResponseEnvelope
from app.schemas.supervision import (
    DATA_SCHEMAS,
    AdaptiveDecisionReview,
    AgentConfigUpdate,
    FeedbackData,
    InspectionGoalCreate,
    MeasurementIngest,
    NextTestDecisionCreate,
    RecordCreate,
    RecordUpdate,
    ReviewDecision,
    ReviewRequest,
    RunRequest,
    StopDecisionCreate,
)
from app.schemas.user import CurrentUser
from pydantic import BaseModel, Field
from app.services.supervision_service import SupervisionService, serialize
from app.services.adaptive_inspection_service import AdaptiveInspectionService

router = APIRouter()


class ManualAssessment(BaseModel):
    version: int = Field(ge=1)
    risk_level: str
    evidence_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=8000)


class CalibrationEvaluation(BaseModel):
    dataset_id: UUID
    predictions: list[float] = Field(min_length=1, max_length=10000)
    outcomes: list[int] = Field(min_length=1, max_length=10000)


class DatasetEnrollment(BaseModel):
    dataset_id: UUID


async def service(current=Depends(get_current_user), db=Depends(get_db)):
    svc = SupervisionService(db, current)
    await svc.permissions()
    return svc


@router.get("/quality-supervision/settings")
async def settings(svc=Depends(service)):
    return ResponseEnvelope(
        data={"enabled": await svc.enabled(), "permissions": await svc.permissions()}
    )


@router.get("/quality-supervision/assignees")
async def assignees(svc=Depends(service)):
    from app.models.user import User

    svc.require_role({"admin", "user", "expert"})
    users = await svc.db.scalars(
        select(User).where(
            User.org_id == svc.org_id, User.is_active.is_(True), User.role.in_(["user", "expert"])
        )
    )
    return ResponseEnvelope(data=[{"value": u.id, "label": u.username} for u in users])


@router.get("/quality-supervision/agent-config")
async def get_agent_config(svc=Depends(service)):
    svc.require_role({"admin", "app_developer", "platform_operator"})
    from agent.subgraphs.supervision.agents import AGENTS

    return ResponseEnvelope(data={name: await svc.agent_config(name) for name in AGENTS})


@router.patch("/quality-supervision/agent-config")
async def update_agent_config(payload: AgentConfigUpdate, svc=Depends(service)):
    from app.models.organization import Organization

    svc.require_role({"admin", "app_developer"})
    org = await svc.db.scalar(
        select(Organization).where(Organization.id == svc.org_id).with_for_update()
    )
    if not org:
        raise NotFoundError("组织不存在")
    settings = dict(org.settings or {})
    settings["supervision_agent_options"] = {
        **settings.get("supervision_agent_options", {}),
        **{k: v.model_dump() for k, v in payload.agents.items()},
    }
    org.settings = settings
    return ResponseEnvelope(data=settings["supervision_agent_options"])


@router.post("/risk-cases/{record_id}/manual-assessment")
async def manual_assessment(record_id: UUID, payload: ManualAssessment, svc=Depends(service)):
    await svc.require_enabled()
    return ResponseEnvelope(
        data=await svc.manual_assessment(
            str(record_id),
            payload.version,
            payload.risk_level,
            payload.evidence_ids,
            payload.reason,
        )
    )


@router.post("/risk-cases/{record_id}/reassessment")
async def reassessment(record_id: UUID, svc=Depends(service)):
    await svc.require_enabled()
    return ResponseEnvelope(data=await svc.reassessment("risk-cases", str(record_id)))


@router.get("/quality-supervision/dataset-targets")
async def dataset_targets(svc=Depends(service)):
    from app.models.dataset import Dataset

    svc.require_role({"user", "expert"})
    rows = await svc.db.scalars(
        select(Dataset).where(
            Dataset.org_id == svc.org_id, Dataset.status == "active", Dataset.deleted_at.is_(None)
        )
    )
    return ResponseEnvelope(data=[{"value": d.id, "label": d.name} for d in rows])


@router.post("/inspection-sessions/{session_id}/dataset-enrollments")
async def enroll_dataset(session_id: UUID, payload: DatasetEnrollment, svc=Depends(service)):
    await svc.require_enabled()
    return ResponseEnvelope(data=await svc.enroll_dataset(str(session_id), str(payload.dataset_id)))


@router.get("/quality-supervision/dataset-enrollments")
async def enrolled_samples(svc=Depends(service)):
    svc.require_role({"algorithm_engineer"})
    rows = await svc.db.scalars(
        select(SupervisionRecord).where(
            SupervisionRecord.org_id == svc.org_id,
            SupervisionRecord.kind == "dataset-enrollments",
            SupervisionRecord.status == "authorized",
        )
    )
    return ResponseEnvelope(
        data=[serialize(r) for r in rows if r.data["dataset_owner_id"] == svc.actor]
    )


@router.get("/inspection-sessions/{session_id}/pending-measurements")
async def pending_measurements(session_id: UUID, svc=Depends(service)):
    from app.models.supervision import MeasurementBatch

    await svc.get("inspection-sessions", str(session_id))
    rows = await svc.db.scalars(
        select(MeasurementBatch).where(
            MeasurementBatch.org_id == svc.org_id, MeasurementBatch.session_id == str(session_id)
        )
    )
    return ResponseEnvelope(
        data=[
            {"batch_id": r.id, "source_key": r.source_key, "errors": r.raw.get("errors", [])}
            for r in rows
            if r.raw.get("status") == "pending"
        ]
    )


@router.post("/inspection-sessions/{session_id}/goals")
async def create_inspection_goal(
    session_id: UUID, payload: InspectionGoalCreate, svc=Depends(service)
):
    adaptive = AdaptiveInspectionService(svc.db, svc.current)
    return ResponseEnvelope(data=await adaptive.create_goal(str(session_id), payload))


@router.get("/inspection-sessions/{session_id}/goal")
async def get_inspection_goal(session_id: UUID, svc=Depends(service)):
    adaptive = AdaptiveInspectionService(svc.db, svc.current)
    return ResponseEnvelope(data=await adaptive.get_goal(str(session_id)))


@router.get("/inspection-sessions/{session_id}/evidence-state")
async def get_inspection_evidence_state(session_id: UUID, svc=Depends(service)):
    adaptive = AdaptiveInspectionService(svc.db, svc.current)
    return ResponseEnvelope(data=await adaptive.get_latest_evidence_state(str(session_id)))


@router.post("/inspection-sessions/{session_id}/next-test-decisions")
async def propose_next_test(
    session_id: UUID, payload: NextTestDecisionCreate, svc=Depends(service)
):
    adaptive = AdaptiveInspectionService(svc.db, svc.current)
    return ResponseEnvelope(data=await adaptive.propose_next_test(str(session_id), payload))


@router.post("/inspection-sessions/{session_id}/stop-decisions")
async def propose_stop_decision(
    session_id: UUID, payload: StopDecisionCreate, svc=Depends(service)
):
    adaptive = AdaptiveInspectionService(svc.db, svc.current)
    return ResponseEnvelope(data=await adaptive.propose_stop(str(session_id), payload))


@router.post(
    "/inspection-sessions/{session_id}/stop-decisions/{decision_id}/decision"
)
async def review_stop_decision(
    session_id: UUID,
    decision_id: UUID,
    payload: AdaptiveDecisionReview,
    svc=Depends(service),
):
    adaptive = AdaptiveInspectionService(svc.db, svc.current)
    return ResponseEnvelope(
        data=await adaptive.review_stop_decision(
            str(session_id),
            str(decision_id),
            approve=payload.decision == "approve",
            comment=payload.comment,
        )
    )


@router.patch("/quality-supervision/settings")
async def change_settings(enabled: bool, svc=Depends(service)):
    from app.models.organization import Organization

    svc.require_role({"admin"})
    org = await svc.db.get(Organization, svc.org_id)
    if not org:
        raise NotFoundError("组织不存在")
    org.settings = {**(org.settings or {}), "quality_supervision_enabled": enabled}
    await svc.db.flush()
    return ResponseEnvelope(data={"enabled": enabled})


def register_records(kind):
    async def list_records(
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=200),
        keyword: str | None = None,
        region_id: UUID | None = None,
        status: str | None = None,
        svc=Depends(service),
    ):
        await svc.require_enabled()
        return ResponseEnvelope(
            data=await svc.list(
                kind, page, size, keyword, str(region_id) if region_id else None, status
            )
        )

    async def create_record(payload: RecordCreate, svc=Depends(service)):
        return ResponseEnvelope(data=await svc.create(kind, payload))

    async def get_record(record_id: UUID, svc=Depends(service)):
        await svc.require_enabled()
        return ResponseEnvelope(data=serialize(await svc.get(kind, str(record_id))))

    async def update_record(record_id: UUID, payload: RecordUpdate, svc=Depends(service)):
        return ResponseEnvelope(data=await svc.update(kind, str(record_id), payload))

    async def revisions(record_id: UUID, svc=Depends(service)):
        await svc.get(kind, str(record_id))
        rows = list(
            await svc.db.scalars(
                select(SupervisionRevision)
                .where(
                    SupervisionRevision.org_id == svc.org_id,
                    SupervisionRevision.record_id == str(record_id),
                )
                .order_by(SupervisionRevision.version.desc())
            )
        )
        return ResponseEnvelope(
            data=[
                {
                    "version": r.version,
                    "action": r.action,
                    "actor_id": r.actor_id,
                    "snapshot": r.snapshot,
                    "created_at": r.created_at,
                }
                for r in rows
            ]
        )

    for suffix, endpoint, methods in (
        ("", list_records, ["GET"]),
        ("", create_record, ["POST"]),
        ("/{record_id}", get_record, ["GET"]),
        ("/{record_id}", update_record, ["PATCH"]),
        ("/{record_id}/revisions", revisions, ["GET"]),
    ):
        router.add_api_route(
            f"/{kind}{suffix}", endpoint, methods=methods, name=f"{kind}_{endpoint.__name__}"
        )
    if kind in {"risk-cases", "sampling-plans", "inspection-sessions"}:

        async def run(record_id: UUID, payload: RunRequest, svc=Depends(service)):
            result = await svc.queue_run(kind, str(record_id), payload)
            await svc.db.commit()
            if result["status"] == "queued":
                try:
                    from worker.tasks.supervision_task import execute_supervision_run

                    execute_supervision_run.delay(result["id"], svc.org_id)
                except Exception:
                    # Durable queued run is picked up by periodic dispatcher, never silently run in process.
                    result["dispatch_status"] = "awaiting_worker"
            return ResponseEnvelope(data=result)

        async def submit_review(record_id: UUID, payload: ReviewRequest, svc=Depends(service)):
            await svc.require_enabled()
            return ResponseEnvelope(data=await svc.submit_review(kind, str(record_id), payload))

        async def feedback(record_id: UUID, payload: FeedbackData, svc=Depends(service)):
            await svc.require_enabled()
            return ResponseEnvelope(data=await svc.feedback(kind, str(record_id), payload))

        router.add_api_route(
            f"/{kind}/{{record_id}}/runs", run, methods=["POST"], name=f"{kind}_run"
        )
        router.add_api_route(
            f"/{kind}/{{record_id}}/reviews", submit_review, methods=["POST"], name=f"{kind}_review"
        )
        router.add_api_route(
            f"/{kind}/{{record_id}}/feedback", feedback, methods=["POST"], name=f"{kind}_feedback"
        )


for _kind in DATA_SCHEMAS:
    register_records(_kind)


@router.get("/supervision-runs/{run_id}")
async def get_run(run_id: UUID, svc=Depends(service)):
    run = await svc.db.scalar(
        select(SupervisionRun).where(
            SupervisionRun.id == str(run_id), SupervisionRun.org_id == svc.org_id
        )
    )
    if not run:
        raise NotFoundError("运行不存在")
    record = await svc.db.get(SupervisionRecord, run.record_id)
    svc.read_access(record.kind)
    return ResponseEnvelope(data=svc.run_response(run))


@router.post("/supervision-runs/{run_id}/retry")
async def retry_run(run_id: UUID, svc=Depends(service)):
    run = await svc.db.scalar(
        select(SupervisionRun)
        .where(SupervisionRun.id == str(run_id), SupervisionRun.org_id == svc.org_id)
        .with_for_update()
    )
    if not run:
        raise NotFoundError("运行不存在")
    record = await svc.get((await svc.db.get(SupervisionRecord, run.record_id)).kind, run.record_id)
    svc.edit_access(record)
    if run.status != "failed" or run.iteration >= 2:
        raise ValidationError("仅未超过两轮上限的失败运行可重试")
    run.status = "queued"
    return ResponseEnvelope(data=svc.run_response(run))


@router.post("/supervision-runs/{run_id}/cancel")
async def cancel_run(run_id: UUID, svc=Depends(service)):
    run = await svc.db.scalar(
        select(SupervisionRun)
        .where(SupervisionRun.id == str(run_id), SupervisionRun.org_id == svc.org_id)
        .with_for_update()
    )
    if not run or run.created_by != svc.actor:
        raise ForbiddenError("仅发起人可取消")
    if run.status in {"queued", "running", "failed"}:
        run.status = "cancelled"
    return ResponseEnvelope(data=svc.run_response(run))


@router.get("/business-reviews")
async def todos(svc=Depends(service)):
    await svc.require_enabled()
    return ResponseEnvelope(data=await svc.todos())


@router.post("/business-reviews/{review_id}/decision")
async def decision(review_id: UUID, payload: ReviewDecision, svc=Depends(service)):
    return ResponseEnvelope(data=await svc.review_decision(str(review_id), payload))


@router.post("/devices/{device_id}/connection")
async def connection(device_id: UUID, svc=Depends(service)):
    await svc.require_enabled()
    return ResponseEnvelope(data=await svc.rotate_connection(str(device_id)))


@router.patch("/devices/{device_id}/runtime")
async def runtime(device_id: UUID, payload: dict, svc=Depends(service)):
    await svc.require_enabled()
    return ResponseEnvelope(data=await svc.device_status(str(device_id), payload))


@router.get("/inspection-sessions/{session_id}/measurements")
async def measurements(session_id: UUID, svc=Depends(service)):
    from app.models.supervision import MeasurementRecord

    await svc.get("inspection-sessions", str(session_id))
    rows = list(
        await svc.db.scalars(
            select(MeasurementRecord).where(
                MeasurementRecord.session_id == str(session_id),
                MeasurementRecord.org_id == svc.org_id,
            )
        )
    )
    return ResponseEnvelope(data=[r.data for r in rows])


@router.post("/inspection-sessions/{session_id}/measurements")
async def ingest_manual(session_id: UUID, payload: MeasurementIngest, svc=Depends(service)):
    if payload.session_id != session_id:
        raise ValidationError("会话编号不匹配")
    return ResponseEnvelope(data=await svc.ingest_or_pending(payload))


@router.post("/inspection-sessions/{session_id}/imports/preview")
async def preview(
    session_id: UUID, file: UploadFile = File(...), mapping: str = Form("{}"), svc=Depends(service)
):
    try:
        fields = json.loads(mapping)
        if not isinstance(fields, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in fields.items()
        ):
            raise ValueError()
        fields = {k: v.strip() for k, v in fields.items() if v.strip()}
    except ValueError:
        raise ValidationError("字段映射必须为JSON对象")
    content = await file.read(10 * 1024 * 1024 + 1)
    return ResponseEnvelope(
        data=await svc.preview_file(str(session_id), file.filename or "", content, fields)
    )


@router.post("/inspection-sessions/{session_id}/imports/confirm")
async def confirm(
    session_id: UUID,
    preview_id: UUID,
    source_key: str = Query(min_length=1, max_length=128),
    svc=Depends(service),
):
    return ResponseEnvelope(
        data=await svc.confirm_file(str(session_id), str(preview_id), source_key)
    )


@router.get("/quality-supervision/measurement-template")
async def template(svc=Depends(service)):
    from fastapi.responses import Response

    svc.require_role({"user", "expert", "algorithm_engineer", "admin"})
    content = "event_id,sample_id,device_id,item,measured_at,value,unit,method,quality_flag\n"
    return Response(
        content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=measurements.csv"},
    )


@router.post("/device-ingest/measurements")
async def ingest_device(
    payload: MeasurementIngest, x_device_token: str = Header(...), db=Depends(get_db)
):
    conn = await db.scalar(
        select(DeviceConnection)
        .where(
            DeviceConnection.token_hash == hashlib.sha256(x_device_token.encode()).hexdigest(),
            DeviceConnection.status == "active",
        )
        .with_for_update()
    )
    if not conn:
        raise ForbiddenError("设备连接凭据无效或已撤销")
    svc = SupervisionService(
        db, CurrentUser(user_id=conn.device_id, org_id=conn.org_id, role="user")
    )
    return ResponseEnvelope(data=await svc.ingest_or_pending(payload, device_id=conn.device_id))


@router.get("/quality-supervision/analytics")
async def analytics(svc=Depends(service)):
    svc.require_role({"admin", "user", "expert", "platform_operator"})
    await svc.require_enabled()

    rows = list(
        await svc.db.scalars(
            select(SupervisionRecord).where(
                SupervisionRecord.org_id == svc.org_id,
                SupervisionRecord.kind == "risk-cases",
                SupervisionRecord.status == "risk_assessed",
            )
        )
    )
    exposures = list(
        await svc.db.scalars(
            select(SupervisionRecord).where(
                SupervisionRecord.org_id == svc.org_id, SupervisionRecord.kind == "exposures"
            )
        )
    )
    report = await svc.execute_agent_via_manager(
        {
            "id": f"situation:{svc.org_id}",
            "kind": "risk-situation",
            "version": 1,
            "as_of": __import__("datetime").datetime.utcnow().isoformat(),
            "knowledge_snapshot_id": f"situation:{svc.org_id}",
            "cases": [serialize(r) for r in rows],
            "exposures": [serialize(r) for r in exposures],
        },
        "market_monitoring",
    )
    plans = list(
        await svc.db.scalars(
            select(SupervisionRecord).where(
                SupervisionRecord.org_id == svc.org_id, SupervisionRecord.kind == "sampling-plans"
            )
        )
    )
    sessions = list(
        await svc.db.scalars(
            select(SupervisionRecord).where(
                SupervisionRecord.org_id == svc.org_id,
                SupervisionRecord.kind == "inspection-sessions",
            )
        )
    )
    report.update(
        plans=[serialize(p) for p in plans],
        sessions=[serialize(s) for s in sessions],
        confirmed_categories=sorted(
            {
                c.data.get("product_category")
                for c in rows
                if c.status == "risk_assessed" and c.data.get("product_category")
            }
        ),
        metric_status="正式查验类别和响应压缩指标需以已签发任务及同口径人工基线统计",
    )
    names = {
        r.id: r.name
        for r in await svc.db.scalars(
            select(SupervisionRecord).where(
                SupervisionRecord.org_id == svc.org_id,
                SupervisionRecord.kind.in_(["regions", "enterprises"]),
            )
        )
    }
    for key in ("complaint_region_id", "sampling_region_id", "enterprise_id"):
        translated = {}
        for identity, count in report["dimensions"][key].items():
            name = names.get(identity, "未登记" if identity == "未登记" else "历史未关联资料")
            translated[name] = translated.get(name, 0) + count
        report["dimensions"][key] = translated
    return ResponseEnvelope(data=report)


@router.post("/quality-supervision/evaluations/calibration")
async def calibration(payload: CalibrationEvaluation, svc=Depends(service)):
    svc.require_role({"algorithm_engineer"})
    from app.models.algo_resources import EvaluationDataset

    dataset = await svc.db.scalar(
        select(EvaluationDataset).where(
            EvaluationDataset.id == str(payload.dataset_id),
            EvaluationDataset.org_id == svc.org_id,
            EvaluationDataset.deleted_at.is_(None),
        )
    )
    if not dataset:
        raise NotFoundError("评测集不存在或不属于当前组织")
    from app.services.supervision_evaluation import calibration_report

    try:
        report = calibration_report(payload.predictions, payload.outcomes)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    report["dataset_id"] = str(payload.dataset_id)
    return ResponseEnvelope(data=report)


def register_import(kind):
    async def import_preview(
        file: UploadFile = File(...), mapping: str = Form("{}"), svc=Depends(service)
    ):
        from app.services.supervision_imports import preview

        try:
            fields = json.loads(mapping)
            if not isinstance(fields, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in fields.items()
            ):
                raise ValueError()
            fields = {k: v.strip() for k, v in fields.items() if v.strip()}
        except ValueError:
            raise ValidationError("字段映射必须为对象")
        return ResponseEnvelope(
            data=await preview(
                svc, kind, file.filename or "", await file.read(10 * 1024 * 1024 + 1), fields
            )
        )

    async def import_confirm(preview_id: UUID, svc=Depends(service)):
        from app.services.supervision_imports import confirm

        await svc.require_enabled()
        return ResponseEnvelope(data=await confirm(svc, kind, str(preview_id)))

    router.add_api_route(
        f"/{kind}/imports/preview", import_preview, methods=["POST"], name=f"import_{kind}_preview"
    )
    router.add_api_route(
        f"/{kind}/imports/confirm", import_confirm, methods=["POST"], name=f"import_{kind}_confirm"
    )


for _import_kind in ("regions", "risk-cases"):
    register_import(_import_kind)
