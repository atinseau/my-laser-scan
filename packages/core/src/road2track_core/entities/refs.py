"""Refs légères et inputs/outputs des activités, transitant entre workflows et activités.

Pas de gros payloads en mémoire : on échange juste des clés MinIO + métadonnées
(cf. specs/02-architecture.md §7).

Ces classes vivent dans `core` (pas dans `pipeline.activities`) pour que les
workflows puissent les importer sans tirer d'adapter (règle dure ADR-012).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from road2track_core.entities.track_kind import TrackKind
from road2track_core.ids import ProjectId, SegmentId


class IngestInput(BaseModel):
    """Input de l'activité `ingest_session`."""

    schema_version: Literal[1] = 1
    project_id: ProjectId
    local_dir: str = Field(description="Chemin absolu local du dossier de capture")
    segment_id: SegmentId | None = Field(
        default=None,
        description="ID de segment à utiliser ; si None, on en génère un nouveau",
    )


class VideoMetadata(BaseModel):
    """Métadonnées immuables d'un fichier vidéo de capture."""

    model_config = ConfigDict(frozen=True)

    duration_s: float = Field(ge=0.0)
    fps: float = Field(ge=0.0)
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    codec: str = ""
    had_audio: bool = Field(
        default=False,
        description="Vrai si le fichier d'origine contenait un track audio "
        "(droppé pendant l'ingestion).",
    )
    bytes_before_audio_drop: int = Field(default=0, ge=0)
    bytes_after_audio_drop: int = Field(default=0, ge=0)


SyncMethod = Literal["utc_aligned", "cross_correlation", "fallback_zero"]


class SyncResult(BaseModel):
    """Résultat de la synchronisation Record3D ↔ Sensor Logger.

    Cf. specs/04-pipeline-ml.md §2.1 (étape 2) et ADR-017.
    """

    model_config = ConfigDict(frozen=True)

    drift_ms: float = Field(description="Drift brut entre les premiers timestamps des deux flux.")
    offset_applied_ms: float = Field(
        default=0.0,
        description="Offset à appliquer au flux IMU pour l'aligner sur ARKit. "
        "0 si UTC aligné ou fallback.",
    )
    method: SyncMethod
    correlation_max: float = Field(default=0.0, ge=-1.0, le=1.0)
    warning: str | None = None


class SegmentRef(BaseModel):
    """Référence à un segment ingéré, échangée entre activités."""

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    raw_uri_prefix: str = Field(description="Ex. s3://raw/<project_id>/<segment_id>/")
    file_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    video: VideoMetadata
    sync: SyncResult


class TrajectoryRef(BaseModel):
    """Référence à une trajectoire fusionnée (output de `fuse_sensors`).

    Cf. specs/04-pipeline-ml.md §2.2 et specs/06-modele-donnees.md §4.4.
    Au POC, le fichier est en JSON (Parquet en V1). Stocké sous
    `s3://intermediates/<project_id>/<segment_id>/trajectory.json`.
    """

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    trajectory_uri: str
    n_samples: int = Field(ge=0)
    duration_s: float = Field(ge=0.0)
    arc_length_m: float = Field(default=0.0, ge=0.0)
    origin_lat: float
    origin_lon: float
    origin_alt: float
    origin_t: float = Field(description="Timestamp UTC du fix GPS d'origine")
    alignment_rmse_m: float = Field(default=0.0, ge=0.0)
    n_gps_fixes_used: int = Field(default=0, ge=0)


class DetectedTrackRef(BaseModel):
    """Référence à une trajectoire tronquée + nature détectée (`detect_kind_and_trim`).

    Cf. specs/04-pipeline-ml.md §2.3, ADR-007, ADR-016. Pour SPECIALE aucun trim
    n'est appliqué (`n_samples_trimmed_at_start = 0`).
    """

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    track_kind: TrackKind
    trimmed_trajectory_uri: str
    n_samples: int = Field(ge=0)
    arc_length_m: float = Field(default=0.0, ge=0.0)
    loop_closure_distance_m: float = Field(
        ge=0.0,
        description="Distance euclidienne start↔end dans le repère ENU (m).",
    )
    n_samples_trimmed_at_start: int = Field(default=0, ge=0)


class SelectKeyframesInput(BaseModel):
    """Input de l'activité `select_keyframes`.

    On a besoin du `SegmentRef` pour retrouver la vidéo brute (raw bucket) et
    du `DetectedTrackRef` pour la trajectoire tronquée (intermediates bucket).
    """

    schema_version: Literal[1] = 1
    segment: SegmentRef
    detected: DetectedTrackRef


class KeyframesRef(BaseModel):
    """Référence aux keyframes sélectionnées (`select_keyframes`).

    Cf. specs/04-pipeline-ml.md §3.1. Au POC, on stocke chaque keyframe en JPEG
    sous `s3://intermediates/<project>/<segment>/keyframes/NNNN.jpg` et un
    manifest `keyframes.json` à la racine.
    """

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    manifest_uri: str
    images_uri_prefix: str
    n_keyframes: int = Field(ge=0)
    min_spacing_m: float = Field(ge=0.0)
    arc_length_m: float = Field(default=0.0, ge=0.0)
