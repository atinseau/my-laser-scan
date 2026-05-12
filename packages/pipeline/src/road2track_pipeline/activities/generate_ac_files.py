"""Activité Temporal : `generate_ac_files` (étape It. 1).

Génère les fichiers de configuration Assetto Corsa (`surfaces.ini`,
`models.ini`, `ui/ui_track.json`) à partir de la trajectoire détectée et des
métadonnées de track. Upload sur MinIO.

Pure CPU + Jinja, pas de dépendance lourde.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from road2track_ac_export import render_all_ac_files
from road2track_core.config import Settings
from road2track_core.entities.refs import AcFilesRef, ExportAcInput
from road2track_storage.object.minio_adapter import MinioObjectStorage
from temporalio import activity

logger = structlog.get_logger(__name__)


@activity.defn(name="generate_ac_files")
async def generate_ac_files(payload: ExportAcInput) -> AcFilesRef:
    """Rend les 3 fichiers AC + upload sur MinIO."""
    settings = Settings()
    project_id = payload.project_id
    segment_id = payload.segment_id

    structlog.contextvars.bind_contextvars(
        project_id=project_id,
        segment_id=segment_id,
        activity_name="generate_ac_files",
    )
    logger.info(
        "generate_ac_files start",
        track_name=payload.track_name,
        track_kind=payload.detected.track_kind.value,
    )

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    outputs_bucket = settings.minio_bucket_outputs

    with tempfile.TemporaryDirectory(prefix="r2t-ac-files-") as tmpdir:
        output_dir = Path(tmpdir)
        result = render_all_ac_files(
            output_dir,
            track_name=payload.track_name,
            track_kind=payload.detected.track_kind.value,
            length_m=payload.detected.arc_length_m,
            description=payload.description,
            country=payload.country,
            track_author=payload.track_author,
        )

        prefix = f"{project_id}/{segment_id}/ac"
        surfaces_key = f"{prefix}/surfaces.ini"
        models_key = f"{prefix}/models.ini"
        ui_key = f"{prefix}/ui/ui_track.json"

        await storage.ensure_bucket(outputs_bucket)
        await storage.upload_file(result.surfaces_ini_path, outputs_bucket, surfaces_key)
        await storage.upload_file(result.models_ini_path, outputs_bucket, models_key)
        await storage.upload_file(result.ui_track_json_path, outputs_bucket, ui_key)

    surfaces_uri = f"s3://{outputs_bucket}/{surfaces_key}"
    models_uri = f"s3://{outputs_bucket}/{models_key}"
    ui_uri = f"s3://{outputs_bucket}/{ui_key}"

    ref = AcFilesRef(
        project_id=project_id,
        segment_id=segment_id,
        surfaces_ini_uri=surfaces_uri,
        models_ini_uri=models_uri,
        ui_track_json_uri=ui_uri,
    )
    logger.info(
        "generate_ac_files done",
        surfaces=surfaces_uri,
        models=models_uri,
        ui=ui_uri,
    )
    return ref
