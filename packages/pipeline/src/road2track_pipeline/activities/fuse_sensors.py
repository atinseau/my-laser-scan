"""Activité Temporal : `fuse_sensors`.

Étape 2.2 du pipeline (cf. specs/04-pipeline-ml.md §2.2).

Au POC : approche simplifiée sans EKF complet.
1. Télécharge depuis MinIO : record3d/poses.json + sensor_logger/gps.json.
2. Trouve l'origine ENU sur le premier fix GPS valide (HDOP < 10 m).
3. Fusion ARKit + GPS via alignement rigide Kabsch (cf. road2track_geo.fusion.trajectory).
4. Sérialise la trajectoire fusionnée en JSON (TODO V1 : Parquet via pyarrow).
5. Upload sur MinIO sous `s3://intermediates/<project>/<segment>/trajectory.json`.

L'EKF complet avec biais IMU + RTS smoothing arrivera en V1 (cf. ADR à venir).
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import numpy as np
import structlog
from road2track_core.config import Settings
from road2track_core.entities.refs import SegmentRef, TrajectoryRef
from road2track_geo.fusion.trajectory import fuse_trajectory
from road2track_storage.object.minio_adapter import MinioObjectStorage
from temporalio import activity

from road2track_pipeline.activities._capture_parsers import (
    parse_record3d_poses,
    parse_sensor_logger_gps,
)

logger = structlog.get_logger(__name__)


def _serialize_trajectory_json(
    project_id: str,
    segment_id: str,
    times_s: np.ndarray,
    positions_enu: np.ndarray,
    quaternions_wxyz: np.ndarray,
    origin_lat: float,
    origin_lon: float,
    origin_alt: float,
    origin_t: float,
    rmse_m: float,
    n_gps_fixes_used: int,
) -> bytes:
    """Sérialise la trajectoire fusionnée en JSON UTF-8.

    Format au POC :
        {
          "schema_version": 1,
          "project_id": "...",
          "segment_id": "...",
          "origin_wgs84": {"lat", "lon", "alt"},
          "origin_t": <utc seconds>,
          "rmse_m": <float>,
          "n_gps_fixes_used": <int>,
          "samples": [{"t", "pos": [e,n,u], "quat": [w,x,y,z]}, ...]
        }
    """
    samples = [
        {
            "t": float(times_s[i]),
            "pos": [
                float(positions_enu[i, 0]),
                float(positions_enu[i, 1]),
                float(positions_enu[i, 2]),
            ],
            "quat": [
                float(quaternions_wxyz[i, 0]),
                float(quaternions_wxyz[i, 1]),
                float(quaternions_wxyz[i, 2]),
                float(quaternions_wxyz[i, 3]),
            ],
        }
        for i in range(len(times_s))
    ]
    payload = {
        "schema_version": 1,
        "project_id": project_id,
        "segment_id": segment_id,
        "origin_wgs84": {"lat": origin_lat, "lon": origin_lon, "alt": origin_alt},
        "origin_t": origin_t,
        "rmse_m": rmse_m,
        "n_gps_fixes_used": n_gps_fixes_used,
        "samples": samples,
    }
    return json.dumps(payload).encode("utf-8")


def _arc_length_m(positions_enu: np.ndarray) -> float:
    if positions_enu.shape[0] < 2:
        return 0.0
    diffs = np.diff(positions_enu, axis=0)
    return float(np.linalg.norm(diffs, axis=1).sum())


@activity.defn(name="fuse_sensors")
async def fuse_sensors(segment_ref: SegmentRef) -> TrajectoryRef:
    """Fusion ARKit + GPS → trajectoire ENU géoréférencée."""
    settings = Settings()

    structlog.contextvars.bind_contextvars(
        project_id=segment_ref.project_id,
        segment_id=segment_ref.segment_id,
        activity_name="fuse_sensors",
    )
    logger.info("fuse_sensors start", raw_uri_prefix=segment_ref.raw_uri_prefix)

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    raw_bucket = settings.minio_bucket_raw
    intermediates_bucket = settings.minio_bucket_intermediates
    raw_prefix = f"{segment_ref.project_id}/{segment_ref.segment_id}"

    with tempfile.TemporaryDirectory(prefix="r2t-fuse-") as tmpdir:
        local_dir = Path(tmpdir)
        # Téléchargement minimal : on prend juste poses.json + gps.json.
        poses_local = local_dir / "record3d" / "poses.json"
        gps_local = local_dir / "sensor_logger" / "gps.json"
        await storage.download_file(raw_bucket, f"{raw_prefix}/record3d/poses.json", poses_local)
        await storage.download_file(raw_bucket, f"{raw_prefix}/sensor_logger/gps.json", gps_local)
        logger.info("inputs downloaded")

        arkit_t, arkit_pos, arkit_quat = parse_record3d_poses(poses_local)

        gps_t, gps_lat, gps_lon, gps_alt, gps_hdop = parse_sensor_logger_gps(gps_local)
        logger.info(
            "inputs parsed",
            arkit_samples=int(arkit_t.size),
            gps_samples=int(gps_t.size),
            gps_valid=int((gps_hdop <= 10.0).sum()),
        )

        fused = fuse_trajectory(
            arkit_t,
            arkit_pos,
            arkit_quat,
            gps_t,
            gps_lat,
            gps_lon,
            gps_alt,
            gps_hdop,
        )
        logger.info(
            "trajectory fused",
            n_samples=fused.times_s.size,
            rmse_m=fused.rmse_m,
            n_gps_fixes_used=fused.n_gps_fixes_used,
            origin_wgs84=fused.origin_wgs84,
        )

        payload = _serialize_trajectory_json(
            project_id=segment_ref.project_id,
            segment_id=segment_ref.segment_id,
            times_s=fused.times_s,
            positions_enu=fused.positions_enu,
            quaternions_wxyz=fused.quaternions_wxyz,
            origin_lat=fused.origin_wgs84[0],
            origin_lon=fused.origin_wgs84[1],
            origin_alt=fused.origin_wgs84[2],
            origin_t=fused.origin_t,
            rmse_m=fused.rmse_m,
            n_gps_fixes_used=fused.n_gps_fixes_used,
        )

    out_key = f"{segment_ref.project_id}/{segment_ref.segment_id}/trajectory.json"
    await storage.ensure_bucket(intermediates_bucket)
    await storage.upload_bytes(payload, intermediates_bucket, out_key)
    trajectory_uri = f"s3://{intermediates_bucket}/{out_key}"
    arc_length_m = _arc_length_m(fused.positions_enu)
    duration_s = float(fused.times_s.max() - fused.times_s.min()) if fused.times_s.size > 1 else 0.0
    if math.isnan(duration_s):
        duration_s = 0.0

    ref = TrajectoryRef(
        project_id=segment_ref.project_id,
        segment_id=segment_ref.segment_id,
        trajectory_uri=trajectory_uri,
        n_samples=int(fused.times_s.size),
        duration_s=duration_s,
        arc_length_m=arc_length_m,
        origin_lat=fused.origin_wgs84[0],
        origin_lon=fused.origin_wgs84[1],
        origin_alt=fused.origin_wgs84[2],
        origin_t=fused.origin_t,
        alignment_rmse_m=fused.rmse_m,
        n_gps_fixes_used=fused.n_gps_fixes_used,
    )
    logger.info(
        "fuse_sensors done",
        trajectory_uri=trajectory_uri,
        arc_length_m=arc_length_m,
        duration_s=duration_s,
    )
    return ref
