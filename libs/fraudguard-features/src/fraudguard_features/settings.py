"""Redis connection settings, shared by every reader and writer of the
feature store -- the same shape as `fraudguard_db.session.DatabaseSettings`
and `fraudguard_events.settings.EventSettings`.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisSettings(BaseSettings):
    """Not derived from `fraudguard_common.BaseServiceSettings`: which Redis
    to use is orthogonal to which service is running, so this composes
    alongside a service's own settings rather than requiring one.
    """

    model_config = SettingsConfigDict(
        env_file=None, extra="ignore", case_sensitive=False
    )

    # Host-side default; the feature-service container overrides this to
    # "redis" the same way the gateway overrides POSTGRES_HOST.
    redis_host: str = "localhost"
    redis_port: int = 6379

    @property
    def url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}"


class LocalRedisSettings(RedisSettings):
    """Reads `.env` for local entry points only -- never inside a container
    image, where configuration must come from real environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
