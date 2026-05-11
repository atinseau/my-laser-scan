"""Tests sur les stubs GPU (train_gs, extract_mesh, bake_textures).

Au scaffold (It. 0) ils lèvent `NotImplementedError`. Ce test verrouille la
signature et l'enregistrement Temporal pour éviter qu'une régression silencieuse
casse le câblage avant la vraie implémentation.
"""

from __future__ import annotations

import pytest
from road2track_core.entities.refs import (
    KeyframesRef,
    MeshRef,
    SceneRef,
    TexturedMeshRef,
)
from road2track_pipeline.activities import (
    bake_textures,
    extract_mesh,
    train_gs,
)


def _keyframes_ref() -> KeyframesRef:
    return KeyframesRef(
        project_id="prj_test",
        segment_id="seg_test",
        manifest_uri="s3://intermediates/prj_test/seg_test/keyframes.json",
        images_uri_prefix="s3://intermediates/prj_test/seg_test/keyframes/",
        n_keyframes=100,
        min_spacing_m=0.5,
        arc_length_m=50.0,
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


# Pour appeler une activité hors d'un worker Temporal, on accède au callable wrappé.
def _callable_of(activity_def: object) -> object:
    return getattr(activity_def, "__wrapped__", activity_def)


@pytest.mark.asyncio
async def test_train_gs_stub_raises() -> None:
    fn = _callable_of(train_gs)
    with pytest.raises(NotImplementedError, match="train_gs"):
        await fn(_keyframes_ref())  # type: ignore[operator]


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
