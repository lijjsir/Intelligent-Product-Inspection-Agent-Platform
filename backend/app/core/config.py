from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PIAP_", case_sensitive=False, extra="ignore")

    app_env: str = "dev"
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_issuer: str = "piap"
    jwt_audience: str = "piap-users"
    jwt_exp_minutes: int = 0
    jwt_refresh_days: int = 0

    db_url: str = "mysql+aiomysql://piap:piap@127.0.0.1:3306/piap_main"
    db_replica_url: str = "mysql+aiomysql://piap:piap@127.0.0.1:3306/piap_main"

    redis_url: str = "redis://localhost:6379/0"
    rate_limit_rpm_default: int = 60
    model_health_timeout_sec: int = 5

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "piap"
    s3_secret_key: str = "piap_password"
    s3_bucket: str = "piap"
    object_storage_backend: str = "local"
    rag_storage_bucket: str = "rag-docs"
    dataset_storage_bucket: str = "dataset-assets"
    dataset_export_bucket: str = "dataset-exports"
    model_artifact_bucket: str = "algo-model-artifacts"
    report_export_bucket: str = "report-exports"
    local_upload_dir: str = "runtime_uploads"
    local_upload_url_prefix: str = "/uploads"
    neo4j_enabled: bool = False
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "neo4j_password"
    neo4j_database: str = "neo4j"
    algo_runner_workdir: str = "runtime_algo_workspace"
    algo_runtime_base_url: str = "http://127.0.0.1:18080"

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    gpu_scheduling_strategy: str = "load_balance"
    gpu_heartbeat_timeout_sec: int = 120
    gpu_ssh_connect_timeout_sec: int = 15
    gpu_ssh_command_timeout_sec: int = 120
    gpu_metric_poll_interval_sec: int = 30
    gpu_enable_real_execution: bool = False
    gpu_job_poll_interval_sec: int = 15
    gpu_remote_status_grace_sec: int = 60
    gpu_runtime_http_timeout_sec: int = 30
    gpu_deploy_startup_timeout_sec: int = 180

    volcengine_api_key: str = ""
    volcengine_model_id: str = ""
    volcengine_embed_model: str = ""
    volcengine_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model_id: str = "deepseek-v4-flash"
    local_openai_api_key: str = ""
    local_openai_base_url: str = "http://127.0.0.1:11434/v1"
    local_openai_docker_base_url: str = "http://host.docker.internal:11434/v1"
    local_openai_model_id: str = "qwen2.5:7b-instruct"
    trust_review_provider: str = "local_openai"
    trust_review_model: str = "qwen2.5:7b-instruct"
    trust_review_timeout_sec: int = 30
    trust_scoring_enabled: bool = True
    paper_check_languagetool_url: str = ""
    paper_check_languagetool_language: str = "zh-CN"
    paper_check_languagetool_timeout_sec: int = 20
    vision_detector_url: str = ""
    vision_detector_api_key: str = ""
    vision_detector_timeout_sec: int = 20

    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "piap_standard_book"
    paper_template_qdrant_collection: str = "paper_template_clauses"
    rag_score_threshold: float = 0.55
    governance_secret: str = "piap-governance-secret"
    agent_route_mode: str = "router_enabled"
    enable_legacy_agent_fallback: bool = False
    cors_allowed_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:15173",
        "http://localhost:15173",
    ]
    cors_allow_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    langfuse_enabled: bool = True
    langfuse_public_key: str | None = "pk-lf-piap-local"
    langfuse_secret_key: str | None = "sk-lf-piap-local-secret"
    langfuse_host: str | None = "http://127.0.0.1:3000"
    langfuse_public_host: str | None = "http://127.0.0.1:3000"
    langfuse_project_id: str | None = "piap-local"
    langfuse_environment: str | None = "local-self-hosted"
    langfuse_release: str | None = None

    langfuse_init_org_id: str | None = None
    langfuse_init_org_name: str | None = None
    langfuse_init_project_id: str | None = None
    langfuse_init_project_name: str | None = None
    langfuse_init_user_email: str | None = None
    langfuse_init_user_name: str | None = None
    langfuse_init_user_password: str | None = None

    @field_validator("jwt_private_key", "jwt_public_key", mode="before")
    @classmethod
    def _normalize_jwt_pem(cls, value):
        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""

        normalized = text.replace("\\n", "\n")
        if "-----BEGIN" in normalized:
            return normalized

        candidate = Path(text)
        if not candidate.is_absolute():
            candidate = Path(__file__).resolve().parents[2] / candidate
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").strip()

        return normalized

    @field_validator(
        "langfuse_public_key",
        "langfuse_secret_key",
        "langfuse_host",
        "langfuse_public_host",
        "langfuse_project_id",
        "langfuse_environment",
        "langfuse_release",
        "langfuse_init_org_id",
        "langfuse_init_org_name",
        "langfuse_init_project_id",
        "langfuse_init_project_name",
        "langfuse_init_user_email",
        "langfuse_init_user_name",
        "langfuse_init_user_password",
        mode="before",
    )
    @classmethod
    def _blank_langfuse_values_to_none(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text if text and text.lower() not in {"none", "null", "undefined"} else None


settings = Settings()
