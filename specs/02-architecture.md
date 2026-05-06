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
- `pipeline/` est divisé en deux sous-dossiers avec des règles **strictes** :
  - `pipeline/workflows/` ← dépend **uniquement** de `core` + signatures (types) d'activités. **Aucun import d'adapter** (`ml`, `storage`, `ac_export`, `cloud_bridge`). Cette règle garantit le **déterminisme Temporal** : un workflow rejoué doit produire la même séquence d'appels.
  - `pipeline/activities/` ← dépend de `core` + adapters concrets. Effets de bord autorisés.
- `services/*` dépendent de `pipeline` (et indirectement de tout ce qui est nécessaire).
- **Aucune dépendance circulaire**. **Aucune flèche vers le haut.**

### Garantie automatique de la règle workflows/adapters

La règle workflows ⇎ adapters est **vérifiée en CI** par un script de lint d'imports :

```bash
# scripts/check_workflow_imports.py
# Échec si un fichier sous packages/pipeline/src/.../workflows/
# importe un module sous packages/{ml,storage,ac_export,cloud_bridge}/.
```

Toute PR qui enfreint la règle est bloquée automatiquement.

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

Exemple complet d'un package racine de la couche domaine :

```toml
# packages/core/pyproject.toml
[project]
name = "road2track-core"
version = "0.1.0"
description = "Domaine pur — entités, value objects, ports, événements."
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.5",
    "numpy>=1.26",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "hypothesis", "pyright", "ruff"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/road2track_core"]
```

### Définition des task queues (centrale)

Toutes les task queues Temporal sont définies dans **un seul endroit** : `packages/core/src/road2track_core/queues.py`.

```python
from enum import StrEnum

class TaskQueue(StrEnum):
    CPU            = "cpu"             # workers Mac (orchestrateur), agnostique
    GPU            = "gpu"             # workers CUDA externes (PC + cloud)
    WINDOWS_TOOLS  = "windows-tools"   # workers Windows natifs (ksEditor pour KN5)
```

Chaque worker Python lit cette enum pour s'enregistrer sur la bonne queue. Voir [`05-infrastructure.md`](./05-infrastructure.md) pour le détail du déploiement de chaque type de worker.

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
│   ├── repository_port.py  # ProjectRepository, SegmentRepository, ...
│   └── notification_port.py
├── queues.py               # TaskQueue enum (cpu, gpu, windows-tools)
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
    ├── project_repo.py     # PostgresProjectRepository implements ProjectRepository (port)
    ├── segment_repo.py     # PostgresSegmentRepository implements SegmentRepository
    └── tile_repo.py        # PostgresTileRepository implements TileRepository
```

**Convention** : chaque repo concret implémente un Protocol défini dans `core/ports/repository_port.py`. Le code applicatif ne dépend que des Protocols, jamais des classes concrètes Postgres. Permet le swap (par ex. mock en tests, SQLite en local pour des essais ponctuels) sans propagation.

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
├── lifecycle.py            # cycle de vie des workers (spawn/shutdown/status)
└── tunnel.py               # helpers Tailscale
```

**Responsabilité limitée** : `cloud_bridge` gère **uniquement** le **cycle de vie** des workers (provisioning, shutdown, healthcheck). Il ne fait **aucun scheduling de tâches** — c'est Temporal qui s'en charge via les task queues. `lifecycle.py` expose des opérations comme `spawn_worker(provider, spec)`, `shutdown_worker(handle)`, `list_workers()`.

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
│   ├── ingest.py                  # → queue cpu
│   ├── fuse_sensors.py            # → queue cpu
│   ├── detect_kind_and_trim.py    # → queue cpu (circuit/spéciale + lead-in)
│   ├── tile.py                    # → queue cpu (découpage spatial)
│   ├── select_keyframes.py        # → queue cpu
│   ├── segment.py                 # → queue gpu (Mask2Former)
│   ├── train_gs.py                # → queue gpu
│   ├── extract_mesh.py            # → queue gpu (2DGS)
│   ├── segment_mesh.py            # → queue cpu (vote sur triangles)
│   ├── decimate_uv.py             # → queue cpu
│   ├── bake.py                    # → queue gpu (multi-vue)
│   ├── estimate_pbr.py            # → queue gpu (NeILF++)
│   ├── stitch.py                  # → queue cpu
│   ├── extract_centerline.py      # → queue cpu
│   ├── generate_ai_line.py        # → queue cpu
│   ├── generate_ac_track.py       # → queue cpu
│   ├── compile_kn5.py             # → queue windows-tools (ksEditor)
│   ├── package_content_manager.py # → queue cpu
│   └── notify.py                  # → queue cpu
└── client.py               # helpers pour starter un workflow depuis API/CLI
```

Liste exhaustive et détails des entrées/sorties dans [`04-pipeline-ml.md`](./04-pipeline-ml.md).

**Règle critique pour les workflows Temporal** : les workflows doivent être **déterministes**. Pas de `datetime.now()` direct, pas de `random` non seedé, pas de I/O. Toute non-déterminisme → activité.

**Invariant des activités** : chaque activité prend **un input Pydantic** et retourne **un output Pydantic**. Aucune mutation d'état global, aucun side-effect implicite. Permet de tester chaque activité unitairement avec un mock du contexte Temporal.

**Session activities pour le pipeline GPU d'une tuile** : les activités GPU `train_gs`, `extract_mesh`, `bake`, `estimate_pbr` sont **chaînées sur un même worker** via une session Temporal pour éviter les transferts MinIO redondants. Voir [ADR-019](./08-decisions.md#adr-019--session-activities-pour-chaîner-le-pipeline-gpu-dune-tuile).

## 5. Patterns appliqués

### 5.1 Ports & Adapters (Hexagonal)

- Les **ports** sont définis dans `core/ports/` comme `Protocol`.
- Les **adapters** vivent dans `storage/`, `ml/`, `cloud_bridge/`.
- Le **pipeline** dépend des ports, pas des adapters concrets.
- L'injection se fait au démarrage des workers : un worker construit ses adapters concrets et les passe aux activités.

### 5.2 CLI — fonctions Typer

Chaque commande CLI (`uv run road2track <cmd>`) est une **fonction Typer typée**. Pas de Command pattern, pas d'OOP forcée. Les inputs sont validés via Pydantic ou les types natifs Typer.

```python
# services/cli/src/main.py
import typer
app = typer.Typer()

@app.command()
def ingest(path: Path, project_id: str | None = None) -> None:
    ...

@app.command()
def process(project_id: str, force: bool = False) -> None:
    ...
```

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

### Optimisation : session activities pour le pipeline GPU

Pour éviter les transferts MinIO redondants entre activités GPU consécutives sur la même tuile (`train_gs` → `extract_mesh` → `bake` → `estimate_pbr`), Temporal **fixe ces activités sur un même worker** via une session. Le `scene.ply` (~2-5 Go) reste en cache local du worker entre les étapes.

```python
# pipeline/workflows/process_tile.py (vue simplifiée)
async with workflow.session(task_queue=TaskQueue.GPU) as session:
    scene = await session.execute_activity(train_gs, tile_ref)
    mesh = await session.execute_activity(extract_mesh, scene)
    textures = await session.execute_activity(bake, mesh, scene)
    pbr = await session.execute_activity(estimate_pbr, mesh, textures)
```

Voir [ADR-019](./08-decisions.md#adr-019--session-activities-pour-chaîner-le-pipeline-gpu-dune-tuile).

### Convention de logging structuré

Tous les services émettent des logs **JSON via `structlog`**. Champs minimaux **toujours** présents :
- `project_id`
- `segment_id` (si applicable)
- `tile_id` (si applicable)
- `workflow_id` (Temporal)
- `activity_name` (Temporal)
- `worker_name` / `host`
- `level`, `timestamp_utc`, `message`

Permet la corrélation cross-machine via Loki + Grafana (cf. [`05-infrastructure.md §9`](./05-infrastructure.md#9-observabilité-optionnelle-v1)).

### Health check au démarrage de chaque worker

Chaque worker (cpu, gpu, windows-tools) exécute une **séquence de vérifications** avant de prendre des tâches :

| Worker | Vérifications |
|---|---|
| `cpu_worker` | Connexion Postgres, MinIO, NATS, Temporal frontend joignable |
| `gpu_worker` | Tous les checks `cpu_worker` + CUDA dispo + version driver compatible + mémoire VRAM ≥ seuil |
| `windows-worker` | Tous les checks `cpu_worker` + `ksEditor.exe` exécutable |

En cas d'échec : exit code ≠ 0 + log d'erreur explicite. Pas de "fail silent".

## 8. Stratégie de tests

| Niveau | Lieu | Outil | But |
|---|---|---|---|
| Unitaire | `tests/unit/<package>/` | pytest, pytest-mock, **hypothesis** | Tester chaque fonction pure (geo, core). Property-based pour la math géométrique (transformations WGS84↔ENU, fusion EKF, rotations quaternions). |
| Intégration | `tests/integration/` | pytest + temporalio.testing | Tester les workflows en mode test (pas de Temporal réel, env in-memory). Activités mockées par défaut, déterminisme vérifié. |
| Adapters | `tests/integration/storage/` | pytest + testcontainers | Tester les adapters contre du vrai MinIO / Postgres en container |
| End-to-end | `tests/e2e/` | pytest | Bout-en-bout sur dataset jouet |

Couverture cible : **80% sur `core` et `geo`, 60% sur `pipeline`**, le reste à effort.

## 9. Anti-patterns interdits

- ❌ Importer `temporalio.workflow` dans une activité.
- ❌ **Importer un adapter** (`road2track_ml`, `road2track_storage`, `road2track_ac_export`, `road2track_cloud_bridge`) **dans un fichier sous `pipeline/workflows/`**. Vérifié par lint en CI.
- ❌ Importer un module ML (`gsplat`, `torch`) dans `core` ou `geo`.
- ❌ Faire un `Path("/...")` dans `core`.
- ❌ Mettre de la logique métier dans une activité (l'activité orchestre l'appel à un adapter, le résultat est traité par le workflow).
- ❌ Mettre de la logique métier dans un service (`services/*`). Les services ne font qu'orchestrer le démarrage et passer des paramètres.
- ❌ Définir un `class Project` ailleurs que dans `core/entities/project.py`.
- ❌ Faire des appels HTTP directs depuis une activité, sans passer par un adapter.
- ❌ Stocker des secrets en dur. Tous les secrets viennent de variables d'environnement chargées par les services.
- ❌ Coder un scheduling de tâches dans `cloud_bridge`. Le scheduling, c'est Temporal.

## 10. Diagramme de flux d'un traitement complet

> **Vue simplifiée.** Le pipeline complet a 19 étapes, détaillées dans [`04-pipeline-ml.md`](./04-pipeline-ml.md). Ci-dessous on regroupe par catégorie pour la lisibilité.

```
CLI: road2track process <project-id>
      │
      ▼
client.py → Temporal: start_workflow(ProcessProject, project_id)
      │
      ▼
Workflow: ProcessProject
      │
      ├─ activity.ingest_session                       [queue cpu]
      ├─ activity.fuse_sensors                         [queue cpu]
      ├─ activity.detect_kind_and_trim                 [queue cpu]
      ├─ activity.tile (découpage spatial)             [queue cpu]
      │
      └─ Pour chaque tuile en parallèle:
            workflow.start_child(ProcessTile, tile_ref)
                  │
                  ├─ activity.select_keyframes         [queue cpu]
                  │
                  └─ Session GPU (même worker, fichiers en cache local) :
                        ├─ activity.segment            [queue gpu]
                        ├─ activity.train_gs           [queue gpu]
                        ├─ activity.extract_mesh       [queue gpu]
                        ├─ activity.bake               [queue gpu]
                        └─ activity.estimate_pbr       [queue gpu]
                  │
                  ├─ activity.segment_mesh             [queue cpu]
                  └─ activity.decimate_uv              [queue cpu]
      │
      ▼
      ├─ activity.stitch                               [queue cpu]
      ├─ activity.extract_centerline                   [queue cpu]
      ├─ activity.generate_ai_line                     [queue cpu]
      ├─ activity.generate_ac_track                    [queue cpu]
      ├─ activity.compile_kn5                          [queue windows-tools]
      ├─ activity.package_content_manager              [queue cpu]
      └─ activity.notify                               [queue cpu]
      │
      ▼
Résultat : zip prêt dans MinIO, lien retourné au CLI
```

Détail de chaque étape dans [`04-pipeline-ml.md`](./04-pipeline-ml.md).
