"""Test d'intégration end-to-end de `select_keyframes`.

Stratégie :
1. Lance un MinIO via testcontainers.
2. Génère une mini vidéo (5 s, 30 fps, color bars) avec ffmpeg.
3. Crée une trajectoire JSON synthétique (200 poses sur 50 m).
4. Upload video + trajectoire dans MinIO.
5. Patch les Settings pour pointer vers le MinIO du container.
6. Appelle `select_keyframes` et vérifie :
   - Le bon nombre de keyframes a été produit (≈ 100 ≈ 50 m / 0.5 m).
   - Le manifest est présent et correctement structuré.
   - Les JPEG existent.

Skipped si docker ou ffmpeg ne sont pas disponibles.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from road2track_core.entities.refs import (
    DetectedTrackRef,
    SegmentRef,
    SelectKeyframesInput,
    SyncResult,
    VideoMetadata,
)
from road2track_core.entities.track_kind import TrackKind
from road2track_storage.object.minio_adapter import MinioObjectStorage

needs_docker = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker indisponible dans l'env de test"
)
needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe indisponibles dans l'env de test",
)


def _make_test_video(path: Path, duration_s: float = 5.0, fps: int = 30) -> None:
    """Génère une vidéo de test avec ffmpeg (lavfi color bars)."""
    import subprocess

    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"smptebars=duration={duration_s}:size=320x240:rate={fps}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _synthetic_trajectory_payload(
    project_id: str, segment_id: str, n_poses: int = 200, length_m: float = 50.0
) -> dict[str, Any]:
    """Trajectoire ENU rectiligne le long de l'axe X sur `length_m`."""
    t0 = 1700000000.0
    duration_s = 5.0
    times = np.linspace(t0, t0 + duration_s, n_poses)
    xs = np.linspace(0.0, length_m, n_poses)
    samples = [
        {
            "t": float(times[i]),
            "pos": [float(xs[i]), 0.0, 0.0],
            "quat": [1.0, 0.0, 0.0, 0.0],
        }
        for i in range(n_poses)
    ]
    return {
        "schema_version": 1,
        "project_id": project_id,
        "segment_id": segment_id,
        "origin_wgs84": {"lat": 45.0, "lon": 6.0, "alt": 100.0},
        "origin_t": t0,
        "rmse_m": 0.0,
        "n_gps_fixes_used": 0,
        "track_kind": TrackKind.SPECIALE.value,
        "loop_closure_distance_m": length_m,
        "n_samples_trimmed_at_start": 0,
        "samples": samples,
    }


@needs_docker
@needs_ffmpeg
@pytest.mark.asyncio
async def test_select_keyframes_end_to_end(
    minio_container: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end : video + trajectoire → keyframes JPEG + manifest dans MinIO."""
    from road2track_pipeline.activities.select_keyframes import (
        select_keyframes,
    )

    project_id = "prj_inttest"
    segment_id = "seg_inttest"
    raw_bucket = "raw"
    intermediates_bucket = "intermediates"

    # 1. Génère vidéo + trajectoire localement.
    video_local = tmp_path / "video.mp4"
    _make_test_video(video_local, duration_s=5.0, fps=30)
    trajectory_payload = _synthetic_trajectory_payload(project_id, segment_id)
    trajectory_local = tmp_path / "trajectory_trimmed.json"
    trajectory_local.write_text(json.dumps(trajectory_payload), encoding="utf-8")

    # 2. Upload dans MinIO.
    storage = MinioObjectStorage(
        endpoint_url=minio_container["endpoint_url"],
        access_key=minio_container["access_key"],
        secret_key=minio_container["secret_key"],
    )
    await storage.ensure_bucket(raw_bucket)
    await storage.ensure_bucket(intermediates_bucket)
    await storage.upload_file(
        video_local, raw_bucket, f"{project_id}/{segment_id}/record3d/video.mp4"
    )
    trajectory_key = f"{project_id}/{segment_id}/trajectory_trimmed.json"
    await storage.upload_file(trajectory_local, intermediates_bucket, trajectory_key)

    # 3. Override les Settings pour pointer vers le MinIO du container.
    endpoint_url = minio_container["endpoint_url"].removeprefix("http://")
    monkeypatch.setenv("MINIO_ENDPOINT", endpoint_url)
    monkeypatch.setenv("MINIO_ACCESS_KEY", minio_container["access_key"])
    monkeypatch.setenv("MINIO_SECRET_KEY", minio_container["secret_key"])
    monkeypatch.setenv("MINIO_BUCKET_RAW", raw_bucket)
    monkeypatch.setenv("MINIO_BUCKET_INTERMEDIATES", intermediates_bucket)

    # 4. Construit l'input et appelle l'activité (callable wrappé).
    segment = SegmentRef(
        project_id=project_id,
        segment_id=segment_id,
        raw_uri_prefix=f"s3://{raw_bucket}/{project_id}/{segment_id}/",
        file_count=1,
        total_bytes=video_local.stat().st_size,
        video=VideoMetadata(
            duration_s=5.0, fps=30.0, width=320, height=240, codec="h264"
        ),
        sync=SyncResult(drift_ms=0.0, method="utc_aligned"),
    )
    detected = DetectedTrackRef(
        project_id=project_id,
        segment_id=segment_id,
        track_kind=TrackKind.SPECIALE,
        trimmed_trajectory_uri=f"s3://{intermediates_bucket}/{trajectory_key}",
        n_samples=200,
        arc_length_m=50.0,
        loop_closure_distance_m=50.0,
        n_samples_trimmed_at_start=0,
    )
    payload = SelectKeyframesInput(segment=segment, detected=detected)

    fn = getattr(select_keyframes, "__wrapped__", select_keyframes)
    ref = await fn(payload)  # type: ignore[operator]

    # 5. Assertions sur le résultat.
    # 50 m / 0.5 m de spacing → ~100 keyframes (± 1 selon échantillonnage).
    assert 95 <= ref.n_keyframes <= 102
    assert ref.min_spacing_m == 0.5
    assert ref.manifest_uri.startswith(f"s3://{intermediates_bucket}/")
    assert ref.images_uri_prefix.endswith("/keyframes/")

    # Vérifie que le manifest est lisible et bien structuré.
    download_dir = tmp_path / "downloaded"
    download_dir.mkdir()
    manifest_local = download_dir / "keyframes.json"
    manifest_key = f"{project_id}/{segment_id}/keyframes.json"
    await storage.download_file(intermediates_bucket, manifest_key, manifest_local)
    manifest = json.loads(manifest_local.read_text(encoding="utf-8"))
    assert manifest["n_keyframes"] == ref.n_keyframes
    assert manifest["min_spacing_m"] == 0.5
    assert len(manifest["keyframes"]) == ref.n_keyframes
    first = manifest["keyframes"][0]
    assert {"idx", "t", "video_t", "pos", "quat", "image_key", "bytes"} <= first.keys()

    # Vérifie qu'au moins une frame JPEG est téléchargeable et non vide.
    first_image_local = download_dir / "0000.jpg"
    await storage.download_file(
        intermediates_bucket, first["image_key"], first_image_local
    )
    assert first_image_local.stat().st_size > 0
    # Bytes JPEG SOI marker.
    assert first_image_local.read_bytes()[:2] == b"\xff\xd8"
