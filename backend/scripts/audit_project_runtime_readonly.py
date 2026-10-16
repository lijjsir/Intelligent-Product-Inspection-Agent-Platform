"""Read-only project readiness audit: counts, statuses, source and index integrity.

Does not authenticate as a user, approve work, publish, reindex, or modify data.
Private document bodies, attachment names and user identities are not exported.
"""
import argparse,asyncio,hashlib,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import httpx
from sqlalchemy import inspect,select,text,bindparam
from uuid import UUID
from app.core.config import settings
from app.models.standard_admission import StandardDocumentRevision,StandardSyncOutbox
from app.models.inspection_standard_library import StandardDocument,InspectionStandardLibrary
from app.models.inspection_execution import InspectionExecutionRun
from app.models.supervision import MeasurementRecord,SupervisionRecord
from app.models.quality_risk import PhysicalSample
from app.services.standard_admission_service import StandardAdmissionService
from app.services.inspection_execution_service import InspectionExecutionService
from app.schemas.user import CurrentUser
from infra.database.session import get_session,reset_async_engine_pool


async def audit():
    result={"observed_at_utc":datetime.now(timezone.utc).isoformat(),"read_only":True,"scope":"database-wide aggregate metadata; formal standard sources only"}
    async with get_session() as db:
        connection=await db.connection()
        tables=await connection.run_sync(lambda c:{name:{col["name"] for col in inspect(c).get_columns(name)} for name in inspect(c).get_table_names()})
        result["database_revisions"]=list(await db.scalars(text("SELECT version_num FROM alembic_version")))
        result["counts"]={}
        standard_orgs=list(await db.scalars(select(StandardDocument.org_id).where(StandardDocument.deleted_at.is_(None)).distinct()))
        binary_orgs=[UUID(value).bytes for value in standard_orgs]
        result["standard_namespace_counts"]={}
        names=["standard_document_revisions","standard_admission_reviews","standard_documents","standard_document_chunks",
               "inspection_standard_libraries","inspection_policy_publications","inspection_execution_runs","inspection_execution_actions",
               "inspection_specs","standard_execution_rules","knowledge_admissions","knowledge_admission_actions","rag_space_grants",
               "memory_items","memory_origins","memory_evidence","memory_scope_bindings","memory_sync_outbox",
               "rag_spaces","rag_documents","quality_attachments","quality_source_records","quality_risk_assessments","quality_risk_cases",
               "inspection_tasks","inspection_results","measurement_records","device_commands","supervision_records","export_jobs",
               "product_categories","quality_products"]
        for name in names:
            if name not in tables:continue
            clause=" WHERE deleted_at IS NULL" if "deleted_at" in tables[name] else ""
            result["counts"][name]=await db.scalar(text(f"SELECT COUNT(*) FROM {name}{clause}"))
            if "org_id" in tables[name] and binary_orgs:
                conditions="deleted_at IS NULL AND " if "deleted_at" in tables[name] else ""
                stmt=text(f"SELECT COUNT(*) FROM {name} WHERE {conditions}org_id IN :orgs").bindparams(bindparam("orgs",expanding=True))
                result["standard_namespace_counts"][name]=await db.scalar(stmt,{"orgs":binary_orgs})
        result["states"]={}
        for name,columns in [("standard_document_revisions",["processing_status","review_status","publication_status"]),
                             ("standard_sync_outbox",["action","status"]),("knowledge_admissions",["review_status","sharing_status","publication_status"]),
                             ("inspection_execution_runs",["status"]),("inspection_policy_publications",["status"]),
                             ("quality_risk_assessments",["status","trust_status"]),("memory_items",["status","review_status"]),
                             ("memory_sync_outbox",["status"]),("inspection_tasks",["status"]),("inspection_results",["verdict"]),
                             ("rag_spaces",["resource_domain","index_status"]),("export_jobs",["status"]),("supervision_records",["kind","status"])]:
            if name not in tables or not set(columns)<=tables[name]:continue
            fields=", ".join(columns)
            clause=" WHERE deleted_at IS NULL" if "deleted_at" in tables[name] else ""
            result["states"][name]=[dict(row) for row in (await db.execute(text(f"SELECT {fields},COUNT(*) AS n FROM {name}{clause} GROUP BY {fields}"))).mappings()]
        current=list((await db.execute(select(StandardDocumentRevision,StandardDocument,InspectionStandardLibrary)
            .join(StandardDocument,StandardDocument.current_revision_id==StandardDocumentRevision.id)
            .join(InspectionStandardLibrary,InspectionStandardLibrary.id==StandardDocument.library_id)
            .where(StandardDocument.deleted_at.is_(None),InspectionStandardLibrary.deleted_at.is_(None),InspectionStandardLibrary.is_active.is_(True)))).all())
        candidates=[c for rev,_,_ in current for c in rev.candidates_json or []]
        result["current_standards"]={"documents":len(current),"review_states":dict(Counter(rev.review_status for rev,_,_ in current)),
            "publication_states":dict(Counter(rev.publication_status for rev,_,_ in current)),"candidate_states":dict(Counter(c.get("status","pending") for c in candidates)),
            "assigned_revisions":sum(bool((rev.review_assignment or {}).get("reviewer_id")) for rev,_,_ in current),
            "confirmed_types":dict(Counter(c.get("candidate_type","unknown") for c in candidates if c.get("status")=="confirmed"))}
        published=list((await db.execute(select(StandardDocumentRevision,StandardDocument).join(StandardDocument,
            StandardDocument.published_revision_id==StandardDocumentRevision.id).where(StandardDocument.deleted_at.is_(None),
                StandardDocumentRevision.publication_status=="published",StandardDocumentRevision.review_status=="approved"))).all())
        result["published_standard_integrity"]=[]
        for rev,doc in published:
            entry={"standard_no":rev.snapshot.get("standard_no"),"revision_no":rev.revision_no,"file_hash_recorded":bool(rev.file_hash),
                   "confirmed_requirements":[{k:c.get(k) for k in ["candidate_type","indicator","measurement_key","execution_mode","clause_no","status"]} for c in rev.candidates_json or [] if c.get("status")=="confirmed"]}
            try:
                content=await asyncio.to_thread(StandardAdmissionService(db,rev.org_id).read_original,rev)
                entry["original_available"]=True
                entry["hash_matches"]=bool(rev.file_hash and hashlib.sha256(content).hexdigest()==rev.file_hash)
            except Exception as exc:entry.update(original_available=False,source_error_type=type(exc).__name__)
            result["published_standard_integrity"].append(entry)
        runs=list(await db.scalars(select(InspectionExecutionRun)))
        result["execution_readiness"]=[]
        for run in runs:
            item={"status":run.status,"row_version":run.row_version,"item_verdict":run.evaluation.get("item_verdict"),
                  "product_verdict":run.evaluation.get("product_verdict"),"risk_level":run.evaluation.get("risk_level"),
                  "source_count":len(run.snapshot.get("source_refs",[])),"observation_kinds":dict(Counter(o.get("kind") for o in run.snapshot.get("observations",[]))),
                  "independent_reviewer_recorded":bool(run.reviewed_by and run.reviewed_by!=run.created_by),
                  "policy_bound":bool(run.snapshot.get("policy",{}).get("publication_id"))}
            links=[]
            for obs in run.snapshot.get("observations",[]):
                if obs.get("kind")!="measurement_record":continue
                measurement=await db.get(MeasurementRecord,obs.get("evidence_id"))
                if not measurement or measurement.org_id!=run.org_id:
                    links.append({"measurement_available":False});continue
                device=await db.get(SupervisionRecord,measurement.device_id)
                sample=await db.get(SupervisionRecord,measurement.sample_id)
                physical=await db.get(PhysicalSample,measurement.sample_id)
                session=await db.get(SupervisionRecord,measurement.session_id)
                links.append({"measurement_available":True,"validation_status":measurement.validation_status,
                    "session_task_matches":bool(session and session.org_id==run.org_id and session.data.get("task_id")==run.task_id),
                    "device_record_available":bool(device and device.org_id==run.org_id and device.kind=="devices" and not device.deleted_at),
                    "sample_record_available":bool(sample and sample.org_id==run.org_id and sample.kind=="samples" and not sample.deleted_at),
                    "physical_sample_available":bool(physical and physical.org_id==run.org_id and not physical.deleted_at),
                    "calibration_version_recorded":bool(measurement.calibration_version)})
            item["measurement_links"]=links
            service=InspectionExecutionService(db,CurrentUser(user_id=run.created_by,org_id=run.org_id,role="user"))
            try:item["current_source_issues"]=await service.validity(run)
            except Exception as exc:item["source_check_error_type"]=type(exc).__name__
            result["execution_readiness"].append(item)
        if "memory_sync_outbox" in tables:
            failures=(await db.execute(text("SELECT o.last_error,o.retry_count,m.status AS memory_status,o.org_id FROM memory_sync_outbox o LEFT JOIN memory_items m ON m.org_id=o.org_id AND m.memory_id=o.memory_id WHERE o.status='failed'"))).mappings().all()
            result["memory_sync_failures"]={"count":len(failures),"memory_states":dict(Counter(r["memory_status"] for r in failures)),
                "retry_counts":dict(Counter(r["retry_count"] for r in failures)),
                "standard_namespace_failures":sum(r["org_id"] in binary_orgs for r in failures),
                "mention_embedding_configuration":sum("embedding" in (r["last_error"] or "").lower() and ("config" in (r["last_error"] or "").lower() or "配置" in (r["last_error"] or "")) for r in failures)}
        result["qdrant"]={}
        headers={"api-key":settings.qdrant_api_key} if settings.qdrant_api_key else {}
        try:
            async with httpx.AsyncClient(base_url=settings.qdrant_url,headers=headers,timeout=15,trust_env=False) as client:
                response=await client.get("/collections");response.raise_for_status()
                collections={item["name"] for item in response.json()["result"]["collections"]}
                for name in sorted(collections):
                    response=await client.get(f"/collections/{name}");response.raise_for_status();info=response.json()["result"]
                    result["qdrant"][name]={"status":info.get("status"),"points_count":info.get("points_count"),"vectors":info.get("config",{}).get("params",{}).get("vectors")}
                for (rev,_),entry in zip(published,result["published_standard_integrity"]):
                    if settings.standard_published_collection not in collections:
                        entry["published_collection_missing"]=True;continue
                    conditions=[{"key":key,"match":{"value":value}} for key,value in {
                        "org_id":rev.org_id,"revision_id":rev.id,"index_generation":rev.index_generation,"resource_domain":"formal_standard"}.items()]
                    response=await client.post(f"/collections/{settings.standard_published_collection}/points/count",json={"filter":{"must":conditions},"exact":True})
                    response.raise_for_status();entry["current_projection_points"]=response.json()["result"]["count"]
        except Exception as exc:result["qdrant_error_type"]=type(exc).__name__
    return result


async def main(output):
    try:result=await audit()
    finally:await reset_async_engine_pool()
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    print(json.dumps({"output":str(path),"database_revisions":result["database_revisions"],"current_standards":result["current_standards"],
        "counts":{k:result["counts"].get(k) for k in ["inspection_execution_runs","inspection_policy_publications","knowledge_admissions","quality_risk_assessments","measurement_records","device_commands"]},
        "published_standard_integrity":result["published_standard_integrity"],"qdrant":result["qdrant"]},ensure_ascii=False))

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",required=True)
    asyncio.run(main(parser.parse_args().output))
