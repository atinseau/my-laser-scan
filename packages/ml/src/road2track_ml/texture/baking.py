"""Baking de textures par projection multi-vue (étape 3.5).

Cf. specs/04-pipeline-ml.md §3.5.

Approche POC simplifiée (pas d'UV unwrap, pas d'atlas KTX2) :

1. Pour chaque vertex du mesh, on calcule la normale interpolée.
2. Pour chaque keyframe :
   - Construire la matrice de projection `K · (R | t)` (cam ← world).
   - Projeter le vertex dans le plan image.
   - Si la projection tombe dans le cadre ET que `vertex_normal · view_dir < -0.3`
     (face caméra), on considère le vertex visible depuis cette frame.
   - Échantillonner la couleur RGB au pixel projeté (bilinéaire).
3. Moyenne pondérée des couleurs sur toutes les keyframes valides
   (poids = max(0, -dot)) → couleur vertex définitive.
4. Sauvegarde du mesh.obj avec ces vertex colors, plus un atlas placeholder
   1024×1024 (utile pour les exports AC qui exigent un texture file, même
   uniforme — sera remplacé par baking + atlas KTX2 en It. 1).

⚠️ Limitations POC explicitement assumées :
- Pas de test d'occlusion par z-buffer (les vertices cachés derrière de la
  géométrie peuvent quand même être colorés). Acceptable pour des scènes
  ouvertes type route ; problématique pour des intérieurs.
- Pas d'UV unwrap (xatlas) → atlas n'est pas réellement utilisé.
- Pas de blending laplacien / seam removal.
- Pas de gestion HDR / tone mapping (on travaille en sRGB linéaire).

Imports `open3d`, `cv2` (opencv-python-headless), `PIL` **lazy**.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

from road2track_ml.gs.dataset import KeyframesDataset
from road2track_ml.gs.intrinsics import CameraIntrinsics

if TYPE_CHECKING:
    pass


DEFAULT_ATLAS_SIZE: int = 1024
DEFAULT_VIEW_ANGLE_THRESHOLD: float = -0.3  # cos(seuil) — < 0 = face caméra
DEFAULT_MIN_SAMPLES_PER_VERTEX: int = 1


@dataclass(frozen=True)
class BakeResult:
    mesh_path: Path
    atlas_path: Path
    materials_path: Path
    n_textured_vertices: int
    n_unseen_vertices: int


def _check_open3d_available() -> None:
    try:
        import open3d  # noqa: F401  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "open3d est requis pour `bake_textures`. Installer l'extra `mesh` "
            "(`uv sync --extra mesh --package road2track-ml`)."
        ) from e


def _pose_to_extrinsics(
    pose_world_from_camera: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Retourne (R_cam_from_world, t_cam_from_world)."""
    pose = np.asarray(pose_world_from_camera, dtype=np.float64)
    rotation = pose[0:3, 0:3]
    translation = pose[0:3, 3]
    return rotation.T, -rotation.T @ translation


def _project_vertices(
    vertices_world: NDArray[np.float64],
    rotation_cam_from_world: NDArray[np.float64],
    translation_cam_from_world: NDArray[np.float64],
    intrinsics: CameraIntrinsics,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_]]:
    """Projette N vertices monde dans le plan image. Retourne (u, v, in_front_mask)."""
    points_cam = vertices_world @ rotation_cam_from_world.T + translation_cam_from_world
    in_front = points_cam[:, 2] > 1e-3
    z = np.where(in_front, points_cam[:, 2], 1.0)
    x = intrinsics.fx * points_cam[:, 0] / z + intrinsics.cx
    y = intrinsics.fy * points_cam[:, 1] / z + intrinsics.cy
    return x, y, in_front


def _sample_bilinear(
    image: NDArray[np.uint8], x: NDArray[np.float64], y: NDArray[np.float64]
) -> NDArray[np.float32]:
    """Sample bilinéaire RGB. Pixels hors-cadre → (0, 0, 0)."""
    h, w, _ = image.shape
    x_clipped = np.clip(x, 0, w - 1.001)
    y_clipped = np.clip(y, 0, h - 1.001)
    x0 = np.floor(x_clipped).astype(np.int64)
    y0 = np.floor(y_clipped).astype(np.int64)
    x1 = x0 + 1
    y1 = y0 + 1
    wx = (x_clipped - x0)[:, None]
    wy = (y_clipped - y0)[:, None]

    image_f = image.astype(np.float32)
    c00 = image_f[y0, x0]
    c01 = image_f[y0, x1]
    c10 = image_f[y1, x0]
    c11 = image_f[y1, x1]
    return (
        c00 * (1 - wx) * (1 - wy)
        + c01 * wx * (1 - wy)
        + c10 * (1 - wx) * wy
        + c11 * wx * wy
    )


def _bake_vertex_colors(
    vertices_world: NDArray[np.float64],
    vertex_normals_world: NDArray[np.float64],
    dataset: KeyframesDataset,
    view_angle_threshold: float = DEFAULT_VIEW_ANGLE_THRESHOLD,
) -> tuple[NDArray[np.float32], NDArray[np.int64]]:
    """Retourne (colors_rgb [N, 3] in [0,1], n_samples_per_vertex [N])."""
    n = vertices_world.shape[0]
    accum_color = np.zeros((n, 3), dtype=np.float64)
    accum_weight = np.zeros((n,), dtype=np.float64)
    sample_count = np.zeros((n,), dtype=np.int64)

    for kf_idx in range(len(dataset)):
        sample = dataset[kf_idx]
        rotation_cam, translation_cam = _pose_to_extrinsics(
            sample.pose_world_from_camera
        )
        camera_pos_world = sample.pose_world_from_camera[0:3, 3]
        intrinsics = sample.intrinsics

        # Direction caméra → vertex (normalisée).
        view_dir = vertices_world - camera_pos_world
        norms = np.linalg.norm(view_dir, axis=1, keepdims=True)
        view_dir_unit = view_dir / np.clip(norms, 1e-9, None)
        dot = np.einsum("ij,ij->i", vertex_normals_world, view_dir_unit)
        facing = dot < view_angle_threshold

        u, v, in_front = _project_vertices(
            vertices_world, rotation_cam, translation_cam, intrinsics
        )
        in_frame = (u >= 0) & (u < intrinsics.width) & (v >= 0) & (v < intrinsics.height)
        valid = facing & in_front & in_frame
        if not valid.any():
            continue

        u_v = u[valid]
        v_v = v[valid]
        weights = np.clip(-dot[valid], 0.0, 1.0)

        rgb = _sample_bilinear(sample.image, u_v, v_v) / 255.0
        accum_color[valid] += rgb * weights[:, None]
        accum_weight[valid] += weights
        sample_count[valid] += 1

    has_color = accum_weight > 0
    colors = np.full((n, 3), 0.5, dtype=np.float32)
    colors[has_color] = (
        accum_color[has_color] / accum_weight[has_color, None]
    ).astype(np.float32)
    return np.clip(colors, 0.0, 1.0), sample_count


def _write_placeholder_atlas(path: Path, size: int = DEFAULT_ATLAS_SIZE) -> None:
    """Atlas uniforme gris asphalte 1024×1024 (placeholder pour exports AC)."""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (size, size), (110, 110, 110))
    img.save(path, format="PNG", optimize=True)


def bake_textures_for_mesh(
    mesh_path: Path,
    keyframes_dir: Path,
    output_dir: Path,
    *,
    intrinsics: CameraIntrinsics,
    atlas_size: int = DEFAULT_ATLAS_SIZE,
) -> BakeResult:
    """Bake les vertex colors par projection multi-vue + écrit un atlas placeholder.

    Args:
        mesh_path : .obj produit par `extract_mesh_from_splat`.
        keyframes_dir : dossier contenant `keyframes.json` + `keyframes/NNNN.jpg`.
        output_dir : dossier où écrire mesh.obj texturé + atlas.png + materials.json.
        intrinsics : intrinsics caméra (par défaut : iPhone 14 Pro).
        atlas_size : taille de l'atlas placeholder (px).

    Returns:
        BakeResult avec les 3 chemins de sortie.
    """
    _check_open3d_available()
    import json

    import open3d as o3d  # type: ignore[import-not-found]

    output_dir.mkdir(parents=True, exist_ok=True)

    mesh: Any = o3d.io.read_triangle_mesh(
        str(mesh_path),
        enable_post_processing=True,
    )
    if len(mesh.vertices) == 0:
        raise ValueError(f"mesh vide : {mesh_path}")
    if not mesh.has_vertex_normals():
        mesh.compute_vertex_normals()

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    normals = np.asarray(mesh.vertex_normals, dtype=np.float64)

    dataset = KeyframesDataset(keyframes_dir, intrinsics=intrinsics)
    colors_rgb, sample_counts = _bake_vertex_colors(vertices, normals, dataset)

    mesh.vertex_colors = o3d.utility.Vector3dVector(colors_rgb.astype(np.float64))

    out_mesh = output_dir / "mesh.obj"
    o3d.io.write_triangle_mesh(
        str(out_mesh),
        mesh,
        write_ascii=False,
        write_vertex_colors=True,
        write_vertex_normals=True,
    )

    atlas_path = output_dir / "atlas.png"
    _write_placeholder_atlas(atlas_path, size=atlas_size)

    materials = {
        "schema_version": 1,
        "atlas": atlas_path.name,
        "atlas_size": atlas_size,
        "uv_unwrap_method": "none_poc",
        "baking_method": "multi_view_vertex_color_avg",
        "view_angle_threshold": DEFAULT_VIEW_ANGLE_THRESHOLD,
        "n_keyframes_used": len(dataset),
    }
    materials_path = output_dir / "materials.json"
    materials_path.write_text(json.dumps(materials, indent=2), encoding="utf-8")

    n_textured = int((sample_counts >= DEFAULT_MIN_SAMPLES_PER_VERTEX).sum())
    n_unseen = int(len(vertices)) - n_textured

    return BakeResult(
        mesh_path=out_mesh,
        atlas_path=atlas_path,
        materials_path=materials_path,
        n_textured_vertices=n_textured,
        n_unseen_vertices=n_unseen,
    )
