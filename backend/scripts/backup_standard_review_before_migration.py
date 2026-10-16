"""Preserve standard identity and governance digests before additive review changes."""
import asyncio,hashlib,json,argparse
from pathlib import Path
from sqlalchemy import text
from infra.database.session import get_session,reset_async_engine_pool

def scalar(value):
    if isinstance(value,bytes):return value.hex()
    if hasattr(value,"isoformat"):return value.isoformat()
    return str(value)

async def main(output):
    try:
        async with get_session() as db:
            versions=list(await db.scalars(text("SELECT version_num FROM alembic_version")))
            queries={
                "documents":"SELECT id, library_id, file_hash, current_revision_id, published_revision_id, review_status, publication_status FROM standard_documents WHERE deleted_at IS NULL",
                "revisions":"SELECT id, document_id, file_hash, row_version, processing_status, review_status, publication_status, snapshot, candidates_json FROM standard_document_revisions",
                "reviews":"SELECT id, revision_id, action, payload_hash FROM standard_admission_reviews",
                "outbox":"SELECT id, revision_id, action, status FROM standard_sync_outbox",
            }
            report={"database_revisions":versions,"read_only":True,"tables":{}}
            for name,query in queries.items():
                rows=[]
                for row in (await db.execute(text(query))).mappings():
                    item=dict(row)
                    for key in ["snapshot","candidates_json"]:
                        if key in item:
                            value=item.pop(key)
                            if isinstance(value,str):value=json.loads(value)
                            item[key+"_sha256"]=hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=scalar).encode()).hexdigest()
                    rows.append(item)
                report["tables"][name]=rows
    finally:await reset_async_engine_pool()
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(report,ensure_ascii=False,indent=2,default=scalar).encode()
    path.write_bytes(raw)
    print(json.dumps({"output":str(path),"sha256":hashlib.sha256(raw).hexdigest(),"counts":{k:len(v) for k,v in report["tables"].items()},"read_only":True}))

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True)
    asyncio.run(main(parser.parse_args().output))
