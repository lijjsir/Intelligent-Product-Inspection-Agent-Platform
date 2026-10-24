"""Read-only local readiness and data inventory. Never connects to a deployment host."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from sqlalchemy import select,text,inspect
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import settings
from app.models.organization import Organization
from app.models.quality_risk import QualityRiskCase,QualityRiskAssessment,QualitySourceRecord,QualityAttachment
from app.models.standard_admission import StandardDocumentRevision
from app.services.standard_admission_service import StandardAdmissionService
from app.services.object_storage.factory import build_object_storage
from infra.database.session import get_session,reset_async_engine_pool


async def inspect_local(org_slug,output):
    if settings.app_env not in {'dev','local','development','test','testing'}:
        raise RuntimeError('This command is restricted to local checks; it never applies production migrations')
    errors=[]
    report={'scope':'local only; read-only database and storage checks','organization':org_slug,
        'remote_connections_performed':False,'data_changes_performed':False,'errors':errors}
    try:
        async with get_session() as db:
            org=await db.scalar(select(Organization).where(Organization.slug==org_slug))
            if not org:raise RuntimeError('The requested local organization does not exist')
            report['local_org_id']=org.id
            report['database_revisions']=list((await db.execute(text('SELECT version_num FROM alembic_version'))).scalars())
            report['source_heads']=ScriptDirectory.from_config(Config('alembic.ini')).get_heads()
            report['schema_current']=set(report['database_revisions'])==set(report['source_heads'])
            conn=await db.connection()
            report['job_table_present']=await conn.run_sync(lambda connection:inspect(connection).has_table('risk_analysis_jobs'))
            if report['job_table_present']:
                report['background_jobs']=list((await db.execute(text('SELECT status,COUNT(*) AS n FROM risk_analysis_jobs GROUP BY status'))).mappings())
                report['background_jobs']=[dict(row) for row in report['background_jobs']]
            if not report['schema_current']:errors.append('本地数据库迁移版本尚未匹配源码')
            cases=list(await db.scalars(select(QualityRiskCase).where(QualityRiskCase.org_id==org.id,QualityRiskCase.deleted_at.is_(None))))
            report['cases']=[]
            for case in cases:
                latest=await db.scalar(select(QualityRiskAssessment).where(QualityRiskAssessment.org_id==org.id,
                    QualityRiskAssessment.risk_case_id==case.id,QualityRiskAssessment.deleted_at.is_(None))
                    .order_by(QualityRiskAssessment.version.desc()).limit(1))
                report['cases'].append({'local_case_id':case.id,'title':case.title,'natural_key':case.scope.get('public_case_key'),
                    'status':case.status,'version':latest.version if latest else None,'professional_review_recorded':bool(latest and latest.reviewed_by)})
            record_ids={rid for case in cases for rid in case.source_record_ids or []}
            records=list(await db.scalars(select(QualitySourceRecord).where(QualitySourceRecord.org_id==org.id,
                QualitySourceRecord.id.in_(record_ids),QualitySourceRecord.deleted_at.is_(None))))
            report['records']=[{'local_record_id':r.id,'external_record_id':r.external_record_id,'content_hash':r.content_hash,
                'data_nature':r.data_nature,'source_url':(r.provenance or {}).get('source_url')} for r in records]
            assets=list(await db.scalars(select(QualityAttachment).where(QualityAttachment.org_id==org.id,
                QualityAttachment.id.in_({aid for r in records for aid in r.attachment_ids or []}),QualityAttachment.deleted_at.is_(None))))
            storage=build_object_storage();report['attachments']=[]
            for asset in assets:
                try:
                    content=await asyncio.to_thread(storage.get_bytes,bucket=asset.bucket,object_key=asset.object_key)
                    valid=bool(content and hashlib.sha256(content[0]).hexdigest()==asset.sha256)
                except Exception:valid=False
                report['attachments'].append({'local_attachment_id':asset.id,'file_name':asset.file_name,'sha256':asset.sha256,'bytes':asset.size_bytes,'original_verified':valid})
                if not valid:errors.append('附件原件校验失败：'+asset.id)
            revisions=list(await db.scalars(select(StandardDocumentRevision).where(StandardDocumentRevision.org_id==org.id)))
            report['repaired_standards']=[]
            service=StandardAdmissionService(db,org.id)
            for revision in revisions:
                repair=revision.snapshot.get('reading_text_repair')
                if not repair:continue
                try:await asyncio.to_thread(service.read_original,revision);valid=True
                except Exception:valid=False
                report['repaired_standards'].append({'local_revision_id':revision.id,'standard_no':revision.snapshot.get('standard_no'),
                    'revision_no':revision.revision_no,'source_file':revision.snapshot.get('file_name'),'sha256':revision.file_hash,
                    'review_status':revision.review_status,'publication_status':revision.publication_status,'original_verified':valid})
                if not valid:errors.append('标准原件校验失败：'+revision.id)
            report['migration_notes']=[
                '此清单记录本地对象，不是可直接覆盖其他数据库的SQL。不同环境须按自然标识映射组织、产品、来源和附件。',
                '现有真实案例材料包与标准PDF须单独保留；代码包不包含数据库内容、对象存储或原件。',
                '未经过真实专业审核的状态继续保留；不能迁移成已审核或冒用其他环境的操作者。']
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(json.dumps({'output':str(output),'schema_current':report['schema_current'],'cases':len(report['cases']),
            'verified_attachments':len(report['attachments']),'repaired_standards':len(report['repaired_standards']),'errors':errors},ensure_ascii=False))
        return not errors
    finally:await reset_async_engine_pool()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--org',default='cqupt');parser.add_argument('--output',type=Path,default=Path('runtime/local_quality_release/inventory.json'))
    args=parser.parse_args()
    raise SystemExit(0 if asyncio.run(inspect_local(args.org,args.output)) else 2)
