import asyncio,json,hashlib
from pathlib import Path
from sqlalchemy import text
from infra.database.session import get_session,reset_async_engine_pool


async def main():
    root=Path("runtime/knowledge_admission_20261005");root.mkdir(parents=True,exist_ok=True)
    target=root/"before_0112_metadata.json"
    if target.exists():raise RuntimeError("保留已有迁移备份，不覆盖")
    async with get_session() as session:
        records={}
        queries={"rag_documents":"SELECT HEX(id) AS id,HEX(org_id) AS org_id,checksum_sha256,parse_status,index_status FROM rag_documents",
            "rag_spaces":"SELECT HEX(id) AS id,HEX(org_id) AS org_id,HEX(created_by) AS created_by,resource_domain FROM rag_spaces",
            "memory_items":"SELECT HEX(id) AS id,memory_id,HEX(org_id) AS org_id,status,review_status,vector_status,graph_status FROM memory_items"}
        for key,query in queries.items():records[key]=[dict(r) for r in (await session.execute(text(query))).mappings()]
        records["counts"]={name:(await session.execute(text(f"SELECT COUNT(*) FROM {name}"))).scalar_one() for name in [
            "standard_documents","standard_document_chunks","memory_origins","memory_evidence","memory_scope_bindings","memory_sync_outbox"]}
    raw=json.dumps(records,sort_keys=True,ensure_ascii=False,indent=2).encode();target.write_bytes(raw)
    print(json.dumps({"backup_sha256":hashlib.sha256(raw).hexdigest(),"counts":{k:len(v) for k,v in records.items() if isinstance(v,list)},"other_counts":records["counts"]}))
    await reset_async_engine_pool()


if __name__=="__main__":asyncio.run(main())
