"""Tests sur la génération des fichiers AC via Jinja."""

from __future__ import annotations

import configparser
import json
from pathlib import Path

from road2track_ac_export import (
    render_all_ac_files,
    render_models_ini,
    render_surfaces_ini,
    render_ui_track_json,
)


def test_render_surfaces_ini_contains_road_and_grass(tmp_path: Path) -> None:
    out = render_surfaces_ini(tmp_path / "surfaces.ini")
    assert out.is_file()
    parser = configparser.ConfigParser()
    parser.read(out)
    assert "SURFACE_0" in parser.sections()
    assert "SURFACE_1" in parser.sections()
    assert parser["SURFACE_0"]["KEY"] == "ROAD"
    assert parser["SURFACE_1"]["KEY"] == "GRASS"
    assert float(parser["SURFACE_0"]["FRICTION"]) == 0.99
    assert float(parser["SURFACE_1"]["FRICTION"]) == 0.6


def test_render_surfaces_ini_custom_friction(tmp_path: Path) -> None:
    out = render_surfaces_ini(
        tmp_path / "surfaces.ini", road_friction=0.85, grass_friction=0.4
    )
    parser = configparser.ConfigParser()
    parser.read(out)
    assert float(parser["SURFACE_0"]["FRICTION"]) == 0.85
    assert float(parser["SURFACE_1"]["FRICTION"]) == 0.4


def test_render_models_ini(tmp_path: Path) -> None:
    out = render_models_ini(tmp_path / "models.ini", mesh_filename="mytrack.kn5")
    parser = configparser.ConfigParser()
    parser.read(out)
    assert "MODEL_0" in parser.sections()
    assert parser["MODEL_0"]["FILE"] == "mytrack.kn5"


def test_render_ui_track_json_circuit(tmp_path: Path) -> None:
    out = render_ui_track_json(
        tmp_path / "ui_track.json",
        track_name="Galibier Descent",
        track_kind="circuit",
        length_m=2350.0,
        description="200m boucle de test",
        country="France",
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["name"] == "Galibier Descent"
    assert data["description"] == "200m boucle de test"
    assert "circuit" in data["tags"]
    assert data["length"] == "2350 m"
    assert data["country"] == "France"
    assert data["run"] == "Counter-clockwise"


def test_render_ui_track_json_speciale_run_default(tmp_path: Path) -> None:
    out = render_ui_track_json(
        tmp_path / "ui_track.json",
        track_name="Col du Galibier",
        track_kind="speciale",
        length_m=12000.0,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["run"] == "Point to point"


def test_render_all_ac_files_layout(tmp_path: Path) -> None:
    result = render_all_ac_files(
        tmp_path,
        track_name="Test Circuit",
        track_kind="circuit",
        length_m=1000.0,
    )
    assert result.surfaces_ini_path == tmp_path / "surfaces.ini"
    assert result.models_ini_path == tmp_path / "models.ini"
    assert result.ui_track_json_path == tmp_path / "ui" / "ui_track.json"
    assert result.surfaces_ini_path.is_file()
    assert result.models_ini_path.is_file()
    assert result.ui_track_json_path.is_file()
