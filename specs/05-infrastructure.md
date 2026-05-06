# 05 — Infrastructure

> Topologie machines, déploiement local, providers GPU, bridges réseau. Le mantra : **local-first, cloud opt-in via Tailscale**.

## 1. Principes

1. **Aucun service ne dépend du cloud pour fonctionner.** Toute l'infra peut tourner sur la machine d'orchestration.
2. **Le compute GPU est toujours externe** au Mac d'orchestration, mais peut être local au réseau (PC Windows) ou cloud (RunPod).
3. **Le réseau d'union est Tailscale.** Tout passe par cet overlay, en LAN ou WAN.
4. **Aucun service exposé publiquement.** Pas d'IPv4 publique, pas de port forward, pas de tunnel HTTP public.

## 2. Topologie machines

### 2.1 Machine d'orchestration (Mac M3 Max)

Hôte de :
- Le `docker-compose` d'infrastructure (Temporal, Postgres, MinIO, NATS, observabilité).
- Les workers CPU Python (`cpu_worker`).
- L'API HTTP (V1+).
- La CLI de dev / admin.

**Pas de GPU compute** sur cette machine. Voir [`08-decisions.md#adr-010`](./08-decisions.md#adr-010--mac-orchestrateur-sans-gpu-compute).

### 2.2 Machine GPU permanente (PC Windows + RTX 4090)

Hôte de :
- Le `gpu_worker` Python en Docker avec NVIDIA Container Toolkit.

Connexion au reste via Tailscale. Aucun service supplémentaire.

**Note** : Le PC héberge aussi `ksEditor` natif Windows pour la compilation KN5. Cf. §5.

### 2.3 Machine GPU à la demande (RunPod, vast.ai)

Hôte temporaire de :
- Une instance du même `gpu_worker` Docker.
- Un client Tailscale pour rejoindre le mesh privé.

Spawn / shutdown via CLI.

## 3. Schéma global

```
                              Tailscale mesh privé
            ┌───────────────────────────────────────────────────┐
            │                                                   │
   ┌────────┴─────────┐                              ┌──────────┴──────────┐
   │  Mac M3 Max      │                              │  PC Windows         │
   │  ──────────────  │                              │  ─────────────────  │
   │  Docker Compose  │                              │  Docker Desktop     │
   │  ├ temporal      │                              │  ├ gpu_worker (CUDA)│
   │  ├ temporal-ui   │                              │  └ ksEditor (host)  │
   │  ├ postgres-temp │                              │                     │
   │  ├ postgres-app  │                              │  Tailscale          │
   │  ├ minio         │                              └──────┬──────────────┘
   │  ├ nats          │                                     │
   │  └ obs (optionnel)                                     │
   │                  │                                     │
   │  uv processes:   │                                     │
   │  ├ cpu_worker    │                                     │
   │  ├ api (V1+)     │                                     │
   │  └ cli           │                                     │
   │                  │                                     │
   │  Tailscale       │                                     │
   └────────┬─────────┘                                     │
            │                                               │
            └───────────────────────────────────────────────┘
                              │
                              │ (à la demande)
                              ▼
                    ┌──────────────────┐
                    │  RunPod pod      │
                    │  ──────────────  │
                    │  CUDA Docker     │
                    │  └ gpu_worker    │
                    │                  │
                    │  Tailscale       │
                    └──────────────────┘
```

## 4. Composants Docker Compose (Mac)

### 4.1 Fichier `docker-compose.yml` (vue logique)

| Service | Image | Ports | Rôle |
|---|---|---|---|
| `temporal` | `temporalio/auto-setup` | 7233 | Frontend Temporal |
| `temporal-ui` | `temporalio/ui` | 8080 | Web UI |
| `postgres-temporal` | `postgres:16` | (interne) | DB Temporal |
| `postgres-app` | `postgres:16` | 5432 | DB applicative |
| `minio` | `minio/minio` | 9000, 9001 | S3 + console |
| `minio-init` | `minio/mc` | — | Crée les buckets au boot |
| `nats` | `nats:2.10-alpine` | 4222, 8222 | Pub/sub + monitoring |

Tous les services binds sur `127.0.0.1` côté hôte. **Aucun port n'est ouvert sur l'IP publique.** Ils sont accessibles via Tailscale grâce à `tailscale serve` ou un binding `tailscale0` documenté plus bas.

### 4.2 Buckets MinIO

- `raw` : captures brutes uploadées.
- `intermediates` : trajectoires, keyframes, scenes GS, mesh par tuile.
- `outputs` : tracks finaux livrés.

Politique : LFU dans `intermediates`, conservation longue dans `raw` et `outputs`.

#### Estimation d'espace par projet

| Bucket | Contenu typique (1 km, 1 tuile) | Contenu (10 km, 13 tuiles) |
|---|---|---|
| `raw` | 5-15 Go (vidéo HEVC + LiDAR + capteurs) | 40-100 Go |
| `intermediates` | 10-30 Go (`scene.ply` 3 Go × 1 + mesh + textures + GS checkpoints) | 80-300 Go |
| `outputs` | 100-300 Mo (KN5 + assets) | 200-600 Mo |
| **Total** | **~50 Go** | **~400 Go** |

**Provisionnement recommandé** :
- POC / It. 0-1 (1 km mono-projet) : **100 Go** dispo MinIO.
- MVP / It. 2 (multi-projet 1 km) : **500 Go**.
- V1 / It. 4 (10-15 km) : **1-2 To** sur disque rapide, ou tiering vers disque externe.

Note : les `intermediates` sont **purgeables** (reproductibles depuis les `raw`). Une tâche cron mensuelle (`uv run road2track maintenance gc-intermediates`) supprime ceux dont le projet est terminé depuis > 30 jours.

### 4.3 Schéma Postgres applicatif

Tables principales (détails dans [`06-modele-donnees.md`](./06-modele-donnees.md)) :
- `projects`
- `segments`
- `trajectories`
- `tiles`
- `tracks`
- `coverage_voxels` (multi-passe)

Migrations gérées par Alembic dans `packages/storage/migrations/`.

### 4.4 NATS

Sujets utilisés :
- `road2track.events.project.<id>.created`
- `road2track.events.project.<id>.session_added`
- `road2track.events.project.<id>.processing.started`
- `road2track.events.project.<id>.processing.tile_completed`
- `road2track.events.project.<id>.processing.completed`
- `road2track.events.project.<id>.error`

L'API SSE / WebSocket relaie ces events vers la web UI.

## 5. Worker GPU

### 5.1 Image Docker `gpu_worker`

Base : `nvidia/cuda:12.4.0-runtime-ubuntu22.04`

Étapes du Dockerfile :
1. Installer Python 3.12, `uv`.
2. Copier le workspace (`packages/`, `services/gpu_worker/`).
3. `uv sync --extra gpu` pour installer torch + gsplat + 2DGS + transformers + open3d + pytorch3d.
4. Installer Tailscale (binaire officiel).
5. Installer Blender 4.2 LTS (téléchargement direct).
6. Pour l'export AC : Wine + ksEditor (alternative au worker Windows).
7. `ENTRYPOINT ["uv", "run", "python", "-m", "services.gpu_worker"]`

Image taggée `road2track/gpu-worker:<version>`, poussée vers un registry privé (Docker Hub privé, GHCR, ou Tailscale-hosted).

### 5.2 Lancement sur le PC Windows

```bash
# Sur le PC, une fois pour toutes
docker compose -f docker-compose.gpu.yml up -d
```

Avec `docker-compose.gpu.yml` qui contient :

```yaml
services:
  gpu-worker:
    image: road2track/gpu-worker:0.1.0
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices: [{ capabilities: [gpu] }]
    environment:
      TEMPORAL_HOST: mac.tailnet-xxxx.ts.net:7233
      MINIO_ENDPOINT: mac.tailnet-xxxx.ts.net:9000
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}
      TASK_QUEUE: gpu
      TS_AUTHKEY: ${TS_AUTHKEY}
    volumes:
      - ./cache:/cache    # cache des modèles HF, etc.
```

Le worker démarre, joint Tailscale via `TS_AUTHKEY`, contacte le Temporal Mac et commence à prendre des tâches.

### 5.3 Lancement sur RunPod

Provisioning via le CLI :

```bash
uv run road2track gpu spawn \
  --provider runpod \
  --gpu l40s \
  --hours 2
```

Comportement :
1. API RunPod : créer un pod avec image `road2track/gpu-worker:0.1.0`.
2. Injection des variables d'env via `template_envs`.
3. Le pod démarre, Tailscale rejoint le mesh.
4. Le worker s'enregistre auprès du Temporal Mac.
5. Le CLI attend que le worker apparaisse dans Temporal puis rend la main.

Shutdown :
```bash
uv run road2track gpu shutdown --provider runpod --pod <id>
# ou
uv run road2track gpu shutdown --all
```

### 5.4 Compilation KN5 — cas particulier

`ksEditor.exe` est un binaire **Windows uniquement**. Options évaluées :

| Option | Détail | Choix |
|---|---|---|
| A | **Worker Windows natif** sur le PC, écoute la queue `windows-tools` | ✅ **MVP / V1** |
| B | **Wine dans un container Linux dédié** (image distincte du `gpu_worker`), expose la queue `windows-tools` aussi | 🧪 **Prototype dès It. 1 en parallèle**. Si validé, devient option principale en V2. |
| C | VM Windows sur cloud (Azure/AWS) | ❌ Rejeté (overhead, coût) |
| D | Reverse-engineer du format KN5 | ❌ Rejeté (risqué, propriétaire) |

#### Option A — Worker Windows natif (MVP)

Sur le PC Windows, deux processus tournent côte-à-côte :

```
PC Windows
├─ Docker Desktop
│   └─ gpu-worker          (queue: gpu)
└─ Process Python natif (uv run python -m services.windows_worker)
    └─ windows-worker      (queue: windows-tools)
        └─ activité: compile_kn5  (lance ksEditor.exe en CLI)
```

Le `windows-worker` n'a **pas besoin de GPU** : c'est un petit process CPU qui appelle `ksEditor.exe`.

#### Option B — Wine container (à valider)

En parallèle de l'option A, on prototype une **image Docker Linux avec Wine + ksEditor.exe** packagés :

```dockerfile
FROM ubuntu:22.04
RUN dpkg --add-architecture i386 && \
    apt update && apt install -y wine64 wine32 winetricks
COPY ksEditor /opt/ksEditor
COPY entrypoint.sh /
ENTRYPOINT ["/entrypoint.sh"]
```

**Critères d'acceptation** (validés à l'It. 1 ou 2) :
- Au moins **5 KN5 différents** générés via Wine doivent être **bit-à-bit identiques** (ou fonctionnellement équivalents en jeu) à ceux générés via Windows natif.
- Pas de régression observée sur les textures, l'AI line, les surfaces.

Si validé → Wine devient **principal en V2**, le PC est rétrogradé en secours. Procédure documentée dans un ADR à ce moment-là.

Si invalidé → on conserve le PC comme dépendance tant que ksEditor reste opaque.

Note : une seule queue `windows-tools` peu importe la techno (PC natif ou Wine container). Le worker s'enregistre, Temporal route. L'utilisateur ne voit pas la différence.

## 6. Tailscale

### 6.1 Configuration

- **Tailnet personnel** de l'utilisateur (gratuit jusqu'à 100 devices).
- **MagicDNS activé** → on accède aux machines par leur nom (`mac.tail-xxxx.ts.net`).
- **Tags ACL** :
  - `tag:orchestrator` (le Mac)
  - `tag:gpu-worker` (le PC, les pods)
- **ACL** :
  - `tag:gpu-worker` peut atteindre `tag:orchestrator` sur ports `7233` (Temporal), `9000` (MinIO), `4222` (NATS), `5432` (Postgres app si besoin pour debug).
  - `tag:orchestrator` peut atteindre `tag:gpu-worker` sur n/a (le worker initie toujours les connexions).

### 6.2 Auth keys

- Une `TS_AUTHKEY` réutilisable, taguée `tag:gpu-worker`, à durée de vie 1 an.
- Stockée dans `.env` non versionné.
- Injectée dans les containers GPU pour qu'ils joignent automatiquement le mesh.

### 6.3 Exposition côté Mac

Les services Docker écoutent sur `127.0.0.1`. Pour les exposer dans le tailnet :

```bash
tailscale serve --bg --tcp 7233 tcp://127.0.0.1:7233
tailscale serve --bg --tcp 9000 tcp://127.0.0.1:9000
tailscale serve --bg --tcp 4222 tcp://127.0.0.1:4222
```

Ou alternative, binder docker-compose sur l'interface `tailscale0` (selon support OS).

### 6.4 Sécurité

- Aucun service n'écoute sur `0.0.0.0`. Tout est `127.0.0.1` ou `tailscale0`.
- Les credentials MinIO sont aléatoires, dans `.env`, jamais committés.
- Les credentials Postgres sont aléatoires.
- Les volumes Docker stockent les données chiffrées si l'utilisateur active FileVault / BitLocker.
- Aucun secret dans les images Docker.

## 6.5 Comportement en l'absence de worker GPU

Lorsqu'un workflow `process` est lancé alors qu'aucun worker GPU n'écoute la queue `gpu` (PC Windows offline et aucun pod cloud actif), le système doit retourner une **erreur explicite et actionnable**, conformément à l'exigence MH-INF-5.

### Comportement attendu

À l'invocation de `uv run road2track process <project-id>`, la CLI vérifie en pré-flight :

1. Liste les workers actifs auprès du Temporal frontend (`describe_task_queue` sur `gpu`).
2. Si zéro worker actif sur `gpu` :
   - Sortie en erreur avec **code retour ≠ 0**.
   - Message standardisé :
     ```
     [error] Aucun worker GPU disponible sur la queue 'gpu'.
     Pour démarrer un pod cloud, lancez :
       uv run road2track gpu spawn --provider runpod --gpu l40s --hours 2
     Ou démarrez le worker local sur le PC Windows :
       docker compose -f docker-compose.gpu.yml up -d
     ```
   - **Aucun provisioning automatique** n'est tenté. Aucun coût cloud n'est engagé sans action explicite de l'utilisateur.
3. Si au moins un worker est actif sur `gpu`, le workflow démarre normalement.

### Justification

Voir [ADR-018](./08-decisions.md#adr-018--pas-de-provisioning-cloud-automatique-au-mvp). Au MVP, la prudence financière prime sur le confort. En V1+, on pourra introduire une option opt-in `--auto-spawn` qui provisionne automatiquement avec un budget plafonné.

## 7. Provider GPU abstraction

```python
# packages/cloud_bridge/src/road2track_cloud_bridge/providers/base.py
class GPUProvider(Protocol):
    name: str

    async def ensure_running(self, spec: GPUSpec) -> WorkerHandle:
        """Garantit qu'un worker est en cours d'exécution. Spawn si besoin."""

    async def shutdown(self, handle: WorkerHandle) -> None: ...

    async def status(self) -> ProviderStatus: ...

    async def list_workers(self) -> list[WorkerHandle]: ...
```

Implémentations :

| Classe | Comportement |
|---|---|
| `LocalDesktopProvider` | "Persistant" : `ensure_running()` ping le PC Windows via Tailscale ; si offline, peut tenter Wake-on-LAN (configurable) ; `shutdown()` est no-op (l'utilisateur arrête manuellement). |
| `RunPodProvider` | "À la demande" : appel API RunPod, polling jusqu'à READY, retourne le `WorkerHandle`. `shutdown()` détruit le pod. |
| `VastProvider` | Idem RunPod. |

Le code applicatif (workflows / activités) **ne connaît pas** ces classes. Il déclare juste un besoin (queue `gpu`), Temporal route. La couche provider sert à la **gestion du cycle de vie** des pods, pas à l'orchestration.

## 8. Scripts CLI infra

| Commande | Effet |
|---|---|
| `make up` | docker-compose up -d (Mac) |
| `make down` | docker-compose down |
| `make logs` | docker-compose logs -f |
| `make worker-cpu` | Démarre `cpu_worker` (process direct, dev) |
| `make worker-cpu-watch` | Idem avec hot reload |
| `make api` | Démarre l'API FastAPI (V1+) |
| `make migrate` | Applique les migrations Alembic |
| `uv run road2track gpu list` | Liste les workers GPU connus |
| `uv run road2track gpu spawn …` | Provisionne un pod cloud |
| `uv run road2track gpu shutdown …` | Arrête un pod cloud |
| `uv run road2track project create <name>` | Crée un projet vide |
| `uv run road2track ingest <path>` | Ingère une session |
| `uv run road2track process <project_id>` | Lance le pipeline |
| `uv run road2track export <project_id>` | Récupère le zip final |

## 9. Observabilité (optionnelle, V1+)

Stack docker-compose additionnelle :
- **Grafana** (UI, port 3000)
- **Loki** (logs, port 3100)
- **Tempo** (traces, port 3200)
- **Prometheus** (métriques, port 9090)

Tous les services Python emettent en OpenTelemetry vers Tempo + Loki. Les workers Temporal exposent des métriques sur `/metrics`.

Désactivable via override `docker-compose.observability.yml`.

## 10. Sauvegardes

Politique simple :

- **Postgres applicatif** : backup `pg_dump` quotidien via cron (host Mac), stocké dans un volume Time Machine ou similaire.
- **MinIO** : sync rsync vers un disque externe ou NAS, manuelle.
- **Pas de backup automatique des `intermediates`** : ils sont reproductibles depuis les `raw`.
- **Backup des `outputs`** : oui, ce sont les livrables.

## 11. Coûts

| Item | Coût |
|---|---|
| Mac M3 Max (poste de dev) | déjà possédé |
| PC Windows + RTX 4090 | déjà possédé |
| Tailscale | gratuit (perso) |
| Stockage local MinIO + Postgres | gratuit |
| Pod RunPod L40S | ~0.8 €/h (à l'usage) |
| Pod RunPod A100 80GB | ~1.5 €/h |
| Bande passante RunPod | incluse |

**Coût d'un run typique** :
- 1 km en local : 0 €.
- 5 km, 1 GPU cloud, ~5 h : ~4-8 €.
- 12 km, 4 GPU cloud parallèles, ~3 h chacun : ~10-20 €.

Le projet n'a aucun coût récurrent. Le cloud est strictement à l'usage.

## 12. Procédures opérationnelles

### 12.1 Démarrage à froid

1. Boot du Mac.
2. `make up` → infra Docker.
3. (sur le PC) Boot Windows + Docker Desktop + `docker compose -f docker-compose.gpu.yml up -d`.
4. Vérifier `tailscale status` sur le Mac : le PC doit être listé en ligne.
5. Vérifier dans Temporal UI (`http://localhost:8080`) que les workers `cpu` et `gpu` sont enregistrés.

### 12.2 Diagnostic réseau

```bash
# Le PC voit-il le Mac ?
tailscale ping mac.tail-xxxx.ts.net

# Le Mac voit-il le PC ?
tailscale ping pc.tail-xxxx.ts.net

# Le Temporal est joignable depuis le PC ?
nc -zv mac.tail-xxxx.ts.net 7233
```

### 12.3 Reset complet

```bash
make down
docker volume prune -f  # ⚠ supprime DB et MinIO data
make up
make migrate
```

## 13. Points d'attention

- **Veille du PC Windows** : à désactiver, sinon les workers tombent. Configuration énergie "performances maximales".
- **Mises à jour Docker Desktop** : peuvent casser le runtime NVIDIA. Tester après chaque update.
- **Versions CUDA** : la version dans l'image Docker doit être ≤ à la version pilote NVIDIA installée sur le PC. Documenter dans le README de `gpu_worker`.
- **Disque** : MinIO peut grossir vite (les `.ply` font des Go). Surveiller, prune les `intermediates` anciens.
- **Tailscale exit nodes** : ne pas activer accidentellement (sinon tout le trafic du Mac passerait par le PC).
