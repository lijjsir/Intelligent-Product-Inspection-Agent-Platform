import asyncio,json
from pathlib import Path
from sqlalchemy import select,text
import httpx
from app.models.user import User
from app.models.inspection_standard_library import StandardDocument
from app.core.security import create_access_token
from infra.database.session import get_session,reset_async_engine_pool


async def main():
    root=Path("runtime/knowledge_admission_20261005")
    before=json.loads((root/"before_0112_metadata.json").read_text(encoding="utf-8"))
    async with get_session() as session:
        namespaces=select(StandardDocument.org_id).where(StandardDocument.deleted_at.is_(None)).distinct()
        users=(await session.execute(select(User).where(User.org_id.in_(namespaces),User.role.in_(["expert","admin"]),
            User.deleted_at.is_(None),User.is_active.is_(True)))).scalars().all()
        selected={}
        for user in users:selected.setdefault(user.role,user)
        counts={name:(await session.execute(text(f"SELECT COUNT(*) FROM {name}"))).scalar_one() for name in [
            "memory_items","memory_origins","memory_evidence","memory_scope_bindings","standard_documents","standard_document_chunks",
            "knowledge_admissions","knowledge_admission_actions","rag_space_grants"]}
        assert counts["standard_documents"]==before["counts"]["standard_documents"]
        assert counts["standard_document_chunks"]==before["counts"]["standard_document_chunks"]
        assert counts["memory_items"]>=len(before["memory_items"])
        checks=[]
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000",trust_env=False,timeout=20) as client:
            for role,user in selected.items():
                token=create_access_token(user.id,extra={"org_id":user.org_id,"role":role,"roles":[role]})
                headers={"Authorization":"Bearer "+token}
                for endpoint in ["/api/v1/knowledge/candidates","/api/v1/knowledge/published","/api/v1/rag-spaces"]:
                    resp=await client.get(endpoint,headers=headers);resp.raise_for_status()
                    if endpoint.endswith("rag-spaces") and role=="admin":
                        assert all(r["created_by"] in {None,user.id} for r in resp.json()["data"])
                    checks.append({"role":role,"endpoint":endpoint,"status":resp.status_code})
            anonymous=await client.get("/api/v1/knowledge/published")
            assert anonymous.status_code in {401,403}
        report={"checks":checks,"counts":counts,"anonymous_denied":True,"live_approvals":0,"live_publications":0}
        (root/"readonly_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report))
    await reset_async_engine_pool()


if __name__=="__main__":asyncio.run(main())
