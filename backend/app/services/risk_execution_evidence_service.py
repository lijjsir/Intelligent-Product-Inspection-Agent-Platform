"""References to native, independently reviewed execution results; no copied intake rows."""
import copy

from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permissions import require_role
from app.models.quality_risk import QualityDataSource, QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.services.execution_evidence_service import ExecutionEvidenceService
from app.services.inspection_execution_service import InspectionExecutionService
from app.services.knowledge_source_service import fingerprint

LAB_KIND = 'risk-lab-verifications'


async def execution_returns(session, org_id, case_id, *, active_only=True, lock=False):
    query = select(SupervisionRecord).where(
        SupervisionRecord.org_id == org_id, SupervisionRecord.kind == LAB_KIND,
        SupervisionRecord.data['case_id'].as_string() == case_id,
    ).order_by(SupervisionRecord.id).execution_options(populate_existing=True)
    rows = await session.scalars(query.with_for_update() if lock else query)
    result = []
    for row in rows:
        if row.data.get('execution_mode') != 'business':
            continue
        for entry in row.data.get('execution_returns', []):
            if not active_only or not entry.get('withdrawn_at'):
                result.append({**copy.deepcopy(entry), 'link_id':row.id})
    return sorted(result, key=lambda item:item['id'])


class RiskExecutionEvidenceService:
    def __init__(self, db, current, storage=None):
        self.db, self.current, self.storage = db, current, storage
        self.org_id = str(current.org_id)
        self.native = InspectionExecutionService(db, current, storage)

    def permissions(self):
        for permission in ('task', 'result', 'inspection_execution', 'quality_material_read_business'):
            require_role(permission, self.current.role)

    async def authorize(self, ref):
        """Recheck shared report origins even when reading an older frozen report."""
        self.permissions()
        await self.native.task(ref['task_id'])
        validator = ExecutionEvidenceService(self.db, self.current, self.storage)
        for origin in ref.get('report_sources', []):
            record = await self.db.scalar(select(QualitySourceRecord).where(
                QualitySourceRecord.id == origin['record_id'], QualitySourceRecord.org_id == self.org_id,
                QualitySourceRecord.deleted_at.is_(None)).execution_options(populate_existing=True))
            if not record:
                raise NotFoundError('回流检测报告的原始来源已撤回或不在当前组织')
            if record.authorization_scope not in {'organization', 'business', 'public'} or not validator.record_authorized(record):
                raise ForbiddenError('检测结果回流需原报告明确共享到业务范围，独立复核授权不能代替共享')
            if record.data_nature != 'observed' or record.record_type != 'inspection_report':
                raise ForbiddenError('回流结果的原报告不再属于真实检测资料')
            if origin['attachment_id'] not in (record.attachment_ids or []):
                raise ForbiddenError('回流结果的原报告附件关联已撤回')
            source = await self.db.scalar(select(QualityDataSource).where(
                QualityDataSource.id == record.source_id, QualityDataSource.org_id == self.org_id,
                QualityDataSource.deleted_at.is_(None), QualityDataSource.status == 'active'))
            if not source:
                raise ForbiddenError('回流结果的资料来源已停用或撤回')
            await validator.attachment(origin['attachment_id'])

    async def checked(self, case, run, *, expected=None):
        self.permissions()
        task = await self.native.task(run.task_id)
        if (task.meta_data or {}).get('execution_mode') == 'demo' or run.snapshot.get('execution_mode') == 'demo':
            raise ValidationError('演示检测结果不能返回正式事项')
        product = (case.scope or {}).get('product_id')
        scope = (run.snapshot.get('task_context') or {}).get('scope') or {}
        if not product or task.quality_product_id != product or scope.get('quality_product_id') != product:
            raise ValidationError('检测任务和冻结结果必须明确关联原事项同一产品')
        for key in ('production_batch_ref', 'unit_serial_ref'):
            if (case.scope or {}).get(key) and scope.get(key) != case.scope[key]:
                raise ValidationError('检测结果的批次或单件范围与原事项不一致')
        if run.status != 'accepted' or not run.reviewed_at or not run.reviewed_by or run.reviewed_by == run.created_by:
            raise ValidationError('只能回流已由另一位专家独立复核的检测结果')
        reports = (run.snapshot.get('task_context') or {}).get('report_links', [])
        sources = []
        for attachment_id in sorted({o['attachment_id'] for o in run.snapshot.get('observations', []) if o.get('kind') == 'report_attachment'}):
            link = next((item for item in reports if item['attachment_id'] == attachment_id), None)
            if not link:
                raise ValidationError('历史检测结果未冻结原报告来源，请重新核验检测结果')
            sources.append({'record_id':link['source_record_id'], 'attachment_id':attachment_id})
        ref = {'run_id':run.id, 'task_id':task.id, 'row_version':run.row_version, 'report_sources':sources}
        await self.authorize(ref)
        verification = await self.native.verification(run)
        if verification['blockers'] or not verification.get('independent_review'):
            raise ValidationError('检测结果当前依据或独立复核已失效', detail={'blockers':verification['blockers']})
        if fingerprint(verification['current_evaluation']) != fingerprint(run.evaluation):
            raise ValidationError('已复核结果与当前项目计算不一致，请重新核对检测结果')
        # Freeze source definitions and sharing state as well as the native result.
        definitions = []
        for source in sources:
            record = await self.db.get(QualitySourceRecord, source['record_id'])
            definitions.append({**source, 'definition':fingerprint({key:getattr(record,key) for key in (
                'content', 'content_hash', 'attachment_ids', 'data_nature', 'authorization_scope', 'product_ref',
                'enterprise_ref', 'provenance', 'occurred_at', 'created_by', 'source_id')})})
        ref['definition_hash'] = fingerprint({'snapshot':run.snapshot, 'evaluation':run.evaluation,
            'status':run.status, 'reviewed_by':run.reviewed_by, 'reviewed_at':run.reviewed_at,
            'row_version':run.row_version, 'review':verification['independent_review'], 'sources':definitions})
        if expected is not None and ref != expected:
            raise ConflictError('检测结果、复核或原报告版本已变化，请撤回旧引用后重新核对')
        return ref

    async def resolve(self, case, ref):
        run = await self.native.get(ref['run_id'])
        # Accepted native runs are immutable through their API. Refresh their
        # identity-map state without locking shared runs in different case orders.
        await self.db.refresh(run)
        await self.checked(case, run, expected=ref)
        return run

    @staticmethod
    def context(run):
        return {'kind':'inspection_execution', 'run_id':run.id, 'task_id':run.task_id,
            'status':run.status, 'row_version':run.row_version, 'current_source_issues':[],
            'evaluation':RiskExecutionEvidenceService.summary(run), 'source_refs':copy.deepcopy(run.snapshot.get('source_refs', [])),
            'observation_refs':[{key:item.get(key) for key in ('evidence_id','kind','measurement_key','sample_id')}
                for item in run.snapshot.get('observations', [])]}

    @staticmethod
    def summary(run):
        return {key:copy.deepcopy(run.evaluation.get(key)) for key in (
            'item_verdict','product_verdict','risk_level','complete_count','expected_count','missing_inputs','boundary')}
