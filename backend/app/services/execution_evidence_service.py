"""Current, tenant-scoped provenance checks shared by execution and risk review.

Checks establish source availability and lineage. They never certify a PDF's
transcribed value, nor turn a complaint into a laboratory finding.
"""
import asyncio
import hashlib
from datetime import datetime, timezone
from io import BytesIO

from pypdf import PdfReader
from sqlalchemy import select

from app.core.datetime import utcnow
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import has_permission
from app.models.quality_risk import QualityAttachment, QualitySourceRecord
from app.models.supervision import MeasurementRecord, SupervisionRecord, SupervisionRevision
from app.services.knowledge_source_service import fingerprint
from app.services.object_storage.factory import build_object_storage

VALIDATOR_VERSION = "execution-evidence-v1"


def parsed_time(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(timezone.utc).replace(tzinfo=None) if result.tzinfo else result
    except (ValueError, TypeError):
        return None


def blocker(code, message, observation=None):
    return {"code": code, "message": message, "evidence_id": (observation or {}).get("evidence_id")}


class ExecutionEvidenceService:
    def __init__(self, session, current, storage=None, *, review_owner=None, review_attachment_ids=(),review_permission="inspection_execution_review"):
        self.session, self.current = session, current
        self.org_id = current.org_id
        self.storage = storage or build_object_storage()
        self._files = {}
        self.review_owner, self.review_attachment_ids = review_owner, set(review_attachment_ids)
        self.review_permission=review_permission

    def record_authorized(self, record):
        return record.created_by == self.current.user_id or (
            record.authorization_scope in {"organization", "business", "public"}
            and has_permission("quality_material_read_business", self.current.role))

    async def attachment(self, attachment_id):
        row = await self.session.scalar(select(QualityAttachment).where(
            QualityAttachment.id == attachment_id, QualityAttachment.org_id == self.org_id,
            QualityAttachment.deleted_at.is_(None)).execution_options(populate_existing=True))
        if not row:
            raise NotFoundError("报告不存在或不在授权范围")
        if row.uploaded_by != self.current.user_id:
            if row.id in self.review_attachment_ids and row.uploaded_by == self.review_owner and has_permission(self.review_permission,self.current.role):
                return row
            records = (await self.session.scalars(select(QualitySourceRecord).where(
                QualitySourceRecord.org_id == self.org_id, QualitySourceRecord.deleted_at.is_(None)))).all()
            if not any(row.id in (r.attachment_ids or []) and self.record_authorized(r) for r in records):
                raise NotFoundError("报告未授权给当前业务范围，请先通过资料接入明确共享")
        return row

    async def file(self, attachment_id, *, pdf=False):
        row = await self.attachment(attachment_id)
        key = (row.id, row.sha256, pdf)
        if key not in self._files:
            try:
                result = await asyncio.to_thread(self.storage.get_bytes, bucket=row.bucket, object_key=row.object_key)
            except Exception:
                raise ValidationError("原报告暂时不可取得，不能确认引用结果") from None
            if not result:
                raise ValidationError("报告只有附件记录，缺少实际原件")
            content, mime = result
            checksum = hashlib.sha256(content).hexdigest()
            if checksum != row.sha256 or len(content) != row.size_bytes:
                raise ValidationError("报告原件哈希或大小与登记来源不一致")
            pages = None
            if pdf or row.mime_type=="application/pdf":
                if row.mime_type != "application/pdf" or not content.lstrip().startswith(b"%PDF-"):
                    raise ValidationError("引用原件不是有效 PDF 检测报告")
                try:
                    reader = PdfReader(BytesIO(content))
                    if reader.is_encrypted:
                        raise ValueError("encrypted")
                    pages = len(reader.pages)
                    if not pages:
                        raise ValueError("empty")
                except Exception:
                    raise ValidationError("报告 PDF 无法读取或需要密码，需补充可核对原件") from None
            self._files[key] = (row, content, {"attachment_id": row.id, "sha256": checksum, "page_count": pages})
        return self._files[key]

    async def report(self, obs):
        row, _, context = await self.file(obs["attachment_id"], pdf=True)
        if row.sha256 != obs.get("source_version"):
            raise ValidationError("报告登记版本与执行快照不一致")
        page = obs.get("report_page")
        if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= context["page_count"]:
            raise ValidationError("报告页码超出原 PDF 的实际范围")
        if not str(obs.get("report_item") or "").strip() or obs.get("value") is None:
            raise ValidationError("报告引用缺少原文项目和转录值")
        # Copies, page aliases and arbitrary item labels do not create new trials.
        # Multiple independent trials must have independent measurement provenance.
        identity = fingerprint({"file": row.sha256, "sample": obs["sample_id"], "indicator": obs["measurement_key"]})
        return {**context, "observation_identity": identity, "report_page": page,
                "report_item": obs["report_item"], "transcription_verified": False}

    async def measurement(self, obs, task_id, session_id):
        issues = []
        def add(code, message):
            issues.append(blocker(code, message, obs))
        row = await self.session.scalar(select(MeasurementRecord).where(
            MeasurementRecord.id == obs["evidence_id"], MeasurementRecord.org_id == self.org_id)
            .execution_options(populate_existing=True))
        if not row:
            return [blocker("measurement_missing", "测量原始记录不存在", obs)], {}
        data = row.data or {}
        if row.validation_status != "accepted" or data.get("quality_flag") != "valid":
            add("measurement_unverified", "测量质量或接收状态未通过核验")
        if fingerprint(data) != obs.get("source_version"):
            add("measurement_changed", "测量数据与冻结版本不一致")
        if row.content_hash!=fingerprint(data):
            add("measurement_hash", "测量原始内容与接收时的哈希不一致")
        if row.event_id!=obs.get("event_id") or row.calibration_version!=obs.get("calibration_version"):
            add("measurement_lineage_changed", "测量试次或登记校准版本与冻结来源不一致")
        if str(row.sample_id) != obs.get("sample_id") or data.get("item") != obs.get("measurement_key") or str(row.device_id) != obs.get("device_id"):
            add("measurement_binding", "测量样品、设备或项目与引用不一致")
        ids = {str(row.session_id), str(row.sample_id), str(row.device_id)}
        entities = (await self.session.scalars(select(SupervisionRecord).where(
            SupervisionRecord.org_id == self.org_id, SupervisionRecord.id.in_(ids))
            .execution_options(populate_existing=True))).all()
        by_id = {r.id: r for r in entities}
        session, sample, device = (by_id.get(str(i)) for i in (row.session_id, row.sample_id, row.device_id))
        if not session or session.kind != "inspection-sessions" or row.session_id != session_id or session.data.get("task_id") != task_id:
            add("session_binding", "测量会话未绑定本次任务")
        elif str(row.sample_id) not in session.data.get("sample_ids", []) or str(row.device_id) not in session.data.get("device_ids", []):
            add("session_membership", "测量样品或设备不在会话范围")
        measured = parsed_time(data.get("measured_at"))
        if not measured or measured > utcnow():
            add("measurement_time", "缺少有效的实际测量时间")
        if not sample or sample.kind != "samples":
            add("sample_missing", "未找到该测量的样品档案，外部样品请引用原检测报告")
        else:
            sampled = parsed_time(sample.data.get("sampled_at"))
            if not sampled or (measured and sampled > measured):
                add("sample_time", "样品采样时间缺失或晚于测量时间")
            if sample.data.get("task_id") != task_id:
                add("sample_task", "样品档案与当前任务不一致")
        calibration = None
        if not device or device.kind != "devices":
            add("device_missing", "未找到测量设备档案，不能以读数接收状态代替来源核验")
        elif measured:
            revisions = (await self.session.scalars(select(SupervisionRevision).where(
                SupervisionRevision.org_id == self.org_id, SupervisionRevision.record_id == device.id,
                SupervisionRevision.created_at <= measured).order_by(SupervisionRevision.version.desc()))).all()
            historical = revisions[0].snapshot if revisions else None
            updated=parsed_time(device.updated_at)
            if not historical and updated and updated <= measured:
                historical = {"version": device.version, "status": device.status, "data": device.data}
            if not historical:
                add("calibration_history", "缺少测量时的设备及校准版本记录")
            else:
                device_data = historical.get("data") or {}
                expires = parsed_time(device_data.get("calibration_expires_at"))
                if historical.get("status") != "active" or device_data.get("calibration_status") != "valid" or not expires or expires < measured:
                    add("calibration_invalid", "测量时设备未启用、校准状态无效或已超出有效期")
                if data.get("item") not in (device_data.get("capabilities") or []):
                    add("device_capability", "测量项目不在设备已登记能力范围")
                versions = {str(historical.get("version")), str(device_data.get("baseline_version") or "")}
                if row.calibration_version and row.calibration_version not in versions:
                    add("calibration_version", "测量登记的校准版本与测量时档案不一致")
                calibration = {"device_id": device.id, "version": historical.get("version"),
                    "definition_hash": fingerprint(historical), "expires_at": device_data.get("calibration_expires_at")}
        context = {"evidence_id": row.id, "source_version": fingerprint(data), "measured_at": data.get("measured_at"),
            "calibration": calibration, "observation_identity": fingerprint({"org": self.org_id,
                "device":str(row.device_id),"sample":str(row.sample_id),"item":data.get("item"),
                "measured_at":measured.isoformat() if measured else None})}
        if obs.get("source_context") and obs["source_context"].get("calibration") != calibration:
            add("calibration_changed", "测量时校准依据与冻结来源不一致")
        return issues, context

    async def validate(self, observations, task_id, session_id):
        issues, sources = [], []
        for obs in observations:
            if obs["kind"] == "measurement_record":
                errors, context = await self.measurement(obs, task_id, session_id)
                issues.extend(errors)
            else:
                try:
                    context = await self.report(obs)
                except (NotFoundError, ValidationError) as exc:
                    issues.append(blocker("report_source", exc.message, obs));context = {}
            sources.append({"evidence_id": obs["evidence_id"], "kind": obs["kind"], **context})
        return {"validator_version": VALIDATOR_VERSION, "checked_at": utcnow().isoformat(),
            "blockers": issues, "uncertainties": [], "sources": sources}
