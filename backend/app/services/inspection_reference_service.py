"""Native execution references use the current task scope, without legacy flags."""
from sqlalchemy import func,or_,select
from app.models.supervision import SupervisionRecord
from app.models.inspection_execution import InspectionPolicyPublication
from app.services.inspection_execution_context_service import InspectionExecutionContextService


class InspectionReferenceService:
    def __init__(self,db,current):self.db,self.current=db,current

    async def page(self,task,kind,*,page=1,size=20,keyword='',selected_ids=()):
        from app.core.exceptions import ValidationError
        if kind not in {'sessions','samples','policies'} or page<1 or not 1<=size<=50 or len(selected_ids)>20:raise ValidationError('检测选择分页参数无效')
        context=InspectionExecutionContextService(self.db,self.current)
        if kind=='policies':
            model=InspectionPolicyPublication;scope=await context.scope(task)
            query=select(model).where(model.org_id==self.current.org_id,model.status=='published')
            columns=[model.snapshot['name'].as_string()]
            def serialize(row):
                issues=context.policy_issues(row,scope)
                return {'value':row.id,'label':f"{row.snapshot.get('name','策略')} · {row.snapshot.get('version','')}"+('（范围不适用）' if issues else ''),'disabled':bool(issues)}
        else:
            model=SupervisionRecord
            query=select(model).where(model.org_id==self.current.org_id,model.kind=='inspection-sessions' if kind=='sessions' else model.kind=='samples',model.data['task_id'].as_string()==task.id)
            columns=[model.name,model.code]
            def serialize(row):return {'value':row.id,'label':f'{row.name} · {row.code}'}
        chosen=list(await self.db.scalars(query.where(model.id.in_(selected_ids)).execution_options(populate_existing=True))) if selected_ids else []
        if keyword.strip():query=query.where(or_(*(col.contains(keyword.strip(),autoescape=True) for col in columns)))
        total=int(await self.db.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows=list(await self.db.scalars(query.order_by(model.created_at.desc(),model.id.desc()).offset((page-1)*size).limit(size)))
        return {'items':[serialize(r) for r in rows],'selected':[serialize(r) for r in chosen],
            'unavailable_selected_ids':sorted(set(selected_ids)-{r.id for r in chosen}),'total':total,'has_more':page*size<total,'page':page,'size':size}
