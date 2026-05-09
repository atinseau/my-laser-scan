"""Tests sur la validation de structure de capture (sans MinIO réel)."""

from __future__ import annotations

from pathlib import Path

import pytest
from road2track_core.errors import InvalidSegmentError
from road2track_pipeline.activities.ingest import REQUIRED_PATHS, _validate_capture_dir


def test_validate_rejects_non_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-dir.txt"
    file_path.write_text("hello")
    with pytest.raises(InvalidSegmentError, match="not found"):
        _validate_capture_dir(file_path)


def test_validate_rejects_missing_required_files(tmp_path: Path) -> None:
    capture = tmp_path / "balade"
    (capture / "record3d").mkdir(parents=True)
    # poses.json manquant + sensor_logger entièrement manquant
    with pytest.raises(InvalidSegmentError, match="missing required files"):
        _validate_capture_dir(capture)


def test_validate_accepts_minimal_valid_layout(tmp_path: Path) -> None:
    capture = tmp_path / "balade"
    for rel in REQUIRED_PATHS:
        full = capture / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text("{}")
    # Doit ne rien lever
    _validate_capture_dir(capture)
