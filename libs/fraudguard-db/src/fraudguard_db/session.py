"""Async engine/session factory shared by every service that talks to
Postgres directly, and the connection settings needed to build one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseSettings(BaseSettings):
    """Postgres connection settings, shared by every service and by Alembic.

    Deliberately not derived from `fraudguard_common.BaseServiceSettings`:
    which database to connect to is orthogonal to which service is running,
    so this composes alongside a service's own settings rather than
    requiring one.
    """

    model_config = SettingsConfigDict(
        env_file=None, extra="ignore", case_sensitive=False
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "fraudguard"
    postgres_password: str = "fraudguard"  # noqa: S105 -- local-dev default, not a secret
    postgres_db: str = "fraudguard"

    @property
    def async_dsn(self) -> str:
        """For application runtime: SQLAlchemy's asyncio engine over asyncpg."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_dsn(self) -> str:
        """For Alembic only. See ADR-0005 for why migrations use a sync driver."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


class LocalDatabaseSettings(DatabaseSettings):
    """Reads `.env` for local entry points only -- never inside a container
    image, where configuration must come from real environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


class Database:
    """Owns one async engine and hands out sessions from it.

    A thin wrapper, not a repository layer -- FraudGuard services query
    SQLAlchemy directly. This exists so application startup/shutdown has a
    single object to create and dispose, and so a readiness probe has one
    `ping()` to call rather than reaching into engine internals itself.
    """

    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self.settings = settings or DatabaseSettings()
        self.engine: AsyncEngine = create_async_engine(
            self.settings.async_dsn, pool_pre_ping=True
        )
        self._session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session

    async def ping(self) -> None:
        """Raise if Postgres is unreachable. Used by readiness probes."""
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()
