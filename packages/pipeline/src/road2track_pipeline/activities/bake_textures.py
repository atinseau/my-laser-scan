"""Activité Temporal : `bake_textures` (étape 3.5, queue `gpu`).

Cf. specs/04-pipeline-ml.md §3.5.

Pipeline POC :
1. DL mesh.obj + keyframes manifest + JPEG depuis MinIO.
2. Bake vertex colors par projection multi-vue
   (`road2track_ml.texture.bake_textures_for_mesh`).
3. Upload mesh.obj texturé + atlas.png + materials.json sur MinIO.
4. Retourne TexturedMeshRef.

L'atlas est un placeholder uniforme au POC (cf. baking.py). Le mesh embarque
les vertex colors → visualisation directe dans Blender.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from road2track_core.config import Settings
from road2track_core.entities.refs import BakeTexturesInput, TexturedMeshRef
from road2track_core.errors import InvalidSegmentError
from road2track_ml.gs import DEFAULT_IPHONE_14_PRO
from road2track_ml.texture import bake_textures_for_mesh
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


def _parse_s3_prefix(uri: str) -> tuple[str, str]:
    bucket, key = _parse_s3_uri(uri)
    return bucket, key.rstrip("/")


@activity.defn(name="bake_textures")
async def bake_textures(payload: BakeTexturesInput) -> TexturedMeshRef:
    """Bake les vertex colors d'un mesh par projection multi-vue."""
    import asyncio

    settings = Settings()
    mesh_ref = payload.mesh
    keyframes_ref = payload.keyframes
    project_id = mesh_ref.project_id
    segment_id = mesh_ref.segment_id

    structlog.contextvars.bind_contextvars(
        project_id=project_id,
        segment_id=segment_id,
        activity_name="bake_textures",
    )
    logger.info(
        "bake_textures start",
        mesh_uri=mesh_ref.mesh_uri,
        manifest_uri=keyframes_ref.manifest_uri,
        n_keyframes=keyframes_ref.n_keyframes,
    )

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    intermediates_bucket = settings.minio_bucket_intermediates

    mesh_bucket, mesh_key = _parse_s3_uri(mesh_ref.mesh_uri)
    manifest_bucket, manifest_key = _parse_s3_uri(keyframes_ref.manifest_uri)
    images_bucket, images_prefix = _parse_s3_prefix(keyframes_ref.images_uri_prefix)

    with tempfile.TemporaryDirectory(prefix="r2t-bake-") as tmpdir:
        local_dir = Path(tmpdir)
        mesh_local = local_dir / "mesh.obj"
        manifest_local = local_dir / "keyframes.json"
        images_local = local_dir / "keyframes"
        images_local.mkdir(parents=True, exist_ok=True)
        output_dir = local_dir / "output"

        await storage.download_file(mesh_bucket, mesh_key, mesh_local)
        await storage.download_file(manifest_bucket, manifest_key, manifest_local)
        await storage.download_directory(images_bucket, images_prefix, images_local)
        logger.info("inputs downloaded")

        result = await asyncio.to_thread(
            bake_textures_for_mesh,
            mesh_local,
            local_dir,
            output_dir,
            intrinsics=DEFAULT_IPHONE_14_PRO,
        )
        logger.info(
            "baking done",
            n_textured=result.n_textured_vertices,
            n_unseen=result.n_unseen_vertices,
        )

        mesh_key_out = f"{project_id}/{segment_id}/textured/mesh.obj"
        atlas_key = f"{project_id}/{segment_id}/textured/atlas.png"
        materials_key = f"{project_id}/{segment_id}/textured/materials.json"
        await storage.upload_file(result.mesh_path, intermediates_bucket, mesh_key_out)
        await storage.upload_file(result.atlas_path, intermediates_bucket, atlas_key)
        await storage.upload_file(
            result.materials_path, intermediates_bucket, materials_key
        )

    mesh_uri = f"s3://{intermediates_bucket}/{mesh_key_out}"
    atlas_uri = f"s3://{intermediates_bucket}/{atlas_key}"
    materials_uri = f"s3://{intermediates_bucket}/{materials_key}"
    ref = TexturedMeshRef(
        project_id=project_id,
        segment_id=segment_id,
        mesh_uri=mesh_uri,
        texture_atlas_uri=atlas_uri,
        material_uri=materials_uri,
        n_textures=1,
        n_textured_vertices=result.n_textured_vertices,
        n_unseen_vertices=result.n_unseen_vertices,
    )
    logger.info(
        "bake_textures done",
        mesh_uri=mesh_uri,
        atlas_uri=atlas_uri,
        n_textured=ref.n_textured_vertices,
        n_unseen=ref.n_unseen_vertices,
    )
    return ref
