"""Shared downstream context. Formal writes retain real-evidence acceptance gates."""
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import ForbiddenError, ConflictError, ValidationError
from app.core.permissions import require_role
from app.models.organization import Organization
from app.models.user import User
from app.services.demo_risk_workflow_service import DemoRiskWorkflowService, now
from app.services.quality_risk_service import stable_hash
from app.services.risk_evidence_validation_service import validate_risk
from app.services.risk_decision_context_service import RiskDecisionContextService
from app.services.supervision_service import SupervisionService


class RiskWorkflowContextService(DemoRiskWorkflowService):
    def __init__(self, db, current, storage=None):
        super().__init__(db, current, storage)
        self.is_demo = settings.quality_demo_enabled
        self.mode = 'demo' if self.is_demo else 'business'
        if not self.is_demo:
            self.allowed_natures = {'observed', 'inferred'}
            self.nature_description = '正式研判不得引用模拟资料或模拟证据'

    async def guard(self, write=False):
        if self.is_demo:
            return await super().guard(write)
        svc = SupervisionService(self.db, self.current)
        await svc.permissions()
        svc.require_role({'expert'})
        for permission in ('quality', 'quality_material_read_business'):
            require_role(permission, self.current.role)
        await svc.require_enabled()
        stmt = select(Organization).where(Organization.id == self.org_id).execution_options(populate_existing=True)
        org = await self.db.scalar(stmt.with_for_update() if write else stmt)
        if not org or (org.settings or {}).get('execution_mode') == 'demo':
            raise ForbiddenError('演示组织不能切换为正式业务流程')
        self.locked = self.locked or write
        return await self.db.get(User, self.actor)

    async def capture(self, case):
        if not self.is_demo and (case.scope or {}).get('execution_mode') == 'demo':
            raise ForbiddenError('演示事项不能进入正式业务流程')
        return await super().capture(case)

    async def validation(self, case, row, captured=None):
        if self.is_demo:
            return await super().validation(case, row, captured)
        basis, issues = captured or await self.capture(case)
        check = await validate_risk(self.db, self.current, case, row, self.risk.storage)
        issues = [*issues, *check['blockers']]
        if any(i.get('code') == 'demo_source_authorization' for i in issues):
            issues.append({'code':'workflow_sharing_required', 'message':'协同和报告须有当前资料共享授权；请由资料所有人明确共享后重新生成研判并独立复核。'})
        return {'checked_at':now(), 'blockers':issues, 'is_current':not issues,
            'basis_hash':stable_hash(basis), 'boundary':'正式研判下游流程保留原始证据及独立复核门禁，不启动抽查或检测。'}

    async def target(self, case_id, assessment_id):
        if self.is_demo:
            return await super().target(case_id, assessment_id)
        case = await self.risk.risk_case(case_id, lock=True)
        latest = await self.latest(case)
        if not latest or latest.id != assessment_id:
            raise ConflictError('研判版本已更新，请刷新核对最新版本')
        await self.capture(case)
        return case, latest

    async def ensure_current(self, case, row):
        if self.is_demo:
            return await super().ensure_current(case, row)
        if not row.submitted_by:
            raise ConflictError('历史研判缺少编写身份，请重新生成并独立复核')
        context = await RiskDecisionContextService(self.db, self.current, self.risk.storage).accepted(case.id)
        if context['source_ref']['assessment_id'] != row.id:
            raise ConflictError('正式研判已有新版本')
        validation = await self.validation(case, row)
        if not validation['is_current']:
            raise ConflictError('当前来源或授权已变化，请重新研判复核', detail={'blockers':validation['blockers']})

    async def context(self, case):
        if self.is_demo:
            context = await super().context(case)
            latest = await self.latest(case)
            return {**context, 'assessment_id':latest.id if latest else None,
                'eligible':bool(latest and latest.status == 'demo_reviewed' and (await self.validation(case, latest))['is_current'])}
        await self.guard()
        latest = await self.latest(case)
        basis, issues = await self.capture(case)
        eligible = False
        if latest:
            try:
                await self.ensure_current(case, latest)
                eligible = True
            except (ConflictError, ForbiddenError, ValidationError) as exc:
                issues = [*issues, {'message':exc.message}]
        return {'enabled':True, 'execution_mode':'business', 'can_author':True, 'eligible':eligible,
            'assessment_id':latest.id if latest else None, 'basis_hash':stable_hash(basis), 'blockers':issues,
            'boundary':'仅当前已独立复核、真实来源仍有效的正式研判可进入下游；模拟资料不进入正式流程。'}

    def content(self, row, case):
        if self.is_demo:
            return row.model_versions['demo_workflow']['content']
        analysis = (row.model_versions or {}).get('analysis_summary') or {}
        level = {'unknown':'未知','low':'低','medium':'中','high':'高','critical':'严重'}.get(row.risk_level, '未知')
        return {'summary':f"{row.risk_type or '质量风险'}：独立复核后本版风险等级为{level}。",
            'reasoning':'\n'.join(filter(None, [
                '生成时分析摘要（供复核追溯）：' + analysis['summary'] if analysis.get('summary') else '',
                '；'.join(row.possible_causes or []) or '分析依据以原始资料、引用证据和独立复核意见为准。'])),
            'limitations':'；'.join(analysis.get('limitations') or ['本报告是风险研判记录，不替代检测报告或抽查执行指令；发生概率以原研判校准状态为准。']),
            'risk_type':row.risk_type, 'risk_level':row.risk_level, 'cited_record_ids':list(case.source_record_ids or []),
            'missing_inputs':list(row.missing_inputs or []), 'recommendations':list(row.recommendations or [])}
