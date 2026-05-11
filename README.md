# my-laser-scan

> **Outil qui transforme une simple balade iPhone en circuit jouable dans Assetto Corsa**, avec un effort utilisateur trivial et un rendu visuel photoréaliste.

[![Statut](https://img.shields.io/badge/statut-It.%200%20software%20complet%20%E2%80%94%20validation%20hardware%20en%20attente-yellow)](./specs/07-roadmap.md)
[![Stack](https://img.shields.io/badge/stack-Python%203.12%20%7C%20Temporal%20%7C%20uv-blue)](./specs/03-stack-technique.md)
[![Architecture](https://img.shields.io/badge/architecture-hexagonale-green)](./specs/02-architecture.md)
[![Licence](https://img.shields.io/badge/licence-privée-lightgrey)](#licence)

---

## Concept en une image

```
   ┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
   │  iPhone  │───▶│   Pipeline   │───▶│   Mesh +     │───▶│  Track AC    │
   │  Pro     │    │   ML local   │    │  textures    │    │  (CM zip)    │
   │  +LiDAR  │    │  + cloud GPU │    │  PBR         │    │              │
   └──────────┘    └──────────────┘    └──────────────┘    └──────────────┘
   capture           Gaussian            game-ready          téléchargeable
   balade            Splatting           assets              jouable dans AC
```

Métaphore : **Strava pour le sim racing**. L'utilisateur capture, attend, télécharge, joue.

---

## Statut du projet

🚧 **Itération 0 — software complet, validation hardware en attente** (snapshot 2026-05-11).
Toutes les activités du pipeline POC (`ingest_session`, `fuse_sensors`, `detect_kind_and_trim`, `select_keyframes`, `train_gs`, `extract_mesh`, `bake_textures`) sont implémentées et testées en CI (146 tests unit + 9 intégration verts). Les 3 activités GPU (`train_gs`, `extract_mesh`, `bake_textures`) ont été écrites **à l'aveugle** sans GPU disponible et **ne sont pas encore chaînées** dans le workflow. Reste à exécuter sur le PC RTX 4090 + capture iPhone réelle pour valider qualité visuelle dans Blender. Détails : [`specs/07-roadmap.md §Statut détaillé au handoff`](./specs/07-roadmap.md).

Voir [`specs/07-roadmap.md`](./specs/07-roadmap.md) pour le plan complet.

---

## Stack technique en un coup d'œil

| Couche | Technologie |
|---|---|
| Runtime | Python 3.12, `uv` (workspace) |
| Orchestration | [Temporal](https://temporal.io/) (Python SDK) |
| API HTTP | FastAPI (V1+) |
| Stockage objet | MinIO (S3-compatible, local) |
| Base de données | Postgres 16 |
| Pub/sub events | NATS |
| Containerisation | Docker + Docker Compose |
| Réseau privé | Tailscale (Mac ↔ PC ↔ pods cloud) |
| ML / 3D | gsplat, 2DGS, Mask2Former, NeILF++, Open3D, PyTorch3D, Blender 4.2 LTS |
| GPU | NVIDIA CUDA 12.4 (RTX 4090 local + RunPod cloud) |
| Tests | pytest, temporalio.testing, testcontainers |
| Outils dev | ruff, pyright (strict), structlog |

Détails et alternatives rejetées : [`specs/03-stack-technique.md`](./specs/03-stack-technique.md).

---

## Architecture matérielle

```
┌───────────────────────────┐
│  Mac M3 Max               │  Orchestrateur (sans GPU compute)
│  - Temporal + Postgres    │  - Workers CPU
│  - MinIO + NATS           │  - CLI / API
│  - Docker Compose         │
└─────────┬─────────────────┘
          │ Tailscale
   ┌──────┴───────┐
   ▼              ▼
┌─────────┐    ┌──────────────┐
│ PC      │    │ RunPod pod   │
│ Win+    │    │ (à la        │
│ RTX4090 │    │  demande)    │
│ CUDA    │    │ A100 / L40S  │
│ Docker  │    │ Docker + TS  │
└─────────┘    └──────────────┘
```

Détails : [`specs/05-infrastructure.md`](./specs/05-infrastructure.md).

---

## Structure prévisionnelle du repo

```
my-laser-scan/
├── README.md                       # ce fichier
├── CLAUDE.md                       # guide opérationnel pour Claude Code
├── Makefile                        # commandes pratiques
├── docker-compose.yml              # infra Mac (Temporal, Postgres, MinIO, NATS)
├── docker-compose.gpu.yml          # override GPU worker (PC ou cloud)
├── pyproject.toml                  # workspace uv root
├── uv.lock
│
├── specs/                          # ─── CAHIER DES CHARGES ───
│   ├── README.md                   # index
│   ├── 00-vision.md
│   ├── 01-cahier-des-charges.md
│   ├── 02-architecture.md
│   ├── 03-stack-technique.md
│   ├── 04-pipeline-ml.md
│   ├── 05-infrastructure.md
│   ├── 06-modele-donnees.md
│   ├── 07-roadmap.md
│   ├── 08-decisions.md             # ADRs
│   └── 09-questions-ouvertes.md
│
├── packages/                       # ─── CODE MÉTIER ───
│   ├── core/                       # domaine pur (Pydantic, ports)
│   ├── geo/                        # math géo, fusion capteurs
│   ├── ml/                         # adapters ML (gsplat, 2DGS, …)
│   ├── storage/                    # adapters MinIO + Postgres
│   ├── ac_export/                  # génération track AC + CM
│   ├── cloud_bridge/               # providers GPU (RunPod, etc.)
│   └── pipeline/                   # workflows + activités Temporal
│
├── services/                       # ─── PROCESSUS RUNTIME ───
│   ├── cpu_worker/
│   ├── gpu_worker/
│   ├── api/                        # V1+
│   └── cli/
│
├── apps/
│   └── ios/                        # V1+
│
├── poc/                            # notebooks d'exploration
│
├── infra/                          # configs Temporal, MinIO, RunPod
│
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/                        # dataset jouet
```

---

## Démarrage rapide

> Les commandes ci-dessous deviendront fonctionnelles au fil des itérations. Voir [`specs/07-roadmap.md`](./specs/07-roadmap.md) pour le statut.

```bash
# 1. Cloner le repo et installer les dépendances
git clone <url> my-laser-scan
cd my-laser-scan
uv sync                                # installe tous les packages workspace

# 2. Démarrer l'infrastructure locale (sur le Mac)
make up                                # docker-compose : Temporal, Postgres, MinIO, NATS
make migrate                           # applique les migrations Alembic

# 3. (Sur le PC Windows) Démarrer le worker GPU
docker compose -f docker-compose.gpu.yml up -d

# 4. Vérifier que tout est connecté
uv run road2track gpu list             # doit lister le PC en ligne
open http://localhost:8080             # Temporal Web UI

# 5. Ingestion d'une capture
uv run road2track project create "Mon premier circuit"
uv run road2track ingest ./captures/balade_test/

# 6. Lancer le pipeline
uv run road2track process <project-id>

# 7. Récupérer le résultat
uv run road2track export <project-id> --output ~/Downloads/
```

---

## Documentation — index

Toute la documentation produit / technique vit dans [`specs/`](./specs/). Pour démarrer :

| Fichier | Sujet | Lire si… |
|---|---|---|
| [`specs/00-vision.md`](./specs/00-vision.md) | Mission, persona, parcours utilisateur | tu veux comprendre le **pourquoi** |
| [`specs/01-cahier-des-charges.md`](./specs/01-cahier-des-charges.md) | Fonctionnalités MoSCoW, contraintes, critères de succès | tu codes une feature |
| [`specs/02-architecture.md`](./specs/02-architecture.md) | Couches clean architecture, workspace, dépendances | tu touches au code |
| [`specs/03-stack-technique.md`](./specs/03-stack-technique.md) | Technologies, versions, alternatives | tu installes ou ajoutes une lib |
| [`specs/04-pipeline-ml.md`](./specs/04-pipeline-ml.md) | Pipeline ML détaillé, tuilage, multi-passe | tu touches au ML |
| [`specs/05-infrastructure.md`](./specs/05-infrastructure.md) | Topologie, Docker, Tailscale, providers GPU | tu touches à l'infra |
| [`specs/06-modele-donnees.md`](./specs/06-modele-donnees.md) | Schemas Pydantic, formats fichiers, structure CM | tu touches aux données |
| [`specs/07-roadmap.md`](./specs/07-roadmap.md) | Itérations, jalons, livrables | tu planifies un sprint |
| [`specs/08-decisions.md`](./specs/08-decisions.md) | ADRs (15 décisions actées) | tu remets en question un choix |
| [`specs/09-questions-ouvertes.md`](./specs/09-questions-ouvertes.md) | Décisions à prendre | tu démarres une feature qui en dépend |

Guides opérationnels pas-à-pas dans [`docs/`](./docs/) :

| Guide | Sujet |
|---|---|
| [`docs/setup-gpu-windows.md`](./docs/setup-gpu-windows.md) | Démarrer le `gpu_worker` sur le PC RTX 4090, relier au Mac via Tailscale |
| [`docs/setup-gpu-cloud.md`](./docs/setup-gpu-cloud.md) | Lancer un `gpu_worker` sur RunPod (spot + checkpointing ADR-022) |

---

## Statut des fonctionnalités

| Catégorie | Détail | Statut |
|---|---|---|
| **Must** Capture (Record3D + Sensor Logger) | Apps existantes au POC, native en It. 2 | 🟡 prévu |
| **Must** Synchronisation Record3D ↔ Sensor Logger | UTC + fallback cross-corrélation IMU (ADR-017) | 🟡 prévu (It. 0) |
| **Must** Détection circuit auto + troncature lead-in | Algo loop closure ; spéciale = utilisateur fait foi (ADR-007/016) | 🟡 prévu |
| **Must** Pipeline 100% automatique | Temporal workflow + 19 activités | 🟡 prévu |
| **Must** Session activities GPU (sticky worker) | Évite les transferts MinIO redondants (ADR-019) | 🟡 prévu (It. 0) |
| **Must** Tuilage spatial (long tronçons) | 800 m / 50 m d'overlap | 🟡 prévu (It. 4) |
| **Must** Export Content Manager | zip + ui_track.json + AI line + pit lane | 🟡 prévu (It. 1) |
| **Must** Infra locale-first (Docker Compose) | Temporal + Postgres + MinIO + NATS | 🟡 prévu (It. 0) |
| **Must** Bridge cloud GPU (RunPod via Tailscale) | Provider abstraction (LocalDesktop + RunPod) | 🟡 prévu (It. 4) |
| **Must** Pas de provisioning auto cloud | Erreur explicite + commande à lancer (ADR-018) | 🟡 prévu (It. 1) |
| **Must** Qualité photoréaliste (PBR baked) | gsplat → 2DGS → bake | 🟡 prévu (It. 0/3) |
| **Should** App iOS native | Replace Record3D + Sensor Logger | ⚪ futur (It. 2) |
| **Should** Pause/reprise + multi-passe | Logique modes A/B/C | ⚪ futur (It. 2) |
| **Should** Markers explicites spéciale (start/end) | Optionnel, opt-in | ⚪ futur (It. 2) |
| **Should** API HTTP FastAPI | Sur Tailscale | ⚪ futur (It. 2) |
| **Should** Web UI status | Temps réel via NATS | ⚪ futur (It. 4) |
| **Could** Anonymisation auto | YOLO + inpainting | ⚪ futur (V2) |
| **Could** Édition légère post-génération | Web UI éditeur | ⚪ futur (V2) |
| **Could** Météo dynamique | HDRi capturé iPhone | ⚪ futur (V2) |
| **Could** Multi-jeux (rFactor, BeamNG) | Adapters supplémentaires | ⚪ futur (V2) |
| **Won't** Multi-tenant / SaaS | — | ❌ jamais |
| **Won't** App Store | — | ❌ jamais |
| **Won't** Authentification / paiement | — | ❌ jamais |
| **Won't** Android | — | ❌ jamais |

Détails : [`specs/01-cahier-des-charges.md`](./specs/01-cahier-des-charges.md).

---

## Pour les nouveaux contributeurs

1. Lire **dans cet ordre** :
   1. [`specs/00-vision.md`](./specs/00-vision.md)
   2. [`specs/01-cahier-des-charges.md`](./specs/01-cahier-des-charges.md)
   3. [`specs/07-roadmap.md`](./specs/07-roadmap.md)
   4. [`specs/02-architecture.md`](./specs/02-architecture.md)
   5. La section concernée par ton sujet (ML / infra / données).
2. Lire [`CLAUDE.md`](./CLAUDE.md) pour les **conventions de code** et les **règles d'or**.
3. Avant de proposer une décision structurante, vérifier qu'elle ne contredit pas un ADR de [`specs/08-decisions.md`](./specs/08-decisions.md).
4. Si la décision est nouvelle ou contradictoire : créer un nouvel ADR plutôt que de coder.

---

## Liens externes utiles

- [Temporal](https://temporal.io/) — orchestrateur durable.
- [Assetto Corsa Content Manager](https://assettocorsa.club/content-manager.html) — gestionnaire de tracks.
- [Custom Shaders Patch (CSP)](https://acstuff.ru/patch/) — extensions graphiques AC.
- [gsplat (Nerfstudio)](https://github.com/nerfstudio-project/gsplat) — Gaussian Splatting.
- [2D Gaussian Splatting](https://github.com/hbb1/2d-gaussian-splatting) — extraction mesh.
- [Record3D](https://record3d.app/) — app iOS LiDAR.
- [Sensor Logger](https://www.tszheichoi.com/sensorlogger) — app iOS capteurs.
- [Tailscale](https://tailscale.com/) — mesh VPN.
- [RunPod](https://www.runpod.io/) — GPU pods cloud.

---

## Licence

Privée. Aucun tiers ne doit avoir accès au code, aux scans ou aux livrables sans autorisation explicite de l'auteur.
