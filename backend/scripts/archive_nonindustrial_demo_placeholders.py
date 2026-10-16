"""Archive only three known out-of-scope empty demo libraries; never deletes files or tasks."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, or_, select

from app.core.ids import uuid7
from app.models import Organization, User
from app.models.audit import AuditLog
from app.models.inspection_spec import InspectionSpec
from app.models.inspection_standard_library import InspectionStandardLibrary, StandardDocument
from app.models.quality_risk import StandardExecutionRule
from app.models.task import InspectionTask
from infra.database.session import get_session, reset_async_engine_pool

ORG_ID = "26c1c3e4-658b-498d-aab7-39b194de478c"
FAMILIES = ("hazelnut", "capsule", "pill")
OUT = Path(__file__).resolve().parents[1] / "runtime/nonindustrial_demo_archive_20261004"


def snapshot(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


async def discover(db, lock=False):
    query = select(InspectionStandardLibrary).where(
        InspectionStandardLibrary.org_id == ORG_ID,
        InspectionStandardLibrary.product_family.in_(FAMILIES),
        InspectionStandardLibrary.deleted_at.is_(None),
    ).order_by(InspectionStandardLibrary.id)
    if lock:
        query = query.with_for_update()
    libraries = list(await db.scalars(query))
    ids = [row.id for row in libraries]
    spec_ids = [row.inspection_spec_id for row in libraries if row.inspection_spec_id]
    codes = [row.spec_code for row in libraries if row.spec_code]
    specs = list(await db.scalars(select(InspectionSpec).where(
        InspectionSpec.org_id == ORG_ID, InspectionSpec.id.in_(spec_ids),
        InspectionSpec.deleted_at.is_(None),
    ).order_by(InspectionSpec.id)))
    documents = await db.scalar(select(func.count()).select_from(StandardDocument).where(
        StandardDocument.library_id.in_(ids), StandardDocument.deleted_at.is_(None),
    ))
    rules = await db.scalar(select(func.count()).select_from(StandardExecutionRule).where(
        StandardExecutionRule.org_id == ORG_ID, StandardExecutionRule.standard_id.in_(ids),
        StandardExecutionRule.deleted_at.is_(None),
    ))
    tasks = await db.scalar(select(func.count()).select_from(InspectionTask).where(
        InspectionTask.org_id == ORG_ID,
        or_(InspectionTask.product_id.in_(FAMILIES), InspectionTask.spec_code.in_(codes),
            InspectionTask.inspection_standard_id.in_(ids)),
    ))
    assert not documents and not rules and not tasks, "发现正文、规则或任务引用，未执行占位归档"
    assert all(not row.rag_space_ids for row in libraries), "占位库存在RAG关联，未扩大归档范围"
    data = {"organization_id": ORG_ID, "libraries": [snapshot(row) for row in libraries],
            "specs": [snapshot(row) for row in specs], "documents": documents, "rules": rules, "tasks": tasks}
    digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    return libraries, specs, data, digest


async def main(apply, expected_hash):
    try:
        async with get_session() as db:
            org = await db.get(Organization, ORG_ID)
            assert org and org.slug == "cqupt", "目标工作组织不匹配"
            if apply:
                await db.scalar(select(Organization.id).where(Organization.id == ORG_ID).with_for_update())
            libraries, specs, data, digest = await discover(db, lock=apply)
            OUT.mkdir(parents=True, exist_ok=True)
            if not apply:
                backup = OUT / "before.json"
                if backup.exists():
                    backup = OUT / f"before_{digest}.json"
                if not backup.exists():
                    backup.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                print(json.dumps({"apply": False, "plan_hash": digest, "libraries": [row.name for row in libraries],
                                  "specs": len(specs), "references": {key:data[key] for key in ('documents','rules','tasks')}} ,ensure_ascii=False))
                return
            assert expected_hash == digest, "盘点摘要已变化，未归档"
            assert (OUT / "before.json").exists(), "缺少备份，未归档"
            actor = await db.scalar(select(User).where(User.org_id == ORG_ID, User.username == "admin", User.role == "admin", User.is_active.is_(True)))
            assert actor, "目标管理员不存在"
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for resource in [*libraries, *specs]:
                resource.is_active = False
                resource.deleted_at = now
                db.add(AuditLog(
                    id=str(uuid7()), org_id=ORG_ID, actor_id=actor.id, actor_role="admin",
                    resource_type="standard_library" if isinstance(resource, InspectionStandardLibrary) else "inspection_spec",
                    resource_id=resource.id, action="archive_outside_project_scope", occurred_at=now,
                    payload_hash=digest,
                ))
            await db.commit()
        async with get_session() as verify:
            remaining = await verify.scalar(select(func.count()).select_from(InspectionStandardLibrary).where(
                InspectionStandardLibrary.org_id == ORG_ID, InspectionStandardLibrary.product_family.in_(FAMILIES),
                InspectionStandardLibrary.deleted_at.is_(None),
            ))
            assert remaining == 0, "归档后仍存在有效的目标占位库"
        result = {"applied": True, "plan_hash": digest, "archived_libraries": len(libraries), "archived_specs": len(specs),
                  "raw_rows_preserved": True, "documents_or_tasks_deleted": 0, "reason": "用户要求替换非本项目工业范围的食品、药品演示项"}
        (OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-hash")
    args=parser.parse_args()
    asyncio.run(main(args.apply,args.expected_hash))
