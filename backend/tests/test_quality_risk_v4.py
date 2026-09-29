from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, DefaultClause, MetaData, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.models import Base, Organization, User
from app.schemas.quality_risk import (
    DataSourceCreate,
    ProductCategoryCreate,
    ProductCreate,
    QualityEventCreate,
    RiskAnalyzeRequest,
    RiskCaseCreate,
    RiskPolicyCreate,
    RiskReviewRequest,
)
from app.schemas.user import CurrentUser
from app.services.quality_risk_service import QualityRiskService


def uid():
    return str(uuid4())


@pytest_asyncio.fixture
async def domain():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    metadata = MetaData()
    selected = {
        "organizations",
        "users",
        "product_categories",
        "quality_products",
        "product_identifiers",
        "quality_data_sources",
        "quality_ingestion_jobs",
        "quality_attachments",
        "quality_source_records",
        "quality_evidence_items",
        "quality_risk_cases",
        "quality_risk_assessments",
        "quality_risk_policies",
        "standard_execution_rules",
    }
    for name in selected:
        table = Base.metadata.tables[name].to_metadata(metadata)
        for column in table.c:
            column.server_default = (
                DefaultClause(text("CURRENT_TIMESTAMP"))
                if isinstance(column.type, DateTime) and column.server_default is not None
                else None
            )
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        org = uid()
        actors = {
            role: uid()
            for role in ("admin", "user", "expert", "expert2", "algorithm_engineer")
        }
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(Organization(id=org, name="试点组织", slug=org, settings={}, is_active=True, created_at=now, updated_at=now))
        for role, actor in actors.items():
            db.add(User(id=actor, org_id=org, username=role, email=f"{role}@example.com", role="expert" if role == "expert2" else role, is_active=True, created_at=now, updated_at=now))
        await db.commit()

        def service(role):
            return QualityRiskService(db, CurrentUser(user_id=actors[role], org_id=org, role="expert" if role == "expert2" else role))

        yield db, service
    await engine.dispose()


@pytest.mark.asyncio
async def test_category_product_and_optional_identifiers(domain):
    _, service = domain
    category = await service("admin").create_category(ProductCategoryCreate(code="EBIKE", name="电动自行车"))
    product = await service("admin").create_product(ProductCreate(category_id=category["id"], name="通勤车型", brand="示例品牌"))
    assert product["category_name"] == "电动自行车"
    assert product["identifiers"] == []
    catalog = await service("user").product_catalog()
    assert catalog["products"][0]["model"] is None


@pytest.mark.asyncio
async def test_source_event_is_idempotent_and_does_not_require_batch_or_serial(domain):
    _, service = domain
    with pytest.raises(ForbiddenError):
        await service("expert").create_source(
            DataSourceCreate(
                code="EXPERT-SOURCE",
                name="专家无权创建的来源",
                source_type="consumer_complaint",
                connector_type="manual",
            )
        )
    source = await service("admin").create_source(DataSourceCreate(code="COMPLAINT", name="投诉导入", source_type="consumer_complaint", connector_type="manual"))
    payload = QualityEventCreate(source_id=source["id"], record_type="consumer_complaint", occurred_at=datetime.now(timezone.utc), content={"text": "电动自行车充电时发热"}, product_ref={})
    first = await service("user").create_event(payload)
    second = await service("user").create_event(payload)
    assert first["id"] == second["id"]
    assert first["product_ref"] == {}
    evidence = await service("user").record_evidence(first["id"])
    assert evidence[0]["nature"] == "observed"


@pytest.mark.asyncio
async def test_risk_draft_preserves_unknown_probability_and_requires_independent_review(domain):
    _, service = domain
    source = await service("admin").create_source(DataSourceCreate(code="INSPECTION", name="抽检数据", source_type="supervision_inspection", connector_type="api"))
    record = await service("user").create_event(QualityEventCreate(source_id=source["id"], record_type="supervision_inspection", occurred_at=datetime.now(timezone.utc), content={"text": "温升超过标准限值", "risk_type": "过热", "risk_level": "high"}))
    case = await service("user").create_risk_case(RiskCaseCreate(title="电动自行车温升风险", scope_type="category", scope={"category_name": "电动自行车"}, source_record_ids=[record["id"]]))
    assessment = await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    assert assessment["risk_level"] == "high"
    assert assessment["probability"] is None
    with pytest.raises(ForbiddenError):
        await service("user").review_risk(case["id"], RiskReviewRequest(decision="accept", comment="通过"))
    reviewed = await service("expert2").review_risk(case["id"], RiskReviewRequest(decision="accept", comment="证据与来源一致"))
    assert reviewed["trust_status"] == "verified"


@pytest.mark.asyncio
async def test_expert_must_resolve_unknown_level_before_accepting(domain):
    _, service = domain
    source = await service("admin").create_source(
        DataSourceCreate(
            code="OPINION",
            name="舆情数据",
            source_type="public_opinion",
            connector_type="manual",
        )
    )
    record = await service("user").create_event(
        QualityEventCreate(
            source_id=source["id"],
            record_type="public_opinion",
            occurred_at=datetime.now(timezone.utc),
            content={"text": "有人反映产品可能存在异味"},
        )
    )
    case = await service("user").create_risk_case(
        RiskCaseCreate(
            title="产品异味线索",
            scope_type="category",
            scope={"name": "充电宝"},
            source_record_ids=[record["id"]],
        )
    )
    assessment = await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    assert assessment["risk_level"] == "unknown"
    with pytest.raises(ValidationError, match="确认风险等级"):
        await service("expert2").review_risk(
            case["id"], RiskReviewRequest(decision="accept", comment="证据仍需专家定级")
        )
    reviewed = await service("expert2").review_risk(
        case["id"],
        RiskReviewRequest(
            decision="accept",
            comment="按现有证据确认低风险并持续观察",
            risk_type="异味线索",
            risk_level="low",
        ),
    )
    assert reviewed["risk_level"] == "low"


@pytest.mark.asyncio
async def test_risk_policy_versions_are_unique_and_new_publish_supersedes_old(domain):
    _, service = domain
    rules = {
        "severity": {"low": 1, "medium": 2, "high": 3, "critical": 4},
        "likelihood": {"rare": 1, "possible": 2, "likely": 3},
        "exposure": {"limited": 1, "regional": 2, "widespread": 3},
        "evidence_sufficiency": {"minimum": 0.8},
        "level_mapping": {
            "low": [0, 2],
            "medium": [3, 4],
            "high": [5, 7],
            "critical": [8, 12],
        },
    }
    v1 = await service("expert").create_policy(
        RiskPolicyCreate(code="RISK-GENERAL", name="通用风险政策", version="v1", rules=rules)
    )
    await service("admin").publish_policy(v1["id"])
    with pytest.raises(ConflictError):
        await service("expert").create_policy(
            RiskPolicyCreate(code="RISK-GENERAL", name="重复版本", version="v1", rules=rules)
        )
    v2 = await service("expert").create_policy(
        RiskPolicyCreate(code="RISK-GENERAL", name="通用风险政策", version="v2", rules=rules)
    )
    await service("admin").publish_policy(v2["id"])
    policies = await service("expert").list_policies()
    assert {item["version"]: item["status"] for item in policies} == {
        "v1": "superseded",
        "v2": "published",
    }


@pytest.mark.asyncio
async def test_selected_policy_applies_evidence_gate_to_risk_draft(domain):
    _, service = domain
    rules = {
        "severity": {"low": 1},
        "likelihood": {"rare": 1},
        "exposure": {"limited": 1},
        "evidence_sufficiency": {"minimum": 0.8},
        "level_mapping": {"low": [0, 2]},
    }
    policy = await service("expert").create_policy(
        RiskPolicyCreate(code="EVIDENCE-GATE", name="证据门槛", version="v1", rules=rules)
    )
    await service("admin").publish_policy(policy["id"])
    source = await service("admin").create_source(
        DataSourceCreate(
            code="INFERRED-SOURCE",
            name="推断线索",
            source_type="public_opinion",
            connector_type="manual",
        )
    )
    record = await service("user").create_event(
        QualityEventCreate(
            source_id=source["id"],
            record_type="public_opinion",
            occurred_at=datetime.now(timezone.utc),
            content={"text": "尚未核实的网络传言"},
            data_nature="inferred",
        )
    )
    case = await service("user").create_risk_case(
        RiskCaseCreate(
            title="待核实线索",
            scope_type="category",
            scope={"name": "电动自行车"},
            source_record_ids=[record["id"]],
        )
    )
    assessment = await service("user").analyze_risk(
        case["id"], RiskAnalyzeRequest(policy_id=policy["id"])
    )
    assert assessment["policy_version"] == "v1"
    assert any("证据充分度未达到政策门槛" in item for item in assessment["missing_inputs"])


@pytest.mark.asyncio
async def test_quality_risk_public_api_contract(domain):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.v1 import quality_risk as api
    from app.api.v1.deps import get_current_user, get_db
    from app.core.error_handlers import register_error_handlers

    db, service = domain
    role = {"value": "admin"}
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(api.router, prefix="/api/v1")

    async def session():
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    def current():
        return service(role["value"]).current

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_user] = current
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        source = (
            await client.post(
                "/api/v1/quality-data/sources",
                json={
                    "code": "API-COMPLAINT",
                    "name": "API投诉",
                    "source_type": "consumer_complaint",
                    "connector_type": "api",
                    "config": {},
                },
            )
        ).json()["data"]
        role["value"] = "user"
        event = (
            await client.post(
                "/api/v1/quality-data/events",
                json={
                    "source_id": source["id"],
                    "record_type": "consumer_complaint",
                    "occurred_at": "2026-09-27T10:00:00",
                    "content": {"text": "产品出现异常发热"},
                },
            )
        ).json()["data"]
        risk = (
            await client.post(
                "/api/v1/risk-cases",
                json={
                    "title": "异常发热风险",
                    "scope_type": "category",
                    "scope": {"name": "电动自行车"},
                    "source_record_ids": [event["id"]],
                },
            )
        ).json()["data"]
        assert risk["scope_type"] == "category"
        role["value"] = "algorithm_engineer"
        assert (await client.get("/api/v1/risk-cases")).status_code == 403


def test_quality_risk_migration_upgrade_and_downgrade():
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE inspection_tasks (id BLOB PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE inspection_standard_libraries (id BLOB PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE public_complaint_intakes (id BLOB PRIMARY KEY)"
        )
        path = (
            Path(__file__).resolve().parents[1]
            / "migrations/versions/0103_quality_risk_realign.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0103", path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        tables = set(inspect(connection).get_table_names())
        assert "quality_source_records" in tables
        assert "quality_risk_assessments" in tables
        assert "standard_execution_rules" in tables
        assert "public_complaint_intakes" in tables
        task_columns = {item["name"] for item in inspect(connection).get_columns("inspection_tasks")}
        assert {"product_category_id", "quality_product_id"}.issubset(task_columns)
        module.downgrade()
        tables = set(inspect(connection).get_table_names())
        assert "quality_source_records" not in tables
        assert "public_complaint_intakes" in tables
