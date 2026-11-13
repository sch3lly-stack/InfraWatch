"""Server configuration, loaded from INFRAWATCH_* environment variables."""
from __future__ import annotations

import logging
import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("infrawatch.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INFRAWATCH_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./infrawatch.db"
    secret_key: str = ""  # JWT signing key. Generated (ephemeral) if empty.
    admin_username: str = "admin"
    admin_password: str = ""  # If empty and no admin exists, a random one is generated and logged once.
    token_ttl_minutes: int = 480

    # Host liveness
    offline_after_seconds: int = 90
    evaluation_interval_seconds: int = 15
    metric_retention_days: int = 30

    # Ingestion limits
    max_batch_samples: int = 500
    max_clock_skew_seconds: int = 300
    max_sample_age_seconds: int = 7 * 86400
    max_checks_per_sample: int = 50

    # Rate limiting (requests per minute)
    rate_limit_login_per_min: int = 10
    rate_limit_register_per_min: int = 10
    rate_limit_ingest_per_min: int = 120
    rate_limit_api_per_min: int = 600
    trust_proxy_headers: bool = False

    # Agent versions
    latest_agent_version: str = "0.1.0"
    min_agent_version: str = "0.1.0"

    # Notifications
    allow_private_webhooks: bool = False
    webhook_timeout_seconds: float = 5.0

    # CORS (dev only). Comma separated origins.
    cors_origins: str = ""
    # Directory of the built frontend, served at "/" if it exists.
    frontend_dir: str = "../frontend/dist"

    run_background_tasks: bool = True


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.secret_key:
        s.secret_key = secrets.token_urlsafe(48)
        log.warning("INFRAWATCH_SECRET_KEY not set; using an ephemeral key (sessions reset on restart)")
    return s
