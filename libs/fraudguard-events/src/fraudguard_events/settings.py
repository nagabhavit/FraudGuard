"""Kafka/Schema Registry connection settings, shared by every producer and
consumer -- the same shape as `fraudguard_db.session.DatabaseSettings`.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class EventSettings(BaseSettings):
    """Not derived from `fraudguard_common.BaseServiceSettings`: which
    broker and registry to use is orthogonal to which service is running,
    so this composes alongside a service's own settings rather than
    requiring one -- same reasoning as `DatabaseSettings`.
    """

    model_config = SettingsConfigDict(
        env_file=None, extra="ignore", case_sensitive=False
    )

    # Host-side default (the external listener in docker-compose.yml); the
    # gateway container overrides this to "kafka:9092" the same way it
    # overrides POSTGRES_HOST.
    kafka_bootstrap_servers: str = "localhost:29092"
    schema_registry_url: str = "http://localhost:8081"


class LocalEventSettings(EventSettings):
    """Reads `.env` for local entry points only -- never inside a container
    image, where configuration must come from real environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
