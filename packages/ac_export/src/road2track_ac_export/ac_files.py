"""Génération des fichiers de configuration Assetto Corsa.

Templates Jinja minimal au POC It. 1 :
- `surfaces.ini` : 2 surfaces (ROAD, GRASS) avec friction par défaut.
- `models.ini` : un seul mesh (mono-tuile au POC).
- `ui/ui_track.json` : métadonnées affichées par Content Manager.

Référence format AC : https://www.assettocorsa.net/forum/ (catégorie modding).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

_TEMPLATES_DIR: Path = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(default_for_string=False),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


@dataclass(frozen=True)
class AcFilesResult:
    surfaces_ini_path: Path
    models_ini_path: Path
    ui_track_json_path: Path


def render_surfaces_ini(
    output_path: Path,
    *,
    road_friction: float = 0.99,
    grass_friction: float = 0.6,
) -> Path:
    env = _env()
    rendered = env.get_template("surfaces.ini.j2").render(
        generated_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        road_friction=road_friction,
        grass_friction=grass_friction,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


def render_models_ini(
    output_path: Path, *, mesh_filename: str = "track.kn5"
) -> Path:
    env = _env()
    rendered = env.get_template("models.ini.j2").render(
        generated_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        mesh_filename=mesh_filename,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


def render_ui_track_json(
    output_path: Path,
    *,
    track_name: str,
    track_kind: str,
    length_m: float,
    description: str = "",
    country: str = "France",
    track_author: str = "road2track",
    extra: dict[str, Any] | None = None,
) -> Path:
    env = _env()
    context: dict[str, Any] = {
        "track_name": track_name,
        "track_kind": track_kind,
        "length_m": length_m,
        "description": description,
        "country": country,
        "track_author": track_author,
    }
    if extra:
        context.update(extra)
    rendered = env.get_template("ui_track.json.j2").render(**context)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


def render_all_ac_files(
    output_dir: Path,
    *,
    track_name: str,
    track_kind: str,
    length_m: float,
    description: str = "",
    country: str = "France",
    track_author: str = "road2track",
) -> AcFilesResult:
    """Rend les 3 fichiers d'un coup dans `output_dir`.

    Layout produit :
        output_dir/surfaces.ini
        output_dir/models.ini
        output_dir/ui/ui_track.json
    """
    surfaces_path = render_surfaces_ini(output_dir / "surfaces.ini")
    models_path = render_models_ini(output_dir / "models.ini")
    ui_path = render_ui_track_json(
        output_dir / "ui" / "ui_track.json",
        track_name=track_name,
        track_kind=track_kind,
        length_m=length_m,
        description=description,
        country=country,
        track_author=track_author,
    )
    return AcFilesResult(
        surfaces_ini_path=surfaces_path,
        models_ini_path=models_path,
        ui_track_json_path=ui_path,
    )
