"""Resolve genuine objects in their existing scope, never client-supplied bodies."""
import hashlib
import json
import re
from sqlalchemy import select
from app.core.exceptions import ForbiddenError,NotFoundError,ValidationError
from app.core.permissions import has_permission
from app.models.knowledge_admission import RagSpaceGrant
from app.models.rag_space import RagSpace,RagDocument,RagDocumentChunk
from app.models.task import InspectionTask
from app.models.result import InspectionResult
from app.models.meeting import MeetingRoom,MeetingRoomMember,MeetingMessage
from app.models.quality_risk import QualitySourceRecord
from app.models.standard_admission import StandardDocumentRevision
from app.models.inspection_standard_library import StandardDocument


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str,separators=(",",":")).encode()).hexdigest()


class KnowledgeSourceService:
    def __init__(self,session,current):self.session,self.current=session,current

    async def row(self,model,object_id):
        q=select(model).where(model.id==object_id,model.org_id==self.current.org_id)
        if hasattr(model,"deleted_at"):q=q.where(model.deleted_at.is_(None))
        row=(await self.session.execute(q)).scalar_one_or_none()
        if not row:raise NotFoundError("来源不存在或不在当前授权范围")
        return row

    async def resolve(self,kind,object_id,quote="",*,organization=False,preview=False):
        actor=self.current.user_id
        org=self.current.org_id
        meta={};body="";shareable=False;authority="reference_only"
        if kind=="rag_document":
            doc=await self.row(RagDocument,object_id);space=await self.row(RagSpace,doc.rag_space_id)
            if space.resource_domain=="formal_standard":
                raise ValidationError("公共标准请引用标准修订，不通过普通资料重复形成标准依据")
            grant=None
            if space.created_by!=actor:
                grant=(await self.session.execute(select(RagSpaceGrant).where(RagSpaceGrant.org_id==org,RagSpaceGrant.space_id==space.id,
                    RagSpaceGrant.user_id==actor,RagSpaceGrant.status=="active"))).scalar_one_or_none()
                if not grant:raise NotFoundError("来源资料未获授权")
            shareable=space.created_by==actor or bool(grant and grant.allow_knowledge_submission)
            if not shareable and not preview:raise ForbiddenError("资料仅授权查阅，尚未授权向审核者提交知识候选")
            chunks=(await self.session.execute(select(RagDocumentChunk.content_text).where(RagDocumentChunk.org_id==org,
                RagDocumentChunk.document_id==doc.id,RagDocumentChunk.deleted_at.is_(None)).order_by(RagDocumentChunk.chunk_index))).scalars().all()
            body="\n".join(chunks)
            digest=doc.checksum_sha256 or fingerprint(body)
            meta={"title":doc.file_name,"space_id":space.id,"owner_id":space.created_by,"file_hash":digest,
                "grant_id":grant.id if grant else None,"grant_version":grant.row_version if grant else None}
        elif kind=="standard_revision":
            if not has_permission("inspection_standard_library_read",self.current.role):raise ForbiddenError("没有标准读取权限")
            rev=await self.row(StandardDocumentRevision,object_id);doc=await self.row(StandardDocument,rev.document_id)
            body="\n".join(p["text"] for p in rev.pages_json or [])
            digest=fingerprint({"snapshot":rev.snapshot,"pages":rev.pages_json})
            authority="formal_standard" if rev.publication_status=="published" and doc.published_revision_id==rev.id else "unpublished_standard"
            meta={"title":rev.snapshot["standard_no"],"document_id":doc.id,"revision_id":rev.id,"publication_status":rev.publication_status,
                "file_hash":rev.file_hash,"standard_status":rev.snapshot.get("standard_status"),"authority":authority}
            shareable=True
        elif kind=="task_result":
            result=await self.row(InspectionResult,object_id);task=await self.row(InspectionTask,result.task_id)
            if task.created_by!=actor and (str(self.current.role)!="expert" or not has_permission("result",self.current.role)):
                raise NotFoundError("结果不在当前任务范围")
            shareable=task.created_by==actor or result.signed_by==actor
            if not shareable:raise ForbiddenError("任务结果可查阅，但知识提交须由任务创建者或签发者进行")
            body=json.dumps({"verdict":result.verdict,"defects":result.defects,"citations":result.citations,
                "reasoning_chain":result.reasoning_chain,"review_note":result.review_note},ensure_ascii=False,default=str)
            digest=fingerprint({"body":body,"reviewed_at":result.reviewed_at,"signed_at":result.signed_at})
            meta={"title":"任务结果","task_id":task.id,"result_status":result.result_status,"reviewed":bool(result.reviewed_at),
                "signed":bool(result.signed_at),"authority":"legacy_result_reference","assessment_scope":(result.reasoning_chain or {}).get('assessment_scope') or 'legacy_auxiliary_record',
                "product_verdict":"not_assessed"}
        elif kind=="meeting_message":
            msg=await self.row(MeetingMessage,object_id);room=await self.row(MeetingRoom,msg.room_id)
            member=(await self.session.execute(select(MeetingRoomMember.id).where(MeetingRoomMember.org_id==org,
                MeetingRoomMember.room_id==room.id,MeetingRoomMember.user_id==actor,MeetingRoomMember.deleted_at.is_(None)))).scalar_one_or_none()
            if room.created_by!=actor and not member:raise NotFoundError("不属于该会议")
            message_meta=msg.metadata_json or {}
            if message_meta.get("recalled_at"):raise NotFoundError("会议消息已撤回")
            recipient=message_meta.get("private_recipient_user_id") or message_meta.get("response_owner_user_id")
            if recipient and actor not in {msg.user_id,recipient}:raise NotFoundError("私人会议消息不可读取")
            shareable=room.created_by==actor and not recipient
            if organization and not shareable:raise ForbiddenError("会议内容跨出会议范围须由会议创建者确认，私人消息不可发布组织知识")
            if not shareable and msg.user_id!=actor:raise ForbiddenError("不能将他人的会议发言提交到其他审核范围")
            body=msg.content;digest=fingerprint({"content":body,"metadata":message_meta})
            meta={"title":"会议发言","room_id":room.id,"message_id":msg.id,"message_type":msg.message_type,
                "authority":"meeting_opinion","private":bool(recipient)}
        elif kind=="intake_record":
            record=await self.row(QualitySourceRecord,object_id)
            own=record.created_by==actor
            if not own and (record.authorization_scope=="private" or not has_permission("quality_material_read_business",self.current.role)):
                raise NotFoundError("资料接入记录不在当前授权范围")
            shareable=own or record.authorization_scope!="private"
            body=json.dumps(record.content,ensure_ascii=False,default=str)
            digest=fingerprint({"content":record.content,"attachments":record.attachment_ids,"nature":record.data_nature})
            meta={"title":"资料接入记录","record_type":record.record_type,"data_nature":record.data_nature,
                "attachment_ids":record.attachment_ids,"authority":"observed_material"}
        elif kind=="inspection_execution":
            from app.services.inspection_execution_service import InspectionExecutionService
            service=InspectionExecutionService(self.session,self.current)
            run=await service.get(object_id)
            serialized=await service.serialize(run)
            issues=serialized['current_source_issues']
            shareable=run.created_by==actor or run.reviewed_by==actor
            if not shareable:raise ForbiddenError("执行结果可查阅，候选提交由发起者或复核者进行")
            from app.services.task_result_bundle_service import execution_digest
            body=json.dumps({'evaluation':run.evaluation,'scope':{'product_verdict':'not_assessed','sample_ids':run.snapshot['sample_ids']},
                'standard_sources':run.snapshot['source_refs'],'policy':run.snapshot['policy'],'row_version':run.row_version,
                'reviewed_by':run.reviewed_by,'reviewed_at':run.reviewed_at,
                'review_history':serialized['review_history']},ensure_ascii=False,default=str)
            digest=execution_digest(run,serialized['review_history'])
            meta={"title":"标准项目执行结果","task_id":run.task_id,"run_id":run.id,"status":run.status,
                "row_version":run.row_version,"assessment_scope":"selected_confirmed_requirements","product_verdict":"not_assessed",
                "authority":"reviewed_selected_items" if run.status=="accepted" and not issues else "execution_draft"}
        else:raise ValidationError("不支持的来源类型")
        if organization and not shareable:raise ForbiddenError("尚未获得将该来源用于组织知识的授权")
        if quote:
            clean=lambda value:re.sub(r"\s+","",value)
            if clean(quote) not in clean(body):raise ValidationError("引用片段与实际来源不一致，请重新选取")
        # Only the deliberately selected excerpt leaves the originating workspace.
        result={"kind":kind,"id":object_id,"source_version":digest,"quote":quote,"metadata":meta,
            "authority":meta.get("authority",authority),"independence_key":meta.get("file_hash") or digest}
        if preview:result["available_excerpt"]=body[:8000]
        return result
