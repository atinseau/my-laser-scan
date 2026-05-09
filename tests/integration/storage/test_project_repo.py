"""Tests d'intégration sur PostgresProjectRepository (SQLite in-memory)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from road2track_core.entities.project import Project, ProjectStatus
from road2track_core.entities.track_kind import TrackKind
from road2track_core.ids import new_project_id
from road2track_core.value_objects.gps import GPSCoord
from road2track_storage.repositories import PostgresProjectRepository
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_then_get(session: AsyncSession) -> None:
    repo = PostgresProjectRepository(session)
    pid = new_project_id()
    now = datetime.now(tz=UTC)
    project = Project(id=pid, name="Test", created_at=now, updated_at=now)
    await repo.create(project)
    await session.commit()

    fetched = await repo.get(pid)
    assert fetched is not None
    assert fetched.id == pid
    assert fetched.name == "Test"
    assert fetched.status == ProjectStatus.DRAFT
    assert fetched.kind is None
    assert fetched.origin_wgs84 is None


@pytest.mark.asyncio
async def test_create_with_kind_and_origin(session: AsyncSession) -> None:
    repo = PostgresProjectRepository(session)
    pid = new_project_id()
    now = datetime.now(tz=UTC)
    project = Project(
        id=pid,
        name="Galibier",
        created_at=now,
        updated_at=now,
        status=ProjectStatus.READY,
        kind=TrackKind.SPECIALE,
        origin_wgs84=GPSCoord(lat=45.064, lon=6.408, alt=2645.0),
    )
    await repo.create(project)
    await session.commit()

    fetched = await repo.get(pid)
    assert fetched is not None
    assert fetched.kind == TrackKind.SPECIALE
    assert fetched.origin_wgs84 is not None
    assert fetched.origin_wgs84.alt == 2645.0


@pytest.mark.asyncio
async def test_get_unknown_returns_none(session: AsyncSession) -> None:
    repo = PostgresProjectRepository(session)
    assert await repo.get("unknown") is None


@pytest.mark.asyncio
async def test_update_status_persists(session: AsyncSession) -> None:
    repo = PostgresProjectRepository(session)
    pid = new_project_id()
    now = datetime.now(tz=UTC)
    await repo.create(Project(id=pid, name="X", created_at=now, updated_at=now))
    await session.commit()

    await repo.update_status(pid, ProjectStatus.PROCESSING)
    await session.commit()

    fetched = await repo.get(pid)
    assert fetched is not None
    assert fetched.status == ProjectStatus.PROCESSING


@pytest.mark.asyncio
async def test_update_workflow_id(session: AsyncSession) -> None:
    repo = PostgresProjectRepository(session)
    pid = new_project_id()
    now = datetime.now(tz=UTC)
    await repo.create(Project(id=pid, name="X", created_at=now, updated_at=now))
    await session.commit()

    await repo.update_workflow_id(pid, "wf-42")
    await session.commit()

    fetched = await repo.get(pid)
    assert fetched is not None
    assert fetched.current_workflow_id == "wf-42"


@pytest.mark.asyncio
async def test_update_status_unknown_id_is_noop(session: AsyncSession) -> None:
    repo = PostgresProjectRepository(session)
    # Doit ne pas lever
    await repo.update_status("unknown", ProjectStatus.READY)
