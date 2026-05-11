"""Activité Temporal : `ingest_session`.

Étape 1 du pipeline (cf. specs/04-pipeline-ml.md §2.1) :
1. Validation du contenu Record3D + Sensor Logger.                         ✓
2. Synchronisation timestamps UTC + fallback cross-corrélation IMU/ARKit.   ✓ (ADR-017)
3. Vérification de cohérence temporelle.                                    ✓
4. Extraction des métadonnées (durée, FPS, résolution, codec).              ✓
5. Drop du track audio (re-mux sans ré-encodage, ~10% de gain).             ✓
6. Upload des fichiers bruts vers MinIO sous `s3://raw/<project_id>/<segment_id>/` (avec
   substitution de la vidéo originale par sa version sans audio).            ✓
7. Persistance Postgres : auto-create du Project si nouveau, puis insert Segment. ✓
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import structlog
from road2track_core.config import Settings
from road2track_core.entities.project import Project, ProjectStatus
from road2track_core.entities.refs import IngestInput, SegmentRef, VideoMetadata
from road2track_core.entities.segment import Segment, SegmentSource
from road2track_core.errors import InvalidSegmentError
from road2track_core.ids import new_segment_id
from road2track_geo.fusion.sync import compute_sync
from road2track_storage.object.minio_adapter import MinioObjectStorage
from road2track_storage.relational.session import (
    create_async_engine_from_settings,
    create_session_factory,
)
from road2track_storage.repositories import (
    PostgresProjectRepository,
    PostgresSegmentRepository,
)
from temporalio import activity

from road2track_pipeline.activities._capture_parsers import (
    find_imu_file,
    parse_record3d_poses,
    parse_sensor_logger_imu,
)
from road2track_pipeline.activities._video import (
    drop_audio_track,
    find_video_file,
    probe_video,
)

logger = structlog.get_logger(__name__)

# Fichiers minimaux exigés dans la capture pour la considérer valide au POC.
REQUIRED_PATHS: tuple[str, ...] = (
    "record3d/poses.json",
    "sensor_logger/gps.json",
)


def _validate_capture_dir(local_dir: Path) -> None:
    if not local_dir.is_dir():
        raise InvalidSegmentError(f"capture directory not found: {local_dir}")

    missing: list[str] = [rel for rel in REQUIRED_PATHS if not (local_dir / rel).is_file()]
    if missing:
        raise InvalidSegmentError(f"missing required files in {local_dir}: {', '.join(missing)}")


async def _upload_capture(
    storage: MinioObjectStorage,
    local_dir: Path,
    bucket: str,
    key_prefix: str,
    overrides: dict[Path, Path],
) -> tuple[int, int]:
    """Upload récursif avec substitution optionnelle de fichiers (ex. vidéo sans audio)."""
    await storage.ensure_bucket(bucket)
    prefix = key_prefix.rstrip("/")

    file_count = 0
    total_bytes = 0
    for path in local_dir.rglob("*"):
        if not path.is_file():
            continue
        actual = overrides.get(path, path)
        relative = path.relative_to(local_dir).as_posix()
        key = f"{prefix}/{relative}"
        total_bytes += await storage.upload_file(actual, bucket, key)
        file_count += 1
    return file_count, total_bytes


@activity.defn(name="ingest_session")
async def ingest_session(payload: IngestInput) -> SegmentRef:
    """Valide la capture, probe la vidéo, drop l'audio, upload sur MinIO."""
    settings = Settings()
    local_dir = Path(payload.local_dir).resolve()
    segment_id = payload.segment_id or new_segment_id()

    structlog.contextvars.bind_contextvars(
        project_id=payload.project_id,
        segment_id=segment_id,
        activity_name="ingest_session",
    )
    logger.info("ingest_session start", local_dir=str(local_dir))

    # 1. Validation
    _validate_capture_dir(local_dir)
    logger.info("capture validated", required_paths=list(REQUIRED_PATHS))

    # 2 + 3. Synchronisation Record3D ARKit ↔ Sensor Logger IMU (cf. ADR-017).
    poses_path = local_dir / "record3d" / "poses.json"
    imu_path = find_imu_file(local_dir)
    arkit_t, arkit_pos, _arkit_quat = parse_record3d_poses(poses_path)
    imu_t, imu_acc = parse_sensor_logger_imu(imu_path)
    sync = compute_sync(arkit_t, arkit_pos, imu_t, imu_acc)
    logger.info(
        "sync computed",
        method=sync.method,
        drift_ms=sync.drift_ms,
        offset_applied_ms=sync.offset_applied_ms,
        correlation_max=sync.correlation_max,
    )
    if sync.warning:
        logger.warning("sync warning", warning=sync.warning)

    # 4. Métadonnées vidéo
    video_path = find_video_file(local_dir)
    probe = await probe_video(video_path)
    logger.info(
        "video probed",
        duration_s=probe.duration_s,
        fps=probe.fps,
        resolution=(probe.width, probe.height),
        codec=probe.codec,
        has_audio=probe.has_audio,
        bytes_size=probe.bytes_size,
    )

    # 5. Drop audio (si nécessaire)
    bytes_after = probe.bytes_size
    overrides: dict[Path, Path] = {}
    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    bucket = settings.minio_bucket_raw
    key_prefix = f"{payload.project_id}/{segment_id}"

    with tempfile.TemporaryDirectory(prefix="r2t-ingest-") as tmpdir:
        if probe.has_audio:
            stripped = Path(tmpdir) / video_path.name
            bytes_after = await drop_audio_track(video_path, stripped)
            overrides[video_path] = stripped
            logger.info(
                "audio dropped",
                bytes_before=probe.bytes_size,
                bytes_after=bytes_after,
                saved=probe.bytes_size - bytes_after,
            )
        else:
            logger.info("no audio track to drop")

        # 6. Upload (avec swap vidéo)
        file_count, total_bytes = await _upload_capture(
            storage=storage,
            local_dir=local_dir,
            bucket=bucket,
            key_prefix=key_prefix,
            overrides=overrides,
        )

    raw_uri_prefix = f"s3://{bucket}/{key_prefix}/"
    video_metadata = VideoMetadata(
        duration_s=probe.duration_s,
        fps=probe.fps,
        width=probe.width,
        height=probe.height,
        codec=probe.codec,
        had_audio=probe.has_audio,
        bytes_before_audio_drop=probe.bytes_size,
        bytes_after_audio_drop=bytes_after,
    )

    # 7. Persistance Postgres : auto-create Project si premier segment, puis insert Segment.
    engine = create_async_engine_from_settings(settings)
    session_factory = create_session_factory(engine)
    raw_paths_dict = {
        "raw_uri_prefix": raw_uri_prefix,
        "video_codec": probe.codec,
    }
    try:
        async with session_factory() as session, session.begin():
            project_repo = PostgresProjectRepository(session)
            existing = await project_repo.get(payload.project_id)
            now = datetime.now(tz=UTC)
            if existing is None:
                await project_repo.create(
                    Project(
                        id=payload.project_id,
                        name=f"Auto — {payload.project_id[:8]}",
                        created_at=now,
                        updated_at=now,
                        status=ProjectStatus.CAPTURING,
                    )
                )
                logger.info("project auto-created", project_id=payload.project_id)
            else:
                await project_repo.update_status(payload.project_id, ProjectStatus.CAPTURING)

            segment_repo = PostgresSegmentRepository(session)
            await segment_repo.create(
                Segment(
                    id=segment_id,
                    project_id=payload.project_id,
                    source=SegmentSource.RECORD_3D_PLUS_SENSOR_LOGGER,
                    captured_at=now,
                    duration_s=probe.duration_s,
                    raw_paths=raw_paths_dict,
                    fps=probe.fps,
                    resolution=(probe.width, probe.height),
                    has_lidar=True,
                )
            )
            logger.info("segment persisted", segment_id=segment_id)
    finally:
        await engine.dispose()

    ref = SegmentRef(
        project_id=payload.project_id,
        segment_id=segment_id,
        raw_uri_prefix=raw_uri_prefix,
        file_count=file_count,
        total_bytes=total_bytes,
        video=video_metadata,
        sync=sync,
    )
    logger.info(
        "ingest_session done",
        file_count=file_count,
        total_bytes=total_bytes,
        raw_uri_prefix=raw_uri_prefix,
    )
    return ref
