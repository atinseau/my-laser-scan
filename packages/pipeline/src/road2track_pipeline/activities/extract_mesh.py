"""Activité Temporal : `extract_mesh` (étape 3.4, queue `gpu`).

Cf. specs/04-pipeline-ml.md §3.4.

Pipeline :
1. DL scene.ply depuis MinIO (output de train_gs).
2. Reconstruction Poisson via `road2track_ml.mesh.extract_mesh_from_splat`.
3. Upload mesh.obj sur MinIO.
4. Retourne MeshRef.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from road2track_core.config import Settings
from road2track_core.entities.refs import MeshRef, SceneRef
from road2track_core.errors import InvalidSegmentError
from road2track_ml.mesh import extract_mesh_from_splat
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


@activity.defn(name="extract_mesh")
async def extract_mesh(scene: SceneRef) -> MeshRef:
    """Reconstruit un mesh Poisson depuis une scène GS puis upload."""
    import asyncio

    settings = Settings()
    project_id = scene.project_id
    segment_id = scene.segment_id

    structlog.contextvars.bind_contextvars(
        project_id=project_id,
        segment_id=segment_id,
        activity_name="extract_mesh",
    )
    logger.info("extract_mesh start", scene_uri=scene.scene_uri)

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    intermediates_bucket = settings.minio_bucket_intermediates
    scene_bucket, scene_key = _parse_s3_uri(scene.scene_uri)

    with tempfile.TemporaryDirectory(prefix="r2t-extract-mesh-") as tmpdir:
        local_dir = Path(tmpdir)
        scene_local = local_dir / "scene.ply"
        output_dir = local_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        await storage.download_file(scene_bucket, scene_key, scene_local)
        logger.info("scene downloaded", bytes=scene_local.stat().st_size)

        result = await asyncio.to_thread(
            extract_mesh_from_splat, scene_local, output_dir
        )
        logger.info(
            "mesh extracted",
            n_vertices=result.n_vertices,
            n_faces=result.n_faces,
            n_gaussians_used=result.n_gaussians_used,
        )

        mesh_key = f"{project_id}/{segment_id}/mesh.obj"
        await storage.upload_file(result.mesh_path, intermediates_bucket, mesh_key)

    mesh_uri = f"s3://{intermediates_bucket}/{mesh_key}"
    ref = MeshRef(
        project_id=project_id,
        segment_id=segment_id,
        mesh_uri=mesh_uri,
        n_vertices=result.n_vertices,
        n_faces=result.n_faces,
    )
    logger.info(
        "extract_mesh done",
        mesh_uri=mesh_uri,
        n_vertices=ref.n_vertices,
        n_faces=ref.n_faces,
    )
    return ref
