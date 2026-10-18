"""Paged references for existing supervision forms; never starts business work."""
from sqlalchemy import func, or_, select

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.permissions import require_role
from app.models.inspection_standard_library import InspectionStandardLibrary
from app.models.quality_risk import QualityRiskCase
from app.models.supervision import SupervisionRecord
from app.models.task import InspectionTask
from app.services.risk_decision_context_service import RiskDecisionContextService
from app.services.task_service import TaskService


class SupervisionOptionService:
    def __init__(self, service):
        self.svc, self.db = service, service.db

    async def page(self, key, *, page=1, size=20, keyword='', task_id=None, selected_ids=()):
        svc = self.svc
        await svc.permissions()
        await svc.require_enabled()
        svc.read_access('inspection-sessions')
        if page < 1 or not 1 <= size <= 50 or len(selected_ids) > 20:
            raise ValidationError('选择列表分页参数无效')
        if task_id:
            task = await TaskService(self.db, svc.org_id, actor_user_id=svc.actor, actor_role=svc.current.role).get_task(task_id)
            if not task or task.org_id != svc.org_id:
                raise NotFoundError('任务不存在或不在当前访问范围')
        kinds = {'regions':'regions','devices':'devices','plans':'sampling-plans','samples':'samples','enterprises':'enterprises','sessions':'inspection-sessions'}
        if key in kinds:
            model = SupervisionRecord
            query = select(model).where(model.org_id == svc.org_id, model.kind == kinds[key], model.status.not_in(['inactive','archived']))
            if key == 'plans': query = query.where(model.status == 'approved')
            if task_id and key in {'samples','sessions'}: query = query.where(model.data['task_id'].as_string() == task_id)
            columns = [model.name, model.code]
        elif key == 'tasks':
            require_role('task', svc.current.role)
            model = InspectionTask
            query = select(model).where(model.org_id == svc.org_id, model.deleted_at.is_(None))
            if str(svc.current.role) == 'user': query = query.where(model.created_by == svc.actor)
            columns = [model.spec_code, model.meta_data['product_name'].as_string(), model.meta_data['task_name'].as_string(), func.lower(func.hex(model.id))]
        elif key == 'standards':
            model = InspectionStandardLibrary
            query = select(model).where(model.org_id == svc.org_id, model.deleted_at.is_(None), model.is_active.is_(True))
            columns = [model.name, model.spec_code]
        elif key == 'cases':
            svc.require_role({'expert'})
            model = QualityRiskCase
            query = select(model).where(model.org_id == svc.org_id, model.deleted_at.is_(None), model.status == 'risk_assessed')
            columns = [model.title, model.code]
        else:
            raise ValidationError('不支持的资料选择类型')
        async def serialize(rows):
            result = []
            for row in rows:
                if key == 'cases':
                    try: context = await RiskDecisionContextService(self.db, svc.current).accepted(row.id)
                    except (ForbiddenError, NotFoundError, ValidationError): continue
                    label = f"{row.code} · {row.title} · 研判第 {context['version']} 版"
                elif key == 'tasks': label = f"{(row.meta_data or {}).get('product_name') or row.product_id} · {row.spec_code} · {row.id}"
                else: label = f"{getattr(row,'code',None) or getattr(row,'spec_code',None) or ''} · {row.name}".strip(' ·')
                result.append({'value':row.id, 'label':label})
            return result
        chosen = await serialize(list(await self.db.scalars(query.where(model.id.in_(selected_ids)).execution_options(populate_existing=True)))) if selected_ids else []
        if keyword.strip(): query = query.where(or_(*(c.contains(keyword.strip(), autoescape=True) for c in columns)))
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = list(await self.db.scalars(query.order_by(model.created_at.desc(), model.id.desc()).offset((page-1)*size).limit(size)))
        return {'items':await serialize(rows), 'selected':chosen, 'unavailable_selected_ids':sorted(set(selected_ids)-{r['value'] for r in chosen}),
            'total':None if key == 'cases' else int(total or 0), 'has_more':page*size < int(total or 0), 'page':page, 'size':size}
