"""Test E2E de la chaîne CPU : `ingest_session` → `fuse_sensors` →
`detect_kind_and_trim` → `select_keyframes`, sur capture synthétique.

Stratégie :
1. Génère une capture complète (ffmpeg + json) via la fixture.
2. Démarre un MinIO via testcontainers.
3. Configure les Settings pour pointer dessus (raw + intermediates buckets).
4. Appelle les 4 activités CPU dans l'ordre, chacune via son callable `__wrapped__`
   (sans passer par Temporal — on teste la logique métier, pas le routage workflow).
5. Vérifie le manifest keyframes final.

Skip si docker OU ffmpeg sont absents (env CI CPU-only).

Couvre les livrables It. 0 "Suite de tests E2E sur dataset jouet (200 m)".
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from road2track_core.config import Settings
from road2track_core.entities.refs import IngestInput, SelectKeyframesInput
from road2track_storage.object.minio_adapter import MinioObjectStorage

from tests.fixtures.synthetic_capture import SyntheticCaptureSpec, write_synthetic_capture

needs_docker = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker indisponible dans l'env de test"
)
needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe indisponibles dans l'env de test",
)


def _callable_of(activity_def: object) -> object:
    return getattr(activity_def, "__wrapped__", activity_def)


@needs_docker
@needs_ffmpeg
@pytest.mark.asyncio
async def test_cpu_chain_end_to_end(
    minio_container: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Capture → ingest → fuse → detect → keyframes — vérifie chaque maillon."""
    from road2track_pipeline.activities import (
        detect_kind_and_trim,
        fuse_sensors,
        ingest_session,
        select_keyframes,
    )

    capture_dir = tmp_path / "capture"
    spec = SyntheticCaptureSpec(
        n_arkit_poses=90,
        n_imu_samples=300,
        n_gps_fixes=20,
        trajectory_kind="circuit",
        arc_length_m=60.0,
    )
    write_synthetic_capture(capture_dir, spec)

    project_id = "prj_e2e"

    raw_bucket = "raw"
    intermediates_bucket = "intermediates"
    endpoint_url = minio_container["endpoint_url"].removeprefix("http://")
    monkeypatch.setenv("MINIO_ENDPOINT", endpoint_url)
    monkeypatch.setenv("MINIO_ACCESS_KEY", minio_container["access_key"])
    monkeypatch.setenv("MINIO_SECRET_KEY", minio_container["secret_key"])
    monkeypatch.setenv("MINIO_BUCKET_RAW", raw_bucket)
    monkeypatch.setenv("MINIO_BUCKET_INTERMEDIATES", intermediates_bucket)
    # Postgres : la fixture ne le démarre pas. ingest_session essaiera de persister
    # un Segment → on saute via env de fallback (SQLite in-memory).
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    settings = Settings()
    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    await storage.ensure_bucket(raw_bucket)
    await storage.ensure_bucket(intermediates_bucket)

    # 1. ingest_session
    ingest_fn = _callable_of(ingest_session)
    segment_ref = await ingest_fn(  # type: ignore[operator]
        IngestInput(project_id=project_id, local_dir=str(capture_dir))
    )
    assert segment_ref.project_id == project_id
    assert segment_ref.file_count > 0
    assert segment_ref.video.duration_s == pytest.approx(spec.duration_s, abs=0.2)

    # 2. fuse_sensors
    fuse_fn = _callable_of(fuse_sensors)
    trajectory_ref = await fuse_fn(segment_ref)  # type: ignore[operator]
    assert trajectory_ref.n_samples == spec.n_arkit_poses
    assert trajectory_ref.alignment_rmse_m < 5.0
    assert trajectory_ref.origin_lat == pytest.approx(spec.origin_lat, abs=0.01)

    # 3. detect_kind_and_trim
    detect_fn = _callable_of(detect_kind_and_trim)
    detected_ref = await detect_fn(trajectory_ref)  # type: ignore[operator]
    assert detected_ref.track_kind.value == "circuit"
    assert detected_ref.arc_length_m == pytest.approx(spec.arc_length_m, rel=0.2)

    # 4. select_keyframes
    select_fn = _callable_of(select_keyframes)
    keyframes_ref = await select_fn(  # type: ignore[operator]
        SelectKeyframesInput(segment=segment_ref, detected=detected_ref)
    )
    # 60 m / 0.5 m = ~120 keyframes attendues.
    assert 80 <= keyframes_ref.n_keyframes <= 150

    # Vérifie le manifest dans MinIO.
    download_dir = tmp_path / "downloaded"
    download_dir.mkdir()
    manifest_local = download_dir / "keyframes.json"
    manifest_key = f"{project_id}/{segment_ref.segment_id}/keyframes.json"
    await storage.download_file(intermediates_bucket, manifest_key, manifest_local)
    manifest = json.loads(manifest_local.read_text(encoding="utf-8"))
    assert manifest["n_keyframes"] == keyframes_ref.n_keyframes
    assert manifest["min_spacing_m"] == 0.5
    assert len(manifest["keyframes"]) == keyframes_ref.n_keyframes
    # Premier keyframe : positions + quat présents.
    first = manifest["keyframes"][0]
    assert {"idx", "t", "video_t", "pos", "quat", "image_key"} <= first.keys()
