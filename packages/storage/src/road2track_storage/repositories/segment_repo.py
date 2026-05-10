"""`PostgresSegmentRepository` — implémente `SegmentRepository` (port)."""

from __future__ import annotations

from datetime import UTC, datetime

from road2track_core.entities.segment import Segment, SegmentSource
from road2track_core.ids import ProjectId, SegmentId
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from road2track_storage.relational.models import SegmentRow


def _row_to_entity(row: SegmentRow) -> Segment:
    return Segment(
        id=row.id,
        project_id=row.project_id,
        source=SegmentSource(row.source),
        captured_at=row.captured_at,
        duration_s=row.duration_s,
        raw_paths=dict(row.raw_paths) if row.raw_paths else {},
        fps=row.fps,
        resolution=(row.width, row.height),
        has_lidar=row.has_lidar,
        notes=row.notes,
    )


class PostgresSegmentRepository:
    """Implémente `road2track_core.ports.SegmentRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, segment: Segment) -> None:
        row = SegmentRow(
            id=segment.id,
            project_id=segment.project_id,
            source=segment.source.value,
            captured_at=segment.captured_at,
            duration_s=segment.duration_s,
            fps=segment.fps,
            width=segment.resolution[0],
            height=segment.resolution[1],
            has_lidar=segment.has_lidar,
            raw_paths=dict(segment.raw_paths),
            notes=segment.notes,
            metadata_json={},
            created_at=datetime.now(tz=UTC),
        )
        self._session.add(row)
        await self._session.flush()

    async def get(self, segment_id: SegmentId) -> Segment | None:
        result = await self._session.execute(
            select(SegmentRow).where(SegmentRow.id == segment_id)
        )
        row = result.scalar_one_or_none()
        return _row_to_entity(row) if row else None

    async def list_for_project(self, project_id: ProjectId) -> list[Segment]:
        result = await self._session.execute(
            select(SegmentRow)
            .where(SegmentRow.project_id == project_id)
            .order_by(SegmentRow.captured_at)
        )
        return [_row_to_entity(row) for row in result.scalars()]
