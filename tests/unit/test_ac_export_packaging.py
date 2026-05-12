"""Tests sur le packaging Content Manager (zip + miniature)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from road2track_ac_export.packaging import (
    build_content_manager_package,
    render_placeholder_preview,
    slugify_track_id,
)


def test_slugify_track_id_keeps_alphanumeric() -> None:
    assert slugify_track_id("Galibier Descent") == "galibier_descent"
    assert slugify_track_id("Col du Galibier !") == "col_du_galibier"
    assert slugify_track_id("123-abc") == "123_abc"


def test_slugify_track_id_fallback_on_empty() -> None:
    assert slugify_track_id("") == "road2track_custom"
    assert slugify_track_id("!!!") == "road2track_custom"


def test_render_placeholder_preview(tmp_path: Path) -> None:
    path = tmp_path / "preview.png"
    render_placeholder_preview(path, track_name="Test Circuit")
    assert path.is_file()
    # PNG SOI marker
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def _make_dummy_file(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_build_package_layout(tmp_path: Path) -> None:
    surfaces = _make_dummy_file(tmp_path / "surfaces.ini", b"[SURFACE_0]\nKEY=ROAD\n")
    models = _make_dummy_file(tmp_path / "models.ini", b"[MODEL_0]\nFILE=track.kn5\n")
    ui = _make_dummy_file(tmp_path / "ui_track.json", b"{}")
    kn5 = _make_dummy_file(tmp_path / "track.kn5", b"\x00\x01\x02")
    ai = _make_dummy_file(tmp_path / "fast_lane.ai", b"\xff\xfe")

    zip_path = tmp_path / "out.zip"
    result = build_content_manager_package(
        zip_path,
        track_name="My Track",
        surfaces_ini=surfaces,
        models_ini=models,
        ui_track_json=ui,
        kn5=kn5,
        fast_lane_ai=ai,
    )

    assert result.track_id == "my_track"
    assert result.zip_path.is_file()
    assert result.bytes_size > 0

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    expected = {
        "content/tracks/my_track/surfaces.ini",
        "content/tracks/my_track/models.ini",
        "content/tracks/my_track/ui/ui_track.json",
        "content/tracks/my_track/ui/preview.png",
        "content/tracks/my_track/track.kn5",
        "content/tracks/my_track/ai/fast_lane.ai",
    }
    assert expected.issubset(names)


def test_build_package_missing_input_raises(tmp_path: Path) -> None:
    surfaces = _make_dummy_file(tmp_path / "surfaces.ini")
    models = _make_dummy_file(tmp_path / "models.ini")
    ui = _make_dummy_file(tmp_path / "ui_track.json")
    kn5 = _make_dummy_file(tmp_path / "track.kn5")
    missing = tmp_path / "missing_fast_lane.ai"
    with pytest.raises(FileNotFoundError, match="input introuvable"):
        build_content_manager_package(
            tmp_path / "out.zip",
            track_name="X",
            surfaces_ini=surfaces,
            models_ini=models,
            ui_track_json=ui,
            kn5=kn5,
            fast_lane_ai=missing,
        )
