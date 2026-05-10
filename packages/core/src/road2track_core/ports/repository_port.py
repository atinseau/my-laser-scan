"""Ports (interfaces) des repositories du domaine.

Les implémentations concrètes vivent dans `packages/storage/src/road2track_storage/repositories/`.
Le code applicatif (pipeline activities) ne dépend que de ces Protocols.

Cf. specs/02-architecture.md §4.4 et §5.3.
"""

from __future__ import annotations

from typing import Protocol

from road2track_core.entities.project import Project, ProjectStatus
from road2track_core.entities.segment import Segment
from road2track_core.ids import ProjectId, SegmentId


class ProjectRepository(Protocol):
    """Persistance des entités `Project`."""

    async def create(self, project: Project) -> None: ...

    async def get(self, project_id: ProjectId) -> Project | None: ...

    async def update_status(self, project_id: ProjectId, status: ProjectStatus) -> None: ...

    async def update_workflow_id(
        self, project_id: ProjectId, workflow_id: str | None
    ) -> None: ...


class SegmentRepository(Protocol):
    """Persistance des entités `Segment`."""

    async def create(self, segment: Segment) -> None: ...

    async def get(self, segment_id: SegmentId) -> Segment | None: ...

    async def list_for_project(self, project_id: ProjectId) -> list[Segment]: ...
