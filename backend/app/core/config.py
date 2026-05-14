from pydantic import model_validator
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

    db_url: str = "mysql+aiomysql://piap:piap@127.0.0.1:3306/piap_main"
    db_replica_url: str = "mysql+aiomysql://piap:piap@127.0.0.1:3306/piap_main"

    redis_url: str = "redis://localhost:16379/0"
    rate_limit_rpm_default: int = 60
    model_health_timeout_sec: int = 5

    s3_endpoint: str = "http://localhost:19000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "piap"
    local_upload_dir: str = "runtime_uploads"
    local_upload_url_prefix: str = "/uploads"

    celery_broker_url: str = "redis://localhost:16379/0"
    celery_result_backend: str = "redis://localhost:16379/0"

    volcengine_api_key: str = ""
    volcengine_model_id: str = ""
    volcengine_embed_model: str = ""
    volcengine_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    vision_detector_url: str = ""
    vision_detector_api_key: str = ""
    vision_detector_timeout_sec: int = 20

    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "piap_standard_book"
    governance_secret: str = ""
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
    langfuse_environment: str = "local"
    langfuse_release: str = "backend-env"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env.lower() not in {"prod", "production"}:
            return self

        required = {
            "jwt_private_key": self.jwt_private_key,
            "jwt_public_key": self.jwt_public_key,
            "governance_secret": self.governance_secret,
        }
        if self.langfuse_enabled:
            required["langfuse_public_key"] = self.langfuse_public_key
            required["langfuse_secret_key"] = self.langfuse_secret_key

        missing = [
            name
            for name, value in required.items()
            if not str(value or "").strip()
            or str(value).strip().lower().startswith(("change_me", "replace-me", "your_"))
        ]
        if missing:
            raise ValueError(f"Missing production settings: {', '.join(sorted(missing))}")
        return self


settings = Settings()
