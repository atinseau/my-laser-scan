"""Entité Segment.

Cf. specs/06-modele-donnees.md §2.2.
Au POC, un segment agglomère les deux flux Record3D + Sensor Logger (ADR-017).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from road2track_core.ids import ProjectId, SegmentId


class SegmentSource(StrEnum):
    RECORD_3D_PLUS_SENSOR_LOGGER = "record3d_plus_sensor_logger"
    NATIVE_APP_V1 = "native_app_v1"


class Segment(BaseModel):
    schema_version: Literal[1] = 1
    id: SegmentId
    project_id: ProjectId
    source: SegmentSource
    captured_at: datetime
    duration_s: float = Field(ge=0.0)
    raw_paths: dict[str, str] = Field(default_factory=dict)
    fps: float = Field(default=0.0, ge=0.0)
    resolution: tuple[int, int] = Field(default=(0, 0))
    has_lidar: bool = True
    notes: str = ""
