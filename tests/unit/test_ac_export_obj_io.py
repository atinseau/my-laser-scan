"""Tests sur l'I/O OBJ + MTL avec coordonnées UV."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from road2track_ac_export.obj_io import write_mtl, write_obj_with_uvs


def test_write_obj_with_uvs_basic(tmp_path: Path) -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    faces = np.array([[0, 1, 2]])
    uvs = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    path = tmp_path / "mesh.obj"
    size = write_obj_with_uvs(path, vertices=vertices, faces=faces, uvs=uvs)
    assert size > 0
    content = path.read_text(encoding="utf-8")
    assert "mtllib track.mtl" in content
    assert "usemtl track_material" in content
    assert "v 0.000000 0.000000 0.000000" in content
    assert "vt 0.000000 0.000000" in content
    # Face avec indices 1-based.
    assert "f 1/1 2/2 3/3" in content


def test_write_obj_with_uvs_includes_colors(tmp_path: Path) -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    faces = np.array([[0, 1, 2]])
    uvs = np.zeros((3, 2))
    colors = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    path = tmp_path / "mesh.obj"
    write_obj_with_uvs(
        path, vertices=vertices, faces=faces, uvs=uvs, vertex_colors=colors
    )
    content = path.read_text(encoding="utf-8")
    # Extension non-standard : v x y z r g b
    assert "v 0.000000 0.000000 0.000000 1.0000 0.0000 0.0000" in content


def test_write_obj_with_uvs_mismatched_uv_count_raises(tmp_path: Path) -> None:
    vertices = np.zeros((3, 3))
    faces = np.array([[0, 1, 2]])
    uvs = np.zeros((2, 2))  # mismatch
    with pytest.raises(ValueError, match="len\\(vertices\\)"):
        write_obj_with_uvs(
            tmp_path / "x.obj", vertices=vertices, faces=faces, uvs=uvs
        )


def test_write_mtl_basic(tmp_path: Path) -> None:
    path = tmp_path / "track.mtl"
    write_mtl(path, atlas_filename="atlas.png")
    content = path.read_text(encoding="utf-8")
    assert "newmtl track_material" in content
    assert "map_Kd atlas.png" in content


def test_write_obj_clips_negative_colors(tmp_path: Path) -> None:
    vertices = np.zeros((1, 3))
    faces = np.zeros((0, 3), dtype=np.int64)
    uvs = np.zeros((1, 2))
    colors = np.array([[-0.5, 2.0, 0.5]])
    path = tmp_path / "mesh.obj"
    write_obj_with_uvs(
        path, vertices=vertices, faces=faces, uvs=uvs, vertex_colors=colors
    )
    content = path.read_text(encoding="utf-8")
    # Clip [0, 1] : -0.5 → 0, 2.0 → 1, 0.5 → 0.5
    assert "0.0000 1.0000 0.5000" in content
