"""Entités domaine Road2Track.

Cf. specs/06-modele-donnees.md §2.
"""

from road2track_core.entities.project import Project, ProjectStatus
from road2track_core.entities.refs import IngestInput, SegmentRef
from road2track_core.entities.segment import Segment, SegmentSource
from road2track_core.entities.track_kind import TrackKind

__all__ = [
    "IngestInput",
    "Project",
    "ProjectStatus",
    "Segment",
    "SegmentRef",
    "SegmentSource",
    "TrackKind",
]
