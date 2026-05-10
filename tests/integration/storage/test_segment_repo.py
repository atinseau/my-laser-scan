"""Tests d'intégration sur PostgresSegmentRepository (SQLite in-memory)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from road2track_core.entities.project import Project
from road2track_core.entities.segment import Segment, SegmentSource
from road2track_core.ids import new_project_id, new_segment_id
from road2track_storage.repositories import (
    PostgresProjectRepository,
    PostgresSegmentRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _create_project(session: AsyncSession) -> str:
    pid = new_project_id()
    repo = PostgresProjectRepository(session)
    await repo.create(Project(id=pid, name="P", created_at=_now(), updated_at=_now()))
    await session.commit()
    return pid


@pytest.mark.asyncio
async def test_create_then_get(session: AsyncSession) -> None:
    pid = await _create_project(session)
    repo = PostgresSegmentRepository(session)
    sid = new_segment_id()
    await repo.create(
        Segment(
            id=sid,
            project_id=pid,
            source=SegmentSource.RECORD_3D_PLUS_SENSOR_LOGGER,
            captured_at=_now(),
            duration_s=42.5,
            fps=60.0,
            resolution=(3840, 2160),
            raw_paths={"video": "s3://raw/foo/bar/video.mp4"},
        )
    )
    await session.commit()

    fetched = await repo.get(sid)
    assert fetched is not None
    assert fetched.id == sid
    assert fetched.project_id == pid
    assert fetched.source == SegmentSource.RECORD_3D_PLUS_SENSOR_LOGGER
    assert fetched.duration_s == 42.5
    assert fetched.resolution == (3840, 2160)
    assert fetched.raw_paths["video"].endswith("video.mp4")


@pytest.mark.asyncio
async def test_list_for_project_orders_by_captured_at(session: AsyncSession) -> None:
    pid = await _create_project(session)
    repo = PostgresSegmentRepository(session)

    early = _now()
    late = datetime(2099, 1, 1, tzinfo=UTC)

    sid_late = new_segment_id()
    await repo.create(
        Segment(
            id=sid_late,
            project_id=pid,
            source=SegmentSource.RECORD_3D_PLUS_SENSOR_LOGGER,
            captured_at=late,
            duration_s=10.0,
        )
    )
    sid_early = new_segment_id()
    await repo.create(
        Segment(
            id=sid_early,
            project_id=pid,
            source=SegmentSource.RECORD_3D_PLUS_SENSOR_LOGGER,
            captured_at=early,
            duration_s=10.0,
        )
    )
    await session.commit()

    segments = await repo.list_for_project(pid)
    assert [s.id for s in segments] == [sid_early, sid_late]


@pytest.mark.asyncio
async def test_get_unknown_returns_none(session: AsyncSession) -> None:
    repo = PostgresSegmentRepository(session)
    assert await repo.get("unknown") is None
