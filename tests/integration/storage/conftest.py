"""Fixtures pour les tests d'intégration storage.

On utilise SQLite in-memory + aiosqlite pour des tests rapides et déterministes,
sans Docker. Les tests Postgres "vrais" (testcontainers) viendront en CI quand
on aura besoin de tester les spécificités JSONB / TIMESTAMPTZ.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from road2track_storage.relational.models import Base
from road2track_storage.relational.session import create_session_factory
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as s:
        yield s
