"""Port d'accès au stockage objet (MinIO / S3-compatible).

Le port est défini ici pour que le pipeline et les activités puissent en dépendre
sans se coupler à une implémentation concrète. L'adapter vit dans
`packages/storage/src/road2track_storage/object/minio_adapter.py`.

Cf. specs/02-architecture.md §5.1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ObjectStoragePort(Protocol):
    """Interface minimale pour un stockage objet S3-compatible."""

    async def upload_directory(
        self, local_dir: Path, bucket: str, key_prefix: str
    ) -> tuple[int, int]:
        """Upload récursif d'un dossier local. Retourne (file_count, total_bytes)."""

    async def upload_file(self, local_path: Path, bucket: str, key: str) -> int:
        """Upload d'un fichier. Retourne la taille uploadée en bytes."""

    async def ensure_bucket(self, bucket: str) -> None:
        """Crée le bucket s'il n'existe pas (idempotent)."""
