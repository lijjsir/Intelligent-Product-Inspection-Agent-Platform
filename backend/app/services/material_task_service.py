from sqlalchemy import select
from app.core.exceptions import ForbiddenError,ValidationError
from app.models.quality_risk import QualityAttachment,QualitySourceRecord
from app.schemas.task import ImageItem
from app.services.knowledge_source_service import KnowledgeSourceService,fingerprint
from app.services.task_service import TaskService


class MaterialTaskService:
    def __init__(self,session,current):self.session,self.current=session,current

    async def draft(self,record_id,payload):
        if str(self.current.role) not in {"user","expert"}:raise ForbiddenError("检测任务由普通用户或授权专家发起")
        await KnowledgeSourceService(self.session,self.current).resolve("intake_record",record_id)
        record=(await self.session.execute(select(QualitySourceRecord).where(QualitySourceRecord.org_id==self.current.org_id,
            QualitySourceRecord.id==record_id,QualitySourceRecord.deleted_at.is_(None)).with_for_update())).scalar_one()
        attachments=(await self.session.execute(select(QualityAttachment).where(QualityAttachment.org_id==self.current.org_id,
            QualityAttachment.id.in_(record.attachment_ids or []),QualityAttachment.deleted_at.is_(None)))).scalars().all()
        images=[a for a in attachments if a.mime_type.startswith("image/") and a.sha256]
        if not images:raise ValidationError("该材料没有可追溯图片；测量资料须进入实验检测流程，不能充当图片任务")
        urls=[f"/api/v1/quality-data/attachments/{a.id}/download" for a in images]
        items=[ImageItem(index=i,url=url,hash=a.sha256) for i,(a,url) in enumerate(zip(images,urls))]
        values=payload.model_dump()
        for key in ["image_urls","image_items","input_mode","metadata"]:values.pop(key,None)
        task=await TaskService(self.session,self.current.org_id).create_task(created_by=self.current.user_id,
            **values,image_urls=urls,image_items=items,metadata={"input_mode":"image","supervision":False,
                "material_reference":{"record_id":record.id,"source_version":fingerprint(record.content),"attachment_ids":[a.id for a in images]},
                "execution_requested":False})
        return {"task_id":task.id,"status":task.status,"source_record_id":record.id,"reused_attachment_ids":[a.id for a in images],
            "notice":"已创建待执行任务，复用原附件；实际执行时仍须检查任务依据和图片输入条件。"}


async def resolve_material_images(session,task):
    reference=(task.meta_data or {}).get("material_reference")
    if not reference:return None
    import asyncio,base64,hashlib
    from app.services.permission_service import PermissionService
    from app.core.permissions import PermissionRole
    from app.schemas.user import CurrentUser
    from app.services.object_storage.factory import build_object_storage
    identity=await PermissionService(session,task.org_id).identity(task.created_by)
    current=CurrentUser(user_id=task.created_by,org_id=task.org_id,role=identity["role"])
    current.role=PermissionRole(identity["role"],identity["effective"])
    await KnowledgeSourceService(session,current).resolve("intake_record",reference["record_id"])
    record=(await session.execute(select(QualitySourceRecord).where(QualitySourceRecord.org_id==task.org_id,
        QualitySourceRecord.id==reference["record_id"],QualitySourceRecord.deleted_at.is_(None)))).scalar_one()
    if fingerprint(record.content)!=reference["source_version"]:raise ValidationError("原始材料已改变，请重新核对任务材料")
    requested=set(reference["attachment_ids"])
    if not requested<=set(record.attachment_ids or []):raise ValidationError("任务引用的附件已失效")
    rows=(await session.execute(select(QualityAttachment).where(QualityAttachment.org_id==task.org_id,
        QualityAttachment.id.in_(requested),QualityAttachment.deleted_at.is_(None)))).scalars().all()
    by_id={a.id:a for a in rows};storage=build_object_storage();images=[]
    for aid in reference["attachment_ids"]:
        asset=by_id.get(aid)
        if not asset or not asset.mime_type.startswith("image/"):raise ValidationError("附件不再是可用检测图片")
        stored=await asyncio.to_thread(storage.get_bytes,bucket=asset.bucket,object_key=asset.object_key)
        if not stored or hashlib.sha256(stored[0]).hexdigest()!=asset.sha256:raise ValidationError("原图片丢失或哈希改变")
        images.append(f"data:{asset.mime_type};base64,"+base64.b64encode(stored[0]).decode("ascii"))
    return images
