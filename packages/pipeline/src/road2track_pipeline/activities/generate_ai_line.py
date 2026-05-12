"""Activité Temporal : `generate_ai_line` (étape B3 d'It. 1).

Lit la trajectoire tronquée produite par `detect_kind_and_trim`, ré-échantillonne
à pas constant et produit `fast_lane.ai` (format binaire AC).

⚠️ Format simplifié au POC : positions + arc length seulement, pas de side
bounds. Cf. `road2track_ac_export.ai_line` pour les détails.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import structlog
from road2track_ac_export.ai_line import write_fast_lane_ai
from road2track_core.config import Settings
from road2track_core.entities.refs import AiLineRef, DetectedTrackRef
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


@activity.defn(name="generate_ai_line")
async def generate_ai_line(detected: DetectedTrackRef) -> AiLineRef:
    """DL trajectory_trimmed.json → write fast_lane.ai → upload."""
    settings = Settings()
    project_id = detected.project_id
    segment_id = detected.segment_id

    structlog.contextvars.bind_contextvars(
        project_id=project_id,
        segment_id=segment_id,
        activity_name="generate_ai_line",
    )
    logger.info(
        "generate_ai_line start",
        trimmed_uri=detected.trimmed_trajectory_uri,
        track_kind=detected.track_kind.value,
    )

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    outputs_bucket = settings.minio_bucket_outputs
    traj_bucket, traj_key = _parse_s3_uri(detected.trimmed_trajectory_uri)

    with tempfile.TemporaryDirectory(prefix="r2t-ai-line-") as tmpdir:
        local_dir = Path(tmpdir)
        traj_local = local_dir / "trajectory_trimmed.json"
        await storage.download_file(traj_bucket, traj_key, traj_local)

        trajectory: dict[str, Any] = json.loads(
            traj_local.read_text(encoding="utf-8")
        )
        samples: list[dict[str, Any]] = trajectory.get("samples", [])
        if len(samples) < 2:
            raise InvalidSegmentError(
                "trajectoire tronquée trop courte pour générer une AI line"
            )

        positions = np.asarray([s["pos"] for s in samples], dtype=np.float64)
        out_path = local_dir / "fast_lane.ai"
        result = write_fast_lane_ai(out_path, positions)

        ai_key = f"{project_id}/{segment_id}/ac/ai/fast_lane.ai"
        await storage.ensure_bucket(outputs_bucket)
        await storage.upload_file(out_path, outputs_bucket, ai_key)

    ai_uri = f"s3://{outputs_bucket}/{ai_key}"
    ref = AiLineRef(
        project_id=project_id,
        segment_id=segment_id,
        fast_lane_uri=ai_uri,
        n_waypoints=result.n_waypoints,
    )
    logger.info(
        "generate_ai_line done",
        fast_lane_uri=ai_uri,
        n_waypoints=result.n_waypoints,
        total_length_m=result.total_length_m,
    )
    return ref
