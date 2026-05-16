from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PIAP_", case_sensitive=False, extra="ignore")

    app_env: str = "dev"
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_issuer: str = "piap"
    jwt_audience: str = "piap-users"
    jwt_exp_minutes: int = 120
    jwt_refresh_days: int = 7

    db_url: str = "mysql+aiomysql://piap:piap@127.0.0.1:13306/piap_main"
    db_replica_url: str = "mysql+aiomysql://piap:piap@127.0.0.1:13306/piap_main"

    redis_url: str = "redis://localhost:16379/0"
    rate_limit_rpm_default: int = 60
    model_health_timeout_sec: int = 5

    s3_endpoint: str = "http://localhost:19000"
    s3_access_key: str = "piap"
    s3_secret_key: str = "piap_password"
    s3_bucket: str = "piap"
    object_storage_backend: str = "local"
    rag_storage_bucket: str = "rag-docs"
    local_upload_dir: str = "runtime_uploads"
    local_upload_url_prefix: str = "/uploads"

    celery_broker_url: str = "redis://localhost:16379/0"
    celery_result_backend: str = "redis://localhost:16379/0"

    volcengine_api_key: str = "88b788ed-5070-42c3-85e7-2641472d2f57"
    volcengine_model_id: str = "ep-20260325082100-v7vs6"
    volcengine_embed_model: str = "ep-20260311135919-gktlx"
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
    vision_detector_url: str = ""
    vision_detector_api_key: str = ""
    vision_detector_timeout_sec: int = 20

    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "piap_standard_book"
    governance_secret: str = "piap-governance-secret"
    agent_route_mode: str = "router_enabled"
    cors_allowed_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:15173",
        "http://localhost:15173",
    ]
    cors_allow_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://127.0.0.1:3000"
    langfuse_public_host: str = "http://127.0.0.1:3000"
    langfuse_project_id: str = ""
    langfuse_environment: str = ""
    langfuse_release: str = ""


settings = Settings()
