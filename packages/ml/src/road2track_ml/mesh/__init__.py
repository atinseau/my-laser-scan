"""Extraction de mesh depuis un Gaussian Splat (étape 3.4 pipeline).

Cf. specs/04-pipeline-ml.md §3.4.
"""

from road2track_ml.mesh.extraction import (
    DEFAULT_OPACITY_THRESHOLD,
    DEFAULT_POISSON_DEPTH,
    DEFAULT_TARGET_FACES,
    MeshExtractionResult,
    extract_mesh_from_splat,
)

__all__ = [
    "DEFAULT_OPACITY_THRESHOLD",
    "DEFAULT_POISSON_DEPTH",
    "DEFAULT_TARGET_FACES",
    "MeshExtractionResult",
    "extract_mesh_from_splat",
]
