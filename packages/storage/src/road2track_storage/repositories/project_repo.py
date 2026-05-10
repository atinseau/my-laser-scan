"""`PostgresProjectRepository` — implémente `ProjectRepository` (port)."""

from __future__ import annotations

from road2track_core.entities.project import Project, ProjectStatus
from road2track_core.entities.track_kind import TrackKind
from road2track_core.ids import ProjectId
from road2track_core.value_objects.gps import GPSCoord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from road2track_storage.relational.models import ProjectRow


def _row_to_entity(row: ProjectRow) -> Project:
    origin: GPSCoord | None = None
    if row.origin_lat is not None and row.origin_lon is not None and row.origin_alt is not None:
        origin = GPSCoord(lat=row.origin_lat, lon=row.origin_lon, alt=row.origin_alt)
    kind = TrackKind(row.kind) if row.kind else None
    return Project(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        updated_at=row.updated_at,
        status=ProjectStatus(row.status),
        kind=kind,
        origin_wgs84=origin,
        current_workflow_id=row.current_workflow_id,
        notes=row.notes,
    )


class PostgresProjectRepository:
    """Implémente `road2track_core.ports.ProjectRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, project: Project) -> None:
        row = ProjectRow(
            id=project.id,
            name=project.name,
            status=project.status.value,
            kind=project.kind.value if project.kind else None,
            origin_lat=project.origin_wgs84.lat if project.origin_wgs84 else None,
            origin_lon=project.origin_wgs84.lon if project.origin_wgs84 else None,
            origin_alt=project.origin_wgs84.alt if project.origin_wgs84 else None,
            current_workflow_id=project.current_workflow_id,
            notes=project.notes,
            metadata_json={},
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
        self._session.add(row)
        await self._session.flush()

    async def get(self, project_id: ProjectId) -> Project | None:
        result = await self._session.execute(
            select(ProjectRow).where(ProjectRow.id == project_id)
        )
        row = result.scalar_one_or_none()
        return _row_to_entity(row) if row else None

    async def update_status(self, project_id: ProjectId, status: ProjectStatus) -> None:
        row = await self._session.get(ProjectRow, project_id)
        if row is None:
            return
        row.status = status.value
        await self._session.flush()

    async def update_workflow_id(
        self, project_id: ProjectId, workflow_id: str | None
    ) -> None:
        row = await self._session.get(ProjectRow, project_id)
        if row is None:
            return
        row.current_workflow_id = workflow_id
        await self._session.flush()
