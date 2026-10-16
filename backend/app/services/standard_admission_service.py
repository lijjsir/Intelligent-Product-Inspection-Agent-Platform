from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from agent.rag.knowledge_indexer import KnowledgeIndexer
from agent.rag.retriever import Retriever
from app.core.config import settings
from app.core.datetime import utcnow
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.models.inspection_standard_library import InspectionStandardLibrary, StandardDocument
from app.models.standard_admission import StandardAdmissionReview, StandardDocumentRevision, StandardSyncOutbox
from app.services.object_storage.factory import build_object_storage
from app.services.standard_candidate_extractor import extract_candidates, extract_metadata_candidates
from app.services.standard_pdf_importer import build_index_docs, extract_pdf_pages, resolve_standard_meta


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def normalize_standard_number(value: str) -> str:
    """Normalize separators that are commonly confused by Chinese PDF OCR.

    Standard numbers in scanned GB PDFs frequently render the ASCII hyphen as
    the Chinese character ``一``.  The normalization is used only for the
    identity check; the stored metadata and original page text remain intact.
    """
    return re.sub(r"[\s/_—–\-一－]", "", str(value or "")).upper()


def snapshot_document(doc):
    return {key: getattr(doc, key) for key in ["standard_no", "standard_name", "domain", "product_category",
        "standard_level", "standard_status", "file_name", "file_path", "file_hash", "file_size"]}


class StandardAdmissionService:
    def __init__(self, session, org_id, actor_id=None):
        if not org_id:
            raise ForbiddenError("标准准入必须有明确组织范围")
        self.session, self.org_id, self.actor_id = session, org_id, actor_id

    async def document(self, document_id, *, lock=False):
        q = select(StandardDocument).join(InspectionStandardLibrary, StandardDocument.library_id==InspectionStandardLibrary.id).where(
            StandardDocument.id==document_id, StandardDocument.org_id==self.org_id, StandardDocument.deleted_at.is_(None),
            InspectionStandardLibrary.org_id==self.org_id, InspectionStandardLibrary.deleted_at.is_(None))
        if lock:
            q = q.with_for_update().execution_options(populate_existing=True)
        doc = (await self.session.execute(q)).scalar_one_or_none()
        if not doc:
            raise NotFoundError("标准文件不存在或不在当前组织")
        return doc

    async def revision(self, document_id, revision_id, *, lock=False):
        doc = await self.document(document_id, lock=lock)
        q = select(StandardDocumentRevision).where(StandardDocumentRevision.id==revision_id,
            StandardDocumentRevision.document_id==doc.id, StandardDocumentRevision.org_id==self.org_id)
        if lock:
            q = q.with_for_update().execution_options(populate_existing=True)
        rev = (await self.session.execute(q)).scalar_one_or_none()
        if not rev:
            raise NotFoundError("标准修订不存在")
        return doc, rev

    async def list_revisions(self, document_id):
        doc = await self.document(document_id)
        rows = (await self.session.execute(select(StandardDocumentRevision).where(
            StandardDocumentRevision.document_id==doc.id, StandardDocumentRevision.org_id==self.org_id).order_by(
                StandardDocumentRevision.revision_no.desc()))).scalars().all()
        return [await self.serialize(row, details=False) for row in rows]

    async def detail(self, document_id, revision_id):
        _, rev = await self.revision(document_id, revision_id)
        return await self.serialize(rev)

    async def serialize(self, rev, *, details=True):
        result = {key: getattr(rev, key) for key in ["id", "document_id", "revision_no", "snapshot", "file_hash",
            "processing_status", "review_status", "publication_status", "extraction_status", "row_version", "index_generation",
            "created_by", "reviewed_by", "published_by", "created_at", "reviewed_at", "published_at", "review_assignment"]}
        result.update(page_count=len(rev.pages_json or []), candidate_count=len(rev.candidates_json or []),
            confirmed_count=sum(c.get("status")=="confirmed" for c in (rev.candidates_json or [])), issues=list(rev.issues_json or []))
        if details:
            result["metadata_candidates"]=extract_metadata_candidates(rev.pages_json or [])
            result["pages"] = rev.pages_json or []
            result["candidates"] = rev.candidates_json or []
            reviews = (await self.session.execute(select(StandardAdmissionReview).where(
                StandardAdmissionReview.org_id==self.org_id, StandardAdmissionReview.revision_id==rev.id).order_by(
                StandardAdmissionReview.created_at))).scalars().all()
            result["reviews"] = [{k: getattr(r, k) for k in ["id", "action", "actor_id", "reason", "evidence_refs", "detail_json", "created_at"]} for r in reviews]
            jobs = (await self.session.execute(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id,
                StandardSyncOutbox.org_id==self.org_id))).scalars().all()
            result["jobs"] = [{k: getattr(j, k) for k in ["id", "action", "status", "attempts", "error_message", "next_attempt_at"]} for j in jobs]
        return result

    async def enqueue(self, rev, action, generation="initial"):
        existing = (await self.session.execute(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id,
            StandardSyncOutbox.action==action, StandardSyncOutbox.generation==generation))).scalar_one_or_none()
        if not existing:
            self.session.add(StandardSyncOutbox(org_id=self.org_id, revision_id=rev.id, action=action, generation=generation))
        await self.session.flush()

    async def receive(self, library_id, files):
        library = (await self.session.execute(select(InspectionStandardLibrary).where(InspectionStandardLibrary.id==library_id,
            InspectionStandardLibrary.org_id==self.org_id, InspectionStandardLibrary.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
        if not library:
            raise NotFoundError("标准库不存在")
        if not 1 <= len(files) <= 20:
            raise ValidationError("每次接收1至20份PDF")
        for name, content, _ in files:
            if not name.lower().endswith(".pdf") or not content.startswith(b"%PDF-") or len(content)>50*1024*1024:
                raise ValidationError("仅接收有效PDF，单份不超过50MB；文件类型不等于标准资格")
        storage = build_object_storage()
        documents = []
        for name, content, _ in files:
            safe_name = Path(name.replace("\\", "/")).name[:255]
            file_hash = hashlib.sha256(content).hexdigest()
            existing = (await self.session.execute(select(StandardDocument).where(StandardDocument.org_id==self.org_id,
                StandardDocument.library_id==library_id, StandardDocument.file_hash==file_hash, StandardDocument.deleted_at.is_(None)))).scalars().first()
            if existing:
                documents.append(existing)
                continue
            meta = resolve_standard_meta(safe_name, source_file_name=safe_name, fallback_domain=library.domain,
                fallback_product_category=library.product_category)
            did, rid = str(uuid7()), str(uuid7())
            object_key = f"standard/{self.org_id}/{library_id}/{did}/{file_hash}.pdf"
            await asyncio.to_thread(storage.put_bytes, bucket=settings.rag_storage_bucket, object_key=object_key,
                data=content, content_type="application/pdf")
            doc = StandardDocument(id=did, org_id=self.org_id, library_id=library_id, file_name=safe_name,
                file_path=object_key, file_hash=file_hash, file_size=len(content), standard_no=meta["standard_no"],
                standard_name=meta["standard_name"], domain=meta["domain"], product_category=meta.get("product_category"),
                standard_level=meta["standard_level"], standard_status="待核实", qdrant_collection=settings.standard_published_collection,
                import_status="pending", current_revision_id=rid, processing_status="pending", review_status="pending", publication_status="unpublished")
            self.session.add(doc)
            await self.session.flush()
            conflicts = (await self.session.execute(select(StandardDocument.id).where(StandardDocument.org_id==self.org_id,
                StandardDocument.standard_no==doc.standard_no, StandardDocument.file_hash!=file_hash,
                StandardDocument.deleted_at.is_(None)))).scalars().all()
            snapshot = snapshot_document(doc)
            snapshot.update(resource_type="unverified", source_url="", publisher="", applicability={}, legacy=False,
                conflicts=[str(i) for i in conflicts])
            rev = StandardDocumentRevision(id=rid, org_id=self.org_id, document_id=did, revision_no=1, snapshot=snapshot,
                file_hash=file_hash, created_by=self.actor_id, issues_json=["待核对类型、来源及适用状态"] + (["同编号不同内容，须核对冲突"] if conflicts else []))
            self.session.add(rev)
            await self.session.flush()
            await self.enqueue(rev, "parse")
            documents.append(doc)
        library.pdf_count = (await self.session.execute(select(func.count()).select_from(StandardDocument).where(
            StandardDocument.library_id==library_id, StandardDocument.org_id==self.org_id, StandardDocument.deleted_at.is_(None)))).scalar_one()
        library.import_status = "pending_review"
        await self.session.flush()
        # MySQL server-generated timestamps must be loaded before sync serialization.
        for document in documents:
            await self.session.refresh(document)
        from app.services.inspection_standard_library_service import InspectionStandardLibraryService
        serializer = InspectionStandardLibraryService(self.session, self.org_id)
        return {"library_id":library_id, "uploaded_count":len(documents), "indexed_count":0, "failed_count":0,
            "documents":[serializer._serialize_document(d) for d in documents]}

    async def amend(self, document_id, payload):
        doc = await self.document(document_id, lock=True)
        _, old = await self.revision(document_id, doc.current_revision_id, lock=True)
        if payload.get("base_revision_id") != old.id:
            raise ConflictError("当前修订已变化，请从当前修订补充信息")
        if old.row_version!=payload["expected_version"]:
            raise ConflictError("修订已经变更，请刷新后重试")
        source_url = payload.get("source_url") or ""
        if source_url and (urlparse(source_url).scheme not in {"https", "http"} or not urlparse(source_url).netloc):
            raise ValidationError("来源地址需为完整http(s)地址")
        for key in ["effective_from", "effective_to", "production_from", "production_to"]:
            if payload.get(key):
                try:
                    date.fromisoformat(payload[key])
                except ValueError:
                    raise ValidationError("日期须为YYYY-MM-DD") from None
        for start, end in [("effective_from", "effective_to"), ("production_from", "production_to")]:
            if payload.get(start) and payload.get(end) and payload[start]>payload[end]:
                raise ValidationError("开始日期不能晚于截止日期")
        changes = {k:v for k,v in payload.items() if k not in {"expected_version", "base_revision_id"}}
        snapshot = {**old.snapshot, **changes}
        if snapshot==old.snapshot:
            return await self.serialize(old)
        number = (await self.session.execute(select(func.max(StandardDocumentRevision.revision_no)).where(
            StandardDocumentRevision.document_id==doc.id))).scalar_one() + 1
        candidates = copy.deepcopy(old.candidates_json or [])
        for item in candidates:
            item.update(status="pending", reviewed_by=None)
        rev = StandardDocumentRevision(org_id=self.org_id, document_id=doc.id, revision_no=number, snapshot=snapshot,
            file_hash=old.file_hash, processing_status=old.processing_status if old.processing_status=="parsed" else "pending",
            extraction_status=old.extraction_status if old.processing_status=="parsed" else "pending",
            pages_json=copy.deepcopy(old.pages_json or []), candidates_json=candidates, issues_json=[], created_by=self.actor_id)
        self.session.add(rev)
        await self.session.flush()
        doc.current_revision_id=rev.id
        doc.review_status="pending"
        doc.processing_status=rev.processing_status
        for key in ["standard_no", "standard_name", "standard_status", "standard_level", "domain", "product_category"]:
            if key not in snapshot:
                continue
            setattr(doc, key, snapshot[key])
        if rev.processing_status!="parsed":
            await self.enqueue(rev, "parse")
        await self.session.flush()
        return await self.serialize(rev)

    async def _action(self, document_id, revision_id, action, payload):
        if not self.actor_id:
            raise ForbiddenError("准入操作需要明确操作者")
        doc, rev = await self.revision(document_id, revision_id, lock=True)
        fingerprint = digest({"revision_id":revision_id,"actor_id":self.actor_id,"action":action,"payload":payload})
        previous = (await self.session.execute(select(StandardAdmissionReview).where(
            StandardAdmissionReview.org_id==self.org_id, StandardAdmissionReview.request_key==payload["request_key"]))).scalar_one_or_none()
        if previous:
            if previous.payload_hash!=fingerprint:
                raise ConflictError("相同操作编号不能用于不同请求")
            return doc, rev, True
        if rev.row_version!=payload["expected_version"]:
            raise ConflictError("修订已经变更，请刷新后重试")
        entry=StandardAdmissionReview(org_id=self.org_id, revision_id=rev.id, action=action, actor_id=self.actor_id,
            request_key=payload["request_key"], payload_hash=fingerprint, reason=payload["reason"],
            evidence_refs=payload.get("evidence_refs") or [], detail_json={k:v for k,v in payload.items() if k not in {"request_key", "reason", "evidence_refs"}})
        try:
            async with self.session.begin_nested():
                self.session.add(entry)
                await self.session.flush()
        except IntegrityError:
            competing=(await self.session.execute(select(StandardAdmissionReview).where(
                StandardAdmissionReview.org_id==self.org_id,StandardAdmissionReview.request_key==payload["request_key"]).with_for_update())).scalar_one_or_none()
            if competing and competing.payload_hash==fingerprint:
                return doc,rev,True
            raise ConflictError("操作编号已被另一请求使用，请刷新") from None
        return doc, rev, False

    async def review(self, document_id, revision_id, payload, *, actor_role):
        # Technical administration alone does not qualify a professional review.
        if str(actor_role)!="expert":
            raise ForbiddenError("专业核验由获授权领域专家完成，管理员可提交和组织发布")
        doc, rev, repeated = await self._action(document_id, revision_id, "review", payload)
        if repeated:
            return await self.serialize(rev)
        if rev.created_by==self.actor_id:
            raise ForbiddenError("提交者不能核验自己的标准修订")
        self.check_reviewer(rev)
        if rev.publication_status!="unpublished":
            raise ConflictError("发布中的修订须先撤回或新建修订")
        decision = payload["decision"]
        if decision=="approve":
            meta=rev.snapshot
            if rev.processing_status!="parsed" or meta.get("resource_type")!="standard":
                raise ValidationError("解析完成且确认为标准后才可批准")
            if not meta.get("source_url") or not meta.get("publisher") or meta.get("standard_status")=="待核实" or not payload.get("evidence_refs"):
                raise ValidationError("批准须核对来源、发布者、标准效力并记录证据")
            if meta.get("conflicts") and len(str(payload.get("conflict_resolution") or "").strip())<8:
                raise ValidationError("同编号不同内容须记录冲突核对与处理依据，不能直接批准")
            body=normalize_standard_number("\n".join(p["text"] for p in rev.pages_json))
            number=normalize_standard_number(meta.get("standard_no", ""))
            if len(number)<6 or number not in body:
                raise ValidationError("标准编号与解析正文尚不一致，请核对原PDF或修复解析")
            await asyncio.to_thread(self.read_original, rev)
        rev.review_status={"approve":"approved", "needs_information":"needs_information", "dispute":"disputed", "reject":"rejected"}[decision]
        rev.reviewed_by=self.actor_id
        rev.reviewed_at=utcnow()
        rev.row_version+=1
        if doc.current_revision_id==rev.id:
            doc.review_status=rev.review_status
        await self.session.flush()
        return await self.serialize(rev)

    def check_reviewer(self, rev):
        assigned = (rev.review_assignment or {}).get("reviewer_id")
        if assigned and assigned != self.actor_id:
            raise ForbiddenError("此修订已分派给另一位专家，请由审核人核对或申请重新分派")

    async def candidate(self, document_id, revision_id, payload, *, can_confirm=False, actor_role=None):
        if payload.get("candidate_type") is None:payload={k:v for k,v in payload.items() if k!="candidate_type"}
        doc, rev, repeated = await self._action(document_id, revision_id, "candidate", payload)
        if repeated:
            return await self.serialize(rev)
        if rev.publication_status!="unpublished":
            raise ConflictError("已发布检测要求不可修改；请建立补充要求的新稿")
        assigned = (rev.review_assignment or {}).get("reviewer_id")
        if assigned and self.actor_id not in {assigned, rev.created_by} and str(actor_role) != "admin":
            raise ForbiddenError("此修订由指定审核人和整理人处理")
        candidates=copy.deepcopy(rev.candidates_json or [])
        source_id=payload["candidate_id"].removeprefix("new:")
        item=next((c for c in candidates if c["id"]==source_id), None)
        if not item:
            raise NotFoundError("检测要求候选不存在")
        if payload["candidate_id"].startswith("new:"):
            item=copy.deepcopy(item)
            item["id"]=str(uuid7())
            candidates.append(item)
        if payload["status"] in {"confirmed", "rejected"}:
            self.check_reviewer(rev)
            if not can_confirm or rev.created_by==self.actor_id or item.get("prepared_by")==self.actor_id:
                raise ForbiddenError("检测要求需由独立领域专家确认")
            defaults={"execution_mode":"manual", "numeric_lower":None, "numeric_upper":None, "numeric_target":None,
                "decision_mode":"direct", "numeric_aggregation":"all", "minimum_observations":1, "expected_conditions":{}}
            checked_fields=["indicator","method","conditions","unit","requirement","operator","measurement_key","applicability",*defaults]
            if payload.get("candidate_type") is not None and payload["candidate_type"]!=item.get("candidate_type"):
                raise ValidationError("条款用途已修改，请先保存整理稿，再独立确认")
            if payload["candidate_id"].startswith("new:") or any(
                payload.get(k,defaults.get(k)) != item.get(k,defaults.get(k)) for k in checked_fields):
                raise ValidationError("技术内容已修改，请先保存整理稿，再由另一位专家确认")
        if payload["status"]=="confirmed":
            if item.get("candidate_type") not in {"inspection_requirement","method_condition","body_clause"}:
                raise ValidationError("请先整理条款用途：产品检测要求、试验方法条件或参考正文")
            needed=["indicator", "method", "conditions", "unit", "requirement", "measurement_key", "applicability"]
            if any(not str(payload.get(k) or "").strip() for k in needed) or payload["operator"]=="unresolved" or not payload.get("evidence_refs"):
                raise ValidationError("确认前需核对指标、方法、条件、单位、要求、测量字段、适用对象及证据；无单位请明确写无量纲")
            if rev.processing_status!="parsed" or not any(p["page_number"]==item.get("page_number") for p in rev.pages_json or []):
                raise ValidationError("需先获得可核对的原文页码与解析结果")
            await asyncio.to_thread(self.read_original, rev)
        fields=["status","indicator","method","conditions","unit","requirement","operator","measurement_key","applicability"]
        item.update({k:payload[k] for k in fields})
        if payload.get("candidate_type") is not None:item["candidate_type"]=payload["candidate_type"]
        execution_fields=["execution_mode","numeric_lower","numeric_upper","numeric_target","decision_mode","numeric_aggregation","minimum_observations","expected_conditions"]
        item.update({k:payload[k] for k in execution_fields if k in payload})
        if payload["status"]=="confirmed" and payload.get("execution_mode")=="numeric":
            from app.services.inspection_requirement_engine import evaluate_requirement
            check=evaluate_requirement(item,[])
            if check["status"]=="manual_required":raise ValidationError("可执行数值关系与限值尚未核对完整")
        item["reviewed_by"]=self.actor_id if payload["status"]=="confirmed" else None
        if payload["status"]=="pending":
            item.update(prepared_by=self.actor_id, prepared_at=utcnow().isoformat())
        elif payload["status"] in {"confirmed", "rejected"}:
            item.update(reviewed_at=utcnow().isoformat(), review_reason=payload["reason"], review_evidence_refs=payload.get("evidence_refs") or [])
        item["missing_fields"]=[] if payload["status"]=="confirmed" else item.get("missing_fields", [])
        rev.candidates_json=candidates
        rev.row_version+=1
        await self.session.flush()
        return await self.serialize(rev)

    async def candidate_review(self, document_id, revision_id, payload, *, can_confirm=False):
        _, rev = await self.revision(document_id, revision_id, lock=True)
        self.check_reviewer(rev)
        item = next((c for c in rev.candidates_json or [] if c["id"]==payload["candidate_id"]), None)
        if not item:
            raise NotFoundError("检测要求候选不存在")
        if not can_confirm or rev.created_by==self.actor_id or item.get("prepared_by")==self.actor_id:
            raise ForbiddenError("本人提交或整理的要求需由另一位授权专家核对")
        fields=["indicator","method","conditions","unit","requirement","operator","measurement_key","applicability",
                "execution_mode","numeric_lower","numeric_upper","numeric_target","decision_mode","numeric_aggregation",
                "minimum_observations","expected_conditions"]
        fields.append("candidate_type")
        defaults={"execution_mode":"manual","decision_mode":"direct","numeric_aggregation":"all","minimum_observations":1,"expected_conditions":{}}
        if payload["decision"] in {"confirm", "reject"}:
            if not payload.get("evidence_refs"):
                raise ValidationError("逐项确认或排除须记录原文核对依据")
            body={**payload, **{k:item.get(k,defaults.get(k)) for k in fields},
                  "status":"confirmed" if payload["decision"]=="confirm" else "rejected"}
            body.pop("decision")
            return await self.candidate(document_id, revision_id, body, can_confirm=True)
        _, rev, repeated = await self._action(document_id, revision_id, "candidate_information", payload)
        if rev.publication_status!="unpublished":
            raise ConflictError("已发布版本不可修改")
        if not repeated:
            candidates=copy.deepcopy(rev.candidates_json)
            target=next(c for c in candidates if c["id"]==item["id"])
            target.update(status="pending",reviewed_by=None,review_reason=payload["reason"],review_evidence_refs=payload.get("evidence_refs") or [])
            rev.candidates_json=candidates;rev.row_version+=1
            await self.session.flush()
        return await self.serialize(rev)

    async def draft_requirements(self, document_id, revision_id, payload):
        doc, base, repeated = await self._action(document_id, revision_id, "draft_requirements", payload)
        if repeated:
            action = await self.session.scalar(select(StandardAdmissionReview).where(
                StandardAdmissionReview.org_id==self.org_id, StandardAdmissionReview.request_key==payload["request_key"]))
            _, draft = await self.revision(document_id, action.detail_json["draft_revision_id"])
            return await self.serialize(draft)
        if base.publication_status!="published" or base.review_status!="approved" or doc.published_revision_id!=base.id:
            raise ConflictError("仅从当前已发布原文建立要求新稿")
        if doc.current_revision_id!=base.id:
            raise ConflictError("已有待核对新稿，请先处理当前修订")
        number = await self.session.scalar(select(func.max(StandardDocumentRevision.revision_no)).where(StandardDocumentRevision.document_id==doc.id))
        snapshot=copy.deepcopy(base.snapshot)
        snapshot["metadata_review_basis_revision_id"]=base.id
        draft=StandardDocumentRevision(org_id=self.org_id,document_id=doc.id,revision_no=number+1,
            snapshot=snapshot,file_hash=base.file_hash,processing_status=base.processing_status,extraction_status=base.extraction_status,
            pages_json=copy.deepcopy(base.pages_json),candidates_json=copy.deepcopy(base.candidates_json),created_by=self.actor_id,
            review_status="approved",reviewed_by=base.reviewed_by,reviewed_at=base.reviewed_at,
            issues_json=["沿用原文与来源核验；修改的检测要求须另行独立确认，当前发布版继续有效"])
        self.session.add(draft);await self.session.flush()
        doc.current_revision_id=draft.id
        action = await self.session.scalar(select(StandardAdmissionReview).where(
            StandardAdmissionReview.org_id==self.org_id,StandardAdmissionReview.request_key==payload["request_key"]))
        action.detail_json={**action.detail_json,"draft_revision_id":draft.id,"metadata_review_basis_revision_id":base.id}
        await self.session.flush()
        return await self.serialize(draft)

    async def publish(self, document_id, revision_id, payload):
        doc, rev, repeated = await self._action(document_id, revision_id, "publish", payload)
        if repeated:
            return await self.serialize(rev)
        if rev.review_status!="approved" or rev.processing_status!="parsed" or rev.publication_status!="unpublished":
            raise ValidationError("只能发布已专业核验且尚未发布的修订")
        if doc.current_revision_id!=rev.id:
            raise ConflictError("请发布当前修订，避免旧稿替换新稿")
        competing=(await self.session.execute(select(StandardDocumentRevision.id).join(StandardDocument,
            StandardDocument.published_revision_id==StandardDocumentRevision.id).where(StandardDocument.org_id==self.org_id,
            StandardDocument.deleted_at.is_(None),StandardDocument.id!=doc.id,
            StandardDocumentRevision.publication_status=="published"))).scalars().all()
        for other_id in competing:
            other=await self.session.get(StandardDocumentRevision,other_id)
            if other.snapshot.get("standard_no")==rev.snapshot.get("standard_no") and other.file_hash!=rev.file_hash:
                raise ConflictError("同编号另有已发布的不同正文；请先仲裁并撤回冲突版本")
        rev.publication_status="publishing"
        rev.published_by=self.actor_id
        rev.index_generation=digest({"revision":rev.id, "pages":rev.pages_json, "collection":settings.standard_published_collection})
        rev.row_version+=1
        # Keep previous published revision active until this projection succeeds.
        if not doc.published_revision_id:
            doc.publication_status="publishing"
        await self.enqueue(rev, "publish", rev.index_generation)
        await self.session.flush()
        return await self.serialize(rev)

    async def withdraw(self, document_id, revision_id, payload):
        doc, rev, repeated = await self._action(document_id, revision_id, "withdraw", payload)
        if repeated:
            return await self.serialize(rev)
        if rev.publication_status not in {"published", "publishing", "suspended"}:
            raise ValidationError("该修订未发布，无需撤回")
        rev.publication_status="withdrawn"
        rev.row_version+=1
        if doc.published_revision_id==rev.id:
            doc.published_revision_id=None
        if not doc.published_revision_id:
            doc.publication_status="withdrawn"
        await self.enqueue(rev, "withdraw", rev.index_generation or "initial")
        await self.session.flush()
        return await self.serialize(rev)

    async def retry(self, document_id, revision_id, payload):
        _, rev, repeated = await self._action(document_id, revision_id, "retry", payload)
        if repeated:
            return await self.serialize(rev)
        jobs = (await self.session.execute(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id,
            StandardSyncOutbox.org_id==self.org_id, StandardSyncOutbox.status=="failed"))).scalars().all()
        if rev.processing_status=="pending":
            await self.enqueue(rev, "parse")
        for job in jobs:
            job.status="pending"
            job.next_attempt_at=None
            job.attempts=0
        rev.row_version+=1
        await self.session.flush()
        return await self.serialize(rev)

    def read_original(self, rev):
        path=str(rev.snapshot["file_path"])
        if rev.snapshot.get("legacy") and Path(path).is_file():
            content=Path(path).read_bytes()
        else:
            stored=build_object_storage().get_bytes(bucket=settings.rag_storage_bucket, object_key=path)
            if not stored:
                raise NotFoundError("原PDF文件暂不可获取；保留元数据供核对")
            content=stored[0]
        if rev.file_hash and hashlib.sha256(content).hexdigest()!=rev.file_hash:
            raise ConflictError("原文件哈希已变化，须提交新的修订")
        return content

    async def search(self, payload, *, library_ids=None):
        start=perf_counter()
        purpose=payload.get("purpose") or "standard_explanation"
        if purpose not in {"standard_explanation", "task_basis"}:
            raise ValidationError("不支持的标准检索用途")
        q=select(StandardDocumentRevision, StandardDocument, InspectionStandardLibrary).join(StandardDocument,
            StandardDocument.published_revision_id==StandardDocumentRevision.id).join(InspectionStandardLibrary,
            StandardDocument.library_id==InspectionStandardLibrary.id).where(StandardDocumentRevision.org_id==self.org_id,
            StandardDocument.org_id==self.org_id, InspectionStandardLibrary.org_id==self.org_id,
            StandardDocument.deleted_at.is_(None), InspectionStandardLibrary.deleted_at.is_(None),
            InspectionStandardLibrary.is_active.is_(True), StandardDocumentRevision.review_status=="approved",
            StandardDocumentRevision.publication_status=="published")
        if library_ids is not None:
            if not library_ids:
                return {"hits":[],"hit_count":0,"candidate_count":0,"latency_ms":0.0,"missing_context":[]}
            q=q.where(StandardDocument.library_id.in_(library_ids))
        rows=(await self.session.execute(q)).all()
        eligible=[]
        missing=[]
        for rev,doc,library in rows:
            meta=rev.snapshot
            if payload.get("revision_id") and rev.id!=payload["revision_id"]:
                continue
            if payload.get("domain") and meta.get("domain")!=payload["domain"]:
                continue
            if payload.get("product_category") and meta.get("product_category")!=payload["product_category"]:
                continue
            if purpose=="task_basis":
                if not payload.get("revision_id"):
                    missing.append("正式任务依据需确认具体修订，不能仅按相似度选择")
                    continue
                if not payload.get("product_category"):
                    missing.append("需提供产品类别并核对适用范围")
                    continue
                context_date=payload.get("production_date")
                if not context_date:
                    missing.append("需提供生产日期以核对历史标准及过渡条件")
                    continue
                try:
                    date.fromisoformat(context_date)
                except ValueError:
                    raise ValidationError("生产日期格式应为YYYY-MM-DD") from None
                if not meta.get("scope_notes"):
                    missing.append("标准适用范围说明尚未核对")
                    continue
                lower=meta.get("production_from") or meta.get("effective_from")
                upper=meta.get("production_to") or meta.get("effective_to")
                if meta.get("standard_status") in {"被代替","废止"} and not upper:
                    missing.append("历史标准须核对适用截止及过渡范围")
                    continue
                if not lower:
                    missing.append("须核对适用日期开始和过渡规则")
                    continue
                if context_date<lower or (upper and context_date>upper):
                    continue
            eligible.append((rev,doc))
        hits=[]
        candidate_count=0
        retriever=Retriever(org_id=self.org_id, collection=settings.standard_published_collection, allow_pseudo_fallback=False)
        for rev,doc in eligible:
            found=await retriever.retrieve(payload["query"], top_k=payload.get("top_k",8), payload_filter={
                "org_id":self.org_id,"resource_domain":"formal_standard","revision_id":rev.id,"index_generation":rev.index_generation})
            candidate_count+=len(found)
            # Verify DB eligibility again after external lookup; cached vectors cannot revive withdrawals.
            fresh=(await self.session.execute(select(StandardDocumentRevision.publication_status, StandardDocument.published_revision_id).join(
                StandardDocument, StandardDocument.id==StandardDocumentRevision.document_id).join(InspectionStandardLibrary,
                InspectionStandardLibrary.id==StandardDocument.library_id).where(StandardDocumentRevision.id==rev.id,
                StandardDocumentRevision.org_id==self.org_id, StandardDocument.deleted_at.is_(None),
                InspectionStandardLibrary.deleted_at.is_(None),InspectionStandardLibrary.is_active.is_(True)).with_for_update())).first()
            if not fresh or fresh[0]!="published" or fresh[1]!=rev.id:
                continue
            for item in found:
                metadata=item.get("payload") or {}
                if metadata.get("org_id")!=self.org_id or metadata.get("revision_id")!=rev.id or metadata.get("index_generation")!=rev.index_generation:
                    continue
                hits.append({**item, "revision_id":rev.id,"publication_status":"published", "purpose":purpose,
                    "standard_no":rev.snapshot["standard_no"],"standard_name":rev.snapshot["standard_name"]})
        hits.sort(key=lambda h:float(h.get("score") or 0), reverse=True)
        hits=hits[:payload.get("top_k",8)]
        return {"hits":hits,"hit_count":len(hits),"candidate_count":candidate_count,"latency_ms":round((perf_counter()-start)*1000,2),
            "missing_context":list(dict.fromkeys(missing))}

    async def requirements(self):
        # The formal overview must stay usable while a newer revision is being
        # reviewed.  Join the revision actually published for the document;
        # `current_revision_id` may already point at an unpublished draft.
        rows=(await self.session.execute(select(StandardDocumentRevision,StandardDocument,InspectionStandardLibrary).join(
            StandardDocument,StandardDocument.published_revision_id==StandardDocumentRevision.id).join(
            InspectionStandardLibrary,InspectionStandardLibrary.id==StandardDocument.library_id).where(
            StandardDocumentRevision.org_id==self.org_id,StandardDocument.org_id==self.org_id,InspectionStandardLibrary.org_id==self.org_id,
            StandardDocument.deleted_at.is_(None),InspectionStandardLibrary.deleted_at.is_(None)).limit(200))).all()
        return [{**c,"document_id":doc.id,"revision_id":rev.id,"library_id":lib.id,"library_name":lib.name,
            "standard_no":rev.snapshot["standard_no"],"publication_status":rev.publication_status,
            "usage_status":"confirmed_requirement" if c.get("status")=="confirmed" and rev.publication_status=="published" else "review_only"}
            for rev,doc,lib in rows for c in rev.candidates_json or []
            if c.get("status") == "confirmed" and rev.publication_status == "published"]

    async def check_applicability(self, document_id, revision_id, payload):
        doc,rev=await self.revision(document_id,revision_id)
        meta=rev.snapshot
        missing=[]
        mismatches=[]
        if rev.publication_status!="published" or doc.published_revision_id!=rev.id:
            missing.append("本修订尚未正式发布或已被暂停/撤回")
        if not payload.get("product_category"):
            missing.append("需提供产品类别")
        elif payload["product_category"]!=meta.get("product_category"):
            mismatches.append("产品类别与此修订登记范围不匹配")
        source_date=payload.get("production_date")
        if not source_date:
            missing.append("需提供产品生产日期")
        else:
            try: date.fromisoformat(source_date)
            except ValueError: raise ValidationError("生产日期须为YYYY-MM-DD") from None
            lower=meta.get("production_from") or meta.get("effective_from")
            upper=meta.get("production_to") or meta.get("effective_to")
            if meta.get("standard_status") in {"被代替","废止"} and not upper:
                missing.append("历史标准须核对适用截止及过渡范围")
            if not lower:
                missing.append("此修订尚未核对适用日期与过渡规则")
            elif source_date<lower or (upper and source_date>upper):
                mismatches.append("生产日期不在登记的适用区间内")
        if not meta.get("scope_notes"):
            missing.append("此修订尚未核对产品范围与过渡说明")
        if not payload.get("conditions"):
            missing.append("需核对具体型号、检测场景与试验条件")
        return {"revision_id":rev.id,"standard_no":meta["standard_no"],"publication_status":rev.publication_status,
            "status":"mismatch" if mismatches else "needs_information" if missing else "scope_match",
            "missing_fields":missing,"mismatches":mismatches,"scope_notes":meta.get("scope_notes") or "",
            "notice":"范围匹配供选择依据；具体方法、条件及检测覆盖仍须专业核对，不能据此认定产品合格。"}


async def process_standard_outbox(session, row, *, indexer=None):
    """Caller locks only the outbox row during I/O; withdrawal can still commit."""
    service=StandardAdmissionService(session,row.org_id)
    rev=await session.get(StandardDocumentRevision,row.revision_id)
    if not rev:
        raise NotFoundError("标准修订不存在")
    doc=await service.document(rev.document_id)
    if row.action=="parse":
        if rev.processing_status=="parsed":
            return
        import tempfile
        content=await asyncio.to_thread(service.read_original,rev)
        with tempfile.TemporaryDirectory(prefix="standard-admission-") as folder:
            file=Path(folder)/"source.pdf"
            file.write_bytes(content)
            pages,total_pages=await asyncio.to_thread(extract_pdf_pages,file)
        if not pages:
            raise ValidationError("未获取可核对的PDF正文")
        missing_pages=[p for p in range(1,total_pages+1) if p not in {item["page_number"] for item in pages}]
        pages=sorted([*pages,*[{"page_number":p,"text":"","extraction_status":"no_text_detected"} for p in missing_pages]],key=lambda p:p["page_number"])
        candidates=extract_candidates(pages)
        _,fresh=await service.revision(doc.id,rev.id,lock=True)
        if fresh.review_status!="pending" or fresh.publication_status!="unpublished":
            raise ConflictError("解析过程遇到状态变化，请刷新")
        fresh.pages_json=pages
        fresh.candidates_json=candidates
        fresh.extraction_status="needs_review" if candidates else "no_candidates"
        fresh.processing_status="parsed"
        fresh.row_version+=1
        fresh.issues_json=list(fresh.issues_json or [])+(["未提取到明确检测要求，可核对原文；不代表标准没有要求"] if not candidates else [])
        if missing_pages:
            fresh.issues_json=[*fresh.issues_json,"未提取到文字的PDF页："+"、".join(map(str,missing_pages))+"；请核对是否为空白、图示或表格页。"]
        if doc.current_revision_id==fresh.id:
            doc.processing_status="parsed"
            doc.import_status="parsed"
            doc.page_count=len(pages)
        return
    indexer=indexer or KnowledgeIndexer(org_id=row.org_id,collection=settings.standard_published_collection,allow_pseudo_fallback=False)
    if row.action=="withdraw":
        await indexer.delete_by_filter({"org_id":row.org_id,"revision_id":rev.id})
        return
    if row.action!="publish":
        raise ValidationError("未知标准同步动作")
    if rev.publication_status!="publishing" or doc.current_revision_id!=rev.id:
        return
    library=await session.get(InspectionStandardLibrary,doc.library_id)
    meta=dict(rev.snapshot)
    # Build projection from saved pages; never read a mutable file for publication.
    docs=build_index_docs(org_id=row.org_id,library_id=doc.library_id,document_id=doc.id,
        file_path=rev.snapshot["file_name"],meta=meta,pages=rev.pages_json,chunk_strategy=library.chunk_strategy)
    for point in docs:
        point["id"]=digest({"base":point["id"],"revision":rev.id,"generation":rev.index_generation})
        point["payload"].update(resource_domain="formal_standard",revision_id=rev.id,index_generation=rev.index_generation,
            file_path=rev.snapshot["file_path"])
    result=await indexer.index(docs)
    if not docs or result.get("accepted")!=len(docs) or result.get("failed_embeddings"):
        raise ValidationError("索引未完整写入；修订仍未正式发布，可重试")
    document_id=doc.id
    session.expire(rev)
    session.expire(doc)
    doc,fresh=await service.revision(document_id, row.revision_id, lock=True)
    if fresh.publication_status!="publishing" or doc.current_revision_id!=fresh.id:
        # A withdrawal/new revision won the race; no activation.
        await indexer.delete_by_filter({"org_id":row.org_id,"revision_id":row.revision_id})
        return
    # Serialize activation against other documents in this namespace. A deadlock
    # is retried by the durable job; conflicting bodies cannot both activate.
    others=(await session.execute(select(StandardDocumentRevision).join(StandardDocument,
        StandardDocument.published_revision_id==StandardDocumentRevision.id).where(StandardDocument.org_id==row.org_id,
        StandardDocument.id!=doc.id,StandardDocument.deleted_at.is_(None),
        StandardDocumentRevision.publication_status=="published").with_for_update())).scalars().all()
    if any(other.snapshot.get("standard_no")==fresh.snapshot.get("standard_no") and other.file_hash!=fresh.file_hash for other in others):
        raise ConflictError("同编号不同正文已有发布版本，请先仲裁并撤回冲突版本")
    library=(await session.execute(select(InspectionStandardLibrary).where(InspectionStandardLibrary.id==doc.library_id,
        InspectionStandardLibrary.org_id==row.org_id,InspectionStandardLibrary.deleted_at.is_(None),InspectionStandardLibrary.is_active.is_(True))
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not library:
        raise ConflictError("标准库已停用，不能激活发布")
    if doc.published_revision_id and doc.published_revision_id!=fresh.id:
        previous=await session.get(StandardDocumentRevision,doc.published_revision_id)
        previous.publication_status="suspended"
        previous.row_version+=1
    fresh.publication_status="published"
    fresh.published_at=utcnow()
    fresh.row_version+=1
    doc.published_revision_id=fresh.id
    doc.publication_status="published"
    doc.chunk_count=len(docs)
    doc.last_indexed_at=utcnow()
    doc.qdrant_collection=settings.standard_published_collection
    doc.import_status="completed"
    await session.flush()
