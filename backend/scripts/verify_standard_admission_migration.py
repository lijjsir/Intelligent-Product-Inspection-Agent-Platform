import asyncio
import hashlib
import json
from pathlib import Path
from sqlalchemy import text
from infra.database.session import get_session, reset_async_engine_pool


async def main():
    async with get_session() as session:
        head=(await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        counts={name:(await session.execute(text(f"SELECT COUNT(*) FROM {name}"))).scalar_one() for name in [
            "standard_documents","standard_document_chunks","standard_document_revisions","standard_admission_reviews","standard_sync_outbox"]}
        published=(await session.execute(text("SELECT COUNT(*) FROM standard_document_revisions WHERE publication_status='published'"))).scalar_one()
        hashes=[{"id":r[0].hex(),"file_hash":r[1]} for r in (await session.execute(text("SELECT id,file_hash FROM standard_documents ORDER BY id")))]
        original=json.loads(Path("runtime/standard_admission_20261005/before_0111.json").read_text(encoding="utf-8"))
        before={row["id"]["binary_hex"]:row["file_hash"] for row in original["standard_documents"]}
        unchanged=all(before[row["id"]]==row["file_hash"] for row in hashes)
        report={"migration":head,"counts":counts,"existing_file_hashes_unchanged":unchanged,
            "published_revisions":published,"legacy_auto_approval":False}
        assert head=="0111_standard_admission" and unchanged
        assert counts["standard_documents"]==len(original["standard_documents"])
        assert counts["standard_document_chunks"]==len(original["standard_document_chunks"])
        Path("runtime/standard_admission_20261005/migration_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False))
    await reset_async_engine_pool()


if __name__=="__main__": asyncio.run(main())
