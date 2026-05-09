"""Tests sur les générateurs d'ID ULID."""

from __future__ import annotations

import re

from road2track_core.ids import (
    new_project_id,
    new_segment_id,
    new_tile_id,
    new_track_id,
)

ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def test_project_id_format() -> None:
    pid = new_project_id()
    assert ULID_RE.match(pid), f"not a ULID: {pid}"


def test_segment_id_format() -> None:
    sid = new_segment_id()
    assert ULID_RE.match(sid)


def test_tile_id_format() -> None:
    tid = new_tile_id()
    assert ULID_RE.match(tid)


def test_track_id_format() -> None:
    tid = new_track_id()
    assert ULID_RE.match(tid)


def test_project_ids_are_unique() -> None:
    ids = {new_project_id() for _ in range(100)}
    assert len(ids) == 100
