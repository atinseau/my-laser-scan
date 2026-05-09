"""Tests sur les entités du domaine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from road2track_core.entities import (
    IngestInput,
    Project,
    ProjectStatus,
    Segment,
    SegmentRef,
    SegmentSource,
    TrackKind,
)
from road2track_core.ids import new_project_id, new_segment_id
from road2track_core.value_objects.gps import GPSCoord


def test_project_minimum() -> None:
    now = datetime.now(tz=UTC)
    p = Project(id=new_project_id(), name="Mon premier circuit", created_at=now, updated_at=now)
    assert p.schema_version == 1
    assert p.status == ProjectStatus.DRAFT
    assert p.kind is None
    assert p.origin_wgs84 is None
    assert p.current_workflow_id is None


def test_project_name_must_not_be_empty() -> None:
    now = datetime.now(tz=UTC)
    with pytest.raises(ValidationError):
        Project(id=new_project_id(), name="", created_at=now, updated_at=now)


def test_project_with_kind_circuit() -> None:
    now = datetime.now(tz=UTC)
    p = Project(
        id=new_project_id(),
        name="Galibier",
        created_at=now,
        updated_at=now,
        status=ProjectStatus.READY,
        kind=TrackKind.SPECIALE,
        origin_wgs84=GPSCoord(lat=45.064, lon=6.408, alt=2645.0),
    )
    assert p.kind == TrackKind.SPECIALE
    assert p.origin_wgs84 is not None
    assert p.origin_wgs84.alt == 2645.0


def test_segment_default_source_record3d_plus_sensor_logger() -> None:
    now = datetime.now(tz=UTC)
    s = Segment(
        id=new_segment_id(),
        project_id=new_project_id(),
        source=SegmentSource.RECORD_3D_PLUS_SENSOR_LOGGER,
        captured_at=now,
        duration_s=120.5,
    )
    assert s.source == SegmentSource.RECORD_3D_PLUS_SENSOR_LOGGER
    assert s.has_lidar is True
    assert s.fps == 0.0


def test_segment_duration_must_be_positive() -> None:
    now = datetime.now(tz=UTC)
    with pytest.raises(ValidationError):
        Segment(
            id=new_segment_id(),
            project_id=new_project_id(),
            source=SegmentSource.RECORD_3D_PLUS_SENSOR_LOGGER,
            captured_at=now,
            duration_s=-1.0,
        )


def test_ingest_input_optional_segment_id() -> None:
    payload = IngestInput(project_id=new_project_id(), local_dir="/tmp/foo")
    assert payload.segment_id is None


def test_segment_ref_validation() -> None:
    ref = SegmentRef(
        project_id=new_project_id(),
        segment_id=new_segment_id(),
        raw_uri_prefix="s3://raw/x/y/",
        file_count=10,
        total_bytes=1024,
    )
    assert ref.file_count == 10


def test_segment_ref_negative_count_rejected() -> None:
    with pytest.raises(ValidationError):
        SegmentRef(
            project_id=new_project_id(),
            segment_id=new_segment_id(),
            raw_uri_prefix="s3://raw/x/y/",
            file_count=-1,
            total_bytes=0,
        )


def test_gps_coord_frozen() -> None:
    g = GPSCoord(lat=45.0, lon=6.0, alt=100.0)
    with pytest.raises(ValidationError):
        g.lat = 0.0  # type: ignore[misc]


def test_gps_coord_lat_bounds() -> None:
    with pytest.raises(ValidationError):
        GPSCoord(lat=91.0, lon=0.0, alt=0.0)
    with pytest.raises(ValidationError):
        GPSCoord(lat=-91.0, lon=0.0, alt=0.0)
