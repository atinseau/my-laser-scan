"""Repositories Postgres concrets.

Chaque classe implémente le Protocol correspondant dans
`road2track_core.ports.repository_port` (cf. specs/02-architecture.md §5.3).
"""

from road2track_storage.repositories.project_repo import PostgresProjectRepository
from road2track_storage.repositories.segment_repo import PostgresSegmentRepository

__all__ = ["PostgresProjectRepository", "PostgresSegmentRepository"]
