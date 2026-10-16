"""Local pre-migration snapshot; never prints contents or connection settings."""
import asyncio
import datetime
import hashlib
import json
from pathlib import Path
from sqlalchemy import text
from infra.database.session import get_session, reset_async_engine_pool


def encode(value):
    if isinstance(value, bytes): return {"binary_hex":value.hex()}
    if isinstance(value,(datetime.datetime,datetime.date)): return value.isoformat()
    raise TypeError(type(value).__name__)


async def main():
    root=Path("/app/backend/runtime/standard_admission_20261005")
    root.mkdir(parents=True,exist_ok=True)
    target=root/"before_0111.json"
    if target.exists():
        raise RuntimeError("Existing migration backup retained; do not overwrite")
    snapshot={}
    async with get_session() as session:
        for name in ["alembic_version","standard_documents","standard_document_chunks","inspection_standard_libraries","rag_spaces","role_permissions"]:
            snapshot[name]=[dict(row) for row in (await session.execute(text(f"SELECT * FROM {name}"))).mappings()]
    data=json.dumps(snapshot,ensure_ascii=False,indent=2,default=encode).encode("utf-8")
    target.write_bytes(data)
    print(json.dumps({"saved":str(target),"sha256":hashlib.sha256(data).hexdigest(),"counts":{k:len(v) for k,v in snapshot.items()}}))
    await reset_async_engine_pool()


if __name__=="__main__": asyncio.run(main())
