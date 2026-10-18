"""Bounded, authorization-checked summaries; evidence validity is checked on detail."""
import base64
import hashlib
import json
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, cast, exists, func, literal, or_, select

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.permissions import has_permission
from app.models.meeting import MeetingRoom, MeetingRoomMember
from app.models.quality_risk import QualityAttachment, QualityDataSource, QualityRiskAssessment, QualityRiskCase, QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.models.task import InspectionTask
from app.services.quality_risk_service import stable_hash

KIND = 'risk-assessment-reports'


def cursor_cipher():
    # Use the configured signing private key, with a purpose-specific derivation.
    # The token hides skipped, inaccessible report IDs and survives worker changes.
    if not settings.jwt_private_key:
        raise ValidationError('分页密钥配置不可用，请联系管理员')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(
        ('risk-report-page-v1\0'+settings.jwt_private_key).encode()).digest()))


def uuid_text(column):
    value = cast(func.lower(func.hex(column)), String)
    return (cast(func.substr(value, 1, 8), String)+literal('-')+func.substr(value, 9, 4)+literal('-')+
        func.substr(value, 13, 4)+literal('-')+func.substr(value, 17, 4)+literal('-')+func.substr(value, 21, 12))


class RiskReportListingService:
    def __init__(self, service):
        self.service, self.db, self.current = service, service.db, service.current
        self.org_id, self.actor, self.mode = service.org_id, service.actor, service.demo.mode

    async def load(self, model, ids, *conditions):
        valid = []
        for value in set(ids):
            try: valid.append(str(UUID(str(value))))
            except (TypeError, ValueError, AttributeError): pass
        result = {}
        for start in range(0, len(valid), 400):
            query = select(model).where(model.org_id == self.org_id, model.id.in_(valid[start:start+400]), *conditions)
            if hasattr(model, 'deleted_at'): query = query.where(model.deleted_at.is_(None))
            rows = await self.db.scalars(query.execution_options(populate_existing=True))
            result.update({r.id:r for r in rows})
        return result

    async def authorized(self, rows):
        rows = [r for r in rows if self.actor in r.data.get('reader_ids', []) and
            r.data.get('snapshot', {}).get('execution_mode') == self.mode and
            stable_hash(r.data['snapshot']) == r.data.get('snapshot_hash')]
        snapshots = [r.data['snapshot'] for r in rows]
        cases = await self.load(QualityRiskCase, [s['case_id'] for s in snapshots])
        assessments = await self.load(QualityRiskAssessment, [s['assessment_id'] for s in snapshots])
        origins = [o for s in snapshots for e in s.get('execution_results', []) for o in e['ref'].get('report_sources', [])]
        records = await self.load(QualitySourceRecord, [r['id'] for s in snapshots for r in s['records']]+[o['record_id'] for o in origins])
        authorized_records = {r.id for r in records.values() if r.created_by == self.actor or
            (r.authorization_scope in {'organization','business','public'} and has_permission('quality_material_read_business', self.current.role))}
        files = await self.load(QualityAttachment, [a['id'] for s in snapshots for a in s['attachments']]+[o['attachment_id'] for o in origins])
        bound = {aid for r in records.values() if r.id in authorized_records for aid in (r.attachment_ids or [])}
        permitted_files = {a.id for a in files.values() if a.uploaded_by == self.actor or a.id in bound}
        remaining = set(files)-permitted_files
        if remaining:
            # Fallback matches the original file rule: another authorized source
            # may share this same file. Query IDs only, never all source bodies.
            query = select(QualityAttachment.id).where(QualityAttachment.org_id == self.org_id,
                QualityAttachment.id.in_(remaining), QualityAttachment.deleted_at.is_(None), exists(select(QualitySourceRecord.id).where(
                    QualitySourceRecord.org_id == self.org_id, QualitySourceRecord.deleted_at.is_(None),
                    or_(QualitySourceRecord.created_by == self.actor, QualitySourceRecord.authorization_scope.in_(['organization','business','public'])
                        if has_permission('quality_material_read_business', self.current.role) else False),
                    cast(QualitySourceRecord.attachment_ids, String).contains(literal('"')+uuid_text(QualityAttachment.id)+literal('"')))))
            permitted_files.update(await self.db.scalars(query))
        sources = await self.load(QualityDataSource, [records[o['record_id']].source_id for o in origins if o['record_id'] in records])
        tasks = await self.load(InspectionTask, [e['ref']['task_id'] for s in snapshots for e in s.get('execution_results', [])])
        suggestions = await self.load(SupervisionRecord, [item['id'] for s in snapshots for item in s['sampling']],
            SupervisionRecord.kind == ('demo-sampling-suggestions' if self.mode == 'demo' else 'risk-sampling-suggestions'))
        links = await self.load(SupervisionRecord, [r.data['snapshot']['collaboration_id'] for r in suggestions.values()]+
            [ref['id'] for s in snapshots for ref in s.get('source_refs', []) if ref['kind'] == 'collab-context'],
            SupervisionRecord.kind == 'risk-collaborations')
        rooms = await self.load(MeetingRoom, [r.data['room_id'] for r in links.values()])
        members = set()
        if rooms:
            members = set(await self.db.scalars(select(MeetingRoomMember.room_id).where(MeetingRoomMember.org_id == self.org_id,
                MeetingRoomMember.user_id == self.actor, MeetingRoomMember.room_id.in_(rooms), MeetingRoomMember.deleted_at.is_(None))))
        link_cases = await self.load(QualityRiskCase, [r.data['case_id'] for r in links.values()])
        link_assessments = await self.load(QualityRiskAssessment, [r.data['assessment_id'] for r in links.values()])
        permitted_links = {r.id for r in links.values() if all(has_permission(p, self.current.role) for p in ('meeting','collab')) and
            r.data.get('execution_mode','demo') == self.mode and self.actor in r.data.get('participant_ids', []) and
            r.data['room_id'] in members and r.data['room_id'] in rooms and
            (rooms[r.data['room_id']].memory_policy or {}).get('risk_collaboration_id') == r.id and
            r.data['case_id'] in link_cases and r.data['assessment_id'] in link_assessments and
            link_assessments[r.data['assessment_id']].risk_case_id == r.data['case_id']}
        result = set()
        for row in rows:
            s = row.data['snapshot']
            if s['case_id'] not in cases or s['assessment_id'] not in assessments: continue
            if self.mode == 'business' and (cases[s['case_id']].scope or {}).get('execution_mode') == 'demo': continue
            if any(r['id'] not in authorized_records for r in s['records']): continue
            if any(a['id'] not in permitted_files for a in s['attachments']): continue
            if any(item['id'] not in suggestions or suggestions[item['id']].data['snapshot']['collaboration_id'] not in permitted_links for item in s['sampling']): continue
            if any(ref['id'] not in permitted_links for ref in s.get('source_refs', []) if ref['kind'] == 'collab-context'): continue
            allowed = True
            for entry in s.get('execution_results', []):
                ref = entry['ref']
                if ref['task_id'] not in tasks or not all(has_permission(p, self.current.role) for p in ('task','result','inspection_execution','quality_material_read_business')):
                    allowed = False; break
                for origin in ref.get('report_sources', []):
                    r = records.get(origin['record_id'])
                    if (not r or r.id not in authorized_records or r.authorization_scope not in {'organization','business','public'} or
                            r.data_nature != 'observed' or r.record_type != 'inspection_report' or origin['attachment_id'] not in (r.attachment_ids or []) or
                            origin['attachment_id'] not in permitted_files or r.source_id not in sources or sources[r.source_id].status != 'active'):
                        allowed = False; break
            if allowed: result.add(row.id)
        return result

    async def page(self, case_id=None, *, size=20, cursor=None, keyword=''):
        await self.service.guard()
        if not 1 <= size <= 50: raise ValidationError('报告每页数量须在 1 到 50 之间')
        keyword = keyword.strip()
        scope = stable_hash([self.org_id, self.actor, self.mode, case_id, keyword, size])
        query = select(SupervisionRecord).where(SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind == KIND,
            SupervisionRecord.data['snapshot']['execution_mode'].as_string() == self.mode,
            cast(SupervisionRecord.data['reader_ids'], String).contains(f'"{self.actor}"', autoescape=True),
            or_(SupervisionRecord.created_by == self.actor,
                SupervisionRecord.data['snapshot']['review']['author_id'].as_string() == self.actor,
                SupervisionRecord.data['snapshot']['review']['reviewer_id'].as_string() == self.actor))
        if case_id: query = query.where(SupervisionRecord.data['snapshot']['case_id'].as_string() == case_id)
        if keyword: query = query.where(SupervisionRecord.name.contains(keyword, autoescape=True))
        if cursor:
            try:
                mark = json.loads(cursor_cipher().decrypt(cursor.encode(), ttl=3600))
                if mark['scope'] != scope: raise ValueError('scope')
                at, rid = datetime.fromisoformat(mark['at']), str(UUID(mark['id']))
                query = query.where(or_(SupervisionRecord.created_at < at,
                    (SupervisionRecord.created_at == at) & (SupervisionRecord.id < rid)))
            except (InvalidToken, ValueError, KeyError, TypeError):
                raise ValidationError('报告分页已失效或筛选条件已变化，请回到第一页') from None
        budget = max(20, size*2)
        fetched = list(await self.db.scalars(query.order_by(SupervisionRecord.created_at.desc(), SupervisionRecord.id.desc()).limit(budget+1)))
        rows = fetched[:budget]
        permitted = await self.authorized(rows)
        items, processed = [], 0
        for row in rows:
            processed += 1
            if row.id in permitted:
                items.append({'id':row.id, 'title':row.name, 'status':row.status, 'frozen_at':row.data['frozen_at'],
                    'effective_status':'snapshot_unchecked', 'source_issues':[], 'validation_checked':False})
            if len(items) == size: break
        more = processed < len(fetched)
        next_cursor = None
        if more and processed:
            last = rows[processed-1]
            next_cursor = cursor_cipher().encrypt(json.dumps({'at':last.created_at.isoformat(), 'id':last.id, 'scope':scope}).encode()).decode()
        return {'items':items, 'next_cursor':next_cursor, 'has_more':bool(next_cursor), 'size':size,
            'notice':'列表为生成时快照摘要；打开报告后核对当前来源和版本。'}
