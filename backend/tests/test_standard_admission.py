"""Real database state transitions with isolated storage/vector adapters."""
import copy
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import DefaultClause, MetaData, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.inspection_standard_library import InspectionStandardLibrary, StandardDocument
from app.models.standard_admission import StandardAdmissionReview, StandardDocumentRevision, StandardSyncOutbox
from app.services.standard_admission_service import StandardAdmissionService, normalize_standard_number, process_standard_outbox
from app.services.standard_candidate_extractor import extract_candidates,extract_metadata_candidates

ORG, OTHER, AUTHOR, EXPERT = [str(uuid.uuid4()) for _ in range(4)]
PDF=b"%PDF-1.4\nstandard-admission test fixture, never a real published standard"


@pytest_asyncio.fixture
async def context(monkeypatch):
    engine=create_async_engine("sqlite+aiosqlite:///:memory:")
    metadata=MetaData()
    for model in [InspectionStandardLibrary,StandardDocument,StandardDocumentRevision,StandardAdmissionReview,StandardSyncOutbox]:
        table=model.__table__.to_metadata(metadata)
        for col in table.c:
            if col.name in {"created_at","updated_at"}:
                col.server_default=DefaultClause(text("CURRENT_TIMESTAMP"))
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    files={}
    class Storage:
        def put_bytes(self,*,bucket,object_key,data,**kw): files[object_key]=data
        def get_bytes(self,*,bucket,object_key): return (files[object_key],"application/pdf") if object_key in files else None
    monkeypatch.setattr("app.services.standard_admission_service.build_object_storage",lambda:Storage())
    monkeypatch.setattr("app.services.standard_admission_service.extract_pdf_pages",lambda file:([
        {"page_number":1,"text":"GB 17761-2018 电动自行车安全技术规范\n6.1.1 最高车速\n最高车速不得大于25 km/h，应按7.1试验。"}],1))
    async with async_sessionmaker(engine,expire_on_commit=False)() as session:
        lib=InspectionStandardLibrary(id=str(uuid.uuid4()),org_id=ORG,name="Admission test fixture",
            product_family="电动自行车",domain="电动自行车",product_category="电动自行车",rag_space_ids=[])
        session.add(lib);await session.flush()
        yield session,lib,files
    await engine.dispose()


async def received(context):
    session,lib,_=context
    service=StandardAdmissionService(session,ORG,AUTHOR)
    result=await service.receive(lib.id,[("GB-17761-2018.pdf",PDF,"application/pdf")])
    doc=await service.document(result["documents"][0]["id"])
    rev=await session.get(StandardDocumentRevision,doc.current_revision_id)
    return service,doc,rev


async def parsed(context):
    service,doc,rev=await received(context)
    row=(await context[0].execute(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id))).scalar_one()
    await process_standard_outbox(context[0],row)
    await context[0].flush()
    return service,doc,rev


def action(rev,**kwargs):
    return {"expected_version":rev.row_version,"request_key":str(uuid.uuid4()),"reason":"isolated behavior test",
        "evidence_refs":["fixture only"],**kwargs}


async def approved(context):
    service,doc,rev=await parsed(context)
    meta={"expected_version":rev.row_version,"base_revision_id":rev.id,"standard_no":"GB 17761-2018","standard_name":"电动自行车安全技术规范",
        "standard_level":"GB","standard_status":"被代替","resource_type":"standard","source_url":"https://example.invalid/fixture",
        "publisher":"Test publisher","effective_from":"2019-04-15","effective_to":"2025-08-31",
        "production_from":"2019-04-15","production_to":"2025-08-31","scope_notes":"Test scope: 电动自行车"}
    detail=await service.amend(doc.id,meta)
    rev=await context[0].get(StandardDocumentRevision,detail["id"])
    expert=StandardAdmissionService(context[0],ORG,EXPERT)
    await expert.review(doc.id,rev.id,action(rev,decision="approve"),actor_role="expert")
    return service,doc,rev


async def prepare_and_confirm(context, doc, rev, payload):
    author=StandardAdmissionService(context[0],ORG,AUTHOR)
    await author.candidate(doc.id,rev.id,{**payload,"status":"pending"})
    target=rev.candidates_json[-1] if payload["candidate_id"].startswith("new:") else next(c for c in rev.candidates_json if c["id"]==payload["candidate_id"])
    await StandardAdmissionService(context[0],ORG,EXPERT).candidate_review(doc.id,rev.id,
        action(rev,candidate_id=target["id"],decision="confirm"),can_confirm=True)


class Indexer:
    def __init__(self,accepted=None): self.points=[];self.accepted=accepted;self.deleted=[]
    async def index(self,docs):
        self.points=copy.deepcopy(docs)
        return {"accepted":len(docs) if self.accepted is None else self.accepted,"failed_embeddings":0}
    async def delete_by_filter(self,filters): self.deleted.append(filters)


@pytest.mark.asyncio
async def test_receive_is_immutable_unpublished_and_idempotent(context):
    service,doc,rev=await received(context)
    result=await service.receive(doc.library_id,[("renamed.pdf",PDF,"application/pdf")])
    assert result["documents"][0]["id"]==doc.id
    assert result["indexed_count"]==0 and doc.published_revision_id is None
    assert rev.snapshot["resource_type"]=="unverified" and rev.publication_status=="unpublished"
    assert len(context[2])==1


@pytest.mark.asyncio
async def test_other_content_with_same_name_preserves_original_and_marks_conflict(context):
    service,doc,rev=await received(context)
    before=dict(context[2])
    result=await service.receive(doc.library_id,[("GB-17761-2018.pdf",PDF+b"other",None)])
    other=await context[0].get(StandardDocumentRevision,result["documents"][0]["current_revision_id"])
    assert doc.id in other.snapshot["conflicts"]
    assert len(context[2])==2 and all(context[2][key]==content for key,content in before.items())


@pytest.mark.asyncio
async def test_wrong_file_type_never_indexes(context):
    with pytest.raises(ValidationError):
        await StandardAdmissionService(context[0],ORG,AUTHOR).receive(context[1].id,[("fake.pdf",b"ordinary text",None)])
    assert not context[2]


@pytest.mark.asyncio
async def test_parse_generates_review_candidates_not_limits(context):
    _,doc,rev=await parsed(context)
    assert rev.processing_status=="parsed" and rev.review_status=="pending"
    assert doc.published_revision_id is None
    assert len(rev.candidates_json)==1 and rev.candidates_json[0]["operator"]=="unresolved"
    assert rev.candidates_json[0]["page_number"]==1 and "25" in rev.candidates_json[0]["source_text"]


@pytest.mark.asyncio
async def test_cross_org_access_denied(context):
    _,doc,rev=await received(context)
    with pytest.raises(NotFoundError):
        await StandardAdmissionService(context[0],OTHER,EXPERT).detail(doc.id,rev.id)


@pytest.mark.asyncio
async def test_admin_role_does_not_qualify_review(context):
    service,doc,rev=await parsed(context)
    with pytest.raises(ForbiddenError):
        await service.review(doc.id,rev.id,action(rev,decision="approve"),actor_role="admin")


@pytest.mark.asyncio
async def test_submitter_cannot_self_review(context):
    service,doc,rev=await parsed(context)
    with pytest.raises(ForbiddenError):
        await service.review(doc.id,rev.id,action(rev,decision="approve"),actor_role="expert")


@pytest.mark.asyncio
async def test_reference_or_unverified_not_approved(context):
    _,doc,rev=await parsed(context)
    with pytest.raises(ValidationError):
        await StandardAdmissionService(context[0],ORG,EXPERT).review(doc.id,rev.id,action(rev,decision="approve"),actor_role="expert")


@pytest.mark.asyncio
async def test_version_conflict_prevents_overwrite(context):
    service,doc,rev=await approved(context)
    with pytest.raises(ConflictError):
        await service.publish(doc.id,rev.id,action(rev,expected_version=1))


@pytest.mark.asyncio
async def test_publish_sync_fail_does_not_activate(context):
    service,doc,rev=await approved(context)
    await service.publish(doc.id,rev.id,action(rev))
    row=(await context[0].execute(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id,StandardSyncOutbox.action=="publish"))).scalar_one()
    with pytest.raises(ValidationError): await process_standard_outbox(context[0],row,indexer=Indexer(accepted=0))
    assert doc.published_revision_id is None and rev.publication_status=="publishing"


@pytest.mark.asyncio
async def test_publish_idempotent_and_withdraw_immediate_before_vector_cleanup(context):
    service,doc,rev=await approved(context)
    payload=action(rev)
    await service.publish(doc.id,rev.id,payload)
    await service.publish(doc.id,rev.id,payload)
    jobs=(await context[0].execute(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id,StandardSyncOutbox.action=="publish"))).scalars().all()
    assert len(jobs)==1
    indexer=Indexer()
    await process_standard_outbox(context[0],jobs[0],indexer=indexer)
    assert doc.published_revision_id==rev.id and rev.publication_status=="published"
    assert indexer.points[0]["payload"]["revision_id"]==rev.id
    await service.withdraw(doc.id,rev.id,action(rev))
    assert doc.published_revision_id is None and rev.publication_status=="withdrawn" and not indexer.deleted


@pytest.mark.asyncio
async def test_withdraw_wins_publish_race(context):
    service,doc,rev=await approved(context)
    await service.publish(doc.id,rev.id,action(rev))
    row=(await context[0].execute(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id,StandardSyncOutbox.action=="publish"))).scalar_one()
    class RacingIndexer(Indexer):
        async def index(self,docs):
            result=await super().index(docs)
            await service.withdraw(doc.id,rev.id,action(rev))
            return result
    indexer=RacingIndexer()
    await process_standard_outbox(context[0],row,indexer=indexer)
    assert doc.published_revision_id is None and rev.publication_status=="withdrawn"
    assert indexer.deleted==[{"org_id":ORG,"revision_id":rev.id}]


@pytest.mark.asyncio
async def test_same_idempotency_key_different_content_conflict(context):
    service,doc,rev=await approved(context)
    payload=action(rev)
    await service.publish(doc.id,rev.id,payload)
    with pytest.raises(ConflictError): await service.publish(doc.id,rev.id,{**payload,"reason":"different"})


@pytest.mark.asyncio
async def test_formal_retrieval_filters_fake_cross_org_and_stale_hit(context,monkeypatch):
    service,doc,rev=await approved(context)
    await service.publish(doc.id,rev.id,action(rev))
    job=(await context[0].execute(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id,StandardSyncOutbox.action=="publish"))).scalar_one()
    indexer=Indexer();await process_standard_outbox(context[0],job,indexer=indexer)
    class Retriever:
        def __init__(self,**kw): pass
        async def retrieve(self,*args,**kw):
            point=indexer.points[0]
            return [{**point,"score":1.0,"quote":point["text"]},
                {**point,"id":"spoof","payload":{**point["payload"],"org_id":OTHER}}]
    monkeypatch.setattr("app.services.standard_admission_service.Retriever",Retriever)
    result=await service.search({"query":"速度","top_k":8})
    assert len(result["hits"])==1 and result["hits"][0]["revision_id"]==rev.id
    await service.withdraw(doc.id,rev.id,action(rev))
    assert (await service.search({"query":"速度"}))["hits"]==[]


@pytest.mark.asyncio
async def test_task_basis_requires_specific_revision_and_production_context(context):
    service,doc,rev=await approved(context)
    await service.publish(doc.id,rev.id,action(rev))
    job=(await context[0].execute(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id,StandardSyncOutbox.action=="publish"))).scalar_one()
    await process_standard_outbox(context[0],job,indexer=Indexer())
    result=await service.search({"query":"速度","purpose":"task_basis"})
    assert not result["hits"] and result["missing_context"]


def test_table_numbers_never_assumed_first_numeric_threshold():
    items=extract_candidates([{"page_number":5,"text":"6.2.1 厚度\n规格 1 2 3\n不得小于 0.8 1.2 1.5"}])
    assert items[0]["operator"]=="unresolved" and items[0]["requirement"]==""
    assert "0.8 1.2 1.5" in items[0]["source_text"]


def test_candidate_keeps_ocr_and_normalized_text_without_guessing_broken_unit():
    items = extract_candidates([{"page_number": 3, "text": "6.2 流动水槽\n温度保持在 20 人士2，试样投入水后为 10 mam"}])
    assert len(items) == 1
    item = items[0]
    assert item["ocr_text"] == item["source_text"]
    assert "10 mam" in item["normalized_text"]
    assert "mm" not in item["normalized_text"]
    assert item["extraction_confidence"] < 0.99


def test_candidate_merges_clause_continuation_across_pdf_pages_without_duplicate():
    items = extract_candidates([
        {"page_number": 1, "text": "6.2 流动水槽\n温度保持在 20 ℃ ± 2 ℃"},
        {"page_number": 2, "text": "水面应高出试样约 20 mm。\n6.3 尺寸\n不得小于 10 mam"},
    ])
    assert [item["clause_no"] for item in items] == ["6.2", "6.3"]
    assert items[0]["page_number"] == 1
    assert "水面应高出试样" in items[0]["source_text"]
    assert "10 mam" in items[1]["normalized_text"] and "10 mm" not in items[1]["normalized_text"]


def test_candidate_accepts_full_width_clause_numbering():
    items = extract_candidates([{"page_number": 4, "text": "８．１ 试验条件\n温度不得高于 25 ℃。"}])
    assert len(items) == 1
    assert items[0]["clause_no"] == "8.1"


def test_candidate_classifies_method_condition_and_body_clause():
    items = extract_candidates([{"page_number": 1, "text": "5.1 仪器设备\n玻璃平板尺寸应大于被测制品最大尺寸。\n1 范围\n本文适用于日用陶瓷器。"}])
    assert any(item["candidate_type"] == "method_condition" for item in items)
    assert any(item["candidate_type"] == "body_clause" for item in items)


def test_header_clues_do_not_infer_authority_or_current_status_from_cited_number():
    clues=extract_metadata_candidates([{"page_number":2,"text":"检测报告依据 GB 17761-2018\n2019-04-15 实施"}])
    assert clues["standard_no"]["value"]=="GB 17761-2018"
    assert clues["effective_from"]["value"]=="2019-04-15"
    assert "resource_type" not in clues and "standard_status" not in clues


def test_standard_number_normalizes_ocr_dash_without_changing_metadata():
    assert normalize_standard_number("GB/T 3298-2022") == "GBT32982022"
    assert normalize_standard_number("GB/T 3298一2022") == "GBT32982022"


@pytest.mark.asyncio
async def test_candidate_confirmation_requires_complete_fields_and_independent_expert(context):
    _,doc,rev=await parsed(context)
    item=rev.candidates_json[0]
    payload=action(rev,candidate_id=item["id"],status="confirmed",indicator="最高车速",method="",conditions="测试条件",
        unit="km/h",requirement="不大于25",operator="le",measurement_key="maximum_speed",applicability="电动自行车")
    with pytest.raises(ValidationError):
        await StandardAdmissionService(context[0],ORG,EXPERT).candidate(doc.id,rev.id,payload,can_confirm=True)
    assert rev.candidates_json[0]["status"]=="pending"


@pytest.mark.asyncio
async def test_one_clause_can_have_multiple_confirmed_projects(context):
    _,doc,rev=await parsed(context)
    item=rev.candidates_json[0]
    payload=action(rev,candidate_id="new:"+item["id"],status="confirmed",indicator="另一规格分支",method="7.1",
        conditions="明确测试条件",unit="km/h",requirement="不大于25",operator="le",measurement_key="maximum_speed",applicability="限定型号")
    await prepare_and_confirm(context,doc,rev,payload)
    assert len(rev.candidates_json)==2
    assert rev.candidates_json[1]["page_number"]==rev.candidates_json[0]["page_number"]
    assert rev.candidates_json[1]["id"]!=rev.candidates_json[0]["id"]


@pytest.mark.asyncio
async def test_historical_applicability_and_incomplete_context(context):
    service,doc,rev=await approved(context)
    await service.publish(doc.id,rev.id,action(rev))
    job=(await context[0].execute(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id,StandardSyncOutbox.action=="publish"))).scalar_one()
    await process_standard_outbox(context[0],job,indexer=Indexer())
    matched=await service.check_applicability(doc.id,rev.id,{"product_category":"电动自行车","production_date":"2021-09-03","conditions":"历史样品试验条件"})
    assert matched["status"]=="scope_match"
    outside=await service.check_applicability(doc.id,rev.id,{"product_category":"电动自行车","production_date":"2026-10-05","conditions":"新生产样品"})
    assert outside["status"]=="mismatch"
    missing=await service.check_applicability(doc.id,rev.id,{})
    assert missing["status"]=="needs_information"


@pytest.mark.asyncio
async def test_reviewed_requirement_cannot_be_mutated_in_place(context):
    service,doc,rev=await approved(context)
    await service.publish(doc.id,rev.id,action(rev))
    item=rev.candidates_json[0]
    with pytest.raises(ConflictError):
        await service.candidate(doc.id,rev.id,action(rev,candidate_id=item["id"],status="pending"))


@pytest.mark.asyncio
async def test_formal_requirements_remain_visible_while_new_revision_is_pending(context):
    service,doc,rev=await parsed(context)
    item=rev.candidates_json[0]
    await prepare_and_confirm(context,doc,rev,action(rev,
        candidate_id=item["id"],status="confirmed",indicator="最高车速",method="7.1",
        conditions="道路试验",unit="km/h",requirement="不大于25",operator="le",
        measurement_key="maximum_speed",applicability="电动自行车"))
    rev=await context[0].get(StandardDocumentRevision,rev.id)
    detail=await service.amend(doc.id,{"expected_version":rev.row_version,"base_revision_id":rev.id,
        "standard_no":"GB 17761-2018","standard_name":"电动自行车安全技术规范",
        "standard_level":"GB","standard_status":"现行","resource_type":"standard",
        "scope_notes":"Test scope: 电动自行车","effective_from":"2019-04-15",
        "source_url":"https://example.invalid/fixture","publisher":"Test publisher"})
    rev=await context[0].get(StandardDocumentRevision,detail["id"])
    item=rev.candidates_json[0]
    await prepare_and_confirm(context,doc,rev,action(rev,
        candidate_id=item["id"],status="confirmed",indicator="最高车速",method="7.1",
        conditions="道路试验",unit="km/h",requirement="不大于25",operator="le",
        measurement_key="maximum_speed",applicability="电动自行车"))
    rev=await context[0].get(StandardDocumentRevision,rev.id)
    await StandardAdmissionService(context[0],ORG,EXPERT).review(doc.id,rev.id,action(rev,decision="approve"),actor_role="expert")
    rev=await context[0].get(StandardDocumentRevision,rev.id)
    await service.publish(doc.id,rev.id,action(rev))
    job=(await context[0].execute(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id,StandardSyncOutbox.action=="publish"))).scalar_one()
    await process_standard_outbox(context[0],job,indexer=Indexer())
    await service.amend(doc.id,{"expected_version":rev.row_version,"base_revision_id":rev.id,
        "standard_no":"GB 17761-2018","standard_name":"电动自行车安全技术规范",
        "standard_level":"GB","standard_status":"现行","resource_type":"standard",
        "scope_notes":"draft scope","effective_from":"2019-04-15"})
    requirements=await service.requirements()
    assert len(requirements)==1
    assert requirements[0]["revision_id"]==rev.id
    assert requirements[0]["usage_status"]=="confirmed_requirement"
