"""Async engine + session factory SQLAlchemy 2.

Le DSN par défaut est construit à partir des Settings (Postgres applicatif).
Pour les tests, on peut injecter un DSN SQLite in-memory.
"""

from __future__ import annotations

from road2track_core.config import Settings
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _to_async_dsn(dsn: str) -> str:
    """Convertit un DSN sync en DSN async (Postgres asyncpg, SQLite aiosqlite)."""
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    if dsn.startswith("sqlite://"):
        return dsn.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return dsn


def create_async_engine_from_settings(settings: Settings | None = None) -> AsyncEngine:
    settings = settings or Settings()
    dsn = _to_async_dsn(settings.postgres_dsn)
    return create_async_engine(dsn, echo=False, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
