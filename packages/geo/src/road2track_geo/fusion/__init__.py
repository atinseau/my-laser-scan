"""Fusion des capteurs Road2Track — sync timestamps, EKF (à venir), alignement multi-segments.

Cf. specs/02-architecture.md §4.2 et specs/04-pipeline-ml.md §2.
"""

from road2track_geo.fusion.sync import (
    CORRELATION_THRESHOLD,
    MAX_OFFSET_S,
    RESAMPLE_HZ,
    UTC_DRIFT_THRESHOLD_MS,
    compute_sync,
    cross_correlation_offset_ms,
)

__all__ = [
    "CORRELATION_THRESHOLD",
    "MAX_OFFSET_S",
    "RESAMPLE_HZ",
    "UTC_DRIFT_THRESHOLD_MS",
    "compute_sync",
    "cross_correlation_offset_ms",
]
