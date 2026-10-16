import copy
import json
from sqlalchemy import or_,select
from sqlalchemy.exc import IntegrityError
from app.core.datetime import utcnow
from app.core.ids import uuid7
from app.core.exceptions import ConflictError,ForbiddenError,NotFoundError,ValidationError
from app.core.permissions import has_permission
from app.models.knowledge_admission import KnowledgeAdmission,KnowledgeAdmissionAction,RagSpaceGrant
from app.models.memory import MemoryItem,MemoryOrigin,MemoryEvidence,MemoryEvent,MemoryDependencyEdge,MemorySyncOutbox
from app.models.meeting import MemoryScopeBinding
from app.models.user import User
from app.models.rag_space import RagSpace
from app.repositories.memory_repo import MemorySyncOutboxRepository
from app.services.knowledge_source_service import KnowledgeSourceService,fingerprint


class KnowledgeAdmissionService:
    def __init__(self,session,current):
        self.session,self.current=session,current
        self.org_id=current.org_id
        self.sources=KnowledgeSourceService(session,current)

    async def get(self,admission_id,*,lock=False):
        q=select(KnowledgeAdmission).where(KnowledgeAdmission.id==admission_id,KnowledgeAdmission.org_id==self.org_id)
        if lock:q=q.with_for_update().execution_options(populate_existing=True)
        item=(await self.session.execute(q)).scalar_one_or_none()
        if not item:raise NotFoundError("知识候选不存在")
        if item.created_by!=self.current.user_id:
            visible=item.snapshot.get("consent_to_review") and (has_permission("knowledge_review",self.current.role) or has_permission("memory_governance",self.current.role))
            visible=visible or (item.publication_status=="published" and item.snapshot.get("requested_scope")=="organization")
            if not visible:raise NotFoundError("知识候选不在当前授权范围")
        return item

    async def serialize(self,item,*,detail=False):
        result={key:getattr(item,key) for key in ["id","memory_id","created_by","snapshot","source_refs","review_status",
            "sharing_status","publication_status","row_version","reviewed_by","share_approved_by","published_by","created_at","reviewed_at","published_at"]}
        if detail:
            actions=(await self.session.execute(select(KnowledgeAdmissionAction).where(KnowledgeAdmissionAction.org_id==self.org_id,
                KnowledgeAdmissionAction.admission_id==item.id).order_by(KnowledgeAdmissionAction.created_at))).scalars().all()
            result["actions"]=[{k:getattr(a,k) for k in ["action","actor_id","reason","details","created_at"]} for a in actions]
            jobs=(await self.session.execute(select(MemorySyncOutbox).where(MemorySyncOutbox.org_id==self.org_id,
                MemorySyncOutbox.memory_id==item.memory_id))).scalars().all()
            result["jobs"]=[{"action":j.action,"status":j.status,"retry_count":j.retry_count,"error":j.last_error} for j in jobs]
        return result

    async def list(self,*,published=False):
        q=select(KnowledgeAdmission).where(KnowledgeAdmission.org_id==self.org_id)
        if published:q=q.where(KnowledgeAdmission.publication_status=="published",
            or_(KnowledgeAdmission.created_by==self.current.user_id,KnowledgeAdmission.sharing_status=="approved"))
        elif has_permission("knowledge_review",self.current.role) or has_permission("memory_governance",self.current.role):
            q=q.where(or_(KnowledgeAdmission.created_by==self.current.user_id,KnowledgeAdmission.snapshot["consent_to_review"].as_boolean().is_(True)))
        else:q=q.where(KnowledgeAdmission.created_by==self.current.user_id)
        items=(await self.session.execute(q.order_by(KnowledgeAdmission.created_at.desc()).limit(200))).scalars().all()
        valid=[]
        for item in items:
            if published:
                memory=await self.memory(item)
                if memory.status!="active":continue
                issues=await self.source_issues(item)
                if issues:continue
            valid.append(await self.serialize(item))
        return valid

    async def submit(self,payload):
        actor=self.current.user_id
        if not payload.get("consent_to_review"):raise ValidationError("需明确授权将所选主张和引用片段提交给审核者；原始资料不会自动共享")
        organization=payload["requested_scope"]=="organization"
        if organization and not payload.get("consent_to_share"):raise ValidationError("组织知识须先获得来源提交者的共享同意")
        request_hash=fingerprint(payload)
        await self.session.execute(select(User.id).where(User.id==actor,User.org_id==self.org_id).with_for_update())
        existing=(await self.session.execute(select(KnowledgeAdmission).where(KnowledgeAdmission.org_id==self.org_id,
            KnowledgeAdmission.created_by==actor,KnowledgeAdmission.request_key==payload["request_key"]))).scalar_one_or_none()
        if existing:
            if existing.payload_hash!=request_hash:raise ConflictError("操作编号已用于其他知识内容")
            return await self.serialize(existing,detail=True)
        refs=[];seen=set()
        for source in payload["sources"]:
            resolved=await self.sources.resolve(source["kind"],source["id"],source.get("quote", ""),organization=organization)
            # Same PDF/measurement/message cited twice remains one origin.
            if resolved["independence_key"] not in seen:
                refs.append(resolved);seen.add(resolved["independence_key"])
        qdl=payload.get("qdl")
        if qdl:
            from app.schemas.qdl import parse_qdl
            parsed=parse_qdl(qdl)
            if not parsed.document:raise ValidationError("QDL结构尚不完整",detail={"errors":list(parsed.errors)})
            qdl=parsed.document.model_dump(mode="json")
            if qdl.get("claim",{}).get("text","").strip()!=payload["claim"].strip():
                raise ValidationError("QDL主张应与本次提交的知识主张一致")
            context=qdl.get("provenance",{}).get("source_context") or {}
            room=qdl.get("provenance",{}).get("room_id")
            valid_contexts=set();valid_rooms=set()
            for ref in refs:
                if ref["kind"]=="standard_revision":valid_contexts.update({("standard",ref["id"]),("standard",ref["metadata"]["document_id"])})
                if ref["kind"]=="task_result":valid_contexts.add(("task",ref["metadata"]["task_id"]))
                if ref["kind"]=="inspection_execution":valid_contexts.add(("task",ref["metadata"]["task_id"]))
                if ref["kind"]=="meeting_message":valid_rooms.add(ref["metadata"]["room_id"])
            if (context.get("source_type"),context.get("source_id")) not in valid_contexts and room not in valid_rooms:
                raise ValidationError("QDL出处须关联本次实际授权的标准、任务或会议来源")
            qdl["provenance"]["org_id"]=self.org_id
            qdl["provenance"]["source_hash"]=fingerprint(refs)
            qdl["applicability"].update(scope_type="user",scope_id=actor)
            qdl["governance"].update(status="candidate",requires_human_confirmation=True,confirmed_by=None,confirmed_at=None)
        for mid in payload.get("related_memory_ids") or []:await self.visible_memory(mid)
        aid=str(uuid7());mid="mem_"+str(uuid7()).replace("-","")
        snapshot={k:v for k,v in payload.items() if k not in {"request_key","sources"}}
        snapshot.update(qdl=qdl,author_role=str(self.current.role))
        admission=KnowledgeAdmission(id=aid,org_id=self.org_id,memory_id=mid,created_by=actor,
            request_key=payload["request_key"],payload_hash=request_hash,snapshot=snapshot,source_refs=refs,
            sharing_status="pending" if organization else "private")
        self.session.add(admission)
        memory=MemoryItem(id=str(uuid7()),memory_id=mid,org_id=self.org_id,user_id=actor,memory_type="inspection_pattern",
            content_summary=payload["claim"],content_json={"summary":payload["claim"],"source_type":"knowledge_admission","knowledge_admission_id":aid,
                "qdl":qdl,"limitations":payload["limitations"]},scope_json={"scope_type":"user","scope_id":actor},
            applicability_json={"product_category":payload["product_category"],"conditions":payload["applicability"],"limitations":payload["limitations"]},
            product_category=payload["product_category"],product_line=payload["product_category"],created_by=actor,created_by_type="human",
            status="candidate",review_status="candidate",readiness_status="collecting",origin_evidence_count=len(refs),
            usage_policy="context_only",privacy_level="tenant_private",ttl_policy="never",confidence=None,trust_score=None)
        self.session.add(memory)
        self.session.add(MemoryScopeBinding(org_id=self.org_id,memory_id=mid,scope_type="user",scope_id=actor,
            binding_kind="home",binding_status="active",created_by=actor))
        for ref in refs:
            self.session.add(MemoryOrigin(id=str(uuid7()),org_id=self.org_id,memory_id=mid,origin_kind=ref["kind"],
                source_type=ref["kind"],source_id=ref["id"],dedupe_key=ref["independence_key"],
                source_span={"quote":ref["quote"]},metadata_json={"source_version":ref["source_version"],"authority":ref["authority"]}))
            self.session.add(MemoryEvidence(id=str(uuid7()),org_id=self.org_id,memory_id=mid,evidence_role="origin",
                source_kind=ref["kind"],source_type=ref["kind"],source_id=ref["id"],independence_key=ref["independence_key"],
                evidence_pointer=ref))
        for parent in set(payload.get("related_memory_ids") or []):
            self.session.add(MemoryDependencyEdge(id=str(uuid7()),org_id=self.org_id,source_memory_id=mid,target_memory_id=parent,
                edge_type="derived_from",metadata_json={"admission_id":aid,"confirmed":False}))
        await self.event(admission,"knowledge.candidate_submitted",{"origin_count":len(refs)})
        await self.session.flush()
        return await self.serialize(admission,detail=True)

    async def visible_memory(self,mid):
        memory=(await self.session.execute(select(MemoryItem).where(MemoryItem.org_id==self.org_id,MemoryItem.memory_id==mid,
            MemoryItem.deleted_at.is_(None)))).scalar_one_or_none()
        if not memory:raise NotFoundError("关联知识不存在")
        statement=select(MemoryScopeBinding.id).where(MemoryScopeBinding.org_id==self.org_id,
            MemoryScopeBinding.memory_id==mid,MemoryScopeBinding.binding_status=="active",MemoryScopeBinding.deleted_at.is_(None),
            or_((MemoryScopeBinding.scope_type=="user")&(MemoryScopeBinding.scope_id==self.current.user_id),
                (MemoryScopeBinding.scope_type=="org_space")&(MemoryScopeBinding.scope_id==self.org_id))).limit(1)
        binding=(await self.session.execute(statement)).scalar_one_or_none()
        if memory.created_by!=self.current.user_id and not binding:raise NotFoundError("关联知识没有授权")
        return memory

    async def event(self,item,kind,payload):
        self.session.add(MemoryEvent(id=str(uuid7()),event_id="evt_"+str(uuid7()).replace("-",""),org_id=self.org_id,
            user_id=self.current.user_id,memory_id=item.memory_id,event_type=kind,source_kind="knowledge_admission",payload_json=payload))

    async def action(self,admission_id,action,payload):
        item=await self.get(admission_id,lock=True)
        h=fingerprint({"id":item.id,"action":action,"actor":self.current.user_id,"payload":payload})
        old=(await self.session.execute(select(KnowledgeAdmissionAction).where(KnowledgeAdmissionAction.org_id==self.org_id,
            KnowledgeAdmissionAction.request_key==payload["request_key"]))).scalar_one_or_none()
        if old:
            if old.payload_hash!=h:raise ConflictError("操作编号已被不同请求使用")
            return item,True
        if item.row_version!=payload["expected_version"]:raise ConflictError("候选状态已经改变，请刷新")
        try:
            async with self.session.begin_nested():
                self.session.add(KnowledgeAdmissionAction(org_id=self.org_id,admission_id=item.id,actor_id=self.current.user_id,
                    action=action,request_key=payload["request_key"],payload_hash=h,reason=payload["reason"],
                    details={k:v for k,v in payload.items() if k not in {"request_key","reason"}}))
                await self.session.flush()
        except IntegrityError:raise ConflictError("操作编号已被并发请求使用，请刷新") from None
        return item,False

    async def review(self,admission_id,payload):
        if str(self.current.role)!="expert" or not has_permission("knowledge_review",self.current.role):raise ForbiddenError("专业知识由授权专家核验")
        item,repeat=await self.action(admission_id,"review",payload)
        if repeat:return await self.serialize(item,detail=True)
        if item.created_by==self.current.user_id:raise ForbiddenError("不能专业确认自己提交的知识")
        if item.publication_status!="unpublished":raise ConflictError("已发布知识须先撤回或提交新的候选版本")
        if payload["decision"]=="approve":
            if not payload.get("evidence_refs"):raise ValidationError("专业核验需记录依据")
            if any(ref["kind"] in {"rag_document","meeting_message"} and not ref.get("quote") for ref in item.source_refs):
                raise ValidationError("私人资料或会议来源须选取可核验的原文片段，仅记录出处不足以确认主张")
            issues=await self.source_issues(item,require_published_standard=False)
            if issues:raise ValidationError("来源有变更或失效，请重新提交",detail={"issues":issues})
        item.review_status={"approve":"approved","needs_information":"needs_information","dispute":"disputed","reject":"rejected"}[payload["decision"]]
        item.reviewed_by=self.current.user_id;item.reviewed_at=utcnow();item.row_version+=1
        memory=await self.memory(item)
        memory.review_status={"approved":"approved","disputed":"disputed","rejected":"rejected"}.get(item.review_status,"candidate")
        if item.review_status=="approved":
            memory.human_approved=True;memory.human_confirmation_count=1
            evidence=(await self.session.execute(select(MemoryEvidence.id).where(MemoryEvidence.org_id==self.org_id,
                MemoryEvidence.memory_id==item.memory_id,MemoryEvidence.evidence_role=="human_confirmation",
                MemoryEvidence.independence_key==f"expert:{self.current.user_id}"))).scalar_one_or_none()
            if not evidence:self.session.add(MemoryEvidence(id=str(uuid7()),org_id=self.org_id,memory_id=item.memory_id,evidence_role="human_confirmation",
                source_kind="human_review",source_type="knowledge_admission",source_id=item.id,
                independence_key=f"expert:{self.current.user_id}",evidence_pointer={"reason":payload["reason"],"refs":payload["evidence_refs"]}))
        else:memory.human_approved=False;memory.human_confirmation_count=0
        await self.event(item,"knowledge.review_decided",{"decision":item.review_status})
        await self.session.flush();return await self.serialize(item,detail=True)

    async def sharing(self,admission_id,payload):
        item,repeat=await self.action(admission_id,"sharing",payload)
        if repeat:return await self.serialize(item,detail=True)
        if item.snapshot["requested_scope"]!="organization" or not item.snapshot["consent_to_share"]:
            raise ValidationError("没有申请组织使用范围或提交者未授权共享")
        if item.publication_status!="unpublished":raise ConflictError("不能改变已发布知识的范围，请先撤回")
        item.sharing_status="approved" if payload["decision"]=="approve" else "rejected"
        item.share_approved_by=self.current.user_id;item.row_version+=1
        await self.event(item,"knowledge.scope_decided",{"scope":"organization","decision":item.sharing_status})
        await self.session.flush();return await self.serialize(item,detail=True)

    async def memory(self,item):
        return (await self.session.execute(select(MemoryItem).where(MemoryItem.org_id==self.org_id,MemoryItem.memory_id==item.memory_id))).scalar_one()

    async def source_issues(self,item,*,require_published_standard=True,visited=None):
        from app.schemas.user import CurrentUser
        original=CurrentUser(user_id=item.created_by,org_id=self.org_id,role=item.snapshot["author_role"])
        visited=set(visited or [])
        if item.id in visited or len(visited)>=40:return ["依赖循环或依赖链过长，需人工核对"]
        visited.add(item.id)
        source_service=KnowledgeSourceService(self.session,original)
        issues=[]
        for ref in item.source_refs:
            try:
                current=await source_service.resolve(ref["kind"],ref["id"],ref["quote"],organization=item.snapshot["requested_scope"]=="organization")
                if current["source_version"]!=ref["source_version"]:issues.append("来源内容或修订发生变化")
                if ref["kind"]=="standard_revision" and require_published_standard and current["authority"]!="formal_standard":issues.append("引用标准尚未发布或已经撤回")
                if ref["kind"]=="inspection_execution" and require_published_standard and current["authority"]!="reviewed_selected_items":issues.append("执行结果尚未复核或依据已失效")
            except (NotFoundError,ForbiddenError,ValidationError):issues.append("来源撤回、删除或授权发生变化")
        for mid in item.snapshot.get("related_memory_ids") or []:
            memory=(await self.session.execute(select(MemoryItem).where(MemoryItem.org_id==self.org_id,MemoryItem.memory_id==mid))).scalar_one_or_none()
            if not memory or memory.status!="active" or memory.deleted_at:issues.append("依赖知识不再有效")
            try:await KnowledgeAdmissionService(self.session,original).visible_memory(mid)
            except NotFoundError:issues.append("依赖知识的授权已撤回")
            if memory:
                parent_id=(memory.content_json or {}).get("knowledge_admission_id")
                if parent_id:
                    parent=(await self.session.execute(select(KnowledgeAdmission).where(KnowledgeAdmission.id==parent_id,
                        KnowledgeAdmission.org_id==self.org_id))).scalar_one_or_none()
                    if not parent or parent.publication_status!="published" or await self.source_issues(parent,visited=visited):
                        issues.append("上游知识的来源或依赖已失效")
        return list(dict.fromkeys(issues))

    async def publish(self,admission_id,payload):
        item,repeat=await self.action(admission_id,"publish",payload)
        if repeat:return await self.serialize(item,detail=True)
        if item.review_status!="approved" or item.publication_status!="unpublished":raise ValidationError("只能发布专业核验通过的未发布候选")
        if item.snapshot["requested_scope"]=="organization" and item.sharing_status!="approved":raise ValidationError("组织范围尚未单独批准")
        issues=await self.source_issues(item)
        if issues:raise ValidationError("来源或依赖不能正式使用",detail={"issues":issues})
        mapping=self.mapping(item,payload)
        if mapping.get("status") not in {"ready","not_required"}:raise ValidationError("跨场景QDL映射尚未完整核对",detail={"mapping":mapping})
        item.publication_status="publishing";item.published_by=self.current.user_id;item.row_version+=1
        memory=await self.memory(item)
        org_scope=item.snapshot["requested_scope"]=="organization"
        target={"scope_type":"org_space" if org_scope else "user","scope_id":self.org_id if org_scope else item.created_by}
        await MemorySyncOutboxRepository(self.session,self.org_id).create_pending(memory_id=item.memory_id,action="UPSERT_ACTIVE_VECTOR",target_backend="qdrant",
            payload={"managed_admission_id":item.id,"memory_id":item.memory_id,"org_id":self.org_id,"user_id":"" if org_scope else item.created_by,
                "memory_type":memory.memory_type,"status":"active","summary":memory.content_summary,"trust_score":0.0,"confidence":0.0,
                "product_line":memory.product_line or "","extra_payload":{"review_status":"approved","resource_domain":"professional_knowledge",
                    "applicability":memory.applicability_json,"scope_bindings":[target],"scope_bindings_json":json.dumps([target]),
                    "claim":memory.content_summary,"admission_id":item.id}})
        await self.event(item,"knowledge.publish_requested",{"target":target})
        await self.session.flush();return await self.serialize(item,detail=True)

    def mapping(self,item,payload):
        if not item.snapshot.get("qdl"):return {"status":"not_required","notice":"主张仍受已核对的产品类别和适用条件限制，不自动扩展到其他场景。"}
        from app.services.knowledge_tunnel_service import KnowledgeTunnelService
        organization=item.snapshot["requested_scope"]=="organization"
        result=KnowledgeTunnelService.transform_qdl(item.snapshot["qdl"],source_scope_type="user",source_scope_id=item.created_by,
            target_scope_type="org_space" if organization else "user",target_scope_id=self.org_id if organization else item.created_by,
            mapping_rules=payload.get("mapping_rules") or {},mapping_version=payload.get("mapping_version") or "explicit-v1",
            interpolation_strategy="explicit",transform_reason=payload["reason"],source_memory_id=item.memory_id)
        return result.as_dict()

    async def withdraw(self,admission_id,payload):
        item,repeat=await self.action(admission_id,"withdraw",payload)
        if repeat:return await self.serialize(item,detail=True)
        if item.created_by!=self.current.user_id and not has_permission("knowledge_publish",self.current.role):raise ForbiddenError("仅提交者或发布管理者可撤回")
        if item.publication_status not in {"published","publishing","suspended"}:raise ValidationError("该知识尚未发布")
        await self.invalidate(item,payload["reason"])
        impacts=(await self.session.execute(select(MemoryDependencyEdge.source_memory_id).where(MemoryDependencyEdge.org_id==self.org_id,
            MemoryDependencyEdge.target_memory_id==item.memory_id,MemoryDependencyEdge.deleted_at.is_(None)))).scalars().all()
        await self.event(item,"knowledge.withdrawn",{"affected_memories":list(impacts)})
        await self.session.flush();return {**await self.serialize(item,detail=True),"affected_memory_ids":list(impacts)}

    async def invalidate(self,item,reason):
        item.publication_status="withdrawn";item.row_version+=1
        memory=await self.memory(item);memory.status="isolated"
        bindings=(await self.session.execute(select(MemoryScopeBinding).where(MemoryScopeBinding.org_id==self.org_id,
            MemoryScopeBinding.memory_id==item.memory_id,MemoryScopeBinding.binding_status=="active"))).scalars().all()
        for binding in bindings:binding.binding_status="revoked";binding.revoked_at=utcnow()
        await MemorySyncOutboxRepository(self.session,self.org_id).create_pending(memory_id=item.memory_id,action="DELETE_ACTIVE_VECTOR",target_backend="qdrant",
            payload={"memory_id":item.memory_id,"reason":reason})
        await MemorySyncOutboxRepository(self.session,self.org_id).create_pending(memory_id=item.memory_id,action="UPDATE_MEMORY_NODE_STATUS",target_backend="neo4j",
            payload={"memory_id":item.memory_id,"org_id":self.org_id,"memory_type":memory.memory_type,"status":"isolated","review_status":memory.review_status,
                "scope_key":"","scope_bindings_json":"[]","origin_kind":"knowledge_admission"})
        await MemorySyncOutboxRepository(self.session,self.org_id).create_pending(memory_id=item.memory_id,action="SOFT_DELETE_MEMORY_EDGES",target_backend="neo4j",payload={"memory_id":item.memory_id})

    async def retry(self,admission_id,payload):
        item,repeat=await self.action(admission_id,"retry",payload)
        if repeat:return await self.serialize(item,detail=True)
        rows=(await self.session.execute(select(MemorySyncOutbox).where(MemorySyncOutbox.org_id==self.org_id,
            MemorySyncOutbox.memory_id==item.memory_id,MemorySyncOutbox.status.in_(["failed","pending"])))).scalars().all()
        for row in rows:row.status="pending";row.retry_count=0;row.last_error=None
        item.row_version+=1;await self.session.flush();return await self.serialize(item,detail=True)


async def guard_managed_memory(session,org_id,memories):
    """All old retrieval paths must respect the new publication/source gate."""
    valid=[]
    for memory in memories:
        aid=(memory.content_json or {}).get("knowledge_admission_id")
        if not aid:valid.append(memory);continue
        item=(await session.execute(select(KnowledgeAdmission).where(KnowledgeAdmission.id==aid,KnowledgeAdmission.org_id==org_id)
            .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not item or item.publication_status!="published" or item.review_status!="approved" or memory.memory_id!=item.memory_id or memory.content_summary!=item.snapshot["claim"]:continue
        from app.schemas.user import CurrentUser
        service=KnowledgeAdmissionService(session,CurrentUser(user_id=item.created_by,org_id=org_id,role=item.snapshot["author_role"]))
        if await service.source_issues(item):
            await service.invalidate(item,"来源或依赖失效，需重新核对")
            continue
        valid.append(memory)
    return valid


async def finish_knowledge_projection(session,org_id,admission_id):
    item=(await session.execute(select(KnowledgeAdmission).where(KnowledgeAdmission.org_id==org_id,KnowledgeAdmission.id==admission_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not item:return
    from app.schemas.user import CurrentUser
    service=KnowledgeAdmissionService(session,CurrentUser(user_id=item.created_by,org_id=org_id,role=item.snapshot["author_role"]))
    if item.publication_status=="published" and not await service.source_issues(item):return
    if item.publication_status!="publishing" or await service.source_issues(item):
        if item.publication_status in {"published","publishing"}:await service.invalidate(item,"同步时来源失效，需重新核对")
        await MemorySyncOutboxRepository(session,org_id).create_pending(memory_id=item.memory_id,action="DELETE_ACTIVE_VECTOR",target_backend="qdrant",payload={"memory_id":item.memory_id})
        return
    memory=await service.memory(item);memory.status="active";memory.review_status="approved"
    if item.snapshot["requested_scope"]=="organization":
        session.add(MemoryScopeBinding(org_id=org_id,memory_id=item.memory_id,scope_type="org_space",scope_id=org_id,
            binding_kind="shared",binding_status="active",approved_by=item.share_approved_by,approved_at=utcnow(),created_by=item.created_by))
    item.publication_status="published";item.published_at=utcnow();item.row_version+=1
    await service.event(item,"knowledge.published",{"scope":item.snapshot["requested_scope"]})
    await MemorySyncOutboxRepository(session,org_id).create_pending(memory_id=item.memory_id,action="UPSERT_MEMORY_NODE",target_backend="neo4j",
        payload={"memory_id":item.memory_id,"org_id":org_id,"memory_type":memory.memory_type,"status":"active","review_status":"approved",
            "origin_kind":"knowledge_admission","scope_key":f"org_space:{org_id}" if item.snapshot["requested_scope"]=="organization" else f"user:{item.created_by}",
            "trust_score":0.0,"confidence":0.0,"sync_version":2,"applicability_json":json.dumps(memory.applicability_json,ensure_ascii=False)})
    for parent in item.snapshot.get("related_memory_ids") or []:
        await MemorySyncOutboxRepository(session,org_id).create_pending(memory_id=item.memory_id,action="UPSERT_MEMORY_EDGE",target_backend="neo4j",
            payload={"org_id":org_id,"source_memory_id":item.memory_id,"target_memory_id":parent,"edge_type":"derived_from","strength":1.0,
                "metadata_json":{"admission_id":item.id}})
