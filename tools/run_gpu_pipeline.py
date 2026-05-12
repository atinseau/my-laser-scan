"""Lance manuellement les activités GPU d'un projet déjà ingéré.

Cas d'usage : `road2track ingest <path>` a été exécuté mais s'est arrêté
avant la phase GPU (workflow `ProcessProject` cassé sur `train_gs` par
exemple). MinIO contient déjà keyframes.json + keyframes/*.jpg. On veut
relancer une activité GPU isolément pour débugger sans repartir de zéro.

Usage :
    # Tout démarrer depuis train_gs (cas standard)
    uv run python tools/run_gpu_pipeline.py <project_id> <segment_id>

    # Démarrer depuis une étape précise après fix d'une plus tôt
    uv run python tools/run_gpu_pipeline.py <project_id> <segment_id> --from extract_mesh
    uv run python tools/run_gpu_pipeline.py <project_id> <segment_id> --from bake_textures

Chaque étape passe par un workflow dédié `RunTrainGs` / `RunExtractMesh` /
`RunBakeTextures` (cf. `packages/pipeline/workflows/gpu_stages.py`) qui
appelle UNE seule activité sur la queue `gpu`. Le résultat est sauvegardé
dans MinIO comme pour un run normal.

Quand toutes les étapes passent vert, utiliser `road2track ingest` qui
enchaîne le tout via `ProcessProject` (plus simple en production).
"""

from __future__ import annotations

import asyncio
import sys

import structlog
import typer
from road2track_core.config import Settings
from road2track_core.entities.refs import (
    BakeTexturesInput,
    KeyframesRef,
    MeshRef,
    SceneRef,
)
from road2track_core.queues import TaskQueue
from road2track_pipeline.logging_setup import configure_logging
from temporalio.client import Client

app = typer.Typer(
    name="run_gpu_pipeline",
    help="Déclenche les activités GPU sur un segment déjà ingéré (debug).",
    no_args_is_help=True,
)

_STAGES: tuple[str, ...] = ("train_gs", "extract_mesh", "bake_textures")

_PROJECT_ID_ARG: str = typer.Argument(..., help="ID du projet.")
_SEGMENT_ID_ARG: str = typer.Argument(..., help="ID du segment.")
_FROM_OPT: str = typer.Option(
    "train_gs",
    "--from",
    "-f",
    help=f"Étape à lancer : {'|'.join(_STAGES)}.",
)
_N_KEYFRAMES_OPT: int = typer.Option(
    100, "--n-keyframes", help="Nombre de keyframes (informatif)."
)


def _build_keyframes_ref(
    settings: Settings, project_id: str, segment_id: str, n_keyframes: int
) -> KeyframesRef:
    bucket = settings.minio_bucket_intermediates
    prefix = f"{project_id}/{segment_id}"
    return KeyframesRef(
        project_id=project_id,
        segment_id=segment_id,
        manifest_uri=f"s3://{bucket}/{prefix}/keyframes.json",
        images_uri_prefix=f"s3://{bucket}/{prefix}/keyframes/",
        n_keyframes=n_keyframes,
        min_spacing_m=0.5,
        arc_length_m=0.0,
    )


def _build_scene_ref(
    settings: Settings, project_id: str, segment_id: str
) -> SceneRef:
    bucket = settings.minio_bucket_intermediates
    prefix = f"{project_id}/{segment_id}"
    return SceneRef(
        project_id=project_id,
        segment_id=segment_id,
        scene_uri=f"s3://{bucket}/{prefix}/scene.ply",
        metrics_uri=f"s3://{bucket}/{prefix}/training_metrics.json",
    )


def _build_mesh_ref(settings: Settings, project_id: str, segment_id: str) -> MeshRef:
    bucket = settings.minio_bucket_intermediates
    prefix = f"{project_id}/{segment_id}"
    return MeshRef(
        project_id=project_id,
        segment_id=segment_id,
        mesh_uri=f"s3://{bucket}/{prefix}/mesh.obj",
    )


@app.command()
def run(
    project_id: str = _PROJECT_ID_ARG,
    segment_id: str = _SEGMENT_ID_ARG,
    start_from: str = _FROM_OPT,
    n_keyframes: int = _N_KEYFRAMES_OPT,
) -> None:
    """Lance une activité GPU isolée via Temporal."""
    if start_from not in _STAGES:
        typer.echo(f"❌ --from doit être l'un de {list(_STAGES)}", err=True)
        raise typer.Exit(code=2)

    settings = Settings()
    configure_logging(level=settings.log_level, worker_name="run_gpu_pipeline")
    logger = structlog.get_logger("run_gpu_pipeline")

    async def _run() -> None:
        client = await Client.connect(
            settings.temporal_host, namespace=settings.temporal_namespace
        )
        logger.info(
            "temporal connected",
            host=settings.temporal_host,
            from_stage=start_from,
            project_id=project_id,
            segment_id=segment_id,
        )

        if start_from == "train_gs":
            keyframes = _build_keyframes_ref(
                settings, project_id, segment_id, n_keyframes
            )
            scene = await client.execute_workflow(
                "RunTrainGs",
                keyframes,
                id=f"gpu-train_gs-{project_id}-{segment_id}",
                task_queue=TaskQueue.CPU.value,
            )
            typer.echo(f"✅ train_gs done — scene_uri = {scene.scene_uri}")

        elif start_from == "extract_mesh":
            scene = _build_scene_ref(settings, project_id, segment_id)
            mesh = await client.execute_workflow(
                "RunExtractMesh",
                scene,
                id=f"gpu-extract_mesh-{project_id}-{segment_id}",
                task_queue=TaskQueue.CPU.value,
            )
            typer.echo(f"✅ extract_mesh done — mesh_uri = {mesh.mesh_uri}")

        elif start_from == "bake_textures":
            mesh = _build_mesh_ref(settings, project_id, segment_id)
            keyframes = _build_keyframes_ref(
                settings, project_id, segment_id, n_keyframes
            )
            payload = BakeTexturesInput(mesh=mesh, keyframes=keyframes)
            textured = await client.execute_workflow(
                "RunBakeTextures",
                payload,
                id=f"gpu-bake_textures-{project_id}-{segment_id}",
                task_queue=TaskQueue.CPU.value,
            )
            typer.echo(f"✅ bake_textures done — textured mesh = {textured.mesh_uri}")

    asyncio.run(_run())


def main() -> None:  # pragma: no cover
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
