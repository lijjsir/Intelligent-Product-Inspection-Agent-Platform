"""Local demo MySQL service benchmark. All synthetic fixtures are rolled back."""
import argparse
import asyncio
import copy
import json
import math
import time
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.quality_demo import validate_demo_settings
from app.models.quality_risk import ProductCategory, QualityProduct, QualityDataSource, QualitySourceRecord, QualityAttachment, QualityRiskCase, QualityRiskAssessment
from app.models.supervision import SupervisionRecord
from app.models.task import InspectionTask
from app.schemas.user import CurrentUser
from app.services.quality_demo_seed import demo_id
from app.services.quality_risk_service import QualityRiskService, stable_hash
from app.services.risk_lab_service import RiskLabService
from app.services.risk_report_service import RiskReportService
from infra.database.session import _engine

MODELS = (ProductCategory, QualityProduct, QualityDataSource, QualitySourceRecord, QualityAttachment,
    QualityRiskCase, QualityRiskAssessment, SupervisionRecord, InspectionTask)


class RollbackOnlySession(AsyncSession):
    async def commit(self):
        raise RuntimeError('Benchmark sessions cannot commit fixtures')


class NoFileReads:
    def get_bytes(self, **kwargs):
        raise AssertionError('Report summaries must not read original files')


class ReadyGate:
    def __init__(self, readers):
        self.readers, self.waiting, self.ready = readers, 0, asyncio.Event()

    async def wait(self):
        self.waiting += 1
        if self.waiting == self.readers: self.ready.set()
        await self.ready.wait()


async def counts(connection, org_id):
    result = {}
    for model in MODELS:
        result[model.__tablename__] = await connection.scalar(select(func.count()).select_from(model).where(model.org_id == org_id))
    return result


async def reader(index, args, actor, peer, org, barrier):
    db = RollbackOnlySession(_engine, expire_on_commit=False)
    tag = f'PERF-RB-{uuid4().hex[:10]}-{index}'
    now = datetime(2020,1,1)
    try:
        category = ProductCategory(org_id=org, code=tag, name=tag, is_active=True)
        db.add(category); await db.flush()
        product = QualityProduct(org_id=org, category_id=category.id, name=tag, attributes={}, is_active=True)
        source = QualityDataSource(org_id=org, code=tag, name='【模拟回滚压测】', source_type='mixed', connector_type='manual', config={}, status='active', created_by=actor)
        attachment = QualityAttachment(org_id=org, uploaded_by=peer, file_name='【无原件的回滚压测元数据】', mime_type='application/pdf',
            size_bytes=0, sha256='0'*64, bucket='quality-demo-rollback-only', object_key=tag)
        db.add_all([product,source,attachment]); await db.flush()
        original = QualitySourceRecord(org_id=org, source_id=source.id, record_type='inspection_report', content={'text':'【模拟回滚压测】未形成检测事实。'},
            content_hash=stable_hash(tag), attachment_ids=[], data_nature='synthetic', authorization_scope='organization',
            product_ref={'product_id':product.id}, created_by=actor)
        shared = QualitySourceRecord(org_id=org, source_id=source.id, record_type='inspection_report', content={'text':'【模拟回滚压测】附件授权索引。'},
            content_hash=stable_hash(tag+'-shared'), attachment_ids=[attachment.id], data_nature='synthetic', authorization_scope='organization', created_by=peer)
        db.add_all([original,shared]); await db.flush()
        case = QualityRiskCase(org_id=org, code=tag+'-MAIN', title=tag+'【模拟回滚压测】', scope_type='product',
            scope={'execution_mode':'demo','product_id':product.id,'category_id':category.id}, status='collecting',
            source_record_ids=[original.id], evidence_ids=[], created_by=actor)
        db.add(case); await db.flush()
        assessment = QualityRiskAssessment(org_id=org, risk_case_id=case.id, version=1, scope=case.scope,
            status='demo_draft', trust_status='needs_review', risk_level='unknown', submitted_by=actor)
        db.add(assessment); await db.flush()
        snapshot = {'schema':'demo-risk-report-v1','execution_mode':'demo','llm_called':False,
            'case_id':case.id,'case_code':case.code,'case_title':case.title,'scope':case.scope,'object_name':product.name,
            'assessment_id':assessment.id,'assessment_version':1,'basis_hash':'0'*64,'assessment_hash':RiskReportService.assessment_hash(assessment),
            'conclusion':{'summary':'【模拟回滚压测】草稿元数据，未经业务复核。','reasoning':'仅测试列表读取。','limitations':'不可用于业务结论。','risk_level':'unknown'},
            'review':{'author_id':actor,'author_name':'模拟压测','reviewer_id':None,'at':None,'comment':'没有执行复核。','status':'demo_draft'},
            'records':[{'id':original.id,'type':'inspection_report','content':original.content,'content_hash':original.content_hash,
                'attachment_ids':[attachment.id],'data_nature':'synthetic','origin':'回滚压测元数据'}],
            'attachments':[{'id':attachment.id,'name':attachment.file_name,'sha256':attachment.sha256}],
            'evidence':[],'laboratory':[],'sampling':[],'source_refs':[],'boundary':'【模拟回滚压测】未经复核，不是业务报告。'}
        report_ids, report_rows = [], []
        for i in range(args.reports):
            sample = copy.deepcopy(snapshot); sample['boundary'] += f' {i}'
            token, rid = stable_hash(sample), str(uuid4()); report_ids.append(rid)
            report_rows.append({'id':rid,'org_id':org,'kind':'risk-assessment-reports','code':token,'name':f'{tag}-R-{i:05}',
                'status':'demo_fixture','version':1,'created_by':actor,'created_at':now,'updated_at':now,
                'data':{'snapshot':sample,'snapshot_hash':token,'frozen_at':now.isoformat(),'reader_ids':[actor]}})
        await db.execute(insert(SupervisionRecord), report_rows)
        task_ids, record_ids, task_rows, record_rows, case_rows = [], [], [], [], []
        for i in range(300):
            tid, rid = str(uuid4()), str(uuid4()); task_ids.append(tid); record_ids.append(rid)
            task_rows.append({'id':tid,'org_id':org,'created_by':actor,'product_id':product.id,'quality_product_id':product.id,
                'spec_code':f'{tag}-TASK-{i:04}','image_urls':[],'status':'pending','meta_data':{'execution_mode':'demo'},'created_at':now+timedelta(seconds=i),'updated_at':now})
            record_rows.append({'id':rid,'org_id':org,'source_id':source.id,'record_type':'inspection_report','content':{'title':f'{tag}-RECORD-{i:04}'},
                'content_hash':stable_hash(rid),'attachment_ids':[],'data_nature':'synthetic','authorization_scope':'organization',
                'product_ref':{'product_id':product.id},'created_by':actor,'created_at':now+timedelta(seconds=i),'updated_at':now})
            if i < 250:
                case_rows.append({'id':str(uuid4()),'org_id':org,'code':f'{tag}-CASE-{i:04}','title':'【模拟回滚压测】', 'scope_type':'product',
                    'scope':{'execution_mode':'demo'},'status':'collecting','source_record_ids':[],'evidence_ids':[],
                    'created_by':actor,'created_at':now,'updated_at':now})
        await db.execute(insert(InspectionTask),task_rows); await db.execute(insert(QualitySourceRecord),record_rows); await db.execute(insert(QualityRiskCase),case_rows)
        current = CurrentUser(user_id=actor,org_id=org,role='expert')
        reports, lab, risk = RiskReportService(db,current), RiskLabService(db,current), QualityRiskService(db,current)
        reports.demo.risk.storage = NoFileReads()
        await barrier.wait()
        durations, cursor, ids = [], None, []
        for _ in range(args.pages):
            start=time.perf_counter(); page=await reports.page(case.id,size=20,cursor=cursor)
            durations.append((time.perf_counter()-start)*1000)
            ids.extend(r['id'] for r in page['items']); cursor=page['next_cursor']
            if not cursor: break
        assert len(ids) == len(set(ids))
        target = await reports.page(case.id,keyword=f'{tag}-R-{args.reports-1:05}')
        assert len(target['items']) == 1
        if index == 0:
            while cursor:
                page=await reports.page(case.id,size=20,cursor=cursor)
                ids.extend(r['id'] for r in page['items']); cursor=page['next_cursor']
            assert len(ids) == len(report_ids) and set(ids) == set(report_ids)
        task_page = await lab.option_page(case.id,'tasks',page=15,selected_ids=[task_ids[0]])
        record_page = await lab.option_page(case.id,'records',keyword=f'{tag}-RECORD-0000',selected_ids=[record_ids[0]])
        case_page = await risk.list_risk_cases(page=13,size=20,status=None,keyword=tag)
        assert task_page['total'] == 300 and task_page['selected'][0]['id'] == task_ids[0]
        assert record_page['total'] == 1 and record_page['items'][0]['id'] == record_ids[0]
        assert case_page['total'] == 251 and case_page['items']
        return {'report_count':args.reports,'timed_requests':len(durations),'durations_ms':durations,
            'all_report_ids_enumerated':index == 0,'late_task_record_and_case_found':True}
    finally:
        await db.rollback()
        await db.close()


async def main(args):
    if not settings.quality_demo_enabled: raise RuntimeError('Only the isolated demo stack is permitted')
    validate_demo_settings(settings)
    async with _engine.connect() as control:
        if await control.scalar(text('SELECT marker FROM quality_demo_environment LIMIT 1')) != 'piap-quality-demo-v1':
            raise RuntimeError('Demo ownership marker missing')
        engines = dict((await control.execute(text('SELECT TABLE_NAME, ENGINE FROM information_schema.tables WHERE table_schema = DATABASE()'))).all())
        if any(engines.get(m.__tablename__) != 'InnoDB' for m in MODELS): raise RuntimeError('Transactional InnoDB tables required')
        if await control.scalar(text("SELECT GET_LOCK('piap_quality_demo.pagination_perf', 0)")) != 1: raise RuntimeError('Another pagination benchmark is running')
        try:
            org, actor, peer = demo_id('organization'), demo_id('demo_analyst'), demo_id('demo_reviewer')
            before=await counts(control,org); await control.commit()
            barrier=ReadyGate(args.readers)
            tasks=[asyncio.create_task(reader(i,args,actor,peer,org,barrier)) for i in range(args.readers)]
            try: results=await asyncio.wait_for(asyncio.gather(*tasks),180)
            finally:
                for task in tasks:
                    if not task.done(): task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
            await control.commit()
            after=await counts(control,org)
            assert before == after, 'Fixture rollback did not preserve baseline counts'
            values=sorted(v for r in results for v in r.pop('durations_ms'))
            print(json.dumps({'passed':True,'mode':'real local demo MySQL; service-level timing','concurrent_readers':args.readers,
                'synthetic_report_fixtures':args.reports*args.readers,'timed_report_requests':len(values),
                'mean_ms':round(sum(values)/len(values),2),'p95_ms':round(values[math.ceil(len(values)*0.95)-1],2),'max_ms':round(values[-1],2),
                'reader_checks':results,'all_fixture_transactions_rolled_back':True,'baseline_counts_unchanged':True,
                'original_file_reads':0,'model_calls':0,'business_reviews_performed':0},ensure_ascii=False))
        finally:
            await control.execute(text("SELECT RELEASE_LOCK('piap_quality_demo.pagination_perf')")); await control.commit()
    await _engine.dispose()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports',type=int,default=1000); parser.add_argument('--readers',type=int,default=4); parser.add_argument('--pages',type=int,default=8)
    args=parser.parse_args()
    if not 201 <= args.reports <= 3000 or not 1 <= args.readers <= 4 or not 1 <= args.pages <= 50:
        parser.error('Use 201–3000 reports, 1–4 readers, 1–50 pages')
    asyncio.run(main(args))
