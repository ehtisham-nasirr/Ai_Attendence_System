"""Backend configuration from the environment (pydantic-settings, standards/06).

Environment-specific values and secrets only. Business configuration (thresholds, grace periods,
retention, schedules) lives in the `settings` table (`facetrack_common.settings_keys`).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    service_name: str = "backend"

    database_url: SecretStr
    redis_url: SecretStr
    jwt_secret: SecretStr
    # Base64 AES-256 key shared with the engine (NFR-8).
    encryption_key: SecretStr

    jwt_algorithm: Literal["HS256"] = "HS256"
    session_minutes: int = Field(default=30, ge=5, le=480)  # §15: session timeout 30 minutes
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict"] = "lax"
    cors_origins: list[str] = Field(default_factory=list)
    portal_base_url: str = "https://facetrack.local"
    api_docs_enabled: bool = True

    # Engine nodes by name, e.g. {"node-1": "http://engine:8100"} (standards/17 §9).
    engine_nodes: dict[str, str] = Field(default_factory=lambda: {"node-1": "http://engine:8100"})
    engine_api_token: SecretStr
    engine_timeout_s: float = 20.0
    # Must match the engines' ENGINE_EMBEDDER: enrollment counts and duplicate checks use this model.
    embedder_model: str = "sface"

    # Object storage (ADR-0005)
    storage_backend: Literal["local", "s3"] = "local"
    media_root: Path = Path("/srv/media")
    s3_endpoint: str = ""
    s3_access_key: SecretStr = SecretStr("")
    s3_secret_key: SecretStr = SecretStr("")
    s3_secure: bool = True
    s3_bucket: str = "facetrack"

    # Live view (MediaMTX). Public URLs are relative paths proxied by Nginx.
    mediamtx_api_url: str = "http://mediamtx:9997"
    mediamtx_webrtc_public_path: str = "/live"
    live_token_seconds: int = 120

    # Uploads (standards/14)
    max_photo_mb: int = 5
    max_zip_mb: int = 200
    max_import_mb: int = 10
    max_zip_files: int = 5000

    login_rate_limit_per_minute: int = 10
    api_key_rate_limit_per_minute: int = 120

    # Integrations (Phase 5 of requirements §16)
    payroll_webhook_secret: SecretStr = SecretStr("")
    hr_api_token: SecretStr = SecretStr("")
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = "facetrack@localhost"
    smtp_starttls: bool = True
    ldap_server_uri: str = ""
    ldap_bind_dn: str = ""
    ldap_bind_password: SecretStr = SecretStr("")
    ldap_base_dn: str = ""
    ldap_user_attribute: str = "sAMAccountName"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required values come from the environment
