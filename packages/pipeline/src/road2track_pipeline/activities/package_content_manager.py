"""Activité Temporal : `package_content_manager` (étape B5 d'It. 1).

Pipeline :
1. DL surfaces.ini + models.ini + ui_track.json + fast_lane.ai + track.kn5.
2. Génère une miniature placeholder.
3. Empaquette en zip CM avec layout `content/tracks/<track_id>/...`.
4. Upload sur MinIO bucket `outputs/<p>/<s>/ac/<track_id>.zip`.
5. Retourne `TrackPackageRef`.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import structlog
from road2track_ac_export.packaging import build_content_manager_package
from road2track_core.config import Settings
from road2track_core.entities.refs import (
    PackageContentManagerInput,
    TrackPackageRef,
)
from road2track_core.errors import InvalidSegmentError
from road2track_storage.object.minio_adapter import MinioObjectStorage
from temporalio import activity

logger = structlog.get_logger(__name__)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise InvalidSegmentError(f"URI S3 invalide: {uri}")
    rest = uri[len("s3://") :]
    if "/" not in rest:
        raise InvalidSegmentError(f"URI S3 sans clé: {uri}")
    bucket, key = rest.split("/", 1)
    return bucket, key


@activity.defn(name="package_content_manager")
async def package_content_manager(
    payload: PackageContentManagerInput,
) -> TrackPackageRef:
    """DL inputs → build zip CM → upload → TrackPackageRef."""
    settings = Settings()
    project_id = payload.project_id
    segment_id = payload.segment_id

    structlog.contextvars.bind_contextvars(
        project_id=project_id,
        segment_id=segment_id,
        activity_name="package_content_manager",
    )
    logger.info("package_content_manager start", track_name=payload.track_name)

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    outputs_bucket = settings.minio_bucket_outputs

    sb, sk = _parse_s3_uri(payload.ac_files.surfaces_ini_uri)
    mb, mk = _parse_s3_uri(payload.ac_files.models_ini_uri)
    ub, uk = _parse_s3_uri(payload.ac_files.ui_track_json_uri)
    kb, kk = _parse_s3_uri(payload.kn5.kn5_uri)
    ab, ak = _parse_s3_uri(payload.ai_line.fast_lane_uri)

    with tempfile.TemporaryDirectory(prefix="r2t-package-") as tmpdir:
        local_dir = Path(tmpdir)
        surfaces_local = local_dir / "surfaces.ini"
        models_local = local_dir / "models.ini"
        ui_local = local_dir / "ui_track.json"
        kn5_local = local_dir / "track.kn5"
        ai_local = local_dir / "fast_lane.ai"
        zip_local = local_dir / "package.zip"

        await asyncio.gather(
            storage.download_file(sb, sk, surfaces_local),
            storage.download_file(mb, mk, models_local),
            storage.download_file(ub, uk, ui_local),
            storage.download_file(kb, kk, kn5_local),
            storage.download_file(ab, ak, ai_local),
        )
        logger.info("inputs downloaded")

        def _build() -> tuple[Path, str, int]:
            result = build_content_manager_package(
                zip_local,
                track_name=payload.track_name,
                surfaces_ini=surfaces_local,
                models_ini=models_local,
                ui_track_json=ui_local,
                kn5=kn5_local,
                fast_lane_ai=ai_local,
            )
            return result.zip_path, result.track_id, result.bytes_size

        zip_path, track_id, bytes_size = await asyncio.to_thread(_build)
        logger.info(
            "package built",
            track_id=track_id,
            bytes_size=bytes_size,
        )

        package_key = f"{project_id}/{segment_id}/ac/{track_id}.zip"
        await storage.upload_file(zip_path, outputs_bucket, package_key)

    package_uri = f"s3://{outputs_bucket}/{package_key}"
    ref = TrackPackageRef(
        project_id=project_id,
        segment_id=segment_id,
        package_uri=package_uri,
        track_name=payload.track_name,
        bytes_size=bytes_size,
    )
    logger.info(
        "package_content_manager done",
        package_uri=package_uri,
        track_id=track_id,
        bytes_size=bytes_size,
    )
    return ref
