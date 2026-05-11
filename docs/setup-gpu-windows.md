# Setup GPU — PC Windows (RTX 4090)

> Guide pas-à-pas pour démarrer le `gpu_worker` sur ton PC Windows avec ta RTX 4090, le relier au Temporal du Mac via Tailscale, et exécuter `train_gs` la première fois.

Référence specs : [`specs/05-infrastructure.md §5`](../specs/05-infrastructure.md), [`ADR-001`](../specs/08-decisions.md#adr-001--infrastructure-locale-sur-mac-orchestrateur), [`ADR-022`](../specs/08-decisions.md#adr-022--stratégie-doptimisation-de-coût-sans-perte-de-qualité).

---

## 1. Pré-requis matériel

| Composant | Minimum POC | Recommandé |
|---|---|---|
| GPU NVIDIA | RTX 3060 12 Go VRAM | RTX 4090 24 Go |
| Driver NVIDIA Windows | ≥ 545.84 | ≥ 555 |
| Disque libre | 50 Go | 200 Go (cache modèles + checkpoints) |
| RAM | 16 Go | 32 Go |
| Réseau | accès Internet pour Tailscale + MinIO du Mac | LAN gigabit avec le Mac |

Vérifie le driver :

```powershell
nvidia-smi
```

Doit afficher `Driver Version: 545.xx+` et `CUDA Version: 12.4+` (la ligne CUDA = max supporté par le driver, pas une version installée).

---

## 2. Docker Desktop + WSL2 + NVIDIA Container Toolkit

### 2.1 Docker Desktop

1. Installer [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
2. Activer **WSL2 backend** dans Settings → General.
3. Activer **Use the WSL 2 based engine** + **Enable integration with my default WSL distro**.

### 2.2 WSL2 Ubuntu (sert d'hôte au runtime NVIDIA)

```powershell
wsl --install -d Ubuntu-22.04
wsl -d Ubuntu-22.04
```

Dans le shell WSL :

```bash
sudo apt-get update && sudo apt-get install -y curl ca-certificates
```

### 2.3 NVIDIA Container Toolkit

Le driver NVIDIA Windows expose le GPU au WSL automatiquement (pas besoin d'installer un driver Linux). Reste à installer le runtime container :

```bash
# Dans WSL Ubuntu
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
```

Redémarrer Docker Desktop. Vérifier :

```powershell
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

Doit afficher la RTX 4090. **Si erreur "could not select device driver"** → vérifier que Docker Desktop utilise bien WSL2 et que la toolkit est installée dans la distro WSL active.

---

## 3. Tailscale

### 3.1 Sur le Mac (orchestrateur)

Si pas déjà fait : `brew install --cask tailscale`, lancer l'app, login.

Côté Mac, exposer les services aux clients du tailnet :

```bash
tailscale serve --bg --tcp 7233 tcp://127.0.0.1:7233   # Temporal
tailscale serve --bg --tcp 9000 tcp://127.0.0.1:9000   # MinIO
tailscale serve --bg --tcp 4222 tcp://127.0.0.1:4222   # NATS
```

Note l'hostname Tailscale du Mac (ex. `mac.tail-xxxx.ts.net`) — il sert de `TEMPORAL_HOST` et `MINIO_ENDPOINT` côté PC.

### 3.2 Génère un auth key réutilisable

Sur https://login.tailscale.com/admin/settings/keys :
- **Reusable** : Yes
- **Ephemeral** : Yes (recommandé pour les workers cloud, OK aussi pour le PC)
- **Tags** : `tag:gpu-worker` (à autoriser dans ACL Tailscale au préalable)
- **Expiration** : 90 jours

Copie la clé `tskey-auth-…`. Tu la mettras dans `TS_AUTHKEY` côté PC.

### 3.3 Sur le PC (option A — Tailscale dans le container)

Le `Dockerfile` du `gpu_worker` installe déjà Tailscale et l'`entrypoint.sh` lance `tailscaled --tun=userspace-networking` si `TS_AUTHKEY` est défini. Rien d'autre à faire.

### 3.3 Sur le PC (option B — Tailscale natif Windows)

Installer l'app Tailscale Windows, login. Dans ce cas, **ne pas** passer `TS_AUTHKEY` au container : il utilisera le réseau de l'hôte (mais le mode `runtime: nvidia` est compatible avec ça).

→ Option A recommandée pour reproductibilité.

---

## 4. Cloner le repo et préparer `.env`

```powershell
cd C:\src
git clone <repo-url> my-laser-scan
cd my-laser-scan
copy .env.example .env
```

Édite `.env` :

```bash
# Pointer vers le Mac via Tailscale
TEMPORAL_HOST=mac.tail-xxxx.ts.net:7233
MINIO_ENDPOINT=mac.tail-xxxx.ts.net:9000
MINIO_ACCESS_KEY=<celle du Mac>
MINIO_SECRET_KEY=<celle du Mac>
NATS_URL=nats://mac.tail-xxxx.ts.net:4222

# Auth Tailscale
TS_AUTHKEY=tskey-auth-…

# Queue GPU
TASK_QUEUE=gpu
```

---

## 5. Activer les extras GPU dans le `Dockerfile`

Le `Dockerfile` du `gpu_worker` a une étape `uv sync` **commentée** par défaut (cf. `services/gpu_worker/Dockerfile`). Décommenter :

```dockerfile
RUN uv sync --frozen --extra gs --extra mesh --extra seg --extra pbr --package road2track-gpu-worker
```

Ça installera torch 2.3+, gsplat, transformers, pytorch3d… La première compilation gsplat prend **15-30 minutes** (nvcc compile les kernels CUDA). Pas étonnant.

> ⚠️ **gsplat ↔ versions CUDA** : `gsplat` doit être compilé contre la même CUDA que le runtime container. L'image base `nvidia/cuda:12.4.0-runtime-ubuntu22.04` fournit le runtime mais pas le compiler. Si la compilation échoue, switcher la base sur `nvidia/cuda:12.4.0-devel-ubuntu22.04` (contient `nvcc`).

---

## 6. Build + run

```powershell
docker compose -f docker-compose.gpu.yml build
docker compose -f docker-compose.gpu.yml up -d
docker compose -f docker-compose.gpu.yml logs -f gpu-worker
```

Logs attendus au démarrage :

```
gpu_worker booting temporal_host=mac.tail-xxxx.ts.net:7233 task_queue=gpu
health check ok check=Temporal
health check ok check=MinIO
temporal connected
gpu_worker registered, polling task queue
```

Si Tailscale prend du temps à se connecter, l'entrypoint attend 2 s puis lance le worker. En cas d'échec health check : `tailscale ping mac.tail-xxxx.ts.net` depuis l'intérieur du container :

```powershell
docker compose -f docker-compose.gpu.yml exec gpu-worker tailscale ping mac.tail-xxxx.ts.net
```

---

## 7. Premier run de `train_gs`

Depuis le Mac :

```bash
uv run road2track ingest ./captures/balade_test
```

Le workflow `ProcessProject` enchaîne `ingest_session` → `fuse_sensors` → `detect_kind_and_trim` → `select_keyframes` sur le `cpu_worker` (Mac). **Au moment d'écrire ces lignes, `train_gs` n'est pas encore chaîné** dans `ProcessProject` (cf. CLAUDE.md §1).

Pour le tester en isolé, lancer directement l'activité via Temporal CLI (ou un script Python qui appelle `start_activity` sur la queue `gpu`).

→ Le câblage de `train_gs` dans le workflow se fera dans un commit dédié, **après** validation manuelle du premier run sur ton PC.

---

## 8. Diagnostic des cas typiques

| Symptôme | Cause probable | Fix |
|---|---|---|
| `nvidia-smi` ne voit pas le GPU dans le container | Toolkit pas installée OU Docker Desktop en mode Hyper-V | Refaire §2.3 + switch en mode WSL2 |
| `gsplat ImportError: libtorch_cuda.so` | Mismatch CUDA torch ↔ runtime image | Aligner `nvidia/cuda:X.Y.Z` et `torch==X.Y` (cf. table de compatibilité PyTorch) |
| Worker se connecte mais ne récupère pas d'activité | Wrong task queue OU temporal namespace | Vérifier `TASK_QUEUE=gpu` et `TEMPORAL_NAMESPACE` |
| `tailscale ping` échoue | Auth key expirée OU ACL bloque le tag | Régénérer la clé + vérifier ACL `tag:gpu-worker` |
| OOM CUDA pendant `train_gs` | Trop de keyframes haute résolution | Réduire `select_keyframes.min_spacing_m` côté manifest OU baisser sh_degree dans GSTrainConfig |
| Lent au premier build (gsplat compile 30 min) | Normal, nvcc compile les kernels | Patience ; les builds suivants utilisent le cache Docker |
| `out of memory` côté `uv sync` | torch + transformers = ~10 Go | Augmenter la RAM allouée à WSL2 (`%USERPROFILE%\.wslconfig` → `memory=12GB`) |

---

## 9. Mise à jour

```powershell
git pull
docker compose -f docker-compose.gpu.yml build
docker compose -f docker-compose.gpu.yml up -d
```

Le volume `gpu-worker-cache` persiste les modèles ML pré-bakés (cf. [ADR-020](../specs/08-decisions.md#adr-020--stratégie-de-cache-pour-les-modèles-ml)) entre les rebuilds.

---

## 10. Arrêt propre

```powershell
docker compose -f docker-compose.gpu.yml down
```

Tailscale se désenregistre automatiquement (ephemeral key).
