"""Entité Project.

Cf. specs/06-modele-donnees.md §2.1.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from road2track_core.entities.track_kind import TrackKind
from road2track_core.ids import ProjectId
from road2track_core.value_objects.gps import GPSCoord


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    CAPTURING = "capturing"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"


class Project(BaseModel):
    schema_version: Literal[1] = 1
    id: ProjectId
    name: str = Field(min_length=1, max_length=200)
    created_at: datetime
    updated_at: datetime
    status: ProjectStatus = ProjectStatus.DRAFT
    kind: TrackKind | None = None
    origin_wgs84: GPSCoord | None = None
    current_workflow_id: str | None = None
    notes: str = ""
