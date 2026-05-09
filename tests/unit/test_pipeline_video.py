"""Tests sur le helper ffprobe / ffmpeg de l'activité ingest.

Subprocess et binaire externe sont mockés (pas besoin de ffmpeg installé).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from road2track_core.errors import InvalidSegmentError
from road2track_pipeline.activities._video import (
    _parse_fps,
    drop_audio_track,
    find_video_file,
    probe_video,
)

# ---------- Helpers purs ----------


def test_parse_fps_fraction() -> None:
    assert _parse_fps("60/1") == 60.0
    assert _parse_fps("30000/1001") == pytest.approx(29.97, rel=0.01)


def test_parse_fps_zero_or_empty() -> None:
    assert _parse_fps("0/0") == 0.0
    assert _parse_fps("") == 0.0


def test_parse_fps_plain_number() -> None:
    assert _parse_fps("60") == 60.0


def test_parse_fps_zero_denominator() -> None:
    assert _parse_fps("60/0") == 0.0


# ---------- find_video_file ----------


def test_find_video_file_mp4(tmp_path: Path) -> None:
    record3d = tmp_path / "record3d"
    record3d.mkdir()
    video = record3d / "video.mp4"
    video.write_bytes(b"")
    assert find_video_file(tmp_path) == video


def test_find_video_file_mov_fallback(tmp_path: Path) -> None:
    record3d = tmp_path / "record3d"
    record3d.mkdir()
    video = record3d / "video.mov"
    video.write_bytes(b"")
    assert find_video_file(tmp_path) == video


def test_find_video_file_missing(tmp_path: Path) -> None:
    (tmp_path / "record3d").mkdir()
    with pytest.raises(InvalidSegmentError, match="aucun fichier"):
        find_video_file(tmp_path)


# ---------- probe_video ----------


def _make_proc(stdout: bytes, stderr: bytes, returncode: int) -> AsyncMock:
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    return proc


@pytest.mark.asyncio
async def test_probe_video_extracts_metadata(tmp_path: Path) -> None:
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"")
    fake_json = json.dumps(
        {
            "format": {"duration": "120.5", "size": "1024000"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "hevc",
                    "width": 3840,
                    "height": 2160,
                    "r_frame_rate": "60/1",
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
    ).encode()
    proc = _make_proc(fake_json, b"", 0)

    async def fake_exec(*_args: object, **_kwargs: object) -> AsyncMock:
        return proc

    with (
        patch("shutil.which", return_value="/usr/bin/ffprobe"),
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
    ):
        result = await probe_video(fake_video)

    assert result.duration_s == 120.5
    assert result.fps == 60.0
    assert result.width == 3840
    assert result.height == 2160
    assert result.codec == "hevc"
    assert result.has_audio is True
    assert result.bytes_size == 1024000


@pytest.mark.asyncio
async def test_probe_video_no_audio_stream(tmp_path: Path) -> None:
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"")
    fake_json = json.dumps(
        {
            "format": {"duration": "60.0", "size": "500000"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30/1",
                }
            ],
        }
    ).encode()
    proc = _make_proc(fake_json, b"", 0)

    async def fake_exec(*_args: object, **_kwargs: object) -> AsyncMock:
        return proc

    with (
        patch("shutil.which", return_value="/usr/bin/ffprobe"),
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
    ):
        result = await probe_video(fake_video)
    assert result.has_audio is False


@pytest.mark.asyncio
async def test_probe_video_no_video_stream_raises(tmp_path: Path) -> None:
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"")
    fake_json = json.dumps(
        {"format": {"duration": "0", "size": "0"}, "streams": []}
    ).encode()
    proc = _make_proc(fake_json, b"", 0)

    async def fake_exec(*_args: object, **_kwargs: object) -> AsyncMock:
        return proc

    with (
        patch("shutil.which", return_value="/usr/bin/ffprobe"),
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        pytest.raises(InvalidSegmentError, match="aucun stream vidéo"),
    ):
        await probe_video(fake_video)


@pytest.mark.asyncio
async def test_probe_video_subprocess_failure(tmp_path: Path) -> None:
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"")
    proc = _make_proc(b"", b"corrupt file", 1)

    async def fake_exec(*_args: object, **_kwargs: object) -> AsyncMock:
        return proc

    with (
        patch("shutil.which", return_value="/usr/bin/ffprobe"),
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        pytest.raises(InvalidSegmentError, match="ffprobe a échoué"),
    ):
        await probe_video(fake_video)


@pytest.mark.asyncio
async def test_probe_video_missing_binary(tmp_path: Path) -> None:
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"")
    with (
        patch("shutil.which", return_value=None),
        pytest.raises(InvalidSegmentError, match="ffprobe"),
    ):
        await probe_video(fake_video)


# ---------- drop_audio_track ----------


@pytest.mark.asyncio
async def test_drop_audio_track_returns_size(tmp_path: Path) -> None:
    input_path = tmp_path / "video.mp4"
    input_path.write_bytes(b"original-with-audio")
    output_path = tmp_path / "out" / "video.mp4"

    async def fake_exec(*_args: object, **_kwargs: object) -> AsyncMock:
        proc = _make_proc(b"", b"", 0)
        # Simule la création du fichier de sortie par ffmpeg.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"shorter")
        return proc

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
    ):
        size = await drop_audio_track(input_path, output_path)

    assert size == len(b"shorter")
    assert output_path.exists()


@pytest.mark.asyncio
async def test_drop_audio_track_failure(tmp_path: Path) -> None:
    input_path = tmp_path / "video.mp4"
    input_path.write_bytes(b"x")
    output_path = tmp_path / "out" / "video.mp4"

    async def fake_exec(*_args: object, **_kwargs: object) -> AsyncMock:
        return _make_proc(b"", b"unsupported codec", 1)

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        pytest.raises(InvalidSegmentError, match="ffmpeg a échoué"),
    ):
        await drop_audio_track(input_path, output_path)
