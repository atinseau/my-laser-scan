"""Identifiants uniques basés sur ULID (sortable, lisibles).

Cf. specs/06-modele-donnees.md §1 (ULID partout).
"""

from __future__ import annotations

from typing import TypeAlias

from ulid import ULID

ProjectId: TypeAlias = str
SegmentId: TypeAlias = str
TileId: TypeAlias = str
TrackId: TypeAlias = str


def new_project_id() -> ProjectId:
    return str(ULID())


def new_segment_id() -> SegmentId:
    return str(ULID())


def new_tile_id() -> TileId:
    return str(ULID())


def new_track_id() -> TrackId:
    return str(ULID())
