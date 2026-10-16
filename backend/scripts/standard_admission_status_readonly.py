import asyncio
import json
from pathlib import Path
from sqlalchemy import text
from infra.database.session import get_session, reset_async_engine_pool


async def main():
    async with get_session() as session:
        status=[dict(row) for row in (await session.execute(text("SELECT processing_status,review_status,publication_status,COUNT(*) AS n FROM standard_document_revisions GROUP BY processing_status,review_status,publication_status"))).mappings()]
        jobs=[dict(row) for row in (await session.execute(text("SELECT status,action,COUNT(*) AS n FROM standard_sync_outbox GROUP BY status,action"))).mappings()]
        candidates=(await session.execute(text("SELECT COALESCE(SUM(JSON_LENGTH(candidates_json)),0) FROM standard_document_revisions"))).scalar_one()
        report={"revision_states":status,"jobs":jobs,"candidate_count":int(candidates)}
        Path("runtime/standard_admission_20261005/current_status.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report))
    await reset_async_engine_pool()


if __name__=="__main__":asyncio.run(main())
