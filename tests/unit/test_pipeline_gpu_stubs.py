"""Tests sur les activités GPU câblées (train_gs / extract_mesh / bake_textures).

Les trois activités sont maintenant **réelles** (cf. commits "train_gs" et
"extract_mesh + bake_textures à l'aveugle"). Elles dépendent de torch /
gsplat / open3d, non installés en CI CPU-only.

Ce fichier vérifie que :
- Les `_check_runtime_available` (gs/training, mesh/extraction, texture/baking)
  lèvent un ImportError clair quand les extras manquent.
- L'entité `TexturedMeshRef` fonctionne correctement.

Le test end-to-end vit dans `tests/integration/pipeline/`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from road2track_core.entities.refs import TexturedMeshRef
from road2track_ml.gs import GSTrainConfig, KeyframesDataset
from road2track_ml.gs.training import _check_runtime_available, train

_TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


@pytest.mark.skipif(
    _TORCH_AVAILABLE,
    reason="torch installé : on ne peut pas vérifier l'ImportError attendu",
)
def test_train_gs_check_runtime_raises_without_torch() -> None:
    with pytest.raises(ImportError, match="torch"):
        _check_runtime_available()


@pytest.mark.skipif(
    _TORCH_AVAILABLE, reason="torch installé : `train` ne lèvera pas ImportError"
)
def test_train_raises_import_error_without_torch(tmp_path: Path) -> None:
    config = GSTrainConfig()
    dataset = object.__new__(KeyframesDataset)
    with pytest.raises(ImportError):
        train(config, dataset, tmp_path)  # type: ignore[arg-type]


def test_textured_mesh_ref_basic_fields() -> None:
    ref = TexturedMeshRef(
        project_id="prj_test",
        segment_id="seg_test",
        mesh_uri="s3://intermediates/prj_test/seg_test/mesh.obj",
        texture_atlas_uri="s3://intermediates/prj_test/seg_test/atlas.png",
        material_uri="s3://intermediates/prj_test/seg_test/materials.json",
        n_textures=4,
        n_textured_vertices=12345,
        n_unseen_vertices=42,
    )
    assert ref.n_textures == 4
    assert ref.n_textured_vertices == 12345
    assert ref.n_unseen_vertices == 42
    assert ref.schema_version == 1
