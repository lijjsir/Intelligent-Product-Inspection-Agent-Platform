"""Create a preparation task and bind its verified origin in one transaction."""
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import ConflictError,ForbiddenError,NotFoundError,ValidationError
from app.core.permissions import require_role
from app.models.quality_risk import QualityProduct,ProductCategory,QualityProductionBatch
from app.services.quality_risk_service import stable_hash
from app.services.task_service import TaskService


class RiskLabTaskService:
    def __init__(self,lab):self.lab,self.db=lab,lab.db

    async def context(self,link_id):
        await self.lab.guard()
        row=await self.lab.row(link_id)
        case=await self.lab.demo.risk.risk_case(row.data['case_id'])
        latest=await self.lab.demo.latest(case)
        scope=case.scope or {};reasons=[]
        for key in ('product_id','category_id','quality_batch_id'):
            if scope.get(key):
                try:UUID(str(scope[key]))
                except (ValueError,TypeError,AttributeError):raise ValidationError('事项对象编号未整理，请先确认产品与批次') from None
        if self.lab.demo.is_demo:reasons.append('演示环境不创建实际检测任务，请使用模拟报告路径验收。')
        if self.lab.path(row.data)!='task' or row.data['mode']!='verify':reasons.append('请选择并保存“组织新的检测”路径。')
        if row.created_by!=self.lab.actor:reasons.append('只有验证申请编写人可以创建并关联任务。')
        if not latest or latest.id!=row.data['assessment_id']:reasons.append('原研判已有新版本，请在最新版本中记录验证申请。')
        if row.data.get('record_ids') or row.data.get('execution_returns'):reasons.append('已有结果回流，请保留原记录，在新版研判中继续处理。')
        product=await self.db.scalar(select(QualityProduct).where(QualityProduct.org_id==self.lab.org_id,QualityProduct.id==scope.get('product_id'),QualityProduct.deleted_at.is_(None))) if scope.get('product_id') else None
        category=await self.db.scalar(select(ProductCategory).where(ProductCategory.org_id==self.lab.org_id,ProductCategory.id==product.category_id,ProductCategory.deleted_at.is_(None))) if product else None
        if not product or not product.is_active or not category or not category.is_active:reasons.append('创建检测任务前须确认有效的具体产品及产品类别，企业或类别不能替代具体产品。')
        if product and scope.get('category_id') and scope['category_id']!=product.category_id:reasons.append('事项产品与类别不一致，请先整理对象。')
        batch=None
        if scope.get('quality_batch_id'):
            batch=await self.db.scalar(select(QualityProductionBatch).where(QualityProductionBatch.org_id==self.lab.org_id,
                QualityProductionBatch.id==scope['quality_batch_id'],QualityProductionBatch.product_id==scope.get('product_id'),QualityProductionBatch.deleted_at.is_(None)))
            if not batch or (scope.get('production_batch_ref') and scope['production_batch_ref']!=batch.original_batch_no):reasons.append('事项批次无法核对，请先整理对象。')
        basis,_=await self.lab.demo.capture(case)
        if row.data.get('basis_hash')!=stable_hash(basis):reasons.append('对象或资料已变化，请重新保存当前验证安排。')
        return {'link_id':row.id,'case_id':case.id,'case_code':case.code,'case_title':case.title,'assessment_id':row.data['assessment_id'],
            'assessment_version':row.data['assessment_version'],'purpose':row.data['purpose'],'revision':row.version,'basis_hash':stable_hash(basis),
            'task_id':row.data.get('task_id'),'can_create':not reasons and not row.data.get('task_id'),'blockers':reasons,
            'product_id':product.id if product else None,'product_name':product.name if product else '尚未确认具体产品',
            'category_id':category.id if category else None,'category_name':category.name if category else '未知',
            'quality_batch_id':batch.id if batch else None,'production_batch_ref':scope.get('production_batch_ref') or (batch.original_batch_no if batch else None),
            'unit_serial_ref':scope.get('unit_serial_ref'),'request_stage':row.data.get('request_stage','reviewed')}

    async def create(self,link_id,payload):
        actor=await self.lab.guard(write=True)
        require_role('task',self.lab.current.role)
        row=await self.lab.row(link_id)
        if row.created_by!=self.lab.actor:raise ForbiddenError('只有验证申请编写人可以创建任务')
        token=stable_hash({'standard':str(payload.inspection_standard_id),'priority':payload.priority})
        existing=row.data.get('task_creation')
        if existing:
            if existing['request_key']!=str(payload.request_key) or existing['payload_hash']!=token:
                raise ConflictError('本申请已经创建任务，请查看原任务，不要重复创建')
            task=await self.lab.task(row.data['task_id'],await self.lab.demo.risk.risk_case(row.data['case_id']))
            return {'task_id':task.id,'link':await self.lab.serialize(row),'reused':True}
        context=await self.context(link_id)
        if not context['can_create']:raise ConflictError('暂不能创建验证任务',detail={'blockers':context['blockers']})
        if row.version!=payload.expected_revision or context['basis_hash']!=payload.expected_basis_hash or row.data['basis_hash']!=payload.expected_basis_hash:
            raise ConflictError('验证申请、对象或资料已变化，请重新保存验证安排后创建任务')
        from app.services.inspection_standard_library_service import InspectionStandardLibraryService
        choices=await InspectionStandardLibraryService(self.db,self.lab.org_id).list_task_choices()
        standard=next((s for s in choices if s['id']==str(payload.inspection_standard_id)),None)
        if not standard:raise ValidationError('请选择当前组织有效的检测标准配置')
        task=await TaskService(self.db,self.lab.org_id,actor_user_id=self.lab.actor,actor_role=self.lab.current.role).create_task(
            created_by=self.lab.actor,product_id=context['product_id'],spec_code=standard['spec_code'],image_urls=[],priority=payload.priority,
            inspection_standard_id=str(payload.inspection_standard_id),product_category_id=context['category_id'],quality_product_id=context['product_id'],
            quality_batch_id=context['quality_batch_id'],metadata={'input_mode':'measurement','supervision':True,'source':'risk_verification',
                'risk_verification_id':row.id,'verification_purpose':row.data['purpose'],'risk_case_id':context['case_id'],
                'risk_assessment_id':context['assessment_id'],'production_batch_ref':context['production_batch_ref'],'unit_serial_ref':context['unit_serial_ref']})
        task.status='pending'  # Preparation only; no runner, device or model is started.
        row.version+=1
        row.data={**row.data,'task_id':task.id,'task_creation':{'request_key':str(payload.request_key),'payload_hash':token},
            'events':[*row.data['events'],self.lab.demo.event(actor,'task_created',task_id=task.id)]}
        await self.db.flush()
        return {'task_id':task.id,'link':await self.lab.serialize(row),'reused':False}

    async def origin(self,link_id,task_id):
        await self.lab.guard()
        row=await self.lab.row(link_id)
        if row.data.get('task_id')!=task_id:raise NotFoundError('检测任务不属于本验证申请')
        case=await self.lab.demo.risk.risk_case(row.data['case_id'])
        await self.lab.task(task_id,case)
        return {key:value for key,value in (await self.context(link_id)).items() if key in {
            'link_id','case_id','case_code','case_title','assessment_id','assessment_version','purpose','task_id','request_stage'}}
