# 06 — Modèle de données

> Schemas Pydantic, formats des fichiers intermédiaires, structure du package final. Toute évolution structurante d'un schema **incrémente le `schema_version`** et est documentée ici.

## 1. Conventions

- Tous les schemas Pydantic v2 vivent dans `packages/core/src/road2track_core/entities/` ou `value_objects/`.
- Tous les manifests JSON portent un champ `schema_version: int`.
- Les coordonnées géographiques sont en **WGS84** (EPSG:4326) au stockage. L'espace de travail interne est **ENU local** au projet.
- Les axes 3D internes sont **Y-up** (compatible Blender et AC). Les conversions depuis ARKit (qui est Y-up aussi) sont triviales.
- Les unités sont **mètres**, **secondes**, **radians** internes ; les angles utilisateur (heading, etc.) en degrés.
- Les timestamps sont **UTC ISO 8601** avec millisecondes.
- Les identifiants sont des **ULID** (sortable, lisibles).

## 2. Entités domaine

### 2.1 `Project`

Un projet = un circuit en construction. Contient une ou plusieurs `Segment`.

```python
class ProjectStatus(StrEnum):
    DRAFT       = "draft"          # créé, pas encore de capture
    CAPTURING   = "capturing"      # au moins une session ingérée
    PROCESSING  = "processing"     # workflow Temporal en cours
    READY       = "ready"          # output disponible
    FAILED      = "failed"
    ARCHIVED    = "archived"

class Project(BaseModel):
    schema_version: Literal[1] = 1
    id: ProjectId                     # ULID
    name: str
    created_at: datetime
    updated_at: datetime
    status: ProjectStatus
    kind: TrackKind | None            # déterminé après détection
    origin_wgs84: GPSCoord | None     # origine ENU choisie au 1er ingest
    notes: str = ""
```

### 2.2 `Segment`

Une plage continue de capture. Plusieurs segments peuvent être ajoutés à un projet.

```python
class SegmentSource(StrEnum):
    RECORD_3D       = "record_3d"
    SENSOR_LOGGER   = "sensor_logger"
    NATIVE_APP_V1   = "native_app_v1"

class Segment(BaseModel):
    schema_version: Literal[1] = 1
    id: SegmentId
    project_id: ProjectId
    source: SegmentSource
    captured_at: datetime
    duration_s: float
    raw_paths: dict[str, str]           # ex. {"video": "s3://raw/proj/seg/video.mp4", ...}
    fps: float
    resolution: tuple[int, int]
    has_lidar: bool
    notes: str = ""
```

### 2.3 `Trajectory`

Trajectoire fusionnée 6DoF d'un projet (toutes sessions concaténées et alignées).

```python
class FusedPose(BaseModel):
    t: float                # secondes depuis le début
    pos: tuple[float, float, float]   # ENU local (x East, y Up, z Nord)
    quat: tuple[float, float, float, float]  # rotation, w x y z
    velocity: tuple[float, float, float]
    confidence: float       # [0, 1]

class Trajectory(BaseModel):
    schema_version: Literal[1] = 1
    project_id: ProjectId
    poses: list[FusedPose]              # éventuellement stocké en parquet pour les longs runs
    sample_rate_hz: float
    origin_wgs84: GPSCoord
    duration_s: float
    arc_length_m: float
```

Pour les longues trajectoires (15 km × 100 Hz = 5 M points), le tableau `poses` est en pratique stocké en **Parquet** sur MinIO et l'objet `Trajectory` ne contient que la `s3://...` URI + résumé statistique.

### 2.4 `Tile`

Une portion spatiale d'un projet, traitée en parallèle.

```python
class TileBounds(BaseModel):
    """Bornes d'index dans la trajectoire + bornes spatiales en ENU local."""
    start_idx: int
    end_idx: int
    arc_start_m: float
    arc_end_m: float
    bbox_enu: tuple[tuple[float, float, float], tuple[float, float, float]]

class TileStatus(StrEnum):
    PENDING        = "pending"
    SEGMENTING     = "segmenting"
    TRAINING_GS    = "training_gs"
    EXTRACTING     = "extracting_mesh"
    BAKING         = "baking"
    PBR            = "estimating_pbr"
    READY          = "ready"
    FAILED         = "failed"

class Tile(BaseModel):
    schema_version: Literal[1] = 1
    id: TileId
    project_id: ProjectId
    index: int                          # 0..N-1
    bounds: TileBounds
    status: TileStatus
    artifacts: dict[str, str] = {}      # clés MinIO des outputs intermédiaires
```

### 2.5 `Track`

Le résultat final livrable.

```python
class TrackKind(StrEnum):
    CIRCUIT  = "circuit"
    SPECIALE = "speciale"

class Track(BaseModel):
    schema_version: Literal[1] = 1
    project_id: ProjectId
    kind: TrackKind
    centerline_arc_length_m: float
    triangle_count: int
    package_uri: str                    # s3://outputs/<project>/track.zip
    cm_metadata: ContentManagerMetadata
    generated_at: datetime
```

### 2.6 `CoverageMap`

Pour le multi-passe : heatmap voxellisée des keyframes par zone.

```python
class VoxelKey(BaseModel):
    x: int  # indices entiers en grille 10x10x10 m
    y: int
    z: int

class CoverageVoxel(BaseModel):
    project_id: ProjectId
    key: VoxelKey
    keyframe_count: int
    avg_quality: float            # variance Laplacien moyenne, etc.

class CoverageMap(BaseModel):
    project_id: ProjectId
    cell_size_m: float = 10.0
    voxels: dict[str, CoverageVoxel]   # clé = "x:y:z"
```

## 3. Value Objects

```python
class GPSCoord(BaseModel):
    lat: float       # degrés décimaux
    lon: float
    alt: float       # mètres au-dessus du géoïde WGS84

class Pose(BaseModel):
    """Pose 6DoF dans un repère donné."""
    translation: tuple[float, float, float]
    quaternion: tuple[float, float, float, float]    # w, x, y, z

class BoundingBox3D(BaseModel):
    min_pt: tuple[float, float, float]
    max_pt: tuple[float, float, float]

class TimeRange(BaseModel):
    start: datetime
    end: datetime
```

## 4. Schemas des fichiers intermédiaires (par étape de pipeline)

### 4.1 `manifest.json` du projet

Stocké dans MinIO sous `s3://raw/<project_id>/manifest.json`.

```json
{
  "schema_version": 1,
  "project": {
    "id": "01HZ7M...",
    "name": "Col du Galibier descente",
    "created_at": "2026-05-01T08:23:11.342Z",
    "status": "capturing",
    "kind": null,
    "origin_wgs84": { "lat": 45.064, "lon": 6.408, "alt": 2645.0 },
    "notes": ""
  },
  "segments": [
    { "id": "01HZ7M...A", "captured_at": "...", "duration_s": 612.3, "...": "..." },
    { "id": "01HZ7M...B", "captured_at": "...", "duration_s": 388.1, "...": "..." }
  ]
}
```

### 4.2 Données de capture (Segment Record3D + Sensor Logger)

Format brut au POC :
```
s3://raw/<project_id>/<segment_id>/
├── record3d/
│   ├── video.mp4               # vidéo RGB compressée HEVC
│   ├── depth/                  # depth maps LiDAR par frame, format .depth ou .png 16-bit
│   ├── poses.json              # poses ARKit [{t, pos, quat}, ...]
│   └── metadata.json           # FPS, intrinsics, device
└── sensor_logger/
    ├── gps.json
    ├── imu.json                # accel + gyro
    ├── barometer.json
    └── magnetometer.json
```

### 4.3 `keyframes.json`

Sortie de `select_keyframes`. Référence sur les frames retenues.

```json
{
  "schema_version": 1,
  "project_id": "01HZ7M...",
  "tile_id": "01HZ7M...",
  "frames": [
    {
      "index": 142,
      "timestamp_s": 4.733,
      "image_uri": "s3://intermediates/.../frame_00142.jpg",
      "depth_uri": "s3://intermediates/.../depth_00142.npy",
      "pose": { "translation": [...], "quaternion": [...] },
      "intrinsics": [fx, fy, cx, cy, width, height],
      "sharpness": 412.7
    }
  ]
}
```

### 4.4 `trajectory.parquet`

Colonnes : `t`, `x`, `y`, `z`, `qw`, `qx`, `qy`, `qz`, `vx`, `vy`, `vz`, `confidence`.

### 4.5 `scene.ply`

Format standard binaire PLY étendu pour gsplat (positions, scales, rotations, opacities, SH coefs). Spécification : voir documentation gsplat.

### 4.6 `mesh.obj` + `vertex_attributes.npz`

- `mesh.obj` : standard.
- `vertex_attributes.npz` : `{ "labels": int32[N], "confidence": float32[N], "normals_smoothed": float32[N, 3] }`.

### 4.7 `textures/`

Par tuile :
```
textures/
├── albedo.png       # 4096×4096 ou 8192×8192 selon longueur
├── normal.png
├── roughness.png
├── ao.png            # optionnel
└── atlas_layout.json # mapping nom_objet → UV chunk
```

## 5. Format final — Content Manager

### 5.1 Structure du zip

```
road2track_<project_id>.zip
└── road2track_<project_id>/
    ├── road2track_<project_id>.kn5
    ├── data/
    │   ├── surfaces.ini
    │   ├── camera.ini
    │   ├── sections.ini
    │   ├── lighting.ini
    │   └── overlays.ini
    ├── ai/
    │   ├── fast_lane.ai
    │   └── pit_lane.ai
    ├── extension/                       # uniquement si spéciale (CSP)
    │   ├── ext_config.ini
    │   └── hill_climb.ini
    └── ui/
        ├── ui_track.json
        ├── preview.png       # 1920×1080 typiquement
        └── outline.png       # 800×600, vue de dessus
```

### 5.2 `ui_track.json`

```json
{
  "name": "Col du Galibier descente",
  "description": "Auto-généré depuis my-laser-scan",
  "tags": ["road2track", "speciale", "alpine"],
  "country": "France",
  "city": "Le Galibier",
  "geotags": ["Alpes"],
  "length": "8.4 km",
  "width": "6 m",
  "pitboxes": "1",
  "run": "Hillclimb",
  "author": "road2track",
  "version": "0.1.0"
}
```

### 5.3 `surfaces.ini`

Définit les frictions par classe de surface. Exemple minimal :

```ini
[SURFACE_0]
KEY=ROAD
FRICTION=0.96
DAMPING=0
WAV=
WAV_PITCH=
FF_EFFECT=
DIRT_ADDITIVE=0
IS_VALID_TRACK=1
BLACK_FLAG_TIME=0
SIN_HEIGHT=0.001
SIN_LENGTH=0.001
VIBRATION_GAIN=0.0
VIBRATION_LENGTH=0.0

[SURFACE_1]
KEY=KERB
FRICTION=0.94
...

[SURFACE_2]
KEY=GRASS
FRICTION=0.6
...
```

Détails complets dans les templates Jinja de `packages/ac_export/ini/templates/`.

### 5.4 `fast_lane.ai`

Format binaire AC. Encodage généré via `packages/ac_export/ai_line/`.

### 5.5 Cas spéciale — `extension/hill_climb.ini`

Pour les tracés point-à-point, dépendance CSP. Définit :
- `START_POINT` : coordonnées du début.
- `FINISH_LINE` : trigger de fin.
- `TIMING_MODE` : `point_to_point`.

## 6. Versioning des schemas

Chaque entité Pydantic a un `schema_version: Literal[N] = N`.

Quand on doit changer un schema :

1. Bumper le `Literal[N]` à `N+1` dans une nouvelle classe `XxxV2`.
2. Garder l'ancienne pour la lecture (`XxxV1`).
3. Écrire un migrateur dans `packages/storage/migrations/data/`.
4. Marquer une déprécation sur `XxxV1` avec date d'échéance (3 mois min).
5. Mettre à jour `06-modele-donnees.md` (ce document).
6. Documenter dans `08-decisions.md` si la migration touche le format public.

## 7. Tables Postgres

(Aperçu informel ; définition formelle dans `packages/storage/relational/models.py`.)

```
projects
  id ULID PK
  name text
  status varchar
  kind varchar nullable
  origin_lat double, origin_lon double, origin_alt double
  metadata jsonb
  created_at timestamptz
  updated_at timestamptz

segments
  id ULID PK
  project_id ULID FK
  source varchar
  captured_at timestamptz
  duration_s real
  raw_paths jsonb
  metadata jsonb
  created_at timestamptz

trajectories
  id ULID PK
  project_id ULID FK
  parquet_uri text
  sample_rate_hz real
  arc_length_m real
  duration_s real
  origin_lat double, origin_lon double, origin_alt double
  created_at timestamptz

tiles
  id ULID PK
  project_id ULID FK
  index int
  bounds jsonb
  status varchar
  artifacts jsonb
  created_at, updated_at timestamptz

tracks
  id ULID PK
  project_id ULID FK UNIQUE
  kind varchar
  package_uri text
  metadata jsonb
  generated_at timestamptz

coverage_voxels
  project_id ULID FK
  vx int, vy int, vz int
  keyframe_count int
  avg_quality real
  PRIMARY KEY (project_id, vx, vy, vz)
```

Index :
- `segments(project_id)`
- `tiles(project_id, index)`
- `coverage_voxels(project_id)`

## 8. Conventions de nommage des objets MinIO

```
s3://raw/<project_id>/manifest.json
s3://raw/<project_id>/<segment_id>/...

s3://intermediates/<project_id>/trajectory.parquet
s3://intermediates/<project_id>/coverage.json
s3://intermediates/<project_id>/<tile_id>/keyframes/
s3://intermediates/<project_id>/<tile_id>/segmentation/
s3://intermediates/<project_id>/<tile_id>/scene.ply
s3://intermediates/<project_id>/<tile_id>/mesh.obj
s3://intermediates/<project_id>/<tile_id>/textures/
s3://intermediates/<project_id>/stitched/track.fbx
s3://intermediates/<project_id>/stitched/textures/

s3://outputs/<project_id>/track.zip
```

## 9. Politique de rétention

- `raw/` : conservé indéfiniment (l'utilisateur peut vouloir retraiter).
- `intermediates/` : nettoyé après 30 jours d'inactivité (configurable). Reproductible depuis `raw/`.
- `outputs/` : conservé indéfiniment.

Tâche cron mensuelle : `uv run road2track maintenance gc-intermediates`.
