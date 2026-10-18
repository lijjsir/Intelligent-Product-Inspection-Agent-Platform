"""Server-owned identity and fail-closed isolation for the local acceptance stack."""
from pathlib import Path

from sqlalchemy.engine import make_url

DEMO_DATABASE = "piap_quality_demo"
DEMO_ORG_SLUG = "piap-quality-demo"
DEMO_CASE_CODE = "DEMO-QS-001"


def validate_demo_settings(settings) -> None:
    if settings.app_env not in {"dev", "local", "test"}:
        raise ValueError("quality demo is only allowed in local development or test")
    primary = make_url(settings.db_url)
    replica = make_url(settings.db_replica_url)
    for url in (primary, replica):
        if url.get_backend_name() != "mysql" or url.database != DEMO_DATABASE:
            raise ValueError("quality demo requires the dedicated piap_quality_demo MySQL database")
        if url.host not in {"mysql", "localhost", "127.0.0.1", "::1"}:
            raise ValueError("quality demo database must be on the isolated local stack")
    if primary != replica:
        raise ValueError("quality demo replica must use the same isolated database")
    root = Path(settings.local_upload_dir)
    if not root.is_absolute() or ".." in root.parts or root.name != "uploads" or root.parent.name != DEMO_DATABASE:
        raise ValueError("quality demo files require a dedicated absolute piap_quality_demo/uploads directory")
    if settings.object_storage_backend != "local":
        raise ValueError("quality demo must use its dedicated local file storage")
    for name in ("s3_bucket", "rag_storage_bucket", "dataset_storage_bucket", "dataset_export_bucket", "model_artifact_bucket", "report_export_bucket"):
        if not str(getattr(settings, name)).startswith("quality-demo-"):
            raise ValueError("quality demo storage namespaces must start with quality-demo-")
    if settings.local_upload_url_prefix != "/quality-demo-uploads":
        raise ValueError("quality demo requires a separate upload URL prefix")
    if settings.neo4j_enabled or settings.langfuse_enabled or settings.gpu_enable_real_execution:
        raise ValueError("quality demo may not connect to normal graph, tracing or GPU execution services")
    redis = make_url(settings.redis_url)
    if redis.host not in {"redis", "localhost", "127.0.0.1", "::1"}:
        raise ValueError("quality demo Redis must be local to the isolated stack")
    if redis.database != "15" or settings.celery_broker_url != settings.redis_url or settings.celery_result_backend != settings.redis_url:
        raise ValueError("quality demo cache and queue must use the dedicated Redis database 15")
    if settings.jwt_issuer != "piap-quality-demo" or settings.jwt_audience != "piap-quality-demo-users":
        raise ValueError("quality demo requires a separate JWT issuer and audience")


def runtime_context(settings) -> dict:
    demo = bool(settings.quality_demo_enabled)
    return {
        "execution_mode": "demo" if demo else "business",
        "label": "演示环境" if demo else "业务环境",
        "notice": "全部为隔离演示数据，不用于正式风险结论。" if demo else None,
        "organization_slug": DEMO_ORG_SLUG if demo else None,
        "case_code": DEMO_CASE_CODE if demo else None,
    }


def demo_schema_metadata():
    """Register every model, including those imported lazily by API modules."""
    from importlib import import_module
    from pkgutil import iter_modules
    from sqlalchemy import DateTime, MetaData
    from sqlalchemy.dialects.mysql import DATETIME

    models = import_module("app.models")
    for module in iter_modules(models.__path__):
        if not module.ispkg:
            import_module(f"app.models.{module.name}")
    metadata = MetaData()
    for table in models.Base.metadata.sorted_tables:
        copied = table.to_metadata(metadata)
        for column in copied.c:
            if isinstance(column.type, DateTime):
                column.type = DATETIME(fsp=3)
    return metadata
