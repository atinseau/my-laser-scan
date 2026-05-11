# CLAUDE.md

> Guide opérationnel destiné à Claude Code (et à tout autre assistant IA / nouveau dev) qui intervient sur ce repo. Ce fichier est court par design et **renvoie systématiquement** vers les documents de spécification dans [`specs/`](./specs/).

## 1. Contexte en deux lignes

Ce projet (`my-laser-scan`, nom interne de la stack : `road2track`) transforme une balade iPhone en circuit Assetto Corsa. **Itération 0 : pipeline POC implémenté de bout en bout côté software (146 unit + 9 intégration verts) ; les 3 activités GPU `train_gs`/`extract_mesh`/`bake_textures` sont écrites à l'aveugle sans GPU disponible et ne sont pas encore chaînées dans `ProcessProject` — validation empirique sur RTX 4090 en attente.**

Lire en priorité :
1. [`README.md`](./README.md) — vue produit + index documentation.
2. [`specs/07-roadmap.md`](./specs/07-roadmap.md) §Statut détaillé au handoff — pour reprendre la séance.
3. [`docs/setup-gpu-windows.md`](./docs/setup-gpu-windows.md) — pour lancer le premier run réel.

## 2. Règles d'or à ne jamais violer

| # | Règle | Source |
|---|---|---|
| 1 | **Pas de Python sur le M3 Max pour le ML.** Le Mac est orchestrateur uniquement. Tout compute ML est CUDA externe. | [`specs/05-infrastructure.md`](./specs/05-infrastructure.md), [ADR-004](./specs/08-decisions.md#adr-004--cuda-only-pas-de-metalmps), [ADR-010](./specs/08-decisions.md#adr-010--mac-orchestrateur-sans-gpu-compute) |
| 2 | **Couches clean architecture strictes.** `core` ne dépend de rien sauf stdlib + Pydantic. Aucune dépendance circulaire. Aucune flèche vers le haut. | [`specs/02-architecture.md`](./specs/02-architecture.md), [ADR-012](./specs/08-decisions.md#adr-012--architecture-hexagonale-en-couches) |
| 3 | **Workflows Temporal déterministes.** Pas de `datetime.now()`, `random` non seedé, I/O. Tout effet de bord → activité. | [`specs/02-architecture.md#54-workflow--activity-temporal`](./specs/02-architecture.md#54-workflow--activity-temporal) |
| 4 | **Toute activité ML va sur queue `gpu`.** Toute activité non-ML va sur `cpu`. | [`specs/04-pipeline-ml.md`](./specs/04-pipeline-ml.md), exigence MH-PIP-4 |
| 5 | **Pas d'app iOS au POC.** Capture via Record3D + Sensor Logger jusqu'à l'It. 2. | [`specs/07-roadmap.md`](./specs/07-roadmap.md), [ADR-009](./specs/08-decisions.md#adr-009--pas-dapp-ios-au-poc) |
| 6 | **Pas de logique métier dans `services/`.** Les services orchestrent le démarrage et passent des paramètres. La logique vit dans `packages/`. | [`specs/02-architecture.md`](./specs/02-architecture.md), exigence CT-COD-5 |
| 7 | **Toute lib ML est derrière `packages/ml/`** avec une interface stable. Les libs sont remplaçables sans propagation. | [`specs/02-architecture.md`](./specs/02-architecture.md), exigence CT-REV-1 |
| 8 | **Aucun secret committé.** Tout passe par `.env` non versionné + `.env.example` versionné. | [`specs/05-infrastructure.md#64-sécurité`](./specs/05-infrastructure.md#64-sécurité), QO-015 |
| 9 | **Toute décision structurante → ADR.** Avant de coder une décision majeure, vérifier qu'elle est dans [`specs/08-decisions.md`](./specs/08-decisions.md). Si non : nouvel ADR avant code. | [`specs/08-decisions.md`](./specs/08-decisions.md) |
| 10 | **Tout schema versionné.** Champ `schema_version: int` sur tous les manifests Pydantic. | [`specs/06-modele-donnees.md#6-versioning-des-schemas`](./specs/06-modele-donnees.md#6-versioning-des-schemas) |

## 3. Conventions de code

### 3.1 Style et qualité

- **Type checking** : pyright en strict (`pyrightconfig.json` à la racine).
- **Lint / format** : ruff. Configuration dans `pyproject.toml` racine.
- **Tests** : pytest + pytest-asyncio + temporalio.testing.
- **Imports** : groupés (stdlib, tiers, locaux) automatiquement par ruff.
- **Docstrings** : courtes, en français, uniquement quand la motivation n'est pas évidente.
- **Commentaires** : minimaux. Si le code a besoin d'un commentaire pour être compris, le code doit être réécrit.
- **Identifiants** : `snake_case` pour fonctions/variables/modules, `PascalCase` pour classes, `SCREAMING_SNAKE_CASE` pour constantes.

### 3.2 Pydantic v2

- Tous les schemas dans `packages/core/entities` ou `value_objects`.
- `BaseModel` partout, jamais de dataclasses pour les schemas applicatifs.
- `model_config = ConfigDict(frozen=True)` par défaut sur les value objects.
- Champs Literal pour les `schema_version`.

### 3.3 Async

- Code async partout où il y a I/O (Temporal, FastAPI, MinIO via aioboto3).
- Code synchrone dans `core` et `geo` (calculs purs).
- Activités Temporal : async par défaut.

### 3.4 Erreurs

- Exceptions custom dans `core/errors.py`.
- Une exception par cas métier (`ProjectNotFoundError`, `InvalidSegmentError`, etc.).
- Pas de `except Exception:` sans re-raise.

### 3.5 Fichiers et noms

- Un module = une responsabilité claire.
- Pas de `utils.py` fourre-tout. Préférer un module nommé par son rôle (`encoding.py`, `time_helpers.py`).
- Tests miroirent la structure : `tests/unit/<package>/<module>_test.py`.

## 4. Architecture en bref

```
core (domaine pur)
  ↑
  └ geo, ml, storage, ac_export, cloud_bridge (adapters)
      ↑
      └ pipeline (workflows + activités Temporal)
          ↑
          └ services (cpu_worker, gpu_worker, api, cli)
```

- `core` n'importe que stdlib + Pydantic (+ numpy autorisé pour value objects géométriques).
- Les **ports** sont dans `core/ports/` comme `Protocol`.
- Les **adapters** implémentent ces ports dans `storage/`, `ml/`, `cloud_bridge/`.
- Le `pipeline` dépend des **ports** (interfaces), pas des adapters concrets.
- L'injection se fait au démarrage des services.

Détails complets : [`specs/02-architecture.md`](./specs/02-architecture.md).

## 5. Commandes utiles (à mesure qu'elles existent)

```bash
# Dépendances
uv sync                                # installe tous les workspace members
uv run <cmd>                           # exécute dans l'env
uv add <pkg> --package <member>        # ajoute une dep à un package précis

# Qualité
uv run ruff check .
uv run ruff format .
uv run pyright

# Tests
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/e2e -k poc

# Infrastructure
make up                                # docker-compose up
make down                              # docker-compose down
make logs                              # logs combinés
make migrate                           # alembic upgrade head

# Workers
make worker-cpu                        # démarre cpu_worker en process direct
make worker-cpu-watch                  # avec hot reload (watchfiles)

# CLI
uv run road2track project create <name>
uv run road2track ingest <path>
uv run road2track process <project_id>
uv run road2track export <project_id>

# GPU bridge
uv run road2track gpu list
uv run road2track gpu spawn --provider runpod --gpu l40s
uv run road2track gpu shutdown --all
```

## 6. Où chercher quoi

| Question | Document |
|---|---|
| Quelle est la mission, le persona ? | [`specs/00-vision.md`](./specs/00-vision.md) |
| Cette feature est-elle au périmètre ? | [`specs/01-cahier-des-charges.md`](./specs/01-cahier-des-charges.md) |
| Comment sont organisés les packages ? | [`specs/02-architecture.md`](./specs/02-architecture.md) |
| Quelle version de telle lib ? | [`specs/03-stack-technique.md`](./specs/03-stack-technique.md) |
| Comment fonctionne tel modèle ML ? | [`specs/04-pipeline-ml.md`](./specs/04-pipeline-ml.md) |
| Comment se connecte le worker GPU ? | [`specs/05-infrastructure.md`](./specs/05-infrastructure.md) |
| Quel est le format de tel manifest ? | [`specs/06-modele-donnees.md`](./specs/06-modele-donnees.md) |
| Quand cette feature doit-elle être livrée ? | [`specs/07-roadmap.md`](./specs/07-roadmap.md) |
| Pourquoi a-t-on choisi X ? | [`specs/08-decisions.md`](./specs/08-decisions.md) |
| Cette décision est-elle déjà actée ? | [`specs/08-decisions.md`](./specs/08-decisions.md) ou [`specs/09-questions-ouvertes.md`](./specs/09-questions-ouvertes.md) |
| Comment je démarre le worker GPU sur mon PC ? | [`docs/setup-gpu-windows.md`](./docs/setup-gpu-windows.md) |
| Comment je lance un pod GPU sur RunPod ? | [`docs/setup-gpu-cloud.md`](./docs/setup-gpu-cloud.md) |

## 7. Anti-patterns interdits

| ❌ Interdit | ✅ À la place |
|---|---|
| Importer `temporalio.workflow` dans une activité | Activités utilisent `temporalio.activity`, pas `workflow` |
| Importer `gsplat`, `torch`, `cv2` dans `core` ou `geo` | Tout ML est dans `packages/ml/` derrière une interface |
| `Path("/...")` ou `requests.get(...)` dans `core` | Adapters dans `storage/`, jamais dans le domaine |
| Logique métier dans une activité | Activité orchestre l'appel à un adapter, le résultat est traité par le workflow |
| Logique métier dans un service | Services = bootstrap uniquement |
| Définir `class Project` ailleurs que `core/entities/project.py` | Une seule source de vérité par entité |
| Appeler `datetime.now()` dans un workflow | `workflow.now()` (déterministe) |
| `random.random()` dans un workflow | `workflow.random()` |
| `asyncio.sleep` dans un workflow | `workflow.sleep` |
| Exposer un service Docker sur `0.0.0.0` | Bind sur `127.0.0.1`, exposition via Tailscale serve |
| Réintroduire MPS/Metal dans le code ML | Voir [ADR-004](./specs/08-decisions.md#adr-004--cuda-only-pas-de-metalmps) |
| Coder une feature qui n'est pas dans le cahier des charges | Ouvrir une discussion → ADR → mise à jour des specs → code |
| Modifier l'architecture sans mettre à jour `specs/02-architecture.md` | Spec d'abord, code ensuite |

## 8. Quand demander confirmation à l'utilisateur

- **Avant** de créer un nouvel ADR.
- **Avant** de modifier le cahier des charges (ajouter/retirer une feature MoSCoW).
- **Avant** une décision technique structurante non documentée.
- **Avant** de toucher au pipeline ML d'une manière qui changerait la qualité visuelle.
- **Avant** de modifier l'arborescence des packages.
- **Avant** d'ajouter une nouvelle dépendance lourde (lib ML, framework).

Pour les modifications mineures (typo, refactor local, ajout d'un test), pas besoin de confirmation.

## 9. Workflow de contribution

1. Lire les sections pertinentes des specs (cf. tableau §6).
2. Vérifier qu'il n'y a pas de question ouverte ([`specs/09-questions-ouvertes.md`](./specs/09-questions-ouvertes.md)) qui bloque ton travail.
3. Implémenter avec les conventions §3.
4. Tester (unitaire + intégration au minimum).
5. Mettre à jour les specs si nécessaire (la spec doit refléter le code, sinon c'est qu'il manque un ADR).
6. Commit avec un message en français, concis, focalisé.

## 10. Branches et commits

- **Branche actuelle de travail** : `claude/lidar-circuit-generator-UCDti`.
- **Convention de commits** : verbe à l'infinitif en français, court.
  - ✅ `Ajouter le scaffold du package core`
  - ✅ `Documenter le pipeline ML`
  - ❌ `Updates`
  - ❌ `WIP`
- Un commit = une intention. Pas de mégacommits.

## 11. Mise à jour de la documentation au fil des itérations

Le projet a un état vivant qui doit refléter le code réel. Toute dérive entre code et documentation est un bug à corriger en priorité.

### 11.1 À la fin d'une tâche (livrable de la roadmap)

Quand un livrable listé dans [`specs/07-roadmap.md`](./specs/07-roadmap.md) est terminé :

1. **Cocher** la case `[ ]` → `[x]` dans `specs/07-roadmap.md`.
2. Si le livrable a livré un comportement utilisateur visible : **mettre à jour le tableau "Statut des fonctionnalités"** du `README.md` (statut 🟡 → ✅).
3. Si le livrable a fermé une question ouverte : **fermer la QO** dans `specs/09-questions-ouvertes.md` (cf. §Procédure dans ce document) et créer un ADR si nécessaire dans `specs/08-decisions.md`.
4. **Commit** avec un message lié à la tâche en français.

### 11.2 À la fin d'une itération

Quand tous les livrables d'une itération sont cochés :

1. Vérifier les **critères go/no-go** de l'itération dans `specs/07-roadmap.md`. Si NO-GO : ne pas passer à la suivante.
2. **Mettre à jour le badge "Statut du projet"** du `README.md` (ex. `🚧 Pré-POC` → `🟢 It. 0 terminée`, puis `🚧 It. 1 en cours`).
3. **Mettre à jour le statut** dans :
   - `README.md` (badge en haut + section "Statut du projet")
   - `CLAUDE.md §1` (Contexte en deux lignes)
   - `specs/README.md` (section "Statut du projet")
4. **Produire** le document `specs/reviews/N-end-of-iteration.md` (méthodologie : cf. [`specs/00-vision.md#méthodologie`](./specs/00-vision.md#méthodologie)). Le document inclut :
   - Récap des livrables réalisés.
   - Écarts entre la spec et le code livré.
   - Mesures empiriques (temps, coûts, qualité).
   - Failles ou risques identifiés.
   - Mises à jour proposées de la spec (si écarts).
5. **Mettre à jour le compteur santé** des QOs en haut de `specs/09-questions-ouvertes.md`.
6. Si des décisions structurantes ont été prises : **nouveaux ADRs** dans `specs/08-decisions.md` avec la colonne "Origine = It. N".

### 11.3 Quand l'architecture ou le périmètre change

1. **Spec d'abord, code ensuite.** Mettre à jour `specs/02-architecture.md` (architecture), `specs/01-cahier-des-charges.md` (périmètre), ou `specs/04-pipeline-ml.md` (ML) **avant** de coder.
2. Si la modification est structurante (ne pourrait pas être facilement annulée) : **nouvel ADR** dans `specs/08-decisions.md`.
3. Si la modification ajoute ou retire une **règle d'or** : mettre à jour la liste §2 ci-dessus.
4. Si la modification touche le glossaire ou les conventions : mettre à jour `specs/01-cahier-des-charges.md §9` et CLAUDE.md §3.

### 11.4 Reviews prévues

Le projet prévoit des reviews systématiques :

- **Fin de chaque itération** : Claude (ou un humain) audite ce qui a été produit, écrit `specs/reviews/N-end-of-iteration.md`, met en évidence les écarts entre code et specs, signale les failles de qualité ou de sécurité.
- **Review finale** : audit complet à la fin de l'It. 4. Document `specs/reviews/final-review.md`.

Les reviews **lient** systématiquement leurs constats aux exigences de [`specs/01-cahier-des-charges.md`](./specs/01-cahier-des-charges.md) et aux ADRs.

---

**Dernière mise à jour de ce fichier** : à synchroniser avec les changements de specs/. Si tu modifies un ADR ou une règle d'or, mets à jour ce fichier.
