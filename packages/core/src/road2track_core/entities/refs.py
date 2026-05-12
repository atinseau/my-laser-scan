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


class SceneRef(BaseModel):
    """Référence à une scène Gaussian Splatting entraînée (`train_gs`).

    Cf. specs/04-pipeline-ml.md §3.3. Output : `scene.ply` + métadonnées
    d'entraînement (config gsplat, métriques PSNR/LPIPS, n_iterations).
    """

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    scene_uri: str = Field(description="s3://intermediates/<p>/<s>/scene.ply")
    metrics_uri: str = Field(
        description="s3://intermediates/<p>/<s>/training_metrics.json"
    )
    n_iterations: int = Field(default=0, ge=0)
    n_gaussians: int = Field(default=0, ge=0)


class MeshRef(BaseModel):
    """Référence à un mesh extrait depuis la scène GS (`extract_mesh`).

    Cf. specs/04-pipeline-ml.md §3.4. Mesh non texturé (`mesh.obj`) +
    métadonnées de décimation / UV unwrap.
    """

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    mesh_uri: str = Field(description="s3://intermediates/<p>/<s>/mesh.obj")
    n_vertices: int = Field(default=0, ge=0)
    n_faces: int = Field(default=0, ge=0)


class TexturedMeshRef(BaseModel):
    """Référence à un mesh texturé (`bake_textures`).

    Cf. specs/04-pipeline-ml.md §3.5. Mesh OBJ + atlas de textures + materials.
    """

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    mesh_uri: str
    texture_atlas_uri: str
    material_uri: str
    n_textures: int = Field(default=0, ge=0)
    n_textured_vertices: int = Field(default=0, ge=0)
    n_unseen_vertices: int = Field(default=0, ge=0)


class BakeTexturesInput(BaseModel):
    """Input de l'activité `bake_textures` (mesh + keyframes à projeter)."""

    schema_version: Literal[1] = 1
    mesh: MeshRef
    keyframes: KeyframesRef


class AcFilesRef(BaseModel):
    """Fichiers `.ini` + `ui_track.json` générés pour Assetto Corsa (It. 1).

    Cf. specs/04-pipeline-ml.md §3.5+ (export AC) et ADR-023 (composition workflows).
    """

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    surfaces_ini_uri: str
    models_ini_uri: str
    ui_track_json_uri: str


class FbxRef(BaseModel):
    """Mesh FBX exporté pour ksEditor (It. 1)."""

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    fbx_uri: str
    n_vertices: int = Field(default=0, ge=0)
    n_faces: int = Field(default=0, ge=0)


class AiLineRef(BaseModel):
    """`fast_lane.ai` généré depuis la trajectoire ENU (It. 1)."""

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    fast_lane_uri: str
    n_waypoints: int = Field(default=0, ge=0)


class Kn5Ref(BaseModel):
    """Binaire `.kn5` compilé via ksEditor sur Windows (It. 1)."""

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    kn5_uri: str
    bytes_size: int = Field(default=0, ge=0)


class TrackPackageRef(BaseModel):
    """Zip Content Manager final installable (It. 1).

    Endpoint stable du workflow `ExportAssettoCorsa` (cf. ADR-023).
    """

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    package_uri: str
    track_name: str
    bytes_size: int = Field(default=0, ge=0)


class ExportAcInput(BaseModel):
    """Input du workflow `ExportAssettoCorsa`.

    Bundle des refs produits par `ProcessProject` + métadonnées de track
    (nom affiché, country, etc.). On laisse le projet_id/segment_id remonter
    explicitement pour ne pas forcer la lecture depuis Postgres.
    """

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    textured_mesh: TexturedMeshRef
    detected: DetectedTrackRef
    track_name: str = Field(description="Nom affiché dans Content Manager.")
    track_author: str = Field(default="road2track", description="Auteur du circuit.")
    country: str = Field(default="France", description="Pays affiché par CM.")
    description: str = Field(
        default="", description="Description longue dans `ui_track.json`."
    )
