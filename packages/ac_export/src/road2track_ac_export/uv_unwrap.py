"""UV unwrap d'un mesh via xatlas.

Lazy import — `xatlas` n'est pas dans les deps de base (extra `fbx`).

L'unwrap génère pour chaque face un mapping (u, v) ∈ [0, 1]². Plusieurs faces
peuvent référencer le même sommet 3D avec des UVs différents — c'est la raison
pour laquelle xatlas retourne un `vmapping` qui duplique les sommets selon les
besoins de l'atlas.

Cf. https://github.com/jpcy/xatlas et https://github.com/mworchel/xatlas-python
pour la doc.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class UvUnwrapResult:
    """Output de xatlas — sommets potentiellement dupliqués pour produire un atlas valide."""

    vertices: NDArray[np.float64]  # (M, 3) — peut être > N initial
    faces: NDArray[np.int64]  # (F, 3)
    uvs: NDArray[np.float64]  # (M, 2) ∈ [0, 1]²
    vmapping: NDArray[np.int64]  # (M,) — index dans le mesh d'origine


def _check_xatlas_available() -> None:
    try:
        import xatlas  # noqa: F401  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - testé sur worker
        raise ImportError(
            "xatlas est requis pour `generate_fbx`. Installer l'extra `fbx` "
            "(`uv sync --extra fbx --package road2track-ac-export`)."
        ) from e


def unwrap_mesh_uvs(
    vertices: NDArray[np.float64],
    faces: NDArray[np.int64],
) -> UvUnwrapResult:
    """Calcule un UV atlas via xatlas et retourne les arrays dupliqués.

    Args:
        vertices : (N, 3) positions monde des sommets.
        faces : (F, 3) indices triangulaires.

    Returns:
        UvUnwrapResult avec sommets potentiellement dupliqués + UVs.
    """
    # Validation shape *avant* l'import xatlas pour que les erreurs métier
    # restent ValueError même quand l'extra `fbx` n'est pas installé.
    if vertices.ndim != 2 or vertices.shape[1] != 3:
        raise ValueError(f"vertices doit être (N, 3) ; got {vertices.shape}")
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError(f"faces doit être (F, 3) ; got {faces.shape}")
    if vertices.shape[0] == 0 or faces.shape[0] == 0:
        raise ValueError("vertices ou faces vides")

    _check_xatlas_available()
    import xatlas  # type: ignore[import-not-found]

    vmapping, indices, uvs = xatlas.parametrize(
        vertices.astype(np.float32), faces.astype(np.uint32)
    )
    new_vertices = vertices[vmapping]
    return UvUnwrapResult(
        vertices=new_vertices.astype(np.float64),
        faces=indices.astype(np.int64),
        uvs=uvs.astype(np.float64),
        vmapping=vmapping.astype(np.int64),
    )
