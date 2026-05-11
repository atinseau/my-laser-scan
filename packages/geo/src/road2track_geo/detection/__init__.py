"""Détection automatique du type de tracé (circuit vs spéciale) et trim du lead-in.

Cf. specs/04-pipeline-ml.md §2.3, ADR-007, ADR-016.
"""

from road2track_geo.detection.track_kind import (
    DEFAULT_LEAD_IN_THRESHOLD_M,
    DEFAULT_LOOP_CLOSURE_THRESHOLD_M,
    DEFAULT_MIN_CIRCUIT_ARC_LENGTH_M,
    detect_track_kind,
    find_lead_in_index,
)

__all__ = [
    "DEFAULT_LEAD_IN_THRESHOLD_M",
    "DEFAULT_LOOP_CLOSURE_THRESHOLD_M",
    "DEFAULT_MIN_CIRCUIT_ARC_LENGTH_M",
    "detect_track_kind",
    "find_lead_in_index",
]
