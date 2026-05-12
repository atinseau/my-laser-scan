"""Activité Temporal : `generate_fbx` (étape B2 d'It. 1).

Pipeline :
1. DL mesh.obj texturé + atlas.png + materials.json depuis MinIO.
2. Charge le mesh (trimesh, lazy).
3. UV unwrap via xatlas → sommets dupliqués + UVs.
4. Écrit un OBJ enrichi (UVs + vertex colors préservés) + MTL référençant
   l'atlas.
5. Upload OBJ + MTL + atlas vers `outputs/<p>/<s>/ac/mesh/`.
6. Retourne `FbxRef` (avec `fbx_uri=None` au POC B2 — conversion FBX en B2b).

⚠️ POC limitations explicites :
- Pas de FBX réel — la conversion OBJ→FBX nécessite Blender (extra `blender`).
  Sera ajoutée en B2b sur la queue `windows-tools` qui aura Blender installé.
- L'atlas reste celui produit par `bake_textures` (placeholder gris au POC).
  Un futur `rebake_uv_textures` réelle re-projettera les keyframes dans
  l'espace UV xatlas.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from road2track_ac_export.obj_io import write_mtl, write_obj_with_uvs
from road2track_ac_export.uv_unwrap import unwrap_mesh_uvs
from road2track_core.config import Settings
from road2track_core.entities.refs import FbxRef, TexturedMeshRef
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


def _load_mesh_with_colors(obj_path: Path) -> tuple[
    object, object, object | None
]:
    """Charge un mesh OBJ via trimesh. Retourne (vertices, faces, vertex_colors|None)."""
    try:
        import trimesh  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "trimesh est requis pour `generate_fbx`. Installer l'extra `fbx` "
            "(`uv sync --extra fbx --package road2track-ac-export`)."
        ) from e

    mesh = trimesh.load(obj_path, force="mesh")
    vertices = mesh.vertices
    faces = mesh.faces
    colors = None
    if hasattr(mesh.visual, "vertex_colors") and mesh.visual.vertex_colors is not None:
        # trimesh stocke en uint8 RGBA, on normalise en float [0, 1] RGB.
        import numpy as np

        rgba = np.asarray(mesh.visual.vertex_colors, dtype=np.float64) / 255.0
        if rgba.ndim == 2 and rgba.shape[1] >= 3:
            colors = rgba[:, 0:3]
    return vertices, faces, colors


@activity.defn(name="generate_fbx")
async def generate_fbx(textured_mesh: TexturedMeshRef) -> FbxRef:
    """UV unwrap + écriture OBJ enrichi + MTL + atlas."""
    import asyncio

    settings = Settings()
    project_id = textured_mesh.project_id
    segment_id = textured_mesh.segment_id

    structlog.contextvars.bind_contextvars(
        project_id=project_id,
        segment_id=segment_id,
        activity_name="generate_fbx",
    )
    logger.info("generate_fbx start", mesh_uri=textured_mesh.mesh_uri)

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    outputs_bucket = settings.minio_bucket_outputs

    mesh_bucket, mesh_key = _parse_s3_uri(textured_mesh.mesh_uri)
    atlas_bucket, atlas_key = _parse_s3_uri(textured_mesh.texture_atlas_uri)

    with tempfile.TemporaryDirectory(prefix="r2t-fbx-") as tmpdir:
        local_dir = Path(tmpdir)
        mesh_local = local_dir / "input_mesh.obj"
        atlas_local = local_dir / "atlas.png"
        output_dir = local_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        await storage.download_file(mesh_bucket, mesh_key, mesh_local)
        await storage.download_file(atlas_bucket, atlas_key, atlas_local)
        logger.info("inputs downloaded")

        def _process() -> tuple[Path, Path, Path, int, int]:
            vertices, faces, colors = _load_mesh_with_colors(mesh_local)
            unwrap = unwrap_mesh_uvs(vertices, faces)
            # Si vertex colors présents, dupliquer selon vmapping.
            colors_out = colors[unwrap.vmapping] if colors is not None else None

            obj_out = output_dir / "mesh.obj"
            mtl_out = output_dir / "track.mtl"
            atlas_out = output_dir / "atlas.png"

            write_obj_with_uvs(
                obj_out,
                vertices=unwrap.vertices,
                faces=unwrap.faces,
                uvs=unwrap.uvs,
                mtl_filename=mtl_out.name,
                vertex_colors=colors_out,
            )
            write_mtl(mtl_out, atlas_filename=atlas_out.name)
            # Copie l'atlas tel quel.
            atlas_out.write_bytes(atlas_local.read_bytes())
            return (
                obj_out,
                mtl_out,
                atlas_out,
                int(unwrap.vertices.shape[0]),
                int(unwrap.faces.shape[0]),
            )

        obj_path, mtl_path, atlas_out_path, n_vertices, n_faces = (
            await asyncio.to_thread(_process)
        )
        logger.info(
            "uv unwrap done",
            n_vertices=n_vertices,
            n_faces=n_faces,
        )

        prefix = f"{project_id}/{segment_id}/ac/mesh"
        obj_key = f"{prefix}/mesh.obj"
        mtl_key = f"{prefix}/track.mtl"
        atlas_key_out = f"{prefix}/atlas.png"
        await storage.ensure_bucket(outputs_bucket)
        await storage.upload_file(obj_path, outputs_bucket, obj_key)
        await storage.upload_file(mtl_path, outputs_bucket, mtl_key)
        await storage.upload_file(atlas_out_path, outputs_bucket, atlas_key_out)

    obj_uri = f"s3://{outputs_bucket}/{obj_key}"
    mtl_uri = f"s3://{outputs_bucket}/{mtl_key}"
    atlas_uri = f"s3://{outputs_bucket}/{atlas_key_out}"

    ref = FbxRef(
        project_id=project_id,
        segment_id=segment_id,
        obj_uri=obj_uri,
        mtl_uri=mtl_uri,
        atlas_uri=atlas_uri,
        fbx_uri=None,
        n_vertices=n_vertices,
        n_faces=n_faces,
    )
    logger.info(
        "generate_fbx done",
        obj_uri=obj_uri,
        mtl_uri=mtl_uri,
        n_vertices=n_vertices,
        n_faces=n_faces,
    )
    return ref
