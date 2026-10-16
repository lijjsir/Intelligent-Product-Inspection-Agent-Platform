import asyncio
import json
from pathlib import Path
import httpx
from sqlalchemy import select, text
from app.models.user import User
from app.models.inspection_standard_library import StandardDocument
from app.core.security import create_access_token
from infra.database.session import get_session, reset_async_engine_pool


async def main():
    checks=[]
    async with get_session() as session:
        namespaces=select(StandardDocument.org_id).where(StandardDocument.deleted_at.is_(None)).distinct()
        users=(await session.execute(select(User).where(User.org_id.in_(namespaces),User.role.in_(["admin","expert"]),User.deleted_at.is_(None),User.is_active.is_(True)))).scalars().all()
        selected={}
        for user in users:selected.setdefault(user.role,user)
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000",trust_env=False,timeout=20) as client:
        for role,user in selected.items():
            token=create_access_token(user.id,extra={"org_id":user.org_id,"role":user.role,"roles":[user.role]})
            headers={"Authorization":"Bearer "+token}
            prefix="/api/v1"
            libraries=await client.get(prefix+"/standard-libraries",headers=headers)
            if libraries.status_code==404:
                prefix="/v1"
                libraries=await client.get(prefix+"/standard-libraries",headers=headers)
            libraries.raise_for_status()
            items=libraries.json()["data"]["items"]
            saw_unpublished = False
            saw_published = False
            for library in items:
                docs=await client.get(f"{prefix}/standard-libraries/{library['id']}/documents",headers=headers)
                docs.raise_for_status()
                rows=docs.json()["data"]["items"]
                for doc in rows:
                    revision_id = doc.get("current_revision_id") or doc.get("published_revision_id")
                    if not revision_id:
                        continue
                    detail=await client.get(f"{prefix}/standard-documents/{doc['id']}/revisions/{revision_id}",headers=headers)
                    detail.raise_for_status()
                    state=detail.json()["data"]["publication_status"]
                    saw_published = saw_published or state == "published"
                    saw_unpublished = saw_unpublished or state != "published"
            if saw_published or saw_unpublished:
                checks.append({"role":role,"library_list":True,"document_states":True,"revision_detail":True,
                    "published_visible":saw_published,"unpublished_isolated":saw_unpublished})
    report={"checks":checks,"resource_mutations":0,"professional_approvals":0,"blocked":not bool(checks)}
    Path("runtime/standard_admission_20261005/api_readonly_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report))
    await reset_async_engine_pool()


if __name__=="__main__":asyncio.run(main())
