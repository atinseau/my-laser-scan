"""Sampling spatial / temporel d'une trajectoire.

Cf. specs/04-pipeline-ml.md §3.1 (sélection des keyframes).
"""

from road2track_geo.sampling.spatial import (
    DEFAULT_MIN_SPACING_M,
    select_indices_by_spacing,
)

__all__ = ["DEFAULT_MIN_SPACING_M", "select_indices_by_spacing"]
