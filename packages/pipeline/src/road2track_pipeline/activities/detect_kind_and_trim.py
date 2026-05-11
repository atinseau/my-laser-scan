"""Activité Temporal : `detect_kind_and_trim`.

Étape 2.3 du pipeline (cf. specs/04-pipeline-ml.md §2.3, ADR-007, ADR-016).

1. Télécharge `trajectory.json` (sortie de `fuse_sensors`).
2. Classifie la trajectoire en CIRCUIT ou SPECIALE via heuristique loop closure.
3. CIRCUIT → tronque le lead-in (samples avant l'entrée de la boucle).
   SPECIALE → aucun trim (ADR-016 : l'utilisateur contrôle les bornes).
4. Sérialise la trajectoire tronquée sous `trajectory_trimmed.json`.
5. Upload sur MinIO et retourne un `DetectedTrackRef`.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import structlog
from numpy.typing import NDArray
from road2track_core.config import Settings
from road2track_core.entities.refs import DetectedTrackRef, TrajectoryRef
from road2track_core.entities.track_kind import TrackKind
from road2track_core.errors import InvalidSegmentError
from road2track_geo.detection import detect_track_kind, find_lead_in_index
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


def _arc_length_m(positions_enu: NDArray[np.float64]) -> float:
    if positions_enu.shape[0] < 2:
        return 0.0
    diffs = np.diff(positions_enu, axis=0)
    return float(np.linalg.norm(diffs, axis=1).sum())


@activity.defn(name="detect_kind_and_trim")
async def detect_kind_and_trim(trajectory_ref: TrajectoryRef) -> DetectedTrackRef:
    """Détecte CIRCUIT/SPECIALE et tronque le lead-in pour les circuits."""
    settings = Settings()

    structlog.contextvars.bind_contextvars(
        project_id=trajectory_ref.project_id,
        segment_id=trajectory_ref.segment_id,
        activity_name="detect_kind_and_trim",
    )
    logger.info(
        "detect_kind_and_trim start",
        trajectory_uri=trajectory_ref.trajectory_uri,
        n_samples=trajectory_ref.n_samples,
    )

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    intermediates_bucket = settings.minio_bucket_intermediates
    bucket, key = _parse_s3_uri(trajectory_ref.trajectory_uri)

    with tempfile.TemporaryDirectory(prefix="r2t-detect-") as tmpdir:
        local = Path(tmpdir) / "trajectory.json"
        await storage.download_file(bucket, key, local)
        payload = json.loads(local.read_text(encoding="utf-8"))

    samples = payload.get("samples", [])
    if not samples:
        raise InvalidSegmentError("trajectoire vide pour detect_kind_and_trim")

    positions = np.asarray([s["pos"] for s in samples], dtype=np.float64)
    track_kind, closure_distance_m = detect_track_kind(positions)
    logger.info(
        "kind detected",
        track_kind=track_kind.value,
        loop_closure_distance_m=closure_distance_m,
    )

    start_idx = find_lead_in_index(positions) if track_kind == TrackKind.CIRCUIT else 0

    samples_trimmed = samples[start_idx:]
    positions_trimmed = positions[start_idx:]
    arc_length_m = _arc_length_m(positions_trimmed)

    out_payload = {
        **payload,
        "track_kind": track_kind.value,
        "loop_closure_distance_m": closure_distance_m,
        "n_samples_trimmed_at_start": start_idx,
        "samples": samples_trimmed,
    }
    out_bytes = json.dumps(out_payload).encode("utf-8")
    out_key = f"{trajectory_ref.project_id}/{trajectory_ref.segment_id}/trajectory_trimmed.json"
    await storage.upload_bytes(out_bytes, intermediates_bucket, out_key)
    trimmed_uri = f"s3://{intermediates_bucket}/{out_key}"

    ref = DetectedTrackRef(
        project_id=trajectory_ref.project_id,
        segment_id=trajectory_ref.segment_id,
        track_kind=track_kind,
        trimmed_trajectory_uri=trimmed_uri,
        n_samples=len(samples_trimmed),
        arc_length_m=arc_length_m,
        loop_closure_distance_m=closure_distance_m,
        n_samples_trimmed_at_start=start_idx,
    )
    logger.info(
        "detect_kind_and_trim done",
        track_kind=track_kind.value,
        trimmed_trajectory_uri=trimmed_uri,
        n_samples=ref.n_samples,
        arc_length_m=arc_length_m,
        n_samples_trimmed_at_start=start_idx,
    )
    return ref
