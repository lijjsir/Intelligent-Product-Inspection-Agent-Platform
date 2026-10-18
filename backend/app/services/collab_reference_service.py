"""Paged active members and joined meeting rooms for collaboration selectors."""
from sqlalchemy import exists,func,select
from app.core.exceptions import ForbiddenError,NotFoundError,ValidationError
from app.models.user import User
from app.models.meeting import MeetingRoom,MeetingRoomMember
from app.services.risk_collaboration_service import check_room_access


class CollabReferenceService:
    def __init__(self,db,current):
        self.db,self.current=db,current

    async def page(self,kind,*,page=1,size=20,keyword='',selected_ids=(),expert_only=False):
        if kind not in {'user','meeting_room'} or page<1 or not 1<=size<=50 or len(selected_ids)>20: raise ValidationError('协同选项分页参数无效')
        org,actor=str(self.current.org_id),str(self.current.user_id)
        if kind=='user':
            model=User;column=User.username
            query=select(model).where(model.org_id==org,model.is_active.is_(True),model.deleted_at.is_(None),model.id!=actor)
            if expert_only:query=query.where(model.role=='expert')
        else:
            model=MeetingRoom;column=model.title
            query=select(model).where(model.org_id==org,model.deleted_at.is_(None),model.status=='active',exists(select(MeetingRoomMember.id).where(
                MeetingRoomMember.org_id==org,MeetingRoomMember.room_id==model.id,MeetingRoomMember.user_id==actor,MeetingRoomMember.deleted_at.is_(None))))
        async def serialize(rows):
            result=[]
            for row in rows:
                if kind=='meeting_room':
                    try:await check_room_access(self.db,org,actor,self.current.role,row)
                    except (ForbiddenError,NotFoundError):continue
                result.append({'value':row.id,'label':row.username if kind=='user' else row.title})
            return result
        chosen=await serialize(list(await self.db.scalars(query.where(model.id.in_(selected_ids)).execution_options(populate_existing=True)))) if selected_ids else []
        if keyword.strip():query=query.where(column.contains(keyword.strip(),autoescape=True))
        count=int(await self.db.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows=list(await self.db.scalars(query.order_by(column,model.id).offset((page-1)*size).limit(size)))
        return {'items':await serialize(rows),'selected':chosen,'unavailable_selected_ids':sorted(set(selected_ids)-{r['value'] for r in chosen}),
            'total':count if kind=='user' else None,'page':page,'size':size,'has_more':page*size<count}
