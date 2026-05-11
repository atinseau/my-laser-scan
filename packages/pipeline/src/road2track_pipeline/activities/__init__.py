"""Activités Temporal du pipeline.

Effets de bord, appels externes, peuvent être ré-tentés par Temporal.
Cf. specs/02-architecture.md §4.7.

Les inputs/outputs Pydantic vivent dans `road2track_core.entities.refs`
pour pouvoir être importés par les workflows sans tirer d'adapter.
"""

from road2track_pipeline.activities.detect_kind_and_trim import detect_kind_and_trim
from road2track_pipeline.activities.fuse_sensors import fuse_sensors
from road2track_pipeline.activities.ingest import ingest_session
from road2track_pipeline.activities.select_keyframes import select_keyframes

__all__ = [
    "detect_kind_and_trim",
    "fuse_sensors",
    "ingest_session",
    "select_keyframes",
]
