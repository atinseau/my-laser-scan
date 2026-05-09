"""CLI Road2Track — Typer.

Commandes prévues (cf. specs/05-infrastructure.md §8) :

    road2track project create <name>
    road2track ingest <path>
    road2track process <project_id>
    road2track export <project_id>
    road2track gpu list / spawn / shutdown
    road2track maintenance backup-outputs / gc-intermediates
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="road2track",
    help="Outil de génération de circuits Assetto Corsa depuis une balade iPhone.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Affiche la version du projet."""
    typer.echo("road2track 0.1.0")


@app.command()
def ingest(path: str, project_id: str | None = None) -> None:
    """Ingère une session de capture (Record3D + Sensor Logger au POC)."""
    raise NotImplementedError("À implémenter à l'It. 0")


@app.command()
def process(project_id: str) -> None:
    """Lance le pipeline de traitement d'un projet."""
    raise NotImplementedError("À implémenter à l'It. 0")


if __name__ == "__main__":
    app()
