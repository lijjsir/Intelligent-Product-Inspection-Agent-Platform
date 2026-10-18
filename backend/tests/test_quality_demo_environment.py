from pathlib import Path
from uuid import uuid4
import io

import pytest
from pydantic import ValidationError as SettingsValidationError
from sqlalchemy import MetaData, select
from fastapi import UploadFile

from test_quality_risk_v4 import domain  # noqa: F401
from app.core.config import Settings
from app.core.quality_demo import runtime_context, demo_schema_metadata
from app.core.exceptions import ValidationError
from app.core.security import verify_password
from app.models.user import User
from app.models.quality_risk import QualityRiskAssessment, QualityRiskCase, QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.schemas.quality_risk import QualityEventCreate, RiskReviewRequest
from app.services import quality_demo_seed
from app.services.quality_demo_seed import seed_quality_demo, demo_id, ACCOUNTS


def demo_settings(tmp_path: Path, **overrides):
    values = dict(_env_file=None, app_env="test", quality_demo_enabled=True,
        db_url="mysql+aiomysql://demo:example@localhost/piap_quality_demo",
        db_replica_url="mysql+aiomysql://demo:example@localhost/piap_quality_demo",
        object_storage_backend="local", local_upload_dir=str(tmp_path / "piap_quality_demo" / "uploads"),
        local_upload_url_prefix="/quality-demo-uploads", neo4j_enabled=False, langfuse_enabled=False,
        redis_url="redis://redis:6379/15", celery_broker_url="redis://redis:6379/15", celery_result_backend="redis://redis:6379/15",
        jwt_issuer="piap-quality-demo", jwt_audience="piap-quality-demo-users",
        jwt_private_key="unit-test-private", jwt_public_key="unit-test-public")
    for name in ["s3_bucket", "rag_storage_bucket", "dataset_storage_bucket", "dataset_export_bucket", "model_artifact_bucket", "report_export_bucket"]:
        values[name] = "quality-demo-" + name.replace("_", "-")
    values.update(overrides)
    return Settings(**values)


def test_demo_settings_and_public_identity(tmp_path):
    settings = demo_settings(tmp_path)
    payload = runtime_context(settings)
    assert payload["execution_mode"] == "demo" and payload["case_code"] == "DEMO-QS-001"
    assert set(payload) == {"execution_mode", "label", "notice", "organization_slug", "case_code"}
    settings.quality_demo_enabled = False
    assert runtime_context(settings)["execution_mode"] == "business"
    assert runtime_context(settings)["organization_slug"] is None


def test_demo_schema_includes_lazily_registered_models_without_mutating_shared_types():
    metadata = demo_schema_metadata()
    assert {"collab_messages", "collab_threads", "collab_message_receipts", "quality_source_records"} <= set(metadata.tables)
    assert metadata.tables["organizations"].c.created_at.type.fsp == 3
    from app.models import Base
    assert getattr(Base.metadata.tables["organizations"].c.created_at.type, "fsp", None) is None


@pytest.mark.parametrize("overrides", [
    {"app_env": "prod"}, {"app_env": "production"},
    {"db_url": "mysql+aiomysql://demo:example@localhost/piap_main"},
    {"db_replica_url": "mysql+aiomysql://demo:example@localhost/piap_main"},
    {"db_url": "mysql+aiomysql://demo:example@10.16.125.125/piap_quality_demo"},
    {"local_upload_dir": "runtime_uploads"}, {"object_storage_backend": "minio"},
    {"report_export_bucket": "report-exports"}, {"redis_url": "redis://redis:6379/0"},
    {"jwt_issuer": "piap"}, {"neo4j_enabled": True}, {"langfuse_enabled": True},
])
def test_demo_refuses_shared_or_remote_configuration(tmp_path, overrides):
    with pytest.raises(SettingsValidationError):
        demo_settings(tmp_path, **overrides)


@pytest.mark.asyncio
async def test_seed_is_repeatable_and_never_approves_or_resets_accounts(domain, monkeypatch):
    db, _ = domain
    monkeypatch.setattr(quality_demo_seed.settings, "quality_demo_enabled", True)
    metadata = MetaData()
    SupervisionRecord.__table__.to_metadata(metadata)
    async with db.bind.begin() as connection:
        await connection.run_sync(metadata.create_all)
    class MemoryStorage:
        def __init__(self): self.objects = {}
        def put_bytes(self, **data): self.objects[data["object_key"]] = data["data"]
    storage = MemoryStorage()
    passwords = {name: "Isolated-test-password-2026" for name, _, _ in ACCOUNTS}
    first = await seed_quality_demo(db, storage, passwords)
    await db.commit()
    second = await seed_quality_demo(db, storage, passwords)
    assert first["case_id"] == second["case_id"] and second["reused"]
    accounts = list(await db.scalars(select(User).where(User.org_id == demo_id("organization"))))
    assert {user.username: user.role for user in accounts} == {"demo_admin": "admin", "demo_analyst": "expert", "demo_reviewer": "expert"}
    assert all(verify_password(passwords[user.username], user.password_hash) for user in accounts)
    cases = list(await db.scalars(select(QualityRiskCase).where(QualityRiskCase.org_id == demo_id("organization"))))
    assessments = list(await db.scalars(select(QualityRiskAssessment).where(QualityRiskAssessment.org_id == demo_id("organization"))))
    records = list(await db.scalars(select(QualitySourceRecord).where(QualitySourceRecord.org_id == demo_id("organization"))))
    assert len(cases) == len(assessments) == 1 and len(records) == 3 and len(storage.objects) == 1
    assert all(record.data_nature == "synthetic" for record in records)
    assert assessments[0].reviewed_by is None and assessments[0].probability is None
    assert assessments[0].status != "accepted" and not assessments[0].model_versions["llm_called"]
    with pytest.raises(ValueError, match="never reset"):
        await seed_quality_demo(db, storage, {**passwords, "demo_reviewer": "Changed-password-should-not-reset"})


@pytest.mark.asyncio
async def test_demo_intake_cannot_masquerade_as_real_evidence(domain, monkeypatch):
    _, service = domain
    monkeypatch.setattr(quality_demo_seed.settings, "quality_demo_enabled", True)
    record = await service("user").create_event(QualityEventCreate(
        record_type="consumer_complaint", content={"text": "演示提交"}, data_nature="observed",
    ))
    assert record["data_nature"] == "synthetic" and record["provenance"]["execution_mode"] == "demo"
    preview = await service("user").preview_import(request_key="demo-preview-policy",
        file=UploadFile(io.BytesIO(b'[{"record_type":"consumer_complaint","text":"demo","data_nature":"observed"}]'), filename="demo.json"))
    assert preview["preview_rows"][0]["data_nature"] == "synthetic"
    assert preview["preview_rows"][0]["provenance"]["execution_mode"] == "demo"
    with pytest.raises(ValidationError, match="演示环境"):
        await service("expert").review_risk(str(uuid4()), RiskReviewRequest(decision="accept", comment="不能确认正式风险"))
