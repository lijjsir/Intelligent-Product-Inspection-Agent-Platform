"""Independent professional review and queue behavior in isolated SQLite."""
import copy
from datetime import datetime, timezone
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import MetaData,DefaultClause,text,select
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models import Organization,User,RolePermission,UserPermission
from app.models.inspection_standard_library import InspectionStandardLibrary,StandardDocument
from app.models.rag_space import RagSpace
from app.models.standard_admission import StandardDocumentRevision,StandardAdmissionReview,StandardSyncOutbox
from app.schemas.user import CurrentUser
from app.core.exceptions import ForbiddenError,ValidationError,ConflictError,NotFoundError
from app.core.permissions import PermissionRole,has_permission
from app.services.permission_service import default_permissions
from app.services.standard_admission_service import StandardAdmissionService
from app.services.standard_review_service import StandardReviewService

ORG,OTHER,ADMIN,EXPERT,EXPERT2=[str(uuid.uuid4()) for _ in range(5)]
def actor(role="expert", user=EXPERT, org=ORG):return CurrentUser(user_id=user,org_id=org,role=role)
def action(rev,**kw):return {"expected_version":rev.row_version,"request_key":str(uuid.uuid4()),"reason":"isolated audit evidence","evidence_refs":["fixture PDF page1"],**kw}

@pytest_asyncio.fixture
async def domain(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr("app.services.standard_admission_service.build_object_storage",lambda:SimpleNamespace(get_bytes=lambda **kw:(b"%PDF-isolated test source", "application/pdf")))
    engine=create_async_engine("sqlite+aiosqlite:///:memory:");meta=MetaData()
    for model in [Organization,User,RolePermission,UserPermission,RagSpace,InspectionStandardLibrary,StandardDocument,StandardDocumentRevision,StandardAdmissionReview,StandardSyncOutbox]:
        table=model.__table__.to_metadata(meta)
        for c in table.c:
            if c.name in {"created_at","updated_at"}:c.server_default=DefaultClause(text("CURRENT_TIMESTAMP"))
    async with engine.begin() as conn:await conn.run_sync(meta.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as db:
        db.add(Organization(id=ORG,name="isolated",slug=ORG,is_active=True))
        for uid,role in [(ADMIN,"admin"),(EXPERT,"expert"),(EXPERT2,"expert")]:
            db.add(User(id=uid,org_id=ORG,username=uid[:8],email=f"{uid}@example.invalid",role=role,is_active=True))
        library=InspectionStandardLibrary(id=str(uuid.uuid4()),org_id=ORG,name="isolated standards",domain="工业",product_family="isolated",rag_space_ids=[])
        db.add(library);await db.flush()
        doc=StandardDocument(id=str(uuid.uuid4()),org_id=ORG,library_id=library.id,standard_no="GB 17761-2018",standard_name="isolated fixture",standard_level="GB",domain="工业",file_name="fixture.pdf",file_path="fixture.pdf")
        db.add(doc);await db.flush()
        candidate={"id":"criterion-1","candidate_type":"inspection_requirement","clause_no":"6.1","page_number":1,"source_text":"isolated PDF text", "status":"pending",
            "indicator":"speed","method":"7.1","conditions":"road","unit":"km/h","requirement":"<=25","operator":"le",
            "measurement_key":"speed","applicability":"isolated product", "execution_mode":"numeric","numeric_upper":25.0,
            "reviewed_by":None,"prepared_by":ADMIN}
        rev=StandardDocumentRevision(org_id=ORG,document_id=doc.id,revision_no=1,created_by=ADMIN,
            snapshot={"standard_no":"GB 17761-2018","standard_name":"isolated fixture","domain":"工业","file_path":"fixture.pdf","file_name":"fixture.pdf","resource_type":"standard", "source_url":"https://example.invalid/fixture","publisher":"fixture","standard_status":"现行"},
            pages_json=[{"page_number":1,"text":"GB 17761-2018 isolated"}],candidates_json=[candidate],processing_status="parsed")
        db.add(rev);await db.flush();doc.current_revision_id=rev.id;await db.flush()
        yield db,doc,rev
    await engine.dispose()

@pytest.mark.asyncio
async def test_queue_is_revision_based_and_scoped_and_claim_moves_to_my_work(domain):
    db,doc,rev=domain;service=StandardReviewService(db,actor())
    result=await service.queue(scope="unassigned")
    assert result["total"]==1 and result["items"][0]["can_claim"] and result["items"][0]["pending_count"]==1
    await service.assign(doc.id,rev.id,action(rev,operation="claim"))
    mine=await service.queue(scope="mine");assert mine["total"]==1 and mine["items"][0]["can_review"]
    assert (await StandardReviewService(db,actor(org=OTHER)).queue(scope="all"))["total"]==0

@pytest.mark.asyncio
async def test_admin_assignment_enforces_designated_reviewer_and_version(domain):
    db,doc,rev=domain;service=StandardReviewService(db,actor("admin",ADMIN))
    await service.assign(doc.id,rev.id,action(rev,operation="assign",reviewer_id=EXPERT,due_at="2026-11-01T10:00:00+08:00"))
    assert rev.review_assignment["domain"]=="工业" and rev.review_assignment["due_at"].endswith("+00:00")
    with pytest.raises(ForbiddenError):
        await StandardAdmissionService(db,ORG,EXPERT2).review(doc.id,rev.id,action(rev,decision="approve"),actor_role="expert")
    with pytest.raises(ConflictError):
        await service.assign(doc.id,rev.id,action(rev,expected_version=1,operation="assign",reviewer_id=EXPERT2))

@pytest.mark.asyncio
async def test_revoked_or_foreign_or_inactive_expert_cannot_be_assigned(domain):
    db,doc,rev=domain
    db.add(UserPermission(org_id=ORG,user_id=EXPERT,overrides={"standard_admission_review":"deny"}));await db.flush()
    with pytest.raises(ValidationError):
        await StandardReviewService(db,actor("admin",ADMIN)).assign(doc.id,rev.id,action(rev,operation="assign",reviewer_id=EXPERT))
    with pytest.raises(NotFoundError):
        await StandardReviewService(db,actor("admin",ADMIN,OTHER)).assign(doc.id,rev.id,action(rev,operation="assign",reviewer_id=EXPERT2))

@pytest.mark.asyncio
async def test_expert_cannot_confirm_their_own_preparation_but_other_expert_can(domain):
    db,doc,rev=domain;c=rev.candidates_json[0]
    fields={k:c[k] for k in ["indicator","method","conditions","unit","requirement","operator","measurement_key","applicability","execution_mode","numeric_upper"]}
    service=StandardAdmissionService(db,ORG,EXPERT)
    await service.candidate(doc.id,rev.id,action(rev,candidate_id=c["id"],status="pending",**fields),actor_role="expert")
    with pytest.raises(ForbiddenError):await service.candidate_review(doc.id,rev.id,action(rev,candidate_id=c["id"],decision="confirm"),can_confirm=True)
    await StandardAdmissionService(db,ORG,EXPERT2).candidate_review(doc.id,rev.id,action(rev,candidate_id=c["id"],decision="confirm"),can_confirm=True)
    assert rev.candidates_json[0]["reviewed_by"]==EXPERT2 and rev.candidates_json[0]["prepared_by"]==EXPERT
    assert rev.candidates_json[0]["review_evidence_refs"]==["fixture PDF page1"]


@pytest.mark.asyncio
async def test_unclassified_candidate_requires_preparation_then_independent_confirmation(domain):
    db,doc,rev=domain;rev.candidates_json=[{**rev.candidates_json[0],'candidate_type':None}];await db.flush()
    with pytest.raises(ValidationError,match='条款用途'):
        await StandardAdmissionService(db,ORG,EXPERT).candidate_review(doc.id,rev.id,action(rev,candidate_id='criterion-1',decision='confirm'),can_confirm=True)
    # The failed request's audit row is flushed in this transaction; use a fresh key for preparation.
    c=rev.candidates_json[0]
    fields={k:c[k] for k in ['indicator','method','conditions','unit','requirement','operator','measurement_key','applicability','execution_mode','numeric_upper']}
    await StandardAdmissionService(db,ORG,EXPERT).candidate(doc.id,rev.id,action(rev,candidate_id=c['id'],status='pending',candidate_type='method_condition',**fields),actor_role='expert')
    with pytest.raises(ForbiddenError):await StandardAdmissionService(db,ORG,EXPERT).candidate_review(doc.id,rev.id,action(rev,candidate_id=c['id'],decision='confirm'),can_confirm=True)
    await StandardAdmissionService(db,ORG,EXPERT2).candidate_review(doc.id,rev.id,action(rev,candidate_id=c['id'],decision='confirm'),can_confirm=True)
    assert rev.candidates_json[0]['candidate_type']=='method_condition' and rev.candidates_json[0]['reviewed_by']==EXPERT2

@pytest.mark.asyncio
async def test_edit_and_confirm_in_one_legacy_request_is_rejected(domain):
    db,doc,rev=domain;c=rev.candidates_json[0]
    body={**c,"numeric_upper":99.0}
    with pytest.raises(ValidationError):await StandardAdmissionService(db,ORG,EXPERT).candidate(doc.id,rev.id,action(rev,candidate_id=c["id"],status="confirmed",
        **{k:body[k] for k in ["indicator","method","conditions","unit","requirement","operator","measurement_key","applicability","execution_mode","numeric_upper"]}),can_confirm=True)

@pytest.mark.asyncio
async def test_metadata_approval_does_not_freeze_unpublished_requirement_work(domain):
    db,doc,rev=domain;expert=StandardAdmissionService(db,ORG,EXPERT)
    await expert.review(doc.id,rev.id,action(rev,decision="approve"),actor_role="expert")
    await expert.candidate_review(doc.id,rev.id,action(rev,candidate_id="criterion-1",decision="confirm"),can_confirm=True)
    assert rev.review_status=="approved" and rev.candidates_json[0]["status"]=="confirmed"

@pytest.mark.asyncio
async def test_published_source_stays_immutable_when_requirements_draft_is_opened(domain):
    db,doc,rev=domain;rev.publication_status="published";rev.review_status="approved";rev.reviewed_by=EXPERT
    doc.published_revision_id=rev.id;await db.flush();before=copy.deepcopy(rev.candidates_json)
    service=StandardAdmissionService(db,ORG,ADMIN);body=action(rev)
    first=await service.draft_requirements(doc.id,rev.id,body);second=await service.draft_requirements(doc.id,rev.id,body)
    assert first["id"]==second["id"] and first["publication_status"]=="unpublished"
    assert first["snapshot"]["metadata_review_basis_revision_id"]==rev.id
    assert doc.published_revision_id==rev.id and rev.candidates_json==before
    assert first["reviewed_by"]==EXPERT

def test_standard_publication_requires_admin_or_explicit_delegation():
    assert "standard_admission_publish" not in default_permissions("expert")
    assert not has_permission("standard_admission_publish","expert")
    assert has_permission("standard_admission_publish",PermissionRole("expert",["standard_admission_publish","inspection_standard_library_read"]))
    assert has_permission("standard_review_assign","admin")


@pytest.mark.asyncio
async def test_claim_and_release_retries_do_not_duplicate_responsibility_changes(domain):
    db,doc,rev=domain
    rev.created_by=None;await db.flush()
    service=StandardReviewService(db,actor())
    claim=action(rev,operation="claim")
    await service.assign(doc.id,rev.id,claim);version=rev.row_version
    await service.assign(doc.id,rev.id,claim);assert rev.row_version==version
    release=action(rev,operation="release")
    await service.assign(doc.id,rev.id,release);version=rev.row_version
    await service.assign(doc.id,rev.id,release)
    assert rev.row_version==version and rev.review_assignment["reviewer_id"] is None


@pytest.mark.asyncio
async def test_missing_original_blocks_professional_confirmation(domain,monkeypatch):
    from types import SimpleNamespace
    db,doc,rev=domain
    monkeypatch.setattr("app.services.standard_admission_service.build_object_storage",lambda:SimpleNamespace(get_bytes=lambda **kw:None))
    with pytest.raises(NotFoundError):
        await StandardAdmissionService(db,ORG,EXPERT).candidate_review(doc.id,rev.id,
            action(rev,candidate_id="criterion-1",decision="confirm"),can_confirm=True)
    assert rev.candidates_json[0]["status"]=="pending"
