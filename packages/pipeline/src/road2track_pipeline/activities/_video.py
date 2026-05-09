"""Helpers ffprobe / ffmpeg pour l'activité `ingest_session`.

Wrappers minces, async, autour des binaires `ffprobe` et `ffmpeg`. Ces binaires
doivent être installés sur la machine où tourne le `cpu_worker` (sur le Mac
d'orchestration : `brew install ffmpeg`). Cf. specs/03-stack-technique.md §1.

Module privé volontairement (préfixe `_`) — réutilisable seulement par les
activités voisines, pas un adapter exposé. Si le besoin émerge ailleurs,
on le promouvra dans un package dédié.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import structlog
from pydantic import BaseModel, Field
from road2track_core.errors import InvalidSegmentError

logger = structlog.get_logger(__name__)


class VideoProbeResult(BaseModel):
    """Résultat brut d'un appel à ffprobe sur un fichier vidéo."""

    duration_s: float = Field(ge=0.0)
    fps: float = Field(ge=0.0)
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    codec: str = ""
    has_audio: bool = False
    bytes_size: int = Field(ge=0)


def _ensure_binary(name: str) -> None:
    """Vérifie qu'un binaire est dans le PATH ; lève InvalidSegmentError sinon."""
    if shutil.which(name) is None:
        raise InvalidSegmentError(
            f"binaire requis introuvable dans le PATH : {name}. "
            "Sur macOS : `brew install ffmpeg`. "
            "Cf. specs/03-stack-technique.md §1."
        )


def _parse_fps(rate_str: str) -> float:
    """Convertit un fraction ffmpeg (ex. '60/1', '30000/1001') en float."""
    if not rate_str or rate_str == "0/0":
        return 0.0
    if "/" in rate_str:
        num_str, _, den_str = rate_str.partition("/")
        num = float(num_str)
        den = float(den_str) if den_str else 1.0
        return num / den if den != 0 else 0.0
    return float(rate_str)


async def probe_video(path: Path) -> VideoProbeResult:
    """Probe un fichier vidéo via ffprobe et retourne ses métadonnées."""
    _ensure_binary("ffprobe")
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise InvalidSegmentError(
            f"ffprobe a échoué sur {path}: {stderr.decode(errors='replace').strip()}"
        )

    data = json.loads(stdout)
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video_stream is None:
        raise InvalidSegmentError(f"aucun stream vidéo dans {path}")

    duration = float(fmt.get("duration", 0.0))
    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    fps = _parse_fps(video_stream.get("r_frame_rate", "0/0"))
    codec = str(video_stream.get("codec_name", ""))
    bytes_size = int(fmt.get("size", 0))

    return VideoProbeResult(
        duration_s=duration,
        fps=fps,
        width=width,
        height=height,
        codec=codec,
        has_audio=audio_stream is not None,
        bytes_size=bytes_size,
    )


async def drop_audio_track(input_path: Path, output_path: Path) -> int:
    """Re-multiplexe la vidéo en gardant uniquement le stream vidéo.

    Pas de ré-encodage (`-c copy`) — opération rapide, sans perte. Cf. spec §2.1
    étape 5 : on économise ~10% de la taille.

    Retourne la taille en bytes du fichier de sortie.
    """
    _ensure_binary("ffmpeg")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",                  # overwrite
        "-i", str(input_path),
        "-map", "0:v:0",       # premier stream vidéo
        "-c:v", "copy",        # pas de ré-encodage
        "-an",                 # drop audio
        str(output_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise InvalidSegmentError(
            f"ffmpeg a échoué sur {input_path}: {stderr.decode(errors='replace').strip()}"
        )

    size = output_path.stat().st_size
    logger.info(
        "audio dropped",
        input=str(input_path),
        output=str(output_path),
        bytes_after=size,
    )
    return size


def find_video_file(local_dir: Path) -> Path:
    """Localise le fichier vidéo Record3D (record3d/video.{mp4,mov,m4v})."""
    record3d = local_dir / "record3d"
    for ext in ("mp4", "mov", "m4v"):
        candidate = record3d / f"video.{ext}"
        if candidate.is_file():
            return candidate
    raise InvalidSegmentError(
        f"aucun fichier video.{{mp4,mov,m4v}} trouvé dans {record3d}"
    )
