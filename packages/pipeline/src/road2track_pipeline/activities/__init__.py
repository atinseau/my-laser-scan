"""Activités Temporal du pipeline.

Effets de bord, appels externes, peuvent être ré-tentés par Temporal.
Cf. specs/02-architecture.md §4.7.

Les inputs/outputs Pydantic vivent dans `road2track_core.entities.refs`
pour pouvoir être importés par les workflows sans tirer d'adapter.
"""

from road2track_pipeline.activities.bake_textures import bake_textures
from road2track_pipeline.activities.detect_kind_and_trim import detect_kind_and_trim
from road2track_pipeline.activities.extract_mesh import extract_mesh
from road2track_pipeline.activities.fuse_sensors import fuse_sensors
from road2track_pipeline.activities.generate_ac_files import generate_ac_files
from road2track_pipeline.activities.ingest import ingest_session
from road2track_pipeline.activities.select_keyframes import select_keyframes
from road2track_pipeline.activities.train_gs import train_gs

__all__ = [
    "bake_textures",
    "detect_kind_and_trim",
    "extract_mesh",
    "fuse_sensors",
    "generate_ac_files",
    "ingest_session",
    "select_keyframes",
    "train_gs",
]
