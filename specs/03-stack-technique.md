# 03 — Stack technique

> Référence exhaustive des technologies retenues, des versions cibles et des alternatives rejetées. Tout ajout d'une nouvelle dépendance doit être documenté ici (avec une justification courte et l'alternative envisagée).

## 1. Tableau de synthèse

| Catégorie | Choix | Version cible | Pourquoi |
|---|---|---|---|
| Runtime | Python | **≥ 3.11** (cible 3.12) | Performances, typing améliorés, support Temporal SDK. Fallback 3.11 si une lib ML coince. |
| Gestion deps | uv | dernière stable | Fast, workspace-aware, lockfile reproductible |
| Orchestrateur | Temporal | 1.x (Python SDK ≥ 1.7) | Durable execution, workflows long-runs, multi-queue |
| HTTP API | FastAPI | ≥ 0.110 | Pydantic v2 natif, async, OpenAPI auto |
| ASGI server | uvicorn | dernière stable | Standard FastAPI |
| Validation / schemas | Pydantic | v2 | Typage strict, perf rust core |
| Object storage | MinIO | dernière stable (2024+) | S3 compatible, déployable local |
| DB applicative | Postgres | 16 | Stable, mature, JSON natif |
| ORM | SQLAlchemy | 2.x (style 2.0) | Mature, typed, supporte async |
| Migrations | Alembic | dernière stable | Standard SQLAlchemy |
| Pub/sub events | NATS | 2.10+ | Léger, bas overhead, parfait pour notifs |
| Containerisation | Docker | Engine 24+ | Standard |
| Compose | Docker Compose | v2 | Standard |
| Réseau overlay | Tailscale | dernière stable | Zero-config mesh, MagicDNS |
| GPU runtime | CUDA | 12.4 | Compatibilité gsplat/2DGS récents. **Driver NVIDIA ≥ R550** (Linux) / **R551** (Windows). |
| ML — GS training | gsplat | dernière stable | Implémentation officielle Nerfstudio, perf |
| ML — Mesh extraction | 2DGS | repo officiel | Mesh propre depuis splats |
| ML — Segmentation | Mask2Former (HF) | via `transformers` 4.40+ | Modèle SOTA, dispo Hugging Face |
| ML — PBR | NeILF++ | repo officiel | Estimation PBR depuis multi-vue |
| 3D ops CPU | Open3D | dernière stable | ICP, point cloud ops |
| 3D ops avancé | PyTorch3D | dernière stable | Mesh ops avec autograd |
| Géo math | PyProj, NumPy, SciPy | stables | Standard |
| Image | OpenCV (`cv2`), Pillow | stables | Standard |
| Mesh / FBX | Blender | 4.2 LTS | Bake, FBX, scriptable Python |
| Track AC build | ksEditor | binaire fourni | Compilation KN5 (Windows) |
| Tests | pytest + pytest-asyncio | dernières stables | Standard |
| Tests — mocking | pytest-mock | dernière stable | Mocks idiomatiques (mocker fixture) |
| Tests — property-based | hypothesis | dernière stable | Tests de propriétés mathématiques sur `geo` (rotations, projections, EKF) |
| Tests Temporal | `temporalio.testing` | inclus dans SDK | Workflows en env in-memory |
| Tests containers | testcontainers | dernière stable | Postgres / MinIO en intégration |
| Lint / format | ruff | dernière stable | Rapide, remplace black + isort + flake8 |
| Type checking | pyright (strict) | dernière stable | Plus strict que mypy, supporte Pydantic v2 |
| Logs | structlog | dernière stable | JSON, contextual |
| Observabilité | OpenTelemetry | dernière stable | Standard |
| Stack obs locale | Grafana + Loki + Tempo | dernière stable | Local, intégrable docker-compose |
| Provider cloud GPU | RunPod (API) | API actuelle | GPU pods Docker, démarrage rapide |
| Provider cloud GPU (alt) | vast.ai | API actuelle | Moins cher, fallback |
| iOS apps capture (POC) | Record3D + Sensor Logger | App Store | Pas de dev iOS au POC |
| iOS app native (V1) | Swift + SwiftUI + ARKit | iOS 17+ | Standard Apple |
| CLI framework | Typer | dernière stable | Pydantic-friendly, basé Click |

## 2. Justifications détaillées

### 2.1 Python (vs TypeScript/Bun)

**Décidé** : Python 3.12.

**Pourquoi** : tout l'écosystème ML/3D que ce projet consomme est natif Python+CUDA :
- gsplat, 2DGS, Mask2Former, NeILF++, Open3D, PyTorch3D : Python uniquement.
- Blender script API : Python.
- Réimplémenter en TS = des mois de travail pour des perfs 10-100× moindres.

**Alternative considérée et rejetée** : TypeScript + Bun pour la couche métier, Python pour les ML workers. Architecture trop complexe pour un MVP solo, double maintenance, contrats CLI/IPC à concevoir, gain marginal.

ADR : [`08-decisions.md#adr-001`](./08-decisions.md#adr-001--stack-python-vs-typescript--bun).

### 2.2 uv (vs poetry, pdm, pip-tools)

**Décidé** : uv.

**Pourquoi** :
- Workspace multi-package natif, parfait pour notre architecture en couches.
- Vitesse incomparable (Rust core).
- Lockfile reproductible.
- Compatible PEP 621 (`pyproject.toml`).
- Gestion des Python en parallèle des dépendances.

**Alternatives** : poetry (plus lent, gestion workspace moins propre), pdm (correct mais moins d'élan), pip-tools (trop bas niveau).

### 2.3 Temporal (vs Prefect, Dagster, Airflow, custom)

**Décidé** : Temporal.

**Pourquoi** :
- **Durable execution** : workflows résistent aux crashs, redémarrages, mises à jour de code.
- **Long-running** natif : un workflow peut durer des heures/jours sans pression mémoire.
- **Multi-queue** : on peut router activités CPU vs GPU sur des workers différents.
- **Reprise sur échec** fine : on rejoue l'activité qui a échoué, pas tout le workflow.
- **Auto-hébergeable**, conforme à la contrainte local-first.
- **Web UI** intégrée pour debug.

**Alternatives** :
- **Prefect** : plus simple à opérer mais durabilité moindre, moins fort sur les très longs workflows. Aurait été acceptable pour un MVP solo, mais on perd des garanties.
- **Dagster** : orienté data assets, mauvais paradigme pour de l'orchestration de jobs ML.
- **Airflow** : trop batch-oriented, mauvais pour workflows interactifs.
- **Stack maison Redis + workers** : on réinvente la roue, mauvais ROI.

ADR : [`08-decisions.md#adr-002`](./08-decisions.md#adr-002--temporal-comme-orchestrateur).

### 2.4 MinIO (vs S3 réel, fichiers locaux)

**Décidé** : MinIO en local pour le dev/POC, possibilité de cibler un vrai S3 compatible plus tard via la même interface.

**Pourquoi** : conforme local-first, S3-compatible donc swap trivial, supporte presigned URLs (utile pour les workers cloud GPU qui doivent download/upload).

### 2.5 Postgres (vs SQLite)

**Décidé** : Postgres 16.

**Pourquoi** : Temporal en a besoin de toute façon, autant standardiser. JSON natif pour les manifests semi-structurés, types riches, robuste sur les transactions concurrentes (workers parallèles).

SQLite serait acceptable pour un POC mono-machine mais pose problème dès qu'on a plusieurs workers en concurrence.

### 2.6 NATS (vs Redis pub/sub, RabbitMQ)

**Décidé** : NATS.

**Pourquoi** : extrêmement léger (binaire de quelques Mo), zéro config, parfait pour les events temps réel UI sans persistance. Pas de queueing critique (Temporal s'en charge).

### 2.7 CUDA only (vs Metal/MPS)

**Décidé** : CUDA exclusivement pour le ML.

**Pourquoi** :
- Tout l'écosystème ML mature est CUDA-first.
- gsplat, 2DGS, NeILF++ ont des kernels CUDA custom non portables.
- Maintenir un chemin MPS ajoute du code et des bugs (les forks MPS de gsplat sont régulièrement cassés).
- L'utilisateur a une RTX 4090 dispo via Tailscale, donc pas de besoin réel.

ADR : [`08-decisions.md#adr-004`](./08-decisions.md#adr-004--cuda-only-pas-de-metalmps).

### 2.8 RunPod (vs Modal, Beam, vast.ai)

**Décidé** : RunPod en provider primaire, vast.ai en fallback.

**Pourquoi RunPod** :
- Pods Docker bruts, on déploie notre propre image.
- Démarrage rapide (~30s).
- API simple.
- Tarifs compétitifs (A100 ~1.5€/h, L40S ~0.8€/h).
- Compatible Tailscale / SSH.

**Alternative Modal rejetée** : Modal n'expose pas un environnement Docker brut "comme un VPS", il impose son framework Python. Moins compatible avec un worker Temporal qui s'enregistre auprès d'un serveur externe.

### 2.9 Tailscale (vs Cloudflare Tunnel, WireGuard manuel)

**Décidé** : Tailscale.

**Pourquoi** : zero-config, MagicDNS, gratuit pour usage perso, multiplateforme, ACL simples, fonctionne identiquement en LAN et WAN.

ADR : [`08-decisions.md#adr-011`](./08-decisions.md#adr-011--tailscale-comme-bridge-réseau).

### 2.10 Blender 4.2 LTS (vs Reality Capture, Metashape)

**Décidé** : Blender pour bake et export FBX/AC.

**Pourquoi** :
- Open source, scriptable Python (`bpy`).
- Bake multi-vue maitrisable, pas de boîte noire.
- Export FBX nativement, paramètres d'axes contrôlables.
- LTS = stabilité de l'API entre les versions.

Reality Capture / Metashape sont commerciaux, fermés, et leur photogrammétrie n'est pas notre étape clé (on utilise GS).

### 2.11 ksEditor (vs export FBX direct + AC charge)

**Décidé** : ksEditor headless pour compiler le KN5 final.

**Pourquoi** : AC charge des fichiers KN5 binaires propriétaires, pas du FBX. Sans ksEditor, on devrait reverse-engineer le format. Le binaire est utilisable en CLI, donc scriptable.

**Limite** : ksEditor est Windows-only. Les activités d'export tournent donc sur le worker Windows ou via un container Wine sur le worker Linux. Voir [`05-infrastructure.md`](./05-infrastructure.md).

## 3. Versions Python et pin policy

- **Python ≥ 3.11**, cible **3.12** sur tous les workers et services. Si une lib ML ne supporte pas 3.12, fallback documenté à 3.11 sans drama.
- **Lockfile uv.lock** committé. Toute mise à jour passe par `uv lock --upgrade-package <pkg>` et est revue.
- **Pin majeur** sur les libs critiques (Temporal, Pydantic, FastAPI).
- **Range mineur** sur les libs ML (qui évoluent vite, rebreaking attendu).

### Procédure en cas de conflit irréductible entre libs ML

Si deux libs ML deviennent **mutuellement incompatibles** (ex. gsplat exige PyTorch 2.6, NeILF++ exige PyTorch 2.4 et la migration n'est pas raisonnable), on isole en **deux images Docker `gpu-worker` distinctes** + **deux task queues spécialisées** :

| Image | Libs principales | Activités | Task queue |
|---|---|---|---|
| `road2track/gpu-worker-gs` | gsplat, 2DGS, Mask2Former, PyTorch X | train_gs, extract_mesh, segment | `gpu-gs` |
| `road2track/gpu-worker-pbr` | NeILF++, PyTorch Y | bake, estimate_pbr | `gpu-pbr` |

Le workflow route les activités vers la bonne queue. Cette procédure est **un fallback défensif** : on essaie en priorité de garder **une seule image** `gpu-worker` qui fait tout, jusqu'à preuve d'un conflit irréductible. Si déclenchée, ouvrir un ADR pour acter le split.

## 4. Outils de dev

| Outil | Usage |
|---|---|
| `uv sync` | Installer les dépendances de tous les workspace members. |
| `uv run <cmd>` | Exécuter une commande dans l'environnement. |
| `uv run ruff check` | Lint. |
| `uv run ruff format` | Format. |
| `uv run pyright` | Type check strict. |
| `uv run pytest` | Tests. |
| `make up` | Lance l'infra docker-compose. |
| `make down` | Arrête l'infra. |
| `make gpu-up` | Active le worker GPU local (sur le PC). |
| `make worker-cpu` | Démarre le `cpu_worker` en process direct (pour dev). |

## 5. Politique de mise à jour des libs ML

Les libs ML évoluent rapidement (un nouveau papier de GS par mois). Pour gérer ça :

1. **Une seule lib ML est mise à jour par PR.** Pas de gros bumps groupés.
2. **Le test E2E sur le dataset jouet** doit passer avant merge.
3. **Le résultat visuel** sur le dataset de référence doit être au moins aussi bon (mesuré subjectivement + métriques PSNR/LPIPS si dispo).
4. **L'ancienne implémentation reste accessible** via une variante de config pendant 1 release, pour pouvoir comparer.

## 6. Dépendances optionnelles / extras

Certaines libs lourdes (PyTorch3D, NeILF++) sont en `extras` pour permettre :
- D'installer le `cpu_worker` sans CUDA.
- D'installer le `gpu_worker` avec tout.
- D'installer juste la CLI sur la machine de dev sans dépendances ML.

```toml
# packages/ml/pyproject.toml (extrait)
[project.optional-dependencies]
gs       = ["gsplat>=...", "torch>=2.3"]
mesh     = ["...2dgs..."]
seg      = ["transformers>=4.40", "torch>=2.3"]
pbr      = ["...neilf..."]
all      = ["road2track-ml[gs,mesh,seg,pbr]"]
```

## 7. Stack frontend (V1+)

Pas de frontend au POC ni au MVP. À partir de la V1 (web UI status, app iOS) :

| Composant | Choix |
|---|---|
| App iOS | Swift + SwiftUI + ARKit, `iOS 17+` |
| Web UI | Astro ou Next.js, à arbitrer |
| Style | Tailwind CSS |

Décision finale du stack frontend reportée à l'amorçage de l'itération concernée (cf. [`09-questions-ouvertes.md`](./09-questions-ouvertes.md)).
