"""Read-only local backup before additive execution review migration.

The backup contains private source metadata; print only counts and checksum.
"""
import argparse,asyncio,hashlib,json
from pathlib import Path
from sqlalchemy import text
from infra.database.session import get_session,reset_async_engine_pool

TABLES=["inspection_execution_runs","inspection_execution_actions","quality_risk_assessments","quality_risk_cases",
    "measurement_records","supervision_records","supervision_revisions","quality_risk_policies",
    "quality_source_records","quality_attachments","standard_documents","standard_document_revisions"]


def scalar(value):
    if isinstance(value,bytes):return value.hex()
    if hasattr(value,"isoformat"):return value.isoformat()
    return str(value)


async def main(output):
    report={"read_only":True,"tables":{}}
    try:
        async with get_session() as db:
            report["database_revisions"]=list(await db.scalars(text("SELECT version_num FROM alembic_version")))
            for name in TABLES:
                report["tables"][name]=[dict(row) for row in (await db.execute(text(f"SELECT * FROM {name} ORDER BY id"))).mappings()]
    finally:await reset_async_engine_pool()
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise RuntimeError("Backup path already exists; choose a new path to preserve the original")
    content=json.dumps(report,ensure_ascii=False,indent=2,default=scalar).encode()
    path.write_bytes(content)
    print(json.dumps({"output":str(path),"sha256":hashlib.sha256(content).hexdigest(),
        "counts":{name:len(rows) for name,rows in report["tables"].items()},"read_only":True}))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True)
    asyncio.run(main(parser.parse_args().output))
