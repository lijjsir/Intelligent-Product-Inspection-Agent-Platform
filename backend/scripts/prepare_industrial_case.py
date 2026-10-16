"""Receive real case assets as raw material and pending technical drafts.

This script cannot approve/publish standards, accept executions, or publish knowledge.
It uses the existing services and records automatic preparation explicitly.
"""
import argparse, asyncio, copy, hashlib, json
from io import BytesIO
from pathlib import Path
from sqlalchemy import select
from starlette.datastructures import UploadFile, Headers

from app.core.permissions import PermissionRole, require_role
from app.models.inspection_standard_library import InspectionStandardLibrary
from app.models.standard_admission import StandardDocumentRevision, StandardSyncOutbox
from app.models.quality_risk import ProductCategory, QualityProduct, QualityAttachment
from app.models.task import InspectionTask
from app.models.user import User
from app.schemas.user import CurrentUser
from app.schemas.quality_risk import ProductCategoryCreate, ProductCreate, QualityEventCreate
from app.schemas.standard_admission import RevisionMetadata, CandidateEdit
from app.services.permission_service import PermissionService
from app.services.quality_risk_service import QualityRiskService
from app.services.inspection_standard_library_service import InspectionStandardLibraryService
from app.services.standard_admission_service import StandardAdmissionService, process_standard_outbox
from app.services.task_service import TaskService
from app.services.inspection_execution_context_service import InspectionExecutionContextService
from app.services.knowledge_source_service import fingerprint
from app.models.inspection_standard_library import StandardDocument
from app.models.quality_risk import QualitySourceRecord
from infra.database.session import get_session, reset_async_engine_pool


async def identity(db,org_id,username):
    user=await db.scalar(select(User).where(User.org_id==org_id,User.username==username,User.is_active.is_(True)))
    if not user:raise ValueError('Preparation actor must be an active user in the requested organization')
    item=await PermissionService(db,org_id).identity(user.id)
    current=CurrentUser(user_id=user.id,org_id=org_id,role=item['role'])
    current.role=PermissionRole(item['role'],item['effective'])
    return current


def load_package(folder):
    folder=Path(folder).resolve();manifest=json.loads((folder/'case.json').read_text(encoding='utf-8'))
    files={}
    for asset in manifest['assets']:
        path=(folder/asset['file_name']).resolve()
        if not path.is_relative_to(folder):raise ValueError('Asset escaped the package')
        content=path.read_bytes()
        if hashlib.sha256(content).hexdigest()!=asset['sha256']:raise ValueError('Case asset hash differs from manifest')
        files[asset['kind']]=(asset,content)
    return manifest,files


async def prepare(db,manifest,files,admin,owner):
    for permission in ['product_master','inspection_standard_library','standard_admission_submit']:
        require_role(permission,admin.role)
    for permission in ['task','inspection_execution','quality_material_submit']:
        require_role(permission,owner.role)
    if str(admin.role)!='admin' or str(owner.role) not in {'user','expert'}:
        raise ValueError('Governance and task preparation require the corresponding actors')
    existing=await db.scalar(select(InspectionTask.id).where(InspectionTask.org_id==owner.org_id,
        InspectionTask.deleted_at.is_(None),InspectionTask.meta_data['case_preparation']['case_id'].as_string()==manifest['case_id']))
    if existing:
        task=await db.get(InspectionTask,existing);plan=copy.deepcopy(task.meta_data['case_preparation'])
        digest=fingerprint(manifest)
        if plan.get('package_hash') and plan['package_hash']!=digest:
            raise ValueError('Case package changed; preserve the prior case and prepare an explicit revision')
        if not plan.get('package_hash'):
            # One-time normalization of the initial preparation, with source identity checks.
            previous=copy.deepcopy(plan['planned_items'])
            for item in previous:
                old=item.pop('raw_repetition_records_available',None)
                if old is not None:item['single_report_value_sufficient_for_comparison']=old
            document=await db.get(StandardDocument,plan['standard_document_id'])
            report=await db.get(QualityAttachment,plan['report_attachment_id'])
            source=await db.get(QualitySourceRecord,plan['source_record_id'])
            if not document or document.org_id!=owner.org_id or document.file_hash!=files['standard'][0]['sha256'] or \
                not report or report.org_id!=owner.org_id or report.sha256!=files['report'][0]['sha256'] or \
                not source or source.org_id!=owner.org_id or source.content.get('product')!=manifest['product'] or \
                previous!=manifest['planned_items']:
                raise ValueError('Existing case differs from the package; do not overwrite its preparation')
            plan.update(planned_items=previous,package_hash=digest)
            task.meta_data={**task.meta_data,'case_preparation':plan};await db.flush()
        return {'task_id':existing,'reused':True,'professional_status':'see_current_workflow'}
    registry=QualityRiskService(db,admin)
    category=await db.scalar(select(ProductCategory).where(ProductCategory.org_id==admin.org_id,
        ProductCategory.name==manifest['product']['name'],ProductCategory.deleted_at.is_(None)))
    if not category:
        category_info=await registry.create_category(ProductCategoryCreate(name=manifest['product']['name'],
            classification_basis='GB 17761-2018及公开历史检验报告列示的产品类型，仅作产品类别登记。'))
        category=await db.get(ProductCategory,category_info['id'])
    product=await db.scalar(select(QualityProduct).where(QualityProduct.org_id==admin.org_id,
        QualityProduct.category_id==category.id,QualityProduct.model==manifest['product']['model'],
        QualityProduct.brand==manifest['product']['brand'],QualityProduct.deleted_at.is_(None)))
    if not product:
        info=await registry.create_product(ProductCreate(category_id=category.id,
            name=f"{manifest['product']['brand']} {manifest['product']['model']}（历史报告样品）",
            model=manifest['product']['model'],brand=manifest['product']['brand'],
            attributes={'record_scope':'历史报告型号记录，不表示收到当前实物或完成检测',
                        'source_report_no':manifest['report_no'],'source_url':manifest['provenance']['report_url']}))
        product=await db.get(QualityProduct,info['id'])
    library_name=manifest['product']['name']+'历史标准库'
    library=await db.scalar(select(InspectionStandardLibrary).where(InspectionStandardLibrary.org_id==admin.org_id,
        InspectionStandardLibrary.name==library_name,InspectionStandardLibrary.deleted_at.is_(None)))
    if not library:
        info=await InspectionStandardLibraryService(db,admin.org_id).create_item({'name':library_name,
            'product_family':category.name,'product_category':category.name,'domain':category.name,
            'applicable_category_ids':[category.id],'applicable_product_ids':[product.id],
            'standard_status':'废止','description':'供历史报告核对；原件和条款待专家核验，不自动用于当前产品准入。'})
        library=await db.get(InspectionStandardLibrary,info['id'])
    admissions=StandardAdmissionService(db,admin.org_id,admin.user_id)
    asset,content=files['standard']
    received=await admissions.receive(library.id,[(asset['file_name'],content,'application/pdf')])
    document=await admissions.document(received['documents'][0]['id'])
    revision=await db.get(StandardDocumentRevision,document.current_revision_id)
    if revision.publication_status!='unpublished' or revision.review_status!='pending':
        raise ValueError('Existing reviewed standard must be handled separately; preparation does not revise it')
    if revision.processing_status!='parsed':
        job=await db.scalar(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==revision.id,
            StandardSyncOutbox.action=='parse').with_for_update())
        await process_standard_outbox(db,job)
        job.status='done';job.error_message=None
    metadata=RevisionMetadata.model_validate({'expected_version':revision.row_version,'base_revision_id':revision.id,
        **manifest['standard_metadata']}).model_dump()
    changed=await admissions.amend(document.id,metadata)
    revision=await db.get(StandardDocumentRevision,changed['id'])
    refs=[]
    for planned in manifest['planned_items']:
        anchor=next((c for c in revision.candidates_json or [] if c['clause_no']==planned['clause_no'] and
                     c['page_number']==planned['standard_page']),None)
        if not anchor:raise ValueError('Required clause was not extracted; check the original in the review workspace')
        draft=CandidateEdit.model_validate({'expected_version':revision.row_version,
            'request_key':f"case-draft:{manifest['case_id']}:{planned['measurement_key']}:{revision.id}",
            'reason':'自动准备技术整理稿，已对照页码；尚非人工专业确认。',
            'evidence_refs':[f"standard PDF p{planned['standard_page']}; method p{planned['method_page']}"],
            'candidate_id':anchor['id'],'status':'pending','candidate_type':planned['candidate_type'],
            'indicator':planned['indicator'],'measurement_key':planned['measurement_key'],'unit':planned['unit'],
            'method':planned['method'],'conditions':planned['conditions'],'requirement':planned['requirement'],
            'operator':planned['operator'],'numeric_upper':planned['numeric_upper'],'numeric_lower':planned['numeric_lower'],
            'execution_mode':'numeric','numeric_aggregation':planned['numeric_aggregation'],
            'minimum_observations':planned['minimum_observations'],'applicability':manifest['standard_metadata']['scope_notes']}).model_dump()
        await admissions.candidate(document.id,revision.id,draft,actor_role='admin')
        refs.append({'revision_id':revision.id,'candidate_id':anchor['id'],'measurement_key':planned['measurement_key']})
    intake=QualityRiskService(db,owner);attachments={}
    for kind in ['report','report_original','photo','transcription']:
        asset,content=files[kind]
        previous=await db.scalar(select(QualityAttachment).where(QualityAttachment.org_id==owner.org_id,
            QualityAttachment.uploaded_by==owner.user_id,QualityAttachment.sha256==asset['sha256'],QualityAttachment.deleted_at.is_(None)))
        if previous:attachments[kind]=previous.id;continue
        mime={'report':'application/pdf','report_original':'application/pdf','photo':'image/jpeg','transcription':'text/csv'}[kind]
        saved=await intake.upload_attachment(UploadFile(BytesIO(content),filename=asset['file_name'],
            headers=Headers({'content-type':mime})))
        attachments[kind]=saved['id']
    source=await intake.create_event(QualityEventCreate(record_type='inspection_report',external_record_id=manifest['report_no'],
        origin_label=manifest['provenance']['report_url'],data_nature='observed',authorization_scope='organization',
        content={'title':manifest['title'],'report_no':manifest['report_no'],'product':manifest['product'],
                 'issued_date':manifest['report_issued_date'],'transcribed_values':[
                     {k:p[k] for k in ['measurement_key','indicator','value','unit','report_page','original_pdf_page']} for p in manifest['planned_items']],
                 'transcription_status':'awaiting_independent_review','limitations':manifest['limitations']},
        product_ref={'product_id':product.id,'category_id':category.id},attachment_ids=list(attachments.values()),
        provenance={**manifest['provenance'],'assets':manifest['assets'],'preparation_actor':admin.user_id,
                    'report_page_map':[{'uploaded_pdf_page':n,'original_pdf_page':n+1,'printed_report_page':n} for n in range(1,6)]}))
    proposal={'schema_version':1,'package_hash':fingerprint(manifest),'case_id':manifest['case_id'],'title':manifest['title'],'report_no':manifest['report_no'],
        'standard_refs':refs,'standard_document_id':document.id,'standard_revision_id':revision.id,'source_record_id':source['id'],
        'report_attachment_id':attachments['report'],'original_attachment_id':attachments['report_original'],
        'planned_items':copy.deepcopy(manifest['planned_items']),'initial_execution_keys':manifest.get('initial_execution_keys',[]),
        'limitations':manifest['limitations'],'preparation':'自动整理，尚非人工专业确认'}
    task=await TaskService(db,owner.org_id,actor_user_id=owner.user_id,actor_role=owner.role).create_task(
        created_by=owner.user_id,product_id=product.id,spec_code='',image_urls=[],priority=5,
        inspection_standard_id=library.id,quality_product_id=product.id,product_category_id=category.id,
        metadata={'input_mode':'report','production_date':manifest['product']['production_date'],
                  'case_preparation':proposal,'execution_requested':False})
    context_service=InspectionExecutionContextService(db,owner)
    context=await context_service.context(task)
    await context_service.link_report(task,{'request_key':f"case-report:{manifest['case_id']}:{task.id}",
        'expected_context_hash':context['context_hash'],'source_record_id':source['id'],'attachment_id':attachments['report'],
        'sample_codes':[manifest['sample_label']],'reason':'自动关联公开报告和登记型号；仅使用原报告检验样品，不把备用车当作独立观测。'})
    return {'task_id':task.id,'document_id':document.id,'revision_id':revision.id,'source_record_id':source['id'],
        'professional_status':'awaiting_review','standard_published':False,'execution_created':False,
        'case_id':manifest['case_id'],'reused':False}


async def main(args):
    manifest,files=load_package(args.package_dir)
    if not args.apply:
        print(json.dumps({'dry_run':True,'case_id':manifest['case_id'],'assets_verified':len(files)},ensure_ascii=False));return
    try:
        async with get_session() as db:
            admin=await identity(db,args.org_id,args.admin_username);owner=await identity(db,args.org_id,args.owner_username)
            result=await prepare(db,manifest,files,admin,owner)
            await db.commit()
    finally:await reset_async_engine_pool()
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package-dir',required=True);p.add_argument('--org-id',required=True)
    p.add_argument('--admin-username',default='admin');p.add_argument('--owner-username',default='user');p.add_argument('--apply',action='store_true')
    p.add_argument('--output',default='runtime/industrial_case_20261014/prepared.json')
    asyncio.run(main(p.parse_args()))
