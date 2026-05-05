# 02 — Architecture

> Architecture en couches, **clean / hexagonale**. Le but est de pouvoir remplacer n'importe quelle implémentation lourde (lib ML, stockage, provider GPU) sans propager de modifications dans le code métier.

## 1. Vue système (machines physiques)

```
┌────────────────────────────────────────────┐
│  Mac M3 Max — Orchestrateur (sans GPU)     │
│                                            │
│  Infrastructure (Docker Compose)           │
│  ├─ Temporal server                        │
│  ├─ Temporal Web UI (port 8080)            │
│  ├─ Postgres × 2 (Temporal + applicatif)   │
│  ├─ MinIO (S3 local)                       │
│  └─ NATS (pub/sub events)                  │
│                                            │
│  Processus Python (uv)                     │
│  ├─ services/cpu_worker (queue: cpu)       │
│  ├─ services/api (FastAPI, V1+)            │
│  └─ services/cli (uv run road2track ...)   │
└──────────────────┬─────────────────────────┘
                   │ Tailscale (overlay réseau)
       ┌───────────┴────────────┐
       ▼                        ▼
┌──────────────────┐    ┌──────────────────┐
│  PC Windows      │    │  RunPod pod      │
│  RTX 4090        │    │  A100 / L40S     │
│                  │    │                  │
│  gpu_worker      │    │  gpu_worker      │
│  Docker + CUDA   │    │  Docker + CUDA   │
│  (queue: gpu)    │    │  (queue: gpu)    │
└──────────────────┘    └──────────────────┘
   permanent              à la demande
```

Détails matériels et infra dans [`05-infrastructure.md`](./05-infrastructure.md).

## 2. Vue logique (couches clean architecture)

```
┌─────────────────────────────────────────────────────────┐
│  4. Interface  (CLI, API, futur web)                    │
│     services/cli, services/api                          │
└──────────────────────────┬──────────────────────────────┘
                           │ dépend de
┌──────────────────────────▼──────────────────────────────┐
│  3. Application  (orchestration, use cases)             │
│     packages/pipeline                                   │
│     - workflows Temporal (déterministes, pure logique)  │
│     - activities (effets de bord, appels infra)         │
└──────────────────────────┬──────────────────────────────┘
                           │ dépend de
┌──────────────────────────▼──────────────────────────────┐
│  2. Adaptateurs  (implémentations concrètes)            │
│     packages/geo       (math, fusion capteurs)          │
│     packages/ml        (gsplat, 2DGS, segmentation, …)  │
│     packages/storage   (MinIO, fichiers, Postgres)      │
│     packages/ac_export (KN5, ini, AI line, CM)          │
│     packages/cloud_bridge (RunPod, Tailscale)           │
└──────────────────────────┬──────────────────────────────┘
                           │ dépend de
┌──────────────────────────▼──────────────────────────────┐
│  1. Domaine  (pur, aucun I/O, aucune lib lourde)        │
│     packages/core                                       │
│     - entities (Project, Segment, Trajectory, Tile, …)  │
│     - value objects (GPSCoord, Pose, BoundingBox, …)    │
│     - events (CaptureUploaded, …)                       │
│     - ports (interfaces : StoragePort, GPUProvider, …)  │
└─────────────────────────────────────────────────────────┘
```

### Règles d'inclusion

- `core` ne dépend que de la stdlib + Pydantic + types primitifs (numpy autorisé pour les value objects géométriques).
- `geo`, `ml`, `storage`, `ac_export`, `cloud_bridge` dépendent de `core` et de leurs libs spécifiques.
- `pipeline` dépend de `core` + des adapters dont il a besoin pour ses activités.
- `services/*` dépendent de `pipeline` (et indirectement de tout ce qui est nécessaire).
- **Aucune dépendance circulaire**. **Aucune flèche vers le haut.**

## 3. Workspace `uv`

```
my-laser-scan/
├── pyproject.toml                  # workspace root
├── uv.lock
├── packages/
│   ├── core/
│   │   └── pyproject.toml          # name: road2track-core
│   ├── geo/
│   │   └── pyproject.toml          # name: road2track-geo
│   ├── ml/
│   │   └── pyproject.toml          # name: road2track-ml
│   ├── storage/
│   │   └── pyproject.toml          # name: road2track-storage
│   ├── ac_export/
│   │   └── pyproject.toml          # name: road2track-ac-export
│   ├── cloud_bridge/
│   │   └── pyproject.toml          # name: road2track-cloud-bridge
│   └── pipeline/
│       └── pyproject.toml          # name: road2track-pipeline
└── services/
    ├── cpu_worker/
    │   └── pyproject.toml
    ├── gpu_worker/
    │   └── pyproject.toml
    ├── api/
    │   └── pyproject.toml
    └── cli/
        └── pyproject.toml
```

Le `pyproject.toml` racine déclare :
```toml
[tool.uv.workspace]
members = ["packages/*", "services/*"]
```

Chaque membre déclare ses dépendances internes avec `tool.uv.sources` :
```toml
# packages/pipeline/pyproject.toml
dependencies = [
    "road2track-core",
    "road2track-geo",
    "road2track-ml",
    "road2track-storage",
    "road2track-ac-export",
    "temporalio>=1.7.0",
]

[tool.uv.sources]
road2track-core = { workspace = true }
road2track-geo = { workspace = true }
# ...
```

## 4. Description détaillée par package

### 4.1 `core` (domaine)

**Responsabilités** : modéliser le domaine métier de manière pure, sans aucune dépendance d'infrastructure.

```
packages/core/src/road2track_core/
├── __init__.py
├── entities/
│   ├── project.py          # Project, ProjectStatus
│   ├── segment.py          # Segment, SegmentKind
│   ├── trajectory.py       # Trajectory, FusedPose
│   ├── tile.py             # Tile, TileBounds
│   ├── track.py            # Track, TrackKind (circuit/spéciale)
│   └── coverage.py         # CoverageMap, VoxelKey
├── value_objects/
│   ├── gps.py              # GPSCoord (lat, lon, alt)
│   ├── pose.py             # Pose (translation, rotation)
│   ├── bbox.py             # BoundingBox 2D / 3D
│   └── time_range.py
├── events/
│   └── domain_events.py    # CaptureUploaded, TileCompleted, ...
├── ports/
│   ├── storage_port.py     # interface abstraite
│   ├── gpu_provider_port.py
│   └── notification_port.py
├── queues.py               # TaskQueue enum (cpu, gpu)
└── errors.py               # exceptions domaine
```

**Interdits absolus dans `core`** :
- Aucun import de `requests`, `aiohttp`, `boto3`, `psycopg`, `temporalio`, `torch`, `cv2`, `open3d`.
- Aucune fonction asynchrone qui parle au monde extérieur.
- Aucun accès au filesystem.

### 4.2 `geo` (calculs géo)

**Responsabilités** : math géométrique et capteurs. Pure CPU, déterministe.

```
packages/geo/src/road2track_geo/
├── fusion/
│   ├── ekf.py              # Extended Kalman Filter GPS+IMU+ARKit
│   ├── alignment.py        # alignement multi-segment (ICP + GPS prior)
│   └── relocalization.py   # relocalisation visuelle entre sessions
├── projections/
│   ├── wgs84.py            # WGS84 ↔ ENU local
│   └── axes.py             # conventions d'axes (Y-up AC)
├── loop_detection/
│   └── detect.py           # circuit vs spéciale (algorithme MH-DET-1)
├── tiling/
│   ├── partition.py        # découpage spatial avec chevauchement
│   └── stitching.py        # recollage de tuiles
└── coverage/
    └── voxel_grid.py       # heatmap de couverture pour le multi-passe
```

### 4.3 `ml` (adaptateurs ML)

**Responsabilités** : interface vers les libs ML lourdes. Chaque sous-module expose une API stable, l'implémentation peut changer.

```
packages/ml/src/road2track_ml/
├── gs/
│   ├── trainer.py          # interface : train(input, output, config)
│   ├── _gsplat_impl.py     # implémentation actuelle
│   └── config.py           # GSConfig (Pydantic)
├── mesh/
│   ├── extractor.py        # interface : extract(scene_ply) -> mesh
│   └── _2dgs_impl.py
├── segmentation/
│   ├── segmenter.py        # interface : segment(images) -> masks
│   └── _mask2former_impl.py
├── pbr/
│   ├── estimator.py        # interface : estimate(mesh, views) -> maps
│   └── _neilf_impl.py
└── bake/
    └── multiview.py        # bake textures multi-vue (notre code custom)
```

Chaque interface est déclarée dans un Protocol (PEP 544) ou ABC. Les implémentations sont privées (`_*_impl.py`).

### 4.4 `storage` (adaptateurs stockage)

```
packages/storage/src/road2track_storage/
├── object/
│   ├── minio_adapter.py    # impl S3 via MinIO
│   └── local_fs_adapter.py # impl filesystem local (tests)
├── relational/
│   ├── postgres_adapter.py
│   └── models.py           # SQLAlchemy
└── repositories/
    ├── project_repo.py     # CRUD Project
    ├── segment_repo.py
    └── tile_repo.py
```

### 4.5 `ac_export` (génération de track AC)

```
packages/ac_export/src/road2track_ac_export/
├── kn5/
│   ├── compiler.py         # FBX → KN5 via ksEditor headless
│   └── fbx_writer.py       # écriture FBX depuis mesh + textures
├── ini/
│   ├── surfaces.py
│   ├── models.py
│   ├── camera.py
│   └── templates/
├── ai_line/
│   ├── generator.py        # B-spline lissage du centerline
│   └── bspline.py
├── content_manager/
│   ├── packager.py         # assemble le zip
│   ├── ui_track.py
│   └── preview.py          # génère preview.png + outline.png
└── circuit_or_spéciale.py  # branche les fichiers selon le kind
```

### 4.6 `cloud_bridge`

```
packages/cloud_bridge/src/road2track_cloud_bridge/
├── providers/
│   ├── base.py             # GPUProvider Protocol
│   ├── runpod.py
│   ├── vast.py
│   └── local_desktop.py    # PC Windows persistant
├── orchestrator.py         # logique : qui prend la prochaine tâche
└── tunnel.py               # helpers Tailscale
```

### 4.7 `pipeline` (cœur applicatif)

```
packages/pipeline/src/road2track_pipeline/
├── workflows/
│   ├── process_project.py  # workflow racine
│   ├── ingest_session.py
│   ├── tile_pipeline.py    # parent qui spawne N process_tile
│   ├── process_tile.py
│   └── stitch_tiles.py
├── activities/
│   ├── ingest.py
│   ├── fuse_sensors.py
│   ├── detect_kind.py      # circuit vs spéciale
│   ├── tile.py
│   ├── train_gs.py         # → queue gpu
│   ├── extract_mesh.py     # → queue gpu
│   ├── segment.py          # → queue gpu
│   ├── bake.py             # → queue gpu
│   ├── estimate_pbr.py     # → queue gpu
│   ├── stitch.py
│   ├── export_ac.py
│   └── notify.py
└── client.py               # helpers pour starter un workflow depuis API/CLI
```

**Règle critique pour les workflows Temporal** : les workflows doivent être **déterministes**. Pas de `datetime.now()` direct, pas de `random` non seedé, pas de I/O. Toute non-déterminisme → activité.

## 5. Patterns appliqués

### 5.1 Ports & Adapters (Hexagonal)

- Les **ports** sont définis dans `core/ports/` comme `Protocol`.
- Les **adapters** vivent dans `storage/`, `ml/`, `cloud_bridge/`.
- Le **pipeline** dépend des ports, pas des adapters concrets.
- L'injection se fait au démarrage des workers : un worker construit ses adapters concrets et les passe aux activités.

### 5.2 Command Pattern (CLI)

Chaque commande CLI (`uv run road2track <cmd>`) est une classe `Command` avec un `execute()`. Le routing est fait par Typer.

### 5.3 Repository Pattern

Toute persistance Postgres passe par des `*Repo` dans `storage/repositories/`. Le code applicatif ne voit jamais SQLAlchemy directement.

### 5.4 Workflow / Activity (Temporal)

- **Workflow** = orchestration, pure logique, aucune I/O directe.
- **Activity** = effet de bord, appel externe, peut tomber en erreur, peut être re-tentée par Temporal.
- **Une activité ne crée jamais un autre workflow directement** (sauf workflows enfants explicites). Elle exécute, retourne.

## 6. Communication entre composants

| De | Vers | Mécanisme |
|---|---|---|
| API / CLI | Workflow | `temporal_client.start_workflow(...)` |
| Workflow | Activity | `workflow.execute_activity(...)` avec `task_queue` |
| Activity (cpu) | Activity (gpu) | Workflow orchestre, Activity ne s'appelle jamais directement |
| Activity | MinIO | Adapter S3, fichiers identifiés par `s3://bucket/key` |
| Activity | Postgres | Repository pattern via `storage` |
| Backend | UI Web (V1) | NATS publish, UI souscrit en SSE/WebSocket |
| iOS app (V1) | Backend | HTTP via FastAPI, sur Tailscale |

## 7. Format des messages entre activités

- Les activités **n'échangent pas de gros payloads en mémoire**. Les fichiers (mesh, textures, .ply) transitent par MinIO via leur clé.
- Les activités s'échangent des **objets Pydantic légers** (`TileRef`, `MeshRef`, `TexturesRef`) qui contiennent les clés MinIO et les métadonnées.
- Les schemas de ces objets vivent dans `core/entities/` et sont versionnés.

## 8. Stratégie de tests

| Niveau | Lieu | Outil | But |
|---|---|---|---|
| Unitaire | `tests/unit/<package>/` | pytest | Tester chaque fonction pure (geo, core) |
| Intégration | `tests/integration/` | pytest + temporalio.testing | Tester les workflows en mode test (pas de Temporal réel, env in-memory) |
| Adapters | `tests/integration/storage/` | pytest + testcontainers | Tester les adapters contre du vrai MinIO / Postgres en container |
| End-to-end | `tests/e2e/` | pytest | Bout-en-bout sur dataset jouet |

Couverture cible : **80% sur `core` et `geo`, 60% sur `pipeline`**, le reste à effort.

## 9. Anti-patterns interdits

- ❌ Importer `temporalio.workflow` dans une activité.
- ❌ Importer un module ML (`gsplat`, `torch`) dans `core` ou `geo`.
- ❌ Faire un `Path("/...")` dans `core`.
- ❌ Mettre de la logique métier dans une activité (l'activité orchestre l'appel à un adapter, le résultat est traité par le workflow).
- ❌ Mettre de la logique métier dans un service (`services/*`). Les services ne font qu'orchestrer le démarrage et passer des paramètres.
- ❌ Définir un `class Project` ailleurs que dans `core/entities/project.py`.
- ❌ Faire des appels HTTP directs depuis une activité, sans passer par un adapter.
- ❌ Stocker des secrets en dur. Tous les secrets viennent de variables d'environnement chargées par les services.

## 10. Diagramme de flux d'un traitement complet

```
CLI: road2track process <project-id>
      │
      ▼
client.py → Temporal: start_workflow(ProcessProject, project_id)
      │
      ▼
Workflow: ProcessProject
      │
      ├─ activity.ingest_session                  [queue cpu]
      ├─ activity.fuse_sensors                    [queue cpu]
      ├─ activity.detect_kind (circuit/spéciale)  [queue cpu]
      ├─ activity.tile (découpage spatial)        [queue cpu]
      │
      └─ Pour chaque tuile en parallèle:
            workflow.start_child(ProcessTile, tile_ref)
                  │
                  ├─ activity.segment             [queue gpu]
                  ├─ activity.train_gs            [queue gpu]
                  ├─ activity.extract_mesh        [queue gpu]
                  ├─ activity.bake                [queue gpu]
                  └─ activity.estimate_pbr        [queue gpu]
      │
      ▼
      ├─ activity.stitch_tiles                    [queue cpu]
      ├─ activity.export_ac                       [queue cpu]
      └─ activity.notify                          [queue cpu]
      │
      ▼
Résultat : zip prêt dans MinIO, lien retourné au CLI
```

Détail de chaque étape dans [`04-pipeline-ml.md`](./04-pipeline-ml.md).
