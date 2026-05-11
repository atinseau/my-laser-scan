"""Activité Temporal : `select_keyframes`.

Étape 3.1 du pipeline (cf. specs/04-pipeline-ml.md §3.1) — exécutée sur la queue
`cpu` (sélection légère, pas de GPU).

POC simplifié :
1. Télécharge la trajectoire tronquée + la vidéo Record3D.
2. Sélection par **diversité spatiale** : 1 frame tous les `min_spacing_m` mètres
   de motion (greedy le long de la trajectoire ENU).
3. Pour chaque pose retenue, calcule le temps vidéo (= t_pose − t_premier_frame
   ARKit) et extrait la frame JPEG correspondante via ffmpeg.
4. Upload les JPEG + un manifest `keyframes.json` sur MinIO.

TODOs explicites (raffinements V1) :
- Filtre netteté (variance Laplacien) — nécessite OpenCV, à introduire dans `ml/`.
- Filtre diversité angulaire (anti-redondance d'orientation).
- Batch extraction via filtre ffmpeg `select=` au lieu de N seeks.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import structlog
from numpy.typing import NDArray
from road2track_core.config import Settings
from road2track_core.entities.refs import KeyframesRef, SelectKeyframesInput
from road2track_core.errors import InvalidSegmentError
from road2track_geo.sampling import DEFAULT_MIN_SPACING_M, select_indices_by_spacing
from road2track_storage.object.minio_adapter import MinioObjectStorage
from temporalio import activity

from road2track_pipeline.activities._video import extract_frame_at_time

logger = structlog.get_logger(__name__)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise InvalidSegmentError(f"URI S3 invalide: {uri}")
    rest = uri[len("s3://") :]
    if "/" not in rest:
        raise InvalidSegmentError(f"URI S3 sans clé: {uri}")
    bucket, key = rest.split("/", 1)
    return bucket, key


def _arc_length_at_indices(
    positions: NDArray[np.float64], indices: NDArray[np.int64]
) -> float:
    if indices.size < 2:
        return 0.0
    selected: NDArray[np.float64] = positions[indices]
    diffs = np.diff(selected, axis=0)
    return float(np.linalg.norm(diffs, axis=1).sum())


@activity.defn(name="select_keyframes")
async def select_keyframes(payload: SelectKeyframesInput) -> KeyframesRef:
    """Sélectionne les keyframes par diversité spatiale + extrait les JPEG."""
    settings = Settings()
    project_id = payload.segment.project_id
    segment_id = payload.segment.segment_id

    structlog.contextvars.bind_contextvars(
        project_id=project_id,
        segment_id=segment_id,
        activity_name="select_keyframes",
    )
    logger.info(
        "select_keyframes start",
        trimmed_trajectory_uri=payload.detected.trimmed_trajectory_uri,
        raw_uri_prefix=payload.segment.raw_uri_prefix,
    )

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    raw_bucket = settings.minio_bucket_raw
    intermediates_bucket = settings.minio_bucket_intermediates
    raw_prefix = f"{project_id}/{segment_id}"
    inter_prefix = f"{project_id}/{segment_id}"

    traj_bucket, traj_key = _parse_s3_uri(payload.detected.trimmed_trajectory_uri)

    with tempfile.TemporaryDirectory(prefix="r2t-keyframes-") as tmpdir:
        local_dir = Path(tmpdir)
        traj_local = local_dir / "trajectory_trimmed.json"
        video_local = local_dir / "video.mp4"
        frames_local = local_dir / "keyframes"
        frames_local.mkdir(parents=True, exist_ok=True)

        await storage.download_file(traj_bucket, traj_key, traj_local)
        await storage.download_file(
            raw_bucket, f"{raw_prefix}/record3d/video.mp4", video_local
        )
        logger.info("inputs downloaded")

        trajectory: dict[str, Any] = json.loads(traj_local.read_text(encoding="utf-8"))
        samples: list[dict[str, Any]] = trajectory.get("samples", [])
        if not samples:
            raise InvalidSegmentError(
                "trajectoire tronquée vide pour select_keyframes"
            )

        times = np.asarray([s["t"] for s in samples], dtype=np.float64)
        positions = np.asarray([s["pos"] for s in samples], dtype=np.float64)
        quaternions = np.asarray([s["quat"] for s in samples], dtype=np.float64)

        indices = select_indices_by_spacing(
            positions, min_spacing_m=DEFAULT_MIN_SPACING_M
        )
        if indices.size == 0:
            raise InvalidSegmentError(
                "aucune keyframe sélectionnée (trajectoire vide ou trop courte)"
            )

        video_start_t = float(times[0])
        keyframe_entries: list[dict[str, Any]] = []
        total_bytes = 0
        for kf_idx, traj_idx in enumerate(indices.tolist()):
            video_t = float(times[traj_idx]) - video_start_t
            image_name = f"{kf_idx:04d}.jpg"
            local_image = frames_local / image_name
            size = await extract_frame_at_time(video_local, video_t, local_image)
            total_bytes += size
            entry: dict[str, Any] = {
                "idx": kf_idx,
                "traj_idx": int(traj_idx),
                "t": float(times[traj_idx]),
                "video_t": video_t,
                "pos": positions[traj_idx].tolist(),
                "quat": quaternions[traj_idx].tolist(),
                "image_key": f"{inter_prefix}/keyframes/{image_name}",
                "bytes": size,
            }
            keyframe_entries.append(entry)

        await storage.ensure_bucket(intermediates_bucket)
        file_count, uploaded_bytes = await storage.upload_directory(
            frames_local, intermediates_bucket, f"{inter_prefix}/keyframes"
        )
        logger.info(
            "keyframes uploaded",
            file_count=file_count,
            total_bytes=uploaded_bytes,
        )

        arc_length_m = _arc_length_at_indices(positions, indices)
        manifest = {
            "schema_version": 1,
            "project_id": project_id,
            "segment_id": segment_id,
            "n_keyframes": len(keyframe_entries),
            "min_spacing_m": DEFAULT_MIN_SPACING_M,
            "video_start_t": video_start_t,
            "arc_length_m": arc_length_m,
            "keyframes": keyframe_entries,
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_key = f"{inter_prefix}/keyframes.json"
        await storage.upload_bytes(manifest_bytes, intermediates_bucket, manifest_key)

    manifest_uri = f"s3://{intermediates_bucket}/{manifest_key}"
    images_prefix = f"s3://{intermediates_bucket}/{inter_prefix}/keyframes/"
    ref = KeyframesRef(
        project_id=project_id,
        segment_id=segment_id,
        manifest_uri=manifest_uri,
        images_uri_prefix=images_prefix,
        n_keyframes=len(keyframe_entries),
        min_spacing_m=DEFAULT_MIN_SPACING_M,
        arc_length_m=arc_length_m,
    )
    logger.info(
        "select_keyframes done",
        manifest_uri=manifest_uri,
        n_keyframes=ref.n_keyframes,
        arc_length_m=arc_length_m,
    )
    return ref
