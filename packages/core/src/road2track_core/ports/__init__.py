"""Ports (interfaces abstraites) du domaine.

Les adapters concrets vivent dans storage/, ml/, ac_export/, cloud_bridge/.
Cf. specs/02-architecture.md §5.1.
"""

from road2track_core.ports.object_storage_port import ObjectStoragePort
from road2track_core.ports.repository_port import ProjectRepository, SegmentRepository

__all__ = ["ObjectStoragePort", "ProjectRepository", "SegmentRepository"]
