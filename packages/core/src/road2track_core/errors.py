"""Exceptions métier du domaine Road2Track.

Une exception par cas métier (cf. CLAUDE.md §3.4).
"""

from __future__ import annotations


class Road2TrackError(Exception):
    """Base de toutes les exceptions du domaine."""


class ProjectNotFoundError(Road2TrackError):
    def __init__(self, project_id: str) -> None:
        super().__init__(f"Project not found: {project_id}")
        self.project_id = project_id


class InvalidSegmentError(Road2TrackError):
    """Segment invalide (structure de capture incorrecte, fichiers manquants, ...)."""


class SegmentNotFoundError(Road2TrackError):
    def __init__(self, segment_id: str) -> None:
        super().__init__(f"Segment not found: {segment_id}")
        self.segment_id = segment_id


class StorageError(Road2TrackError):
    """Erreur d'accès au stockage objet (MinIO / S3)."""


class HealthCheckError(Road2TrackError):
    """Un health check critique a échoué au démarrage d'un service."""
