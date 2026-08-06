"""Shared settings base for every FraudGuard service.

Every service subclasses `BaseServiceSettings` and adds its own fields (a
Postgres DSN, a Redis URL, ...). The base only owns the fields every service
needs regardless of what it does, so a service cannot forget to configure its
own log level or accidentally diverge on what "environment" means.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment, used to gate environment-specific behaviour.

    A plain string would let a typo like "prod" silently fail to match
    "production" in a comparison; the enum makes that a load-time error
    instead of a production incident.
    """

    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Mirrors `logging`'s level names so settings stay free of stdlib imports."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class BaseServiceSettings(BaseSettings):
    """Fields every FraudGuard service must configure, and nothing else.

    Subclasses add service-specific fields (data store URLs, timeouts). This
    class deliberately does not read a `.env` file itself: in production,
    configuration arrives as real environment variables (Milestone 29), and a
    silent fallback to a `.env` file in that environment would mask a missing
    variable instead of failing startup loudly.
    """

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    service_name: str
    environment: Environment = Environment.LOCAL
    log_level: LogLevel = LogLevel.INFO

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


class LocalDevSettings(BaseServiceSettings):
    """Convenience base for local development: reads `.env` if present.

    Services wire this in only for local entry points (e.g. `uvicorn` run via
    `uv run`), never in the container image, so production never depends on a
    file that is gitignored and may not exist.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
