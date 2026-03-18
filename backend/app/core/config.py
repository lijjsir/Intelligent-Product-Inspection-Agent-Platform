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

    redis_url: str = "redis://localhost:6379/0"
    rate_limit_rpm_default: int = 60

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "piap"
    s3_secret_key: str = "piap_password"
    s3_bucket: str = "piap"

    vector_db_host: str = "localhost"
    vector_db_port: int = 19530


settings = Settings()
