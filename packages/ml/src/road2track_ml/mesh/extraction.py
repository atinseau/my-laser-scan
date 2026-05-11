"""Extraction de mesh depuis une scène Gaussian Splatting (étape 3.4).

Cf. specs/04-pipeline-ml.md §3.4.

Approche POC : reconstruction Poisson via Open3D.
1. Lire scene.ply (gaussiennes).
2. Filtrer par opacité (seuil par défaut 0.5).
3. Convertir chaque gaussienne en point orienté (normale = axe de plus petit
   scale rotaté par le quaternion).
4. Couleur par-vertex = SH DC → RGB (linéaire, sans tone mapping).
5. Poisson reconstruction (Open3D, depth=10 par défaut).
6. Crop des triangles dans les zones de basse densité (≤ 5e percentile).
7. Decimation quadratic edge collapse vers `target_faces`.
8. Sauvegarde en .obj avec vertex colors (lisible directement dans Blender via
   "Vertex Color" shader node).

Imports `open3d` **lazy** : module importable sans open3d installé pour les
tests CPU. Au premier appel, `ImportError` clair si manquant.

⚠️ Code écrit à l'aveugle sans GPU/open3d disponible — à débugger lors du
premier run. Points sensibles :
- Convention quaternion wxyz → matrice 3×3 via scipy (déjà disponible).
- Open3D attend normales pointant vers l'extérieur ; on prend l'axe de plus
  petit scale rotaté, signe pas garanti → peut nécessiter d'orienter par
  cohérence (voisinage).
- `depth=10` Poisson est lourd RAM (~16 Go pour 500k gaussiennes), réduire si
  besoin.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

from road2track_ml.gs.ply_io import read_gaussian_splat_ply

if TYPE_CHECKING:
    pass


DEFAULT_OPACITY_THRESHOLD: float = 0.5
DEFAULT_TARGET_FACES: int = 200_000
DEFAULT_POISSON_DEPTH: int = 10
DEFAULT_DENSITY_QUANTILE_CROP: float = 0.05


@dataclass(frozen=True)
class MeshExtractionResult:
    mesh_path: Path
    n_vertices: int
    n_faces: int
    n_gaussians_used: int


def _check_open3d_available() -> None:
    try:
        import open3d  # noqa: F401  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - testé sur PC GPU
        raise ImportError(
            "open3d est requis pour `extract_mesh`. Installer l'extra `mesh` "
            "(`uv sync --extra mesh --package road2track-ml`)."
        ) from e


def _sigmoid(x: NDArray[np.float32]) -> NDArray[np.float32]:
    return 1.0 / (1.0 + np.exp(-x))


def _sh_dc_to_rgb(sh_dc: NDArray[np.float32]) -> NDArray[np.float32]:
    """Approximation : RGB = SH_DC * 0.282 + 0.5, puis clip [0, 1]."""
    rgb = sh_dc * 0.28209479177387814 + 0.5
    return np.clip(rgb, 0.0, 1.0)


def _normals_from_gaussians(
    quats_wxyz: NDArray[np.float32], scales_log: NDArray[np.float32]
) -> NDArray[np.float32]:
    """La gaussienne approxime un disque ; la normale est l'axe de plus petit scale."""
    scales = np.exp(scales_log)
    smallest_axis_idx = np.argmin(scales, axis=1)  # (N,)

    quat_xyzw = quats_wxyz[:, [1, 2, 3, 0]]
    # Normaliser pour éviter une rotation dégénérée (gsplat sauvegarde wxyz non normés).
    norms = np.linalg.norm(quat_xyzw, axis=1, keepdims=True)
    quat_xyzw = quat_xyzw / np.clip(norms, 1e-9, None)
    rotations = Rotation.from_quat(quat_xyzw).as_matrix()  # (N, 3, 3)

    normals = np.take_along_axis(
        rotations, smallest_axis_idx[:, None, None].repeat(3, axis=1), axis=2
    ).squeeze(-1)
    return normals.astype(np.float32)


def extract_mesh_from_splat(
    scene_ply_path: Path,
    output_dir: Path,
    *,
    opacity_threshold: float = DEFAULT_OPACITY_THRESHOLD,
    target_faces: int = DEFAULT_TARGET_FACES,
    poisson_depth: int = DEFAULT_POISSON_DEPTH,
    density_quantile_crop: float = DEFAULT_DENSITY_QUANTILE_CROP,
) -> MeshExtractionResult:
    """Extrait un mesh triangulé depuis une scène GS.

    Args:
        scene_ply_path : chemin vers scene.ply produit par `train_gs`.
        output_dir : dossier où écrire mesh.obj.
        opacity_threshold : seuil sigmoid(opacity) pour garder une gaussienne.
        target_faces : nombre cible de faces après decimation.
        poisson_depth : profondeur octree Poisson (8-12 ; 10 = équilibre RAM/qualité).
        density_quantile_crop : on supprime les vertices sous ce quantile de densité.

    Returns:
        MeshExtractionResult avec le chemin .obj et les comptes.
    """
    _check_open3d_available()

    import open3d as o3d  # type: ignore[import-not-found]

    splat = read_gaussian_splat_ply(scene_ply_path)
    means = splat["means"]
    opacities = _sigmoid(splat["opacities_logit"])
    mask = opacities > opacity_threshold
    n_gaussians_used = int(mask.sum())
    if n_gaussians_used == 0:
        raise ValueError(
            f"aucune gaussienne au-dessus du seuil opacité {opacity_threshold} ; "
            "training probablement effondré"
        )

    means_f = means[mask].astype(np.float64)
    normals = _normals_from_gaussians(
        splat["quats_wxyz"][mask], splat["scales_log"][mask]
    ).astype(np.float64)
    colors = _sh_dc_to_rgb(splat["sh_dc"][mask]).astype(np.float64)

    pcd: Any = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(means_f)
    pcd.normals = o3d.utility.Vector3dVector(normals)
    pcd.colors = o3d.utility.Vector3dVector(colors)
    pcd.orient_normals_consistent_tangent_plane(k=30)

    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=poisson_depth
    )

    densities_np = np.asarray(densities)
    if densities_np.size > 0 and density_quantile_crop > 0.0:
        threshold = float(np.quantile(densities_np, density_quantile_crop))
        keep_mask = densities_np >= threshold
        mesh.remove_vertices_by_mask(np.logical_not(keep_mask))

    if len(mesh.triangles) > target_faces:
        mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=target_faces)

    mesh.compute_vertex_normals()

    output_dir.mkdir(parents=True, exist_ok=True)
    mesh_path = output_dir / "mesh.obj"
    o3d.io.write_triangle_mesh(
        str(mesh_path),
        mesh,
        write_ascii=False,
        write_vertex_colors=True,
        write_vertex_normals=True,
    )

    return MeshExtractionResult(
        mesh_path=mesh_path,
        n_vertices=int(len(mesh.vertices)),
        n_faces=int(len(mesh.triangles)),
        n_gaussians_used=n_gaussians_used,
    )
