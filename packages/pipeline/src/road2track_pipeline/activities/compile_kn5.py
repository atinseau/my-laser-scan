"""Activité Temporal : `compile_kn5` (étape B4 d'It. 1, queue `windows-tools`).

Compile un `.kn5` Assetto Corsa via ksEditor.exe.

Pipeline :
1. DL OBJ + MTL + atlas (FbxRef) + ini files (AcFilesRef) depuis MinIO.
2. Localise `ksEditor.exe` (env KSEDITOR_PATH ou défaut Steam path).
3. Si trouvé : invoque ksEditor en mode batch → produit `track.kn5`.
4. Sinon (sandbox / CI) : produit un **.kn5 placeholder** (zip des inputs
   renommé en `.kn5`) pour permettre aux étapes aval (`package_content_manager`)
   d'être testées sans ksEditor.
5. Upload sur MinIO et retourne `Kn5Ref` avec `ks_editor_available` indiquant
   si le vrai ksEditor a tourné.

⚠️ Le vrai mode ksEditor n'est testé qu'au moment de la validation sur ton
PC Windows. Sandbox = toujours placeholder.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import structlog
from road2track_core.config import Settings
from road2track_core.entities.refs import Kn5Input, Kn5Ref
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


def _find_kseditor() -> Path | None:
    """Cherche ksEditor.exe via env ou Steam path par défaut."""
    env = os.environ.get("KSEDITOR_PATH")
    if env:
        path = Path(env)
        if path.is_file():
            return path
    via_path = shutil.which("ksEditor")
    if via_path:
        return Path(via_path)
    # Fallback Steam (à vérifier sur ton install) :
    steam_candidates = [
        Path(
            r"C:\Program Files (x86)\Steam\steamapps\common\assettocorsa\sdk\editor\ksEditor.exe"
        ),
    ]
    for candidate in steam_candidates:
        if candidate.is_file():
            return candidate
    return None


async def _run_kseditor(
    kseditor: Path, project_fbx: Path, output_dir: Path
) -> Path:
    """Invoque ksEditor en mode batch. Retourne le path du .kn5 produit."""
    proc = await asyncio.create_subprocess_exec(
        str(kseditor),
        "-saveKn5",
        str(project_fbx),
        "-outputDir",
        str(output_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise InvalidSegmentError(
            f"ksEditor a échoué (rc={proc.returncode}) : "
            f"{stderr.decode(errors='replace').strip()}"
        )
    candidates = list(output_dir.glob("*.kn5"))
    if not candidates:
        raise InvalidSegmentError(
            f"ksEditor n'a pas produit de .kn5 dans {output_dir}"
        )
    return candidates[0]


def _write_placeholder_kn5(
    output_path: Path, inputs: list[Path]
) -> int:
    """Zip les inputs sous un nom `.kn5`. Permet de tester l'aval sans ksEditor."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in inputs:
            if path.is_file():
                z.write(path, arcname=path.name)
    return output_path.stat().st_size


@activity.defn(name="compile_kn5")
async def compile_kn5(payload: Kn5Input) -> Kn5Ref:
    """Compile (ou stub) le .kn5 et upload."""
    settings = Settings()
    project_id = payload.fbx.project_id
    segment_id = payload.fbx.segment_id

    structlog.contextvars.bind_contextvars(
        project_id=project_id,
        segment_id=segment_id,
        activity_name="compile_kn5",
    )

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    outputs_bucket = settings.minio_bucket_outputs

    obj_bucket, obj_key = _parse_s3_uri(payload.fbx.obj_uri)
    mtl_bucket, mtl_key = _parse_s3_uri(payload.fbx.mtl_uri)
    atlas_bucket, atlas_key = _parse_s3_uri(payload.fbx.atlas_uri)
    surfaces_bucket, surfaces_key = _parse_s3_uri(payload.ac_files.surfaces_ini_uri)
    models_bucket, models_key = _parse_s3_uri(payload.ac_files.models_ini_uri)

    kseditor = _find_kseditor()
    logger.info(
        "compile_kn5 start",
        kseditor=str(kseditor) if kseditor else "NOT FOUND (placeholder mode)",
    )

    with tempfile.TemporaryDirectory(prefix="r2t-kn5-") as tmpdir:
        local_dir = Path(tmpdir)
        obj_local = local_dir / "mesh.obj"
        mtl_local = local_dir / "track.mtl"
        atlas_local = local_dir / "atlas.png"
        surfaces_local = local_dir / "surfaces.ini"
        models_local = local_dir / "models.ini"
        output_dir = local_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        await asyncio.gather(
            storage.download_file(obj_bucket, obj_key, obj_local),
            storage.download_file(mtl_bucket, mtl_key, mtl_local),
            storage.download_file(atlas_bucket, atlas_key, atlas_local),
            storage.download_file(surfaces_bucket, surfaces_key, surfaces_local),
            storage.download_file(models_bucket, models_key, models_local),
        )
        logger.info("inputs downloaded")

        kn5_local = output_dir / "track.kn5"
        ks_editor_available = kseditor is not None
        if ks_editor_available and kseditor is not None:
            try:
                produced = await _run_kseditor(kseditor, obj_local, output_dir)
                if produced != kn5_local:
                    produced.rename(kn5_local)
            except InvalidSegmentError:
                logger.warning("ksEditor failed — falling back to placeholder")
                ks_editor_available = False

        if not ks_editor_available:
            _write_placeholder_kn5(
                kn5_local,
                [obj_local, mtl_local, atlas_local, surfaces_local, models_local],
            )

        kn5_key = f"{project_id}/{segment_id}/ac/track.kn5"
        await storage.upload_file(kn5_local, outputs_bucket, kn5_key)
        bytes_size = kn5_local.stat().st_size

    kn5_uri = f"s3://{outputs_bucket}/{kn5_key}"
    ref = Kn5Ref(
        project_id=project_id,
        segment_id=segment_id,
        kn5_uri=kn5_uri,
        bytes_size=bytes_size,
        ks_editor_available=ks_editor_available,
    )
    logger.info(
        "compile_kn5 done",
        kn5_uri=kn5_uri,
        bytes_size=bytes_size,
        ks_editor_available=ks_editor_available,
    )
    return ref
