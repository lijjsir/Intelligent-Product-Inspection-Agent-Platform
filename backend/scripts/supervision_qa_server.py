"""Isolated SQLite QA server; uses production routes/services and test fixtures."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4
from sqlalchemy import MetaData, select, text, DateTime, DefaultClause
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.models import (
    Base,
    Organization,
    User,
    ProductLine,
    ProductSku,
    ProductBatch,
    InspectionTask,
    InspectionSpec,
    InspectionStandardLibrary,
    StandardDocument,
    StandardDocumentChunk,
)
from app.models.supervision import SupervisionRun
from app.core.security import create_access_token, hash_password
import infra.database.session as sessions

qa_path = Path(__file__).resolve().parents[2] / ".codex_tmp/supervision_qa.sqlite"
qa_path.parent.mkdir(exist_ok=True)
engine = create_async_engine("sqlite+aiosqlite:///" + qa_path.as_posix())
factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session():
    async with factory() as db:
        yield db


sessions.get_session = get_session
manifest = {}


def uid():
    return str(uuid4())


async def tick():
    from worker.tasks.supervision_task import _execute

    while True:
        await asyncio.sleep(0.5)
        async with factory() as db:
            runs = list(
                await db.scalars(select(SupervisionRun).where(SupervisionRun.status == "queued"))
            )
            keys = [(r.id, r.org_id) for r in runs]
        for rid, oid in keys:
            await _execute(rid, oid)


@asynccontextmanager
async def lifespan(app):
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        cloned = table.to_metadata(metadata)
        for c in cloned.c:
            c.server_default = (
                DefaultClause(text("CURRENT_TIMESTAMP"))
                if isinstance(c.type, DateTime) and c.server_default is not None
                else None
            )
            c.server_onupdate = None
    async with engine.begin() as c:
        await c.run_sync(metadata.drop_all)
        await c.run_sync(metadata.create_all)
    now = datetime.utcnow()
    org, sku, batch, line, spec, standard, task, doc, chunk = [uid() for _ in range(9)]
    roles = {
        r: uid()
        for r in [
            "admin",
            "user",
            "expert",
            "platform_operator",
            "algorithm_engineer",
            "app_developer",
            "expert2",
        ]
    }
    async with factory() as db:
        db.add(
            Organization(
                id=org,
                name="质监验证组织（测试）",
                slug="quality-qa",
                is_active=True,
                settings={"quality_supervision_enabled": True},
                created_at=now,
                updated_at=now,
            )
        )
        for role, actor in roles.items():
            db.add(
                User(
                    id=actor,
                    org_id=org,
                    username=role,
                    email=f"{role}@example.com",
                    role="expert" if role == "expert2" else role,
                    is_active=True,
                    password_hash=hash_password("QualityQa!2026"),
                    created_at=now,
                    updated_at=now,
                )
            )
        db.add(
            ProductLine(
                id=line,
                org_id=org,
                code="QA-EV",
                name="电动自行车（测试）",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ProductSku(
                id=sku,
                org_id=org,
                product_line_id=line,
                code="QA-EV-001",
                name="测试车",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ProductBatch(
                id=batch,
                org_id=org,
                product_sku_id=sku,
                batch_no="QA-B001",
                name="测试批次",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            InspectionSpec(
                id=spec,
                org_id=org,
                spec_code="QA-STD",
                name="测试门槛",
                version="v1",
                product_family="qa-ev",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            InspectionStandardLibrary(
                id=standard,
                org_id=org,
                name="测试标准材料",
                product_family="qa-ev",
                inspection_spec_id=spec,
                spec_code="QA-STD",
                rag_space_ids=[],
                is_active=True,
                standard_status="现行",
                applicability={"clause_version": "qa-v1", "effective_from": "2026-01-01T00:00:00"},
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            StandardDocument(
                id=doc,
                org_id=org,
                library_id=standard,
                standard_no="QA-001",
                standard_name="测试条款",
                domain="qa",
                standard_level="测试",
                file_name="qa.txt",
                file_path="qa.txt",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            StandardDocumentChunk(
                id=chunk,
                document_id=doc,
                library_id=standard,
                chunk_index=0,
                chunk_text="测试条件：温升上限45C。仅用于接口测试。",
                qdrant_point_id=uid(),
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            InspectionTask(
                id=task,
                org_id=org,
                created_by=roles["user"],
                product_id="QA-EV-001",
                spec_code="QA-STD",
                product_sku_id=sku,
                batch_id=batch,
                inspection_standard_id=standard,
                image_urls=[],
                meta_data={"input_mode": "measurement", "supervision": True},
                status="collecting",
                priority=5,
                created_at=now,
                updated_at=now,
            )
        )
        await db.commit()
    manifest.update(
        org_id=org,
        sku_id=sku,
        batch_id=batch,
        standard_id=standard,
        task_id=task,
        roles={
            r: {
                "user_id": u,
                "role": "expert" if r == "expert2" else r,
                "token": create_access_token(
                    u, {"org_id": org, "role": "expert" if r == "expert2" else r}
                ),
            }
            for r, u in roles.items()
        },
    )
    worker = asyncio.create_task(tick())
    yield
    worker.cancel()
    await engine.dispose()


from main import create_app
from app.api.v1.deps import get_db

app = create_app()
app.router.lifespan_context = lifespan


async def db_dependency():
    async with factory() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


app.dependency_overrides[get_db] = db_dependency


@app.get("/qa/manifest")
def qa_manifest():
    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="隔离质监QA服务：生产路由与SQLite测试材料，不用于真实业务验收"
    )
    parser.add_argument(
        "--isolated-test-data",
        action="store_true",
        required=True,
        help="确认使用专用SQLite测试数据；不连接生产业务数据库",
    )
    parser.parse_args()
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8123, log_level="warning")
