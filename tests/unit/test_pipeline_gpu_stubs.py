"""Tests sur les activités GPU (train_gs / extract_mesh / bake_textures).

- `train_gs` est maintenant **câblée** : DL MinIO → load dataset → train() → upload.
  Pour la tester end-to-end il faut MinIO + torch + GPU (cf.
  `tests/integration/pipeline/test_train_gs.py`). Ici on se contente de vérifier
  que `road2track_ml.gs.train(...)` lève `ImportError` quand torch n'est pas
  installé (cas du sandbox CPU-only).
- `extract_mesh` et `bake_textures` restent des stubs `NotImplementedError`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from road2track_core.entities.refs import (
    MeshRef,
    SceneRef,
    TexturedMeshRef,
)
from road2track_ml.gs import GSTrainConfig, KeyframesDataset
from road2track_ml.gs.training import _check_runtime_available, train
from road2track_pipeline.activities import (
    bake_textures,
    extract_mesh,
)


def _scene_ref() -> SceneRef:
    return SceneRef(
        project_id="prj_test",
        segment_id="seg_test",
        scene_uri="s3://intermediates/prj_test/seg_test/scene.ply",
        metrics_uri="s3://intermediates/prj_test/seg_test/training_metrics.json",
        n_iterations=30000,
        n_gaussians=500000,
    )


def _mesh_ref() -> MeshRef:
    return MeshRef(
        project_id="prj_test",
        segment_id="seg_test",
        mesh_uri="s3://intermediates/prj_test/seg_test/mesh.obj",
        n_vertices=100000,
        n_faces=200000,
    )


def _callable_of(activity_def: object) -> object:
    return getattr(activity_def, "__wrapped__", activity_def)


_TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


@pytest.mark.skipif(
    _TORCH_AVAILABLE,
    reason="torch installé : on ne peut pas vérifier l'ImportError attendu",
)
def test_check_runtime_raises_without_torch() -> None:
    with pytest.raises(ImportError, match="torch"):
        _check_runtime_available()


@pytest.mark.skipif(
    _TORCH_AVAILABLE, reason="torch installé : `train` ne lèvera pas ImportError"
)
def test_train_raises_import_error_without_torch(tmp_path: Path) -> None:
    config = GSTrainConfig()
    # Dataset minimum non utilisé — `train` doit lever avant de l'utiliser.
    dataset = object.__new__(KeyframesDataset)
    with pytest.raises(ImportError):
        train(config, dataset, tmp_path)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_extract_mesh_stub_raises() -> None:
    fn = _callable_of(extract_mesh)
    with pytest.raises(NotImplementedError, match="extract_mesh"):
        await fn(_scene_ref())  # type: ignore[operator]


@pytest.mark.asyncio
async def test_bake_textures_stub_raises() -> None:
    fn = _callable_of(bake_textures)
    with pytest.raises(NotImplementedError, match="bake_textures"):
        await fn(_mesh_ref())  # type: ignore[operator]


def test_textured_mesh_ref_basic_fields() -> None:
    ref = TexturedMeshRef(
        project_id="prj_test",
        segment_id="seg_test",
        mesh_uri="s3://intermediates/prj_test/seg_test/mesh.obj",
        texture_atlas_uri="s3://intermediates/prj_test/seg_test/atlas.png",
        material_uri="s3://intermediates/prj_test/seg_test/materials.json",
        n_textures=4,
    )
    assert ref.n_textures == 4
    assert ref.schema_version == 1
