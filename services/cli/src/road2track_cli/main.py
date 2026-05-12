"""CLI Road2Track — Typer.

Commandes (cf. specs/05-infrastructure.md §8) :

    road2track ingest <path> [--project-id <id>]
    road2track export <project_id> [--target assetto-corsa] [--track-name ...]
    road2track gpu list / spawn / shutdown   (à venir)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import structlog
import typer
from road2track_core.config import Settings
from road2track_core.entities.refs import (
    DetectedTrackRef,
    ExportAcInput,
    IngestInput,
    TexturedMeshRef,
)
from road2track_core.entities.track_kind import TrackKind
from road2track_core.ids import new_project_id
from road2track_pipeline.client import (
    start_export_assetto_corsa,
    start_process_project,
)
from road2track_pipeline.logging_setup import configure_logging
from road2track_pipeline.workflows.export_assetto_corsa import (
    ExportAssettoCorsaResult,
)
from road2track_pipeline.workflows.process_project import ProcessProjectResult

app = typer.Typer(
    name="road2track",
    help="Outil de génération de circuits Assetto Corsa depuis une balade iPhone.",
    no_args_is_help=True,
)

# Singletons module-level pour Typer (évite B008 — function call in default).
_PATH_ARG: Path = typer.Argument(
    ...,
    exists=True,
    file_okay=False,
    dir_okay=True,
    readable=True,
    help="Chemin du dossier de capture (Record3D + Sensor Logger).",
)
_PROJECT_ID_OPT: str | None = typer.Option(
    None,
    "--project-id",
    "-p",
    help="ID de projet existant. Si omis, un nouveau projet est créé.",
)


@app.command()
def version() -> None:
    """Affiche la version du projet."""
    typer.echo("road2track 0.1.0")


@app.command()
def ingest(path: Path = _PATH_ARG, project_id: str | None = _PROJECT_ID_OPT) -> None:
    """Ingère une session de capture et lance le workflow `ProcessProject`."""
    settings = Settings()
    configure_logging(level=settings.log_level, worker_name="cli")
    logger = structlog.get_logger("cli.ingest")

    pid = project_id or new_project_id()
    payload = IngestInput(project_id=pid, local_dir=str(path.resolve()))
    workflow_id = f"process-{pid}"

    logger.info(
        "starting ProcessProject workflow",
        project_id=pid,
        workflow_id=workflow_id,
        local_dir=str(path.resolve()),
    )

    async def run() -> None:
        handle = await start_process_project(payload, workflow_id=workflow_id)
        typer.echo(f"workflow démarré : {handle.id} (run_id: {handle.result_run_id})")
        result = cast(ProcessProjectResult, await handle.result())
        seg = result.segment
        traj = result.trajectory
        detected = result.detected
        keyframes = result.keyframes
        scene = result.scene
        mesh = result.mesh
        textured = result.textured_mesh
        typer.echo("✅ traitement terminé")
        typer.echo(f"  project_id    : {seg.project_id}")
        typer.echo(f"  segment_id    : {seg.segment_id}")
        typer.echo(f"  files         : {seg.file_count}")
        typer.echo(f"  bytes         : {seg.total_bytes}")
        typer.echo(f"  raw uri       : {seg.raw_uri_prefix}")
        typer.echo(
            f"  video         : {seg.video.width}x{seg.video.height} @ "
            f"{seg.video.fps:.1f} fps, {seg.video.duration_s:.1f} s, codec={seg.video.codec}"
        )
        if seg.video.had_audio:
            saved = seg.video.bytes_before_audio_drop - seg.video.bytes_after_audio_drop
            typer.echo(
                f"  audio drop    : {saved} bytes économisés "
                f"({seg.video.bytes_before_audio_drop} → {seg.video.bytes_after_audio_drop})"
            )
        typer.echo(
            f"  sync          : {seg.sync.method} (drift={seg.sync.drift_ms:.0f} ms, "
            f"offset={seg.sync.offset_applied_ms:.0f} ms)"
        )
        typer.echo(
            f"  trajectoire   : {traj.n_samples} poses, {traj.duration_s:.1f} s, "
            f"{traj.arc_length_m:.0f} m, RMSE alignement {traj.alignment_rmse_m:.2f} m"
        )
        typer.echo(
            f"  origine       : ({traj.origin_lat:.6f}, {traj.origin_lon:.6f}, "
            f"alt {traj.origin_alt:.1f} m)"
        )
        typer.echo(f"  trajectory uri: {traj.trajectory_uri}")
        typer.echo(
            f"  type détecté  : {detected.track_kind.value} "
            f"(closure={detected.loop_closure_distance_m:.1f} m, "
            f"trim lead-in={detected.n_samples_trimmed_at_start} poses)"
        )
        typer.echo(f"  trajectoire tronquée : {detected.trimmed_trajectory_uri}")
        typer.echo(
            f"  keyframes     : {keyframes.n_keyframes} JPEG "
            f"(spacing={keyframes.min_spacing_m:.2f} m, "
            f"arc {keyframes.arc_length_m:.0f} m)"
        )
        typer.echo(f"  manifest      : {keyframes.manifest_uri}")
        typer.echo(
            f"  scene GS      : {scene.n_gaussians} gaussiennes, "
            f"{scene.n_iterations} iter"
        )
        typer.echo(f"  scene uri     : {scene.scene_uri}")
        typer.echo(
            f"  mesh          : {mesh.n_vertices} vertices / {mesh.n_faces} faces"
        )
        typer.echo(f"  mesh uri      : {mesh.mesh_uri}")
        typer.echo(
            f"  textured      : {textured.n_textured_vertices} vertex colorés "
            f"({textured.n_unseen_vertices} non vus)"
        )
        typer.echo(f"  textured uri  : {textured.mesh_uri}")
        typer.echo("✅ POC complet — mesh texturé prêt pour Blender")

    asyncio.run(run())


# ----------------------------------------------------------------------- export

_EXPORT_PROJECT_ID_ARG: str = typer.Argument(..., help="ID du projet (ulid).")
_EXPORT_SEGMENT_ID_ARG: str = typer.Argument(..., help="ID du segment (ulid).")
_EXPORT_TARGET_OPT: str = typer.Option(
    "assetto-corsa", "--target", help="Cible : assetto-corsa (autres targets V2)."
)
_EXPORT_TRACK_NAME_OPT: str = typer.Option(
    "Road2Track Custom", "--track-name", help="Nom affiché dans Content Manager."
)
_EXPORT_AUTHOR_OPT: str = typer.Option(
    "road2track", "--track-author", help="Auteur du circuit."
)
_EXPORT_COUNTRY_OPT: str = typer.Option(
    "France", "--country", help="Pays affiché par CM."
)
_EXPORT_DESCRIPTION_OPT: str = typer.Option(
    "", "--description", help="Description longue."
)
_EXPORT_KIND_OPT: str = typer.Option(
    "circuit", "--kind", help="circuit | speciale (récupéré de detect_kind_and_trim)."
)
_EXPORT_ARC_LENGTH_OPT: float = typer.Option(
    0.0, "--arc-length-m", help="Longueur de la trajectoire (m)."
)


@app.command()
def export(
    project_id: str = _EXPORT_PROJECT_ID_ARG,
    segment_id: str = _EXPORT_SEGMENT_ID_ARG,
    target: str = _EXPORT_TARGET_OPT,
    track_name: str = _EXPORT_TRACK_NAME_OPT,
    track_author: str = _EXPORT_AUTHOR_OPT,
    country: str = _EXPORT_COUNTRY_OPT,
    description: str = _EXPORT_DESCRIPTION_OPT,
    kind: str = _EXPORT_KIND_OPT,
    arc_length_m: float = _EXPORT_ARC_LENGTH_OPT,
) -> None:
    """Export d'un projet vers un format de jeu de simulation (POC : Assetto Corsa).

    Au B1, on passe les refs en arguments (textured_mesh + detected). Une
    prochaine itération lira automatiquement depuis Postgres via project_id.
    """
    if target != "assetto-corsa":
        typer.echo(f"❌ target '{target}' non supporté. Utilise 'assetto-corsa'.", err=True)
        raise typer.Exit(code=2)
    if kind not in ("circuit", "speciale"):
        typer.echo(f"❌ --kind doit être circuit | speciale (got '{kind}')", err=True)
        raise typer.Exit(code=2)

    settings = Settings()
    configure_logging(level=settings.log_level, worker_name="cli")
    logger = structlog.get_logger("cli.export")

    bucket = settings.minio_bucket_intermediates
    out_bucket = settings.minio_bucket_outputs
    prefix = f"{project_id}/{segment_id}"

    textured_ref = TexturedMeshRef(
        project_id=project_id,
        segment_id=segment_id,
        mesh_uri=f"s3://{bucket}/{prefix}/textured/mesh.obj",
        texture_atlas_uri=f"s3://{bucket}/{prefix}/textured/atlas.png",
        material_uri=f"s3://{bucket}/{prefix}/textured/materials.json",
    )
    detected_ref = DetectedTrackRef(
        project_id=project_id,
        segment_id=segment_id,
        track_kind=TrackKind(kind),
        trimmed_trajectory_uri=f"s3://{bucket}/{prefix}/trajectory_trimmed.json",
        n_samples=0,
        arc_length_m=arc_length_m,
        loop_closure_distance_m=0.0,
    )
    payload = ExportAcInput(
        project_id=project_id,
        segment_id=segment_id,
        textured_mesh=textured_ref,
        detected=detected_ref,
        track_name=track_name,
        track_author=track_author,
        country=country,
        description=description,
    )
    workflow_id = f"export-ac-{project_id}-{segment_id}"

    logger.info(
        "starting ExportAssettoCorsa workflow",
        project_id=project_id,
        segment_id=segment_id,
        workflow_id=workflow_id,
        track_name=track_name,
    )

    async def run() -> None:
        handle = await start_export_assetto_corsa(payload, workflow_id=workflow_id)
        typer.echo(f"workflow démarré : {handle.id} (run_id: {handle.result_run_id})")
        result = cast(ExportAssettoCorsaResult, await handle.result())
        typer.echo("✅ export AC done")
        typer.echo(f"  bucket sortie   : {out_bucket}")
        typer.echo(f"  surfaces.ini    : {result.ac_files.surfaces_ini_uri}")
        typer.echo(f"  models.ini      : {result.ac_files.models_ini_uri}")
        typer.echo(f"  ui_track.json   : {result.ac_files.ui_track_json_uri}")
        if result.track_package is not None:
            typer.echo(
                f"  zip CM         : {result.track_package.package_uri} "
                f"({result.track_package.bytes_size} bytes)"
            )
        else:
            typer.echo(
                "  zip CM         : pas encore (FBX + ksEditor + packaging à venir)"
            )

    asyncio.run(run())


if __name__ == "__main__":
    app()
