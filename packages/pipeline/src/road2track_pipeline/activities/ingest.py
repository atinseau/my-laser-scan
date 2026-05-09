"""Activité Temporal : `ingest_session`.

Étape 1 du pipeline (cf. specs/04-pipeline-ml.md §2.1) :
1. Validation du contenu Record3D + Sensor Logger.
2. Synchronisation timestamps UTC + fallback cross-corrélation IMU/ARKit (TODO It. 0).
3. Vérification de cohérence temporelle.
4. Extraction des métadonnées de base.
5. Drop du track audio (TODO It. 0).
6. Upload des fichiers bruts vers MinIO sous `s3://raw/<project_id>/<segment_id>/`.
7. Insertion d'une entrée Segment en Postgres (TODO It. 0).

Au bootstrap minimal, on fait : validation structure + upload directory.
Les étapes 2/3/5/7 viennent au fur et à mesure des prochains commits de l'It. 0.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from road2track_core.config import Settings
from road2track_core.entities.refs import IngestInput, SegmentRef
from road2track_core.errors import InvalidSegmentError
from road2track_core.ids import new_segment_id
from road2track_storage.object.minio_adapter import MinioObjectStorage
from temporalio import activity

logger = structlog.get_logger(__name__)

# Fichiers minimaux exigés dans la capture pour la considérer valide au POC.
REQUIRED_PATHS: tuple[str, ...] = (
    "record3d/poses.json",
    "sensor_logger/gps.json",
)


def _validate_capture_dir(local_dir: Path) -> None:
    if not local_dir.is_dir():
        raise InvalidSegmentError(f"capture directory not found: {local_dir}")

    missing: list[str] = [
        rel for rel in REQUIRED_PATHS if not (local_dir / rel).is_file()
    ]
    if missing:
        raise InvalidSegmentError(
            f"missing required files in {local_dir}: {', '.join(missing)}"
        )


@activity.defn(name="ingest_session")
async def ingest_session(payload: IngestInput) -> SegmentRef:
    """Valide la capture, l'upload sur MinIO, retourne une SegmentRef."""
    settings = Settings()
    local_dir = Path(payload.local_dir).resolve()
    segment_id = payload.segment_id or new_segment_id()

    structlog.contextvars.bind_contextvars(
        project_id=payload.project_id,
        segment_id=segment_id,
        activity_name="ingest_session",
    )
    logger.info("ingest_session start", local_dir=str(local_dir))

    _validate_capture_dir(local_dir)
    logger.info("capture validated", required_paths=list(REQUIRED_PATHS))

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    bucket = settings.minio_bucket_raw
    key_prefix = f"{payload.project_id}/{segment_id}"
    file_count, total_bytes = await storage.upload_directory(
        local_dir=local_dir,
        bucket=bucket,
        key_prefix=key_prefix,
    )

    raw_uri_prefix = f"s3://{bucket}/{key_prefix}/"
    ref = SegmentRef(
        project_id=payload.project_id,
        segment_id=segment_id,
        raw_uri_prefix=raw_uri_prefix,
        file_count=file_count,
        total_bytes=total_bytes,
    )
    logger.info(
        "ingest_session done",
        file_count=file_count,
        total_bytes=total_bytes,
        raw_uri_prefix=raw_uri_prefix,
    )
    return ref
