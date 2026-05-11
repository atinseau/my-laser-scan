"""CLI Road2Track — Typer.

Commandes prévues (cf. specs/05-infrastructure.md §8) :

    road2track ingest <path> --project-id <id>
    road2track process <project_id>     (à venir)
    road2track export <project_id>      (à venir)
    road2track gpu list / spawn / shutdown   (à venir)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
import typer
from road2track_core.config import Settings
from road2track_core.entities.refs import IngestInput
from road2track_core.ids import new_project_id
from road2track_pipeline.client import start_process_project
from road2track_pipeline.logging_setup import configure_logging

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
        result = await handle.result()
        seg = result.segment
        traj = result.trajectory
        detected = result.detected
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

    asyncio.run(run())


if __name__ == "__main__":
    app()
