"""Activité Temporal : `train_gs` (étape 3.3, queue `gpu`).

Cf. specs/04-pipeline-ml.md §3.3 + ADR-022.

Pipeline d'exécution :
1. Télécharge le manifest keyframes + tous les JPEG depuis MinIO.
2. Charge le dataset (poses + images + intrinsics iPhone par défaut).
3. (Optionnel) Télécharge un checkpoint à reprendre.
4. Lance `road2track_ml.gs.train(...)`.
5. Upload `scene.ply` + `training_metrics.json` sur MinIO.
6. Upload chaque checkpoint via callback (ADR-022 levier #1).

⚠️ Cette activité tourne sur le `gpu_worker`. Les imports torch/gsplat sont
faits **lazy** côté `road2track_ml.gs.training` : tant que les extras GPU ne
sont pas installés, un appel réel lèvera `ImportError` clair et Temporal
remontera l'erreur.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from road2track_core.config import Settings
from road2track_core.entities.refs import KeyframesRef, SceneRef
from road2track_core.errors import InvalidSegmentError
from road2track_ml.gs import (
    DEFAULT_IPHONE_14_PRO,
    GSTrainConfig,
    KeyframesDataset,
    train,
)
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


@activity.defn(name="train_gs")
async def train_gs(keyframes: KeyframesRef) -> SceneRef:
    """Train Gaussian Splatting puis upload scene.ply + métriques."""
    settings = Settings()
    project_id = keyframes.project_id
    segment_id = keyframes.segment_id

    structlog.contextvars.bind_contextvars(
        project_id=project_id,
        segment_id=segment_id,
        activity_name="train_gs",
    )
    logger.info(
        "train_gs start",
        manifest_uri=keyframes.manifest_uri,
        n_keyframes=keyframes.n_keyframes,
    )

    storage = MinioObjectStorage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )
    intermediates_bucket = settings.minio_bucket_intermediates

    manifest_bucket, manifest_key = _parse_s3_uri(keyframes.manifest_uri)
    images_bucket, images_prefix = _parse_s3_prefix(keyframes.images_uri_prefix)

    with tempfile.TemporaryDirectory(prefix="r2t-train-gs-") as tmpdir:
        local_dir = Path(tmpdir)
        manifest_local = local_dir / "keyframes.json"
        images_local = local_dir / "keyframes"
        images_local.mkdir(parents=True, exist_ok=True)
        output_dir = local_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        await storage.download_file(manifest_bucket, manifest_key, manifest_local)
        await storage.download_directory(images_bucket, images_prefix, images_local)
        logger.info("inputs downloaded")

        dataset = KeyframesDataset(local_dir, intrinsics=DEFAULT_IPHONE_14_PRO)
        config = GSTrainConfig()

        # Callback de checkpoint → upload MinIO (ADR-022).
        async def _upload_checkpoint(step: int, local_path: Path) -> None:
            ckpt_key = (
                f"{project_id}/{segment_id}/checkpoints/ckpt_{step:06d}.pt"
            )
            await storage.upload_file(local_path, intermediates_bucket, ckpt_key)
            logger.info(
                "checkpoint uploaded",
                step=step,
                uri=f"s3://{intermediates_bucket}/{ckpt_key}",
            )

        # `train` est synchrone (boucle compute lourde) ; on attache un hook
        # qui fait du fire-and-forget async via run_coroutine_threadsafe.
        import asyncio

        loop = asyncio.get_running_loop()

        def _checkpoint_hook(step: int, local_path: Path) -> None:
            asyncio.run_coroutine_threadsafe(
                _upload_checkpoint(step, local_path), loop
            ).result()

        result = await asyncio.to_thread(
            train,
            config,
            dataset,
            output_dir,
            checkpoint_callback=_checkpoint_hook,
        )
        logger.info(
            "training done",
            n_gaussians=result.n_gaussians_final,
            mean_psnr=result.mean_psnr,
            final_loss=result.final_loss,
        )

        scene_key = f"{project_id}/{segment_id}/scene.ply"
        metrics_key = f"{project_id}/{segment_id}/training_metrics.json"
        await storage.upload_file(result.scene_ply_path, intermediates_bucket, scene_key)
        await storage.upload_file(result.metrics_path, intermediates_bucket, metrics_key)

    scene_uri = f"s3://{intermediates_bucket}/{scene_key}"
    metrics_uri = f"s3://{intermediates_bucket}/{metrics_key}"
    ref = SceneRef(
        project_id=project_id,
        segment_id=segment_id,
        scene_uri=scene_uri,
        metrics_uri=metrics_uri,
        n_iterations=int(config.n_iterations),
        n_gaussians=result.n_gaussians_final,
    )
    logger.info(
        "train_gs done",
        scene_uri=scene_uri,
        metrics_uri=metrics_uri,
        n_gaussians=ref.n_gaussians,
    )
    return ref
