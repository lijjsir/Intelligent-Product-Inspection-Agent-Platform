from sqlalchemy import select
from app.core.datetime import utcnow
from app.core.exceptions import ConflictError,ForbiddenError,NotFoundError,ValidationError
from app.core.ids import uuid7
from app.models.knowledge_admission import RagSpaceGrant
from app.models.rag_space import RagSpace
from app.models.user import User
from app.models.memory import MemoryEvent


class KnowledgeWorkspaceService:
    def __init__(self,session,current):self.session,self.current=session,current

    async def own(self,space_id):
        space=(await self.session.execute(select(RagSpace).where(RagSpace.id==space_id,RagSpace.org_id==self.current.org_id,
            RagSpace.created_by==self.current.user_id,RagSpace.resource_domain=="workspace",RagSpace.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
        if not space:raise NotFoundError("仅资料所有者可授权共享，公共标准通过标准流程维护")
        return space

    async def targets(self):
        users=(await self.session.execute(select(User.id,User.username,User.role).where(User.org_id==self.current.org_id,
            User.id!=self.current.user_id,User.is_active.is_(True),User.deleted_at.is_(None),User.role.in_(["expert","user"])).limit(200))).all()
        return [{"id":r[0],"name":r[1],"role":r[2]} for r in users]

    async def grants(self,space_id):
        await self.own(space_id)
        rows=(await self.session.execute(select(RagSpaceGrant).where(RagSpaceGrant.org_id==self.current.org_id,
            RagSpaceGrant.space_id==space_id))).scalars().all()
        return [{k:getattr(r,k) for k in ["id","user_id","status","row_version","reason","allow_knowledge_submission"]} for r in rows]

    async def share(self,space_id,payload,*,revoke=False):
        await self.own(space_id)
        user=(await self.session.execute(select(User).where(User.id==payload["user_id"],User.org_id==self.current.org_id,
            User.is_active.is_(True),User.deleted_at.is_(None)))).scalar_one_or_none()
        if not user or user.id==self.current.user_id:raise ValidationError("共享对象须为本组织的其他有效用户")
        grant=(await self.session.execute(select(RagSpaceGrant).where(RagSpaceGrant.org_id==self.current.org_id,
            RagSpaceGrant.space_id==space_id,RagSpaceGrant.user_id==user.id).with_for_update())).scalar_one_or_none()
        version=grant.row_version if grant else 0
        if version!=payload["expected_version"]:raise ConflictError("共享授权已变化，请刷新")
        if revoke and not grant:raise NotFoundError("共享授权不存在")
        if not grant:
            grant=RagSpaceGrant(org_id=self.current.org_id,space_id=space_id,user_id=user.id,granted_by=self.current.user_id,
                reason=payload["reason"],allow_knowledge_submission=payload["allow_knowledge_submission"])
            self.session.add(grant)
        else:
            grant.row_version+=1;grant.status="revoked" if revoke else "active";grant.revoked_at=utcnow() if revoke else None
            grant.reason=payload["reason"];grant.allow_knowledge_submission=payload["allow_knowledge_submission"] if not revoke else False
        self.session.add(MemoryEvent(id=str(uuid7()),event_id="evt_"+str(uuid7()).replace("-",""),org_id=self.current.org_id,
            user_id=self.current.user_id,event_type="knowledge.material_scope_changed",source_kind="rag",
            payload_json={"space_id":space_id,"target_user_id":user.id,"state":"revoked" if revoke else "active","reason":payload["reason"]}))
        await self.session.flush()
        return await self.grants(space_id)
