import copy
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import MetaData,DefaultClause,select,text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models.rag_space import RagSpace,RagDocument,RagDocumentChunk
from app.models.knowledge_admission import KnowledgeAdmission,KnowledgeAdmissionAction,RagSpaceGrant
from app.models.memory import MemoryItem,MemoryOrigin,MemoryEvidence,MemoryEvent,MemoryDependencyEdge,MemorySyncOutbox
from app.models.meeting import MemoryScopeBinding
from app.models.user import User
from app.models.organization import Organization
from app.schemas.user import CurrentUser
from app.services.knowledge_admission_service import KnowledgeAdmissionService,finish_knowledge_projection,guard_managed_memory
from app.services.knowledge_workspace_service import KnowledgeWorkspaceService
from app.services.knowledge_source_service import KnowledgeSourceService
from app.repositories.rag_space_repo import RagSpaceRepository
from app.core.exceptions import ConflictError,ForbiddenError,NotFoundError,ValidationError

ORG,OTHER,AUTHOR,EXPERT,PEER,ADMIN=[str(uuid.uuid4()) for _ in range(6)]


def actor(user=AUTHOR,role="expert",org=ORG):return CurrentUser(user_id=user,org_id=org,role=role)


@pytest_asyncio.fixture
async def data():
    engine=create_async_engine("sqlite+aiosqlite:///:memory:");meta=MetaData()
    models=[RagSpace,RagDocument,RagDocumentChunk,KnowledgeAdmission,KnowledgeAdmissionAction,RagSpaceGrant,MemoryItem,
        MemoryOrigin,MemoryEvidence,MemoryEvent,MemoryDependencyEdge,MemorySyncOutbox,MemoryScopeBinding,User,Organization]
    for model in models:
        table=model.__table__.to_metadata(meta)
        for col in table.c:
            if col.name in {"created_at","updated_at"}:col.server_default=DefaultClause(text("CURRENT_TIMESTAMP"))
    async with engine.begin() as c:await c.run_sync(meta.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as session:
        for uid,role in [(AUTHOR,"expert"),(EXPERT,"expert"),(PEER,"expert"),(ADMIN,"admin")]:
            session.add(User(id=uid,org_id=ORG,username="fixture-"+uid,email=uid+"@example.invalid",role=role,is_active=True))
        space=RagSpace(id=str(uuid.uuid4()),org_id=ORG,created_by=AUTHOR,name="private fixture",resource_domain="workspace")
        doc=RagDocument(id=str(uuid.uuid4()),org_id=ORG,rag_space_id=space.id,node_id=str(uuid.uuid4()),uploaded_by=AUTHOR,
            file_name="expert-note.md",file_url="fixture",size_bytes=8,checksum_sha256="fixture-hash",bucket="fixture",object_key="fixture",
            parse_status="parsed",index_status="ready")
        session.add_all([space,doc]);await session.flush()
        session.add(RagDocumentChunk(org_id=ORG,rag_space_id=space.id,document_id=doc.id,node_id=doc.node_id,
            chunk_index=1,content_text="续航变化需核对试验条件，不能仅凭投诉认定产品不合格。",content_preview="fixture",qdrant_point_id="fixture"))
        await session.flush();yield session,space,doc
    await engine.dispose()


def submit_body(doc,scope="organization"):
    return {"request_key":str(uuid.uuid4()),"claim":"续航变化应结合实际试验条件核验","product_category":"电动自行车",
        "applicability":"同类型续航分析场景","limitations":"不作为产品合格判定依据",
        "sources":[{"kind":"rag_document","id":doc.id,"quote":"不能仅凭投诉认定产品不合格"}],"requested_scope":scope,
        "consent_to_review":True,"consent_to_share":scope=="organization","qdl":None,"related_memory_ids":[]}


def action(item,**kwargs):return {"expected_version":item.row_version,"request_key":str(uuid.uuid4()),"reason":"isolated fixture reason","evidence_refs":["fixture source"],**kwargs}


async def submitted(data,scope="organization"):
    s,_,doc=data
    service=KnowledgeAdmissionService(s,actor());result=await service.submit(submit_body(doc,scope))
    item=await s.get(KnowledgeAdmission,result["id"])
    return service,item


async def approved(data):
    service,item=await submitted(data)
    await KnowledgeAdmissionService(data[0],actor(EXPERT)).review(item.id,action(item,decision="approve"))
    await KnowledgeAdmissionService(data[0],actor(ADMIN,"admin")).sharing(item.id,action(item,decision="approve"))
    return service,item


@pytest.mark.asyncio
async def test_private_file_is_not_visible_even_to_administrator(data):
    s,space,doc=data
    for uid in [PEER,ADMIN]:
        assert await RagSpaceRepository(s).get(org_id=ORG,rag_space_id=space.id,owner_user_id=uid,include_system=True) is None
        with pytest.raises(NotFoundError):await KnowledgeSourceService(s,actor(uid,"admin" if uid==ADMIN else "expert")).resolve("rag_document",doc.id)


@pytest.mark.asyncio
async def test_owner_grant_enables_reading_and_revocation_is_immediate(data):
    s,space,_=data;service=KnowledgeWorkspaceService(s,actor())
    rows=await service.share(space.id,{"user_id":PEER,"expected_version":0,"reason":"read-only fixture","allow_knowledge_submission":False})
    assert await RagSpaceRepository(s).get(org_id=ORG,rag_space_id=space.id,owner_user_id=PEER)
    await service.share(space.id,{"user_id":PEER,"expected_version":rows[0]["row_version"],"reason":"revoke fixture","allow_knowledge_submission":False},revoke=True)
    assert await RagSpaceRepository(s).get(org_id=ORG,rag_space_id=space.id,owner_user_id=PEER) is None


@pytest.mark.asyncio
async def test_read_grant_does_not_allow_knowledge_export(data):
    s,space,doc=data
    await KnowledgeWorkspaceService(s,actor()).share(space.id,{"user_id":PEER,"expected_version":0,"reason":"read-only fixture","allow_knowledge_submission":False})
    preview=await KnowledgeSourceService(s,actor(PEER)).resolve("rag_document",doc.id,preview=True)
    assert preview["available_excerpt"]
    with pytest.raises(ForbiddenError):await KnowledgeAdmissionService(s,actor(PEER)).submit(submit_body(doc))


@pytest.mark.asyncio
async def test_source_quote_is_checked_against_real_body(data):
    with pytest.raises(ValidationError):await KnowledgeSourceService(data[0],actor()).resolve("rag_document",data[2].id,"不存在的指标999")


@pytest.mark.asyncio
async def test_duplicate_reference_remains_one_origin_and_no_auto_promotion(data):
    s,_,doc=data;payload=submit_body(doc);payload["sources"]*=2
    result=await KnowledgeAdmissionService(s,actor()).submit(payload)
    assert len(result["source_refs"])==1 and result["publication_status"]=="unpublished"
    memory=(await s.execute(select(MemoryItem).where(MemoryItem.memory_id==result["memory_id"]))).scalar_one()
    assert memory.status=="candidate" and memory.origin_evidence_count==1
    assert (await s.execute(select(MemorySyncOutbox))).scalars().all()==[]


@pytest.mark.asyncio
async def test_submit_requires_explicit_review_and_share_consent(data):
    payload=submit_body(data[2]);payload["consent_to_share"]=False
    with pytest.raises(ValidationError):await KnowledgeAdmissionService(data[0],actor()).submit(payload)


@pytest.mark.asyncio
async def test_self_review_and_admin_qualification_are_denied(data):
    service,item=await submitted(data)
    with pytest.raises(ForbiddenError):await service.review(item.id,action(item,decision="approve"))
    with pytest.raises(ForbiddenError):await KnowledgeAdmissionService(data[0],actor(ADMIN,"admin")).review(item.id,action(item,decision="approve"))


@pytest.mark.asyncio
async def test_other_tenant_cannot_review_source_or_candidate(data):
    _,item=await submitted(data)
    with pytest.raises(NotFoundError):await KnowledgeAdmissionService(data[0],actor(EXPERT,org=OTHER)).get(item.id)


@pytest.mark.asyncio
async def test_publication_needs_both_professional_and_scope_decisions(data):
    service,item=await submitted(data)
    await KnowledgeAdmissionService(data[0],actor(EXPERT)).review(item.id,action(item,decision="approve"))
    with pytest.raises(ValidationError):await service.publish(item.id,action(item))
    assert item.sharing_status=="pending" and item.publication_status=="unpublished"


@pytest.mark.asyncio
async def test_publish_waits_for_vector_and_withdraw_blocks_before_cleanup(data):
    service,item=await approved(data)
    await service.publish(item.id,action(item))
    memory=await service.memory(item)
    assert item.publication_status=="publishing" and memory.status=="candidate"
    assert await guard_managed_memory(data[0],ORG,[memory])==[]
    await finish_knowledge_projection(data[0],ORG,item.id)
    assert item.publication_status=="published" and memory.status=="active"
    await service.withdraw(item.id,action(item))
    assert item.publication_status=="withdrawn" and memory.status=="isolated"
    assert await guard_managed_memory(data[0],ORG,[memory])==[]


@pytest.mark.asyncio
async def test_source_deleted_or_revoked_cannot_be_used_after_publish(data):
    service,item=await approved(data);await service.publish(item.id,action(item));await finish_knowledge_projection(data[0],ORG,item.id)
    from app.core.datetime import utcnow
    data[2].deleted_at=utcnow();await data[0].flush()
    assert await guard_managed_memory(data[0],ORG,[await service.memory(item)])==[]
    assert item.publication_status=="withdrawn"


@pytest.mark.asyncio
async def test_withdraw_before_vector_completion_is_not_reactivated(data):
    service,item=await approved(data);await service.publish(item.id,action(item));await service.withdraw(item.id,action(item))
    await finish_knowledge_projection(data[0],ORG,item.id)
    assert item.publication_status=="withdrawn" and (await service.memory(item)).status=="isolated"


@pytest.mark.asyncio
async def test_idempotent_submission_does_not_duplicate_sources_or_memory(data):
    payload=submit_body(data[2]);service=KnowledgeAdmissionService(data[0],actor())
    first=await service.submit(payload);second=await service.submit(payload)
    assert first["id"]==second["id"]
    with pytest.raises(ConflictError):await service.submit({**payload,"claim":"another conflicting claim"})


@pytest.mark.asyncio
async def test_duplicate_projection_completion_does_not_remove_published_vector(data):
    service,item=await approved(data);await service.publish(item.id,action(item));await finish_knowledge_projection(data[0],ORG,item.id)
    before=(await data[0].execute(select(MemorySyncOutbox).where(MemorySyncOutbox.action=="DELETE_ACTIVE_VECTOR"))).scalars().all()
    await finish_knowledge_projection(data[0],ORG,item.id)
    after=(await data[0].execute(select(MemorySyncOutbox).where(MemorySyncOutbox.action=="DELETE_ACTIVE_VECTOR"))).scalars().all()
    assert item.publication_status=="published" and len(before)==len(after)==0


@pytest.mark.asyncio
async def test_withdraw_stops_grandchild_without_first_retrieving_middle_dependency(data):
    service,root=await approved(data);await service.publish(root.id,action(root));await finish_knowledge_projection(data[0],ORG,root.id)
    parent=root;children=[]
    for number in [1,2]:
        payload=submit_body(data[2]);payload["claim"]+=str(number);payload["related_memory_ids"]=[parent.memory_id]
        result=await service.submit(payload);child=await data[0].get(KnowledgeAdmission,result["id"])
        await KnowledgeAdmissionService(data[0],actor(EXPERT)).review(child.id,action(child,decision="approve"))
        await KnowledgeAdmissionService(data[0],actor(ADMIN,"admin")).sharing(child.id,action(child,decision="approve"))
        await service.publish(child.id,action(child));await finish_knowledge_projection(data[0],ORG,child.id)
        children.append(child);parent=child
    result=await service.withdraw(root.id,action(root))
    assert children[0].memory_id in result["affected_memory_ids"]
    assert await guard_managed_memory(data[0],ORG,[await service.memory(children[1])])==[]
    assert children[1].publication_status=="withdrawn"
