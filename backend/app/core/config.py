from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PIAP_", case_sensitive=False, extra="ignore")

    app_env: str = "dev"
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_issuer: str = "piap"
    jwt_audience: str = "piap-users"
    jwt_exp_minutes: int = 15
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

    vector_db_host: str = "localhost"
    vector_db_port: int = 19530

    celery_broker_url: str = "redis://localhost:16379/0"
    celery_result_backend: str = "redis://localhost:16379/0"

    volcengine_api_key: str = "88b788ed-5070-42c3-85e7-2641472d2f57"
    volcengine_model_id: str = "ep-20260310154131-fp54f"
    volcengine_embed_model: str = "ep-20260311135919-gktlx"
    volcengine_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    vision_detector_url: str = ""
    vision_detector_api_key: str = ""
    vision_detector_timeout_sec: int = 20

    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "piap_standard_book"
    governance_secret: str = "piap-governance-secret"


settings = Settings()
