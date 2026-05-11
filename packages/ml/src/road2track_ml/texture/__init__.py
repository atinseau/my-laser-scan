"""Baking de textures sur mesh (étape 3.5 pipeline).

Cf. specs/04-pipeline-ml.md §3.5.
"""

from road2track_ml.texture.baking import (
    DEFAULT_ATLAS_SIZE,
    DEFAULT_VIEW_ANGLE_THRESHOLD,
    BakeResult,
    bake_textures_for_mesh,
)

__all__ = [
    "DEFAULT_ATLAS_SIZE",
    "DEFAULT_VIEW_ANGLE_THRESHOLD",
    "BakeResult",
    "bake_textures_for_mesh",
]
