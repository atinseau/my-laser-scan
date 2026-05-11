"""Tests sur l'I/O PLY format Gaussian Splatting."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from road2track_ml.gs import read_gaussian_splat_ply, save_gaussian_splat_ply


def _dummy_gaussians(n: int, sh_degree: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(42)
    sh_rest_count = 3 * ((sh_degree + 1) ** 2 - 1)
    return {
        "means": rng.standard_normal((n, 3)).astype(np.float32),
        "sh_dc": rng.standard_normal((n, 3)).astype(np.float32),
        "sh_rest": rng.standard_normal((n, sh_rest_count)).astype(np.float32),
        "opacities_logit": rng.standard_normal(n).astype(np.float32),
        "scales_log": rng.standard_normal((n, 3)).astype(np.float32),
        "quats_wxyz": rng.standard_normal((n, 4)).astype(np.float32),
    }


def test_ply_roundtrip_sh_degree_3(tmp_path: Path) -> None:
    n = 50
    data = _dummy_gaussians(n, sh_degree=3)
    path = tmp_path / "scene.ply"
    bytes_written = save_gaussian_splat_ply(path, sh_degree=3, **data)
    assert bytes_written > 0
    assert path.is_file()

    loaded = read_gaussian_splat_ply(path)
    np.testing.assert_array_almost_equal(loaded["means"], data["means"], decimal=5)
    np.testing.assert_array_almost_equal(loaded["sh_dc"], data["sh_dc"], decimal=5)
    np.testing.assert_array_almost_equal(loaded["sh_rest"], data["sh_rest"], decimal=5)
    np.testing.assert_array_almost_equal(
        loaded["opacities_logit"], data["opacities_logit"], decimal=5
    )
    np.testing.assert_array_almost_equal(
        loaded["scales_log"], data["scales_log"], decimal=5
    )
    np.testing.assert_array_almost_equal(loaded["quats_wxyz"], data["quats_wxyz"], decimal=5)


def test_ply_roundtrip_sh_degree_0(tmp_path: Path) -> None:
    n = 10
    data = _dummy_gaussians(n, sh_degree=0)
    path = tmp_path / "scene.ply"
    save_gaussian_splat_ply(path, sh_degree=0, **data)
    loaded = read_gaussian_splat_ply(path)
    assert loaded["sh_rest"].shape == (n, 0)
    np.testing.assert_array_almost_equal(loaded["means"], data["means"], decimal=5)


def test_ply_wrong_shape_raises(tmp_path: Path) -> None:
    data = _dummy_gaussians(10, sh_degree=3)
    data["sh_dc"] = np.zeros((10, 4), dtype=np.float32)  # mauvais nb de colonnes
    with pytest.raises(ValueError, match="sh_dc must be"):
        save_gaussian_splat_ply(tmp_path / "scene.ply", sh_degree=3, **data)
