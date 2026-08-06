"""Unit tests for connection-string construction -- no database required."""

from __future__ import annotations

from fraudguard_db.session import DatabaseSettings


def test_async_dsn_uses_the_asyncpg_driver() -> None:
    settings = DatabaseSettings(
        postgres_host="db.internal",
        postgres_port=5433,
        postgres_user="alice",
        postgres_password="secret",
        postgres_db="fraudguard_test",
    )
    assert settings.async_dsn == (
        "postgresql+asyncpg://alice:secret@db.internal:5433/fraudguard_test"
    )


def test_sync_dsn_uses_the_psycopg_driver_for_alembic() -> None:
    settings = DatabaseSettings(
        postgres_host="db.internal",
        postgres_port=5433,
        postgres_user="alice",
        postgres_password="secret",
        postgres_db="fraudguard_test",
    )
    assert (
        settings.sync_dsn
        == "postgresql+psycopg://alice:secret@db.internal:5433/fraudguard_test"
    )


def test_defaults_match_docker_compose_local_development_values() -> None:
    settings = DatabaseSettings()
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432
    assert settings.postgres_user == "fraudguard"
    assert settings.postgres_db == "fraudguard"
