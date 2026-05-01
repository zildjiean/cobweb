from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="COBWEB_",
        case_sensitive=False,
        extra="ignore",
    )

    env: Literal["local", "dev", "stg", "prod"] = "local"
    debug: bool = False

    secret_key: str = Field(min_length=32)
    access_token_ttl_min: int = 30
    refresh_token_ttl_days: int = 14

    database_url: str = "postgresql+asyncpg://cobweb:cobweb@localhost:5432/cobweb"
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://cobweb:cobweb@localhost:5672/"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "cobweb"
    s3_secret_key: str = "cobwebsecret"
    s3_bucket: str = "cobweb-artifacts"
    s3_region: str = "us-east-1"

    opensearch_url: str = "http://localhost:9200"

    cors_allowed_origins_raw: str = "http://localhost:3000"

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins_raw.split(",") if o.strip()]

    worker_token: str = "dev-worker-token-change-me"

    # Dev convenience: skip the ownership-verification step on target creation
    # so testers can scan immediately. Defaults to True only in `local` env.
    dev_skip_target_verification: bool = False

    smtp_host: str = ""
    smtp_user: str = ""
    smtp_password: str = ""

    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_discovery_url: str = ""
    oidc_redirect_uri: str = "http://localhost:3000/oidc/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
