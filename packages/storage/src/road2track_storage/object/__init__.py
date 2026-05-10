"""Adapters de stockage objet (MinIO + filesystem local pour les tests).

Cf. specs/02-architecture.md §4.4.
"""

from road2track_storage.object.minio_adapter import MinioObjectStorage

__all__ = ["MinioObjectStorage"]
