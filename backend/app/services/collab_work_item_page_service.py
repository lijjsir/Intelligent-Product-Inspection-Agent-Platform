"""Bounded mixed-source collaboration pages with native access checks."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, func, literal, or_, select, union_all

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.collab import CollabMessage, CollabMessageReceipt, CollabThread, CollabThreadParticipant
from app.models.meeting import MeetingRoom, MeetingRoomMember, MemoryTransferLog
from app.models.memory import MemoryItem
from app.services.record_scan_page import read_mark, write_mark


class CollabWorkItemPageService:
    def __init__(self, service):
        self.svc=service;self.db=service._session;self.org=service._org_id;self.actor=service._user_id

    def index(self,*,item_type=None,keyword='',scope_type=None,room_id=None):
        message,thread,receipt=CollabMessage,CollabThread,CollabMessageReceipt
        action=select(literal('action_request').label('kind'),message.id.label('id'),message.created_at.label('at')).join(thread,and_(thread.id==message.thread_id,thread.org_id==self.org)).where(
            message.org_id==self.org,message.deleted_at.is_(None),thread.deleted_at.is_(None),message.message_type=='action_request',
            exists(select(CollabThreadParticipant.id).where(CollabThreadParticipant.org_id==self.org,CollabThreadParticipant.thread_id==thread.id,
                CollabThreadParticipant.participant_type=='user',CollabThreadParticipant.participant_id==self.actor,CollabThreadParticipant.deleted_at.is_(None))),
            or_(and_(message.sender_type=='user',message.sender_id==self.actor),exists(select(receipt.id).where(receipt.org_id==self.org,receipt.message_id==message.id,
                receipt.recipient_type=='user',receipt.recipient_id==self.actor,receipt.deleted_at.is_(None)))))
        if scope_type: action=action.where(or_(thread.source_type==scope_type,thread.target_type==scope_type))
        if room_id: action=action.where(or_(and_(thread.source_type=='meeting_room',thread.source_id==room_id),and_(thread.target_type=='meeting_room',thread.target_id==room_id)))
        if keyword: action=action.where(or_(thread.title.contains(keyword,autoescape=True),message.content.contains(keyword,autoescape=True),message.metadata_json['action_request']['title'].as_string().contains(keyword,autoescape=True)))
        transfer=MemoryTransferLog
        # Room scope IDs are strings, while room primary keys are binary UUIDs.
        from app.services.risk_report_listing_service import uuid_text
        host=exists(select(MeetingRoom.id).where(MeetingRoom.org_id==self.org,uuid_text(MeetingRoom.id)==transfer.to_scope_id,MeetingRoom.deleted_at.is_(None),or_(MeetingRoom.created_by==self.actor,
            exists(select(MeetingRoomMember.id).where(MeetingRoomMember.org_id==self.org,MeetingRoomMember.room_id==MeetingRoom.id,MeetingRoomMember.user_id==self.actor,MeetingRoomMember.role=='host',MeetingRoomMember.deleted_at.is_(None))))))
        memory=select(literal('memory_share').label('kind'),transfer.id.label('id'),transfer.created_at.label('at')).where(transfer.org_id==self.org,transfer.deleted_at.is_(None),
            or_(transfer.from_scope_type!=transfer.to_scope_type,transfer.from_scope_id!=transfer.to_scope_id),
            or_(func.coalesce(transfer.requested_by,transfer.operator_id)==self.actor,transfer.decided_by==self.actor,
                and_(transfer.to_scope_type=='user',transfer.to_scope_id==self.actor),and_(transfer.to_scope_type=='org_space',literal(self.svc._role=='admin')),
                and_(transfer.to_scope_type=='meeting_room',host)))
        if scope_type: memory=memory.where(or_(transfer.from_scope_type==scope_type,transfer.to_scope_type==scope_type))
        if room_id: memory=memory.where(or_(transfer.from_scope_id==room_id,transfer.to_scope_id==room_id))
        if keyword:
            memory=memory.outerjoin(MemoryItem,and_(MemoryItem.org_id==self.org,MemoryItem.memory_id==transfer.memory_id,MemoryItem.deleted_at.is_(None))).where(or_(
                MemoryItem.content_summary.contains(keyword,autoescape=True),MemoryItem.content_json['title'].as_string().contains(keyword,autoescape=True),transfer.transfer_reason.contains(keyword,autoescape=True)))
        return (action if item_type=='action_request' else memory if item_type=='memory_share' else union_all(action,memory)).subquery()

    async def item(self,kind,rid,view=None):
        svc=self.svc
        if kind=='action_request':
            message=await svc._repo.get_message(self.org,rid)
            if not message or message.message_type!='action_request': raise NotFoundError('工作项不存在')
            thread=await svc._ensure_user_participates(str(message.thread_id))
            receipts=(await svc._repo.list_receipts(self.org,[rid])).get(rid,[])
            receipt=next((r for r in receipts if r.recipient_type=='user' and str(r.recipient_id)==self.actor),None)
            initiated=str(message.sender_id)==self.actor
            if not initiated and receipt is None: raise ForbiddenError('工作项不在当前范围')
            status=svc._action_request_status(message,receipts);can=await svc._can_handle_action_request(thread,message,receipt)
            if view=='pending' and not(status=='pending' and can): return None
            if view=='initiated' and not initiated: return None
            if view=='processed' and status=='pending': return None
            return await svc._serialize_action_request_work_item(message,receipt,thread,receipts)
        if kind!='memory_share': raise ValidationError('工作项类型无效')
        row=await self.db.scalar(select(MemoryTransferLog).where(MemoryTransferLog.id==rid,MemoryTransferLog.org_id==self.org,MemoryTransferLog.deleted_at.is_(None)).execution_options(populate_existing=True))
        if not row or (row.from_scope_type,row.from_scope_id)==(row.to_scope_type,row.to_scope_id): raise NotFoundError('工作项不存在')
        status=svc._normalize_transfer_status(row.status);can=await svc._can_handle_memory_share(row)
        initiated=str(row.requested_by or row.operator_id or '')==self.actor
        relevant=initiated or can or str(row.decided_by or '')==self.actor
        if not relevant: raise ForbiddenError('工作项不在当前范围')
        if view=='pending' and not(status=='pending_approval' and can): return None
        if view=='initiated' and not initiated: return None
        if view=='processed' and status=='pending_approval': return None
        return await svc._serialize_memory_share_work_item(row,can_handle=can)

    async def page(self,*,view='pending',item_type=None,scope_type=None,room_id=None,keyword='',size=20,cursor=None):
        if view not in {'pending','initiated','processed'} or item_type not in {None,'action_request','memory_share'} or not 1<=size<=50: raise ValidationError('工作项分页参数无效')
        keyword=keyword.strip();scope=[self.org,self.actor,str(self.svc._role),view,item_type,scope_type,room_id,keyword,size]
        purpose='collab-work-page-v1';index=self.index(item_type=item_type,keyword=keyword,scope_type=scope_type,room_id=room_id)
        query=select(index);mark=read_mark(purpose,scope,cursor)
        if mark:
            at=datetime.fromisoformat(mark['at']);kind=mark.get('kind')
            if kind not in {'action_request','memory_share'}: raise ValidationError('分页已失效，请返回第一页')
            query=query.where(or_(index.c.at<at,and_(index.c.at==at,or_(index.c.kind<kind,and_(index.c.kind==kind,index.c.id<mark['id'])))))
        budget=max(20,size*2);rows=(await self.db.execute(query.order_by(index.c.at.desc(),index.c.kind.desc(),index.c.id.desc()).limit(budget+1))).all()
        items=[];processed=0
        for row in rows[:budget]:
            processed+=1
            try: item=await self.item(row.kind,row.id,view)
            except (ForbiddenError,NotFoundError): continue
            if item: items.append(item)
            if len(items)==size: break
        last=rows[processed-1] if processed else None
        token=write_mark(purpose,scope,{'at':last.at.isoformat(),'id':last.id,'kind':last.kind}) if last and processed<len(rows) else None
        return {'items':items,'next_cursor':token,'has_more':bool(token),'size':size,'order':'created_at_desc'}

    async def get(self,work_item_id):
        try: kind,rid=work_item_id.split(':',1);rid=str(UUID(rid))
        except (ValueError,AttributeError): raise ValidationError('工作项编号无效') from None
        return await self.item(kind,rid)
