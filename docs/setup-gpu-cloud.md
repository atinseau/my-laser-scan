# Setup GPU — Cloud (RunPod, spillover)

> Guide pas-à-pas pour lancer un `gpu_worker` sur un pod cloud RunPod, le relier au Temporal du Mac via Tailscale, et profiter du spot pricing + checkpointing (cf. [ADR-022](../specs/08-decisions.md#adr-022--stratégie-doptimisation-de-coût-sans-perte-de-qualité)).

Référence specs : [`specs/05-infrastructure.md §5.3`](../specs/05-infrastructure.md), [`ADR-018`](../specs/08-decisions.md#adr-018--pas-dauto-provisioning-cloud-au-poc), [`ADR-022`](../specs/08-decisions.md#adr-022).

---

## 1. Pourquoi le cloud ?

- **Quand le PC tourne déjà** sur un autre projet (parallélisme).
- **Quand un job tire un L40S/A100** (80 Go VRAM) pour une scène longue (> 1 km).
- **Pour les pics ponctuels** : louer 2 h à 1 €/h plutôt qu'attendre la nuit.

Coûts indicatifs (snapshot 2026-05) :

| GPU | RunPod community | RunPod spot |
|---|---|---|
| L40S 48 Go | ~0.8 €/h | ~0.4 €/h |
| A100 80 Go | ~1.5 €/h | ~0.8 €/h |

Le **spot** est ~50% moins cher mais peut être évincé. Le `gpu_worker` checkpointe toutes les 5 000 itérations sur MinIO (cf. ADR-022 levier #1) → reprise automatique après éviction, perte max ~15 min.

---

## 2. Pré-requis

1. **Compte RunPod** : https://runpod.io, valider l'email, charger ≥ 20 $ de crédit.
2. **API key RunPod** : Settings → API Keys → "Create API Key" → copier dans `.env` côté Mac :
   ```bash
   RUNPOD_API_KEY=rp_…
   ```
3. **Auth key Tailscale réutilisable** (cf. [`setup-gpu-windows.md §3.2`](./setup-gpu-windows.md#32-génère-un-auth-key-réutilisable)) avec **Ephemeral: Yes** et tag `tag:gpu-worker`.
4. **Image Docker publiée** : tu dois pousser ton image `road2track/gpu-worker:0.1.0` quelque part accessible depuis RunPod. Trois options :
   - **A. RunPod registry interne** (recommandé) : push direct.
   - **B. GitHub Container Registry** (`ghcr.io/<user>/road2track-gpu-worker:0.1.0`).
   - **C. Docker Hub** (`<user>/road2track-gpu-worker:0.1.0`).

   Build et push depuis ton PC :
   ```powershell
   docker buildx build -t ghcr.io/<user>/road2track-gpu-worker:0.1.0 -f services/gpu_worker/Dockerfile --push .
   ```

---

## 3. Topologie réseau

```
┌──────── Mac (orchestrateur) ─────────┐
│  temporal:7233 (binded 127.0.0.1)    │
│  minio:9000                          │
│  nats:4222                           │
│  + Tailscale "serve" → exposés au    │
│    tailnet privé                     │
└──────────────────────────────────────┘
              ▲
              │ Tailscale userspace networking
              │
┌──────── Pod RunPod ──────────────────┐
│  gpu_worker (image road2track/...)   │
│  tailscaled --tun=userspace          │
│  → tailscale up --authkey=…          │
│  TEMPORAL_HOST=mac.tail-xxxx.ts.net  │
└──────────────────────────────────────┘
```

**Aucun port n'est ouvert sur Internet**. RunPod ne voit que l'IP Tailscale du Mac, joignable uniquement par les nodes de ton tailnet.

---

## 4. Lancement manuel via UI RunPod

### 4.1 Créer un pod

1. RunPod → Pods → **Deploy** → **GPU Cloud** (Community Cloud OK pour POC).
2. **GPU type** : "L40" ou "L40S" (24-48 Go) → recommandé pour démarrer.
3. **Region** : la plus proche (latence Tailscale).
4. **Template** : "Custom Template" → onglet **Edit Template**.

### 4.2 Configuration du template

| Champ | Valeur |
|---|---|
| Container Image | `ghcr.io/<user>/road2track-gpu-worker:0.1.0` |
| Container Disk | 50 Go (cache modèles + checkpoints temporaires) |
| Volume Mount | `/cache` → 100 Go persistant (optionnel, accélère les redéploiements) |
| Expose HTTP Ports | aucun |
| Expose TCP Ports | aucun (tout passe par Tailscale) |
| Container Start Command | `/entrypoint.sh uv run python -m services.gpu_worker` |

### 4.3 Variables d'environnement

```
TEMPORAL_HOST=mac.tail-xxxx.ts.net:7233
TEMPORAL_NAMESPACE=default
MINIO_ENDPOINT=mac.tail-xxxx.ts.net:9000
MINIO_ACCESS_KEY=<celle du Mac>
MINIO_SECRET_KEY=<celle du Mac>
MINIO_BUCKET_RAW=raw
MINIO_BUCKET_INTERMEDIATES=intermediates
MINIO_BUCKET_OUTPUTS=outputs
NATS_URL=nats://mac.tail-xxxx.ts.net:4222
TS_AUTHKEY=tskey-auth-…
TASK_QUEUE=gpu
LOG_LEVEL=INFO
```

### 4.4 Spot vs On-Demand

- **On-Demand** : pas d'éviction, ~0.8 €/h L40S.
- **Spot Interruptible** : ~50% moins cher, éviction possible avec 30 s de préavis.

→ **Pour `train_gs`** : spot OK, le checkpointing 5k iter rattrape les évictions (cf. ADR-022).
→ **Pour `bake_textures` / `extract_mesh`** (étapes longues mais sans checkpoint intra-step) : prendre **On-Demand** ou découper en sous-jobs courts.

### 4.5 Démarrer le pod

Click "Deploy". RunPod pulle l'image (~2-5 min la première fois), démarre le container, et `entrypoint.sh` rejoint le tailnet.

Vérifie côté Mac :

```bash
tailscale status | grep gpu-worker
# Doit apparaître : 100.x.x.x   gpu-worker-runpod-xxxx   <user>@   linux  active; ...
```

Vérifie les logs du pod dans l'UI RunPod (onglet "Logs") :

```
gpu_worker booting temporal_host=mac.tail-xxxx.ts.net:7233 task_queue=gpu
health check ok check=Temporal
health check ok check=MinIO
temporal connected
gpu_worker registered, polling task queue
```

---

## 5. Lancement programmé via CLI (V1+)

Le module `packages/cloud_bridge/` est prévu pour automatiser ça (cf. [`specs/05-infrastructure.md §5.4`](../specs/05-infrastructure.md)).

**Au POC, non implémenté** : on utilise l'UI RunPod (§4) ou `curl` sur l'API.

Pour référence, la CLI ciblée à terme :

```bash
uv run road2track gpu spawn \
    --provider runpod \
    --gpu l40s \
    --spot \
    --hours 2 \
    --image ghcr.io/<user>/road2track-gpu-worker:0.1.0

uv run road2track gpu list
uv run road2track gpu shutdown --provider runpod --pod <id>
```

→ Status : **non implémenté**. Voir [ADR-018](../specs/08-decisions.md#adr-018--pas-dauto-provisioning-cloud-au-poc) — au POC on accepte un setup cloud manuel.

---

## 6. Stratégie spot + checkpointing (ADR-022)

L'éviction d'un pod spot fait perdre tout le RAM/VRAM. Le `gpu_worker` :

1. À chaque `checkpoint_every` itérations (défaut 5000, cf. `GSTrainConfig`), `train_gs` sauve un `.pt` local puis l'**upload sur MinIO** via le callback async.
2. À la prochaine reprise (nouveau pod, OU re-spawn du même pod), le workflow `ProcessProject` réassigne l'activité `train_gs`. Le worker recharge le dernier checkpoint depuis MinIO (champ `resume_from_checkpoint_uri` de `GSTrainConfig`) et reprend la boucle là où elle s'était arrêtée.
3. Loss et n_gaussians sont restaurés. Perte effective < 15 min en moyenne (5 000 iter à ~3000 iter/s → ~1.5 min).

Pour activer la reprise côté code :

```python
config = GSTrainConfig(
    resume_from_checkpoint_uri="s3://intermediates/<project>/<segment>/checkpoints/ckpt_010000.pt",
)
```

L'activité Temporal `train_gs` détecte ce champ, télécharge le `.pt` avant de lancer `train(...)`.

---

## 7. Diagnostic

| Symptôme | Cause probable | Fix |
|---|---|---|
| Pod démarre mais `tailscale status` ne montre rien sur le Mac | TS_AUTHKEY expirée ou mauvais tag | Vérifier la clé + ACL Tailscale autorise `tag:gpu-worker` |
| Worker se connecte puis se bloque sur `health check Temporal` | `tailscale serve` pas configuré côté Mac OU port 7233 non exposé | Sur le Mac : `tailscale serve --bg --tcp 7233 tcp://127.0.0.1:7233` |
| `gsplat ImportError: undefined symbol` | Image compilée avec une autre version CUDA que le runtime RunPod | Aligner la base `nvidia/cuda:X.Y.Z` avec la driver du pod (visible dans `nvidia-smi` côté pod) |
| Coût qui explose | Pods orphelins après éviction non détectée | `runpod` UI → kill tous les pods inactifs. À terme, `road2track gpu list` les listera automatiquement |
| Latence MinIO élevée (uploads checkpoints lents) | Pod cross-continent | Choisir une region proche du Mac, OU déployer un MinIO miroir cloud (V1+) |

---

## 8. Coûts observés (à mettre à jour empiriquement à It. 0/1)

À compléter après le premier run réel :

| Métrique | Mesure |
|---|---|
| `train_gs` 30k iter L40S spot | _TBD_ minutes / _TBD_ € |
| `train_gs` 30k iter L40S on-demand | _TBD_ minutes / _TBD_ € |
| `extract_mesh` L40S | _TBD_ |
| `bake_textures` L40S | _TBD_ |
| Bande passante in/out par projet | _TBD_ Go |

Cf. [`specs/07-roadmap.md`](../specs/07-roadmap.md) — la production de `specs/reviews/0-end-of-iteration.md` doit inclure ces mesures.
