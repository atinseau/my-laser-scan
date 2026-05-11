# 07 — Roadmap

> Plan d'attaque par itérations. Chaque itération a un **objectif unique**, un **livrable mesurable**, et un **critère go/no-go** pour passer à la suivante.

## Vue d'ensemble

```
┌─ It. 0 ─────┐ ┌─ It. 1 ──────┐ ┌─ It. 2 ──────┐ ┌─ It. 3 ─────┐ ┌─ It. 4 ─────┐
│  POC qualité│ │  Pipeline    │ │  Multi-      │ │  Qualité    │ │  Passage à  │
│  texturale  │→│  bout-en-    │→│  segment +   │→│  texturale  │→│  l'échelle  │
│             │ │  bout        │ │  app iOS     │ │  V2         │ │  10-15 km   │
│  ~1-2 sem   │ │  ~5-6 sem    │ │  ~4-5 sem    │ │  ~3-4 sem   │ │  variable   │
└─────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ └─────────────┘
```

Chaque itération hérite des acquis de la précédente. **Aucune itération ne jette du code de la précédente** — toute refonte non triviale est considérée comme un signal qu'il faut revoir l'architecture.

---

## Itération 0 — POC qualité texturale

**Durée estimée** : 1 à 2 semaines.

### Objectif unique

Valider que la chaîne **Gaussian Splatting → 2DGS → bake multi-vue** produit une qualité texturale **acceptable** sur 200 m de balade en marche.

### Pourquoi en premier

C'est le **risque #1** du projet. Si la qualité texturale est insuffisante malgré tuning, toutes les itérations suivantes seraient à reconcevoir. On dérisque ici.

### Périmètre

Inclus :
- Squelette du repo `road2track/` (workspace `uv`, `core`, `geo`, `ml`, `pipeline`, `cpu_worker`, `gpu_worker`).
- `docker-compose.yml` minimal (Temporal + Postgres + MinIO).
- `docker-compose.gpu.yml` pour le PC.
- Image `gpu_worker` Docker avec CUDA + dépendances ML.
- CLI minimal : `uv run road2track ingest <path>` et `uv run road2track process <id>`.
- Workflow Temporal `ProcessProject` mono-segment, mono-tuile, sans tuilage.
- Activités : `ingest`, `select_keyframes`, `train_gs`, `extract_mesh`, `bake_textures`.
- Capture via Record3D + Sensor Logger sur **200 m en marche, boucle fermée volontaire**.
- Sortie : un dossier `output/<project>/mesh.obj + textures/` ouvrable dans Blender.

Exclu (pour les itérations suivantes) :
- Pas d'export AC.
- ~~Pas de détection circuit/spéciale~~ → pull-forward implémenté en It. 0 (cf. livrable ci-dessus).
- Pas de tuilage.
- Pas de PBR (NeILF++).
- Pas de stitching.
- Pas d'API HTTP.
- Pas d'app iOS.
- Pas de fusion capteurs sophistiquée (on accepte les poses ARKit brutes).
- Pas de RunPod (tout local entre Mac et PC).

### Livrables

- [x] Repo initialisé avec workspace `uv` complet.
- [ ] `make up` démarre l'infra sur le Mac.
- [ ] `docker compose -f docker-compose.gpu.yml up` démarre le `gpu_worker` sur le PC, qui se connecte au Temporal Mac via Tailscale.
- [x] `uv run road2track ingest ./captures/balade_test` enregistre un projet et un segment via le workflow `ProcessProject`. Le workflow chaîne `ingest_session` (upload MinIO + persistance Postgres), `fuse_sensors` (fusion ARKit + GPS → trajectoire ENU géoréférencée, alignement Kabsch), `detect_kind_and_trim` (classification circuit/spéciale par loop closure + troncature du lead-in pour les circuits, pull-forward de l'It. 1 — cf. ADR-007/ADR-016) puis `select_keyframes` (sampling spatial tous les 0.5 m + extraction JPEG ffmpeg + upload MinIO).
- [ ] `uv run road2track process <project-id>` lance le workflow complet jusqu'au mesh + textures (étapes downstream à implémenter).
- [ ] Le résultat est ouvert dans Blender et **visuellement validé** par l'utilisateur.
- [ ] **Validation technique du pattern session activities** Temporal (cf. [ADR-019](./08-decisions.md#adr-019--session-activities-pour-chaîner-le-pipeline-gpu-dune-tuile)). Si KO, fallback documenté dans un ADR de remplacement.
- [x] **Cross-corrélation IMU/ARKit** opérationnelle comme fallback de la sync UTC (cf. [ADR-017](./08-decisions.md#adr-017--synchronisation-record3d--sensor-logger-via-timestamps-utc)). Code dans `road2track_geo.fusion.sync.compute_sync` + `cross_correlation_offset_ms`.
- [x] **Lint CI** qui vérifie que `pipeline/workflows/` n'importe aucun adapter (cf. [`02-architecture.md §2`](./02-architecture.md#règles-dinclusion)).
- [x] **Health checks** au démarrage du `cpu_worker` (Temporal, Postgres, MinIO, NATS) ; même mécanisme prévu pour `gpu_worker`.
- [ ] **Mesure empirique du temps GS 30k iter** pour valider ou ajuster le critère "< 6 h pour 1 km" du MVP (cf. `04 §3.3`).
- [x] **Mixed precision FP16 activée** dans `train_gs` (cf. [ADR-022](./08-decisions.md#adr-022--stratégie-doptimisation-de-coût-sans-perte-de-qualité), levier #2). Câblée dans `GSTrainConfig.use_fp16=True` + `torch.amp.autocast` + `GradScaler`. Gain réel à mesurer empiriquement sur RTX 4090.
- [ ] Production de `specs/reviews/0-end-of-iteration.md` à la fin.

### Statut détaillé au handoff (snapshot 2026-05-11)

> Section ajoutée pour permettre la reprise à froid. À jour de la branche
> `claude/lidar-circuit-generator-UCDti` (commit `0d77da1` au moment d'écrire).

**Code écrit, testé en CI (146 unit + 9 intégration)** :

| Activité | Module | Statut | Validé hardware ? |
|---|---|---|---|
| `ingest_session` | `pipeline/activities/ingest.py` | ✅ implémenté | ❌ |
| `fuse_sensors` | `pipeline/activities/fuse_sensors.py` + `geo/fusion/trajectory.py` | ✅ Kabsch ARKit↔GPS | ❌ |
| `detect_kind_and_trim` | `pipeline/activities/detect_kind_and_trim.py` + `geo/detection/track_kind.py` | ✅ pull-forward de l'It. 1 | ❌ |
| `select_keyframes` | `pipeline/activities/select_keyframes.py` + `geo/sampling/spatial.py` | ✅ sampling 0.5 m + ffmpeg JPEG | ❌ |
| `train_gs` | `pipeline/activities/train_gs.py` + `ml/gs/{config,dataset,intrinsics,initialization,losses,checkpoint,ply_io,training}.py` | ✅ **à l'aveugle** (gsplat + FP16 + checkpoint MinIO 5k iter) | ❌ |
| `extract_mesh` | `pipeline/activities/extract_mesh.py` + `ml/mesh/extraction.py` | ✅ **à l'aveugle** (Poisson Open3D + decimation) | ❌ |
| `bake_textures` | `pipeline/activities/bake_textures.py` + `ml/texture/baking.py` | ✅ **à l'aveugle** (projection multi-vue vertex colors) | ❌ |

**Workflow `ProcessProject`** chaîne **`ingest_session → fuse_sensors → detect_kind_and_trim → select_keyframes`** uniquement.
Les trois activités GPU (`train_gs`, `extract_mesh`, `bake_textures`) sont **registrées** sur le `gpu_worker` (queue `gpu`) mais **non chaînées** dans le workflow. Décision : on attend une validation manuelle de chaque étape avant de chaîner, pour éviter de tout casser au premier run.

**Limitations POC explicitement assumées** (à éventuellement adresser en It. 0 ou reporter en It. 1) :

| # | Limitation | Module concerné | Impact POC visuel Blender | Bloquant It. 1 (AC export) ? |
|---|---|---|---|---|
| 1 | Pas de z-buffer occlusion lors du projection vertex color | `ml/texture/baking.py:_bake_vertex_colors` | ⚠️ utile si scène non 100% ouverte | oui |
| 2 | Pas d'UV unwrap réel — atlas placeholder uniforme | `ml/texture/baking.py:_write_placeholder_atlas` | ❌ vertex colors suffisent | **oui, bloquant** |
| 3 | Pas de blending laplacien / seam removal multi-vue | `ml/texture/baking.py` | ❌ qualité fine | nice-to-have |
| 4 | Pas de tone mapping HDR (travail en sRGB linéaire) | `ml/texture/baking.py` | ❌ niche (scènes très contrastées) | nice-to-have |

**Risques connus du code GPU "à l'aveugle"** (Module `ml/gs/training.py`) :
- Convention quaternion gsplat (wxyz vs xyzw selon version).
- `viewmat` = `T_camera_world` ; signe de `-R.T @ t` peut être faux selon convention ARKit.
- `gsplat.rasterization` signature exacte (présence/absence de `packed`, `render_mode`, etc. selon version installée).
- Mixed precision FP16 : possible NaN si `GradScaler` mal initialisé.
- `Poisson reconstruction` Open3D : RAM ~16 Go pour 500k gaussiennes à `depth=10`.

**Procédure de test (premier run sur hardware)** :

1. Mac : `make up` + `tailscale serve --bg --tcp 7233 tcp://127.0.0.1:7233` (idem MinIO 9000, NATS 4222).
2. Mac : `make worker-cpu` (process direct).
3. PC Windows : décommenter `RUN uv sync --frozen --extra gs --extra mesh ...` dans `services/gpu_worker/Dockerfile`, puis `docker compose -f docker-compose.gpu.yml build` (≈30 min nvcc) + `up -d`. Suivre [`docs/setup-gpu-windows.md`](../docs/setup-gpu-windows.md).
4. Capture iPhone Record3D Pro + Sensor Logger sur ~200 m boucle fermée.
5. Mac : `uv run road2track ingest ./captures/balade_test` → exécute jusqu'à `select_keyframes`.
6. **Étape manuelle** : déclencher `train_gs` → `extract_mesh` → `bake_textures` une par une (Temporal UI sur http://127.0.0.1:8233 OU script `tools/run_gpu_pipeline.py` à écrire). Permet de débugger chaque étape isolément.
7. Télécharger `intermediates/<p>/<s>/textured/mesh.obj` depuis MinIO, ouvrir dans Blender, valider visuellement.

**Pour clore l'It. 0** :
- [ ] Câbler `train_gs → extract_mesh → bake_textures` dans `ProcessProject` (≈30 lignes).
- [ ] Créer `tools/run_gpu_pipeline.py` ou `road2track process <id> --from select_keyframes` pour faciliter le re-run.
- [ ] Z-buffer occlusion dans `bake_textures` si la qualité visuelle est insuffisante (optionnel).
- [ ] Mesures empiriques (temps GS 30k iter, PSNR, RMSE Kabsch sur vrai GPS) à reporter dans `specs/reviews/0-end-of-iteration.md`.
- [ ] Décision go/no-go It. 1.

### Critère go/no-go

| Critère | Mesure |
|---|---|
| Le mesh est cohérent | La route est reconnaissable, pas de gros trous. |
| Les textures sont issues des photos | Pas de stylisé ; pixels reconnaissables. |
| La qualité est jugée "acceptable" | Validation visuelle subjective dans Blender. |
| Le pipeline est rejouable | Re-run sur le même dataset → résultat équivalent. |
| Couverture de tests sur `core` et `geo` | ≥ 80% sur les modules touchés. |

**Si NO-GO** : on ré-évalue la stack ML. Alternatives à explorer dans l'ordre : Mip-Splatting, Gaussian Frosting, photogrammétrie classique (COLMAP + Reality Capture), NeRFacto. Voir [`09-questions-ouvertes.md`](./09-questions-ouvertes.md).

### Dépendances

- Capture Record3D Pro + Sensor Logger préalable sur un tronçon test.
- Tailscale configuré entre Mac et PC.
- Docker NVIDIA Container Toolkit installé sur le PC.

---

## Itération 1 — Pipeline bout-en-bout (MVP cœur)

**Durée estimée** : 5 à 6 semaines (le scope inclut EKF, segmentation, decimation, FBX, ksEditor, AI line, packaging CM, tests E2E — réalisme solo dev).

### Objectif unique

Produire un **circuit AC installable et roulable** sur 1 km, depuis l'ingestion jusqu'à un zip Content Manager, sans intervention manuelle.

### Périmètre

Inclus :
- Tout l'It. 0.
- Fusion capteurs **EKF** (GPS+IMU+ARKit). Voir [`04-pipeline-ml.md#22-fusion-capteurs`](./04-pipeline-ml.md#22-fusion-capteurs).
- Détection circuit/spéciale (`detect_kind`).
- Segmentation sémantique (Mask2Former).
- Segmentation du mesh + decimation + UV unwrap.
- Génération du `.fbx`, des fichiers AC (`surfaces.ini`, `models.ini`, etc.).
- Génération de la `fast_lane.ai` (algorithme simple).
- Compilation `.kn5` via ksEditor sur le PC Windows (worker `windows-tools`).
- Packaging Content Manager (zip + `ui_track.json` + miniatures).
- Publication du résultat dans MinIO + URL téléchargeable.
- CLI : `uv run road2track export <project-id> --output ~/Downloads/`.
- Estimation PBR via **fallback** (pas de NeILF++ encore) : tile asphalte procédurale + roughness par classe.

Exclu :
- Pas de tuilage (mono-tuile, max ~1 km en VRAM).
- Pas de stitching (n'a pas de sens en mono-tuile).
- Pas d'app iOS.
- Pas de pause/reprise/multi-passe (mono-segment).
- Pas de NeILF++ (V1).
- Pas de RunPod (tout sur le PC local).
- Pas d'API HTTP (CLI suffit).

### Livrables

- [ ] Tous les workflows / activités décrits dans `04-pipeline-ml.md` pour le mono-tuile.
- [ ] Templates Jinja des fichiers AC.
- [ ] Worker `windows-tools` (natif Windows sur le PC) qui compile le KN5 via `ksEditor.exe`.
- [ ] 🧪 **Prototype `wine-worker`** (image Docker Linux + Wine + ksEditor) en parallèle, à valider sur 5 KN5 de référence avant la fin de l'itération. Si validé → permet de retirer la dépendance PC en V2 (cf. QO-007).
- [ ] **Validation empirique de l'orientation des axes** (Y-up ou Z-up) pour AC, fixée définitivement (cf. `06 §1`).
- [ ] **Commande `make backup-outputs`** opérationnelle (copie incrémentale datée des outputs MinIO vers un dossier local).
- [ ] **Spot pricing + checkpointing GS** opérationnel (cf. [ADR-022](./08-decisions.md#adr-022--stratégie-doptimisation-de-coût-sans-perte-de-qualité), levier #1) : checkpoint MinIO toutes les 5 000 iter, reprise automatique après éviction d'un pod spot. Gain attendu : -50% sur le cloud spend.
- [ ] Suite de tests E2E sur dataset jouet (200 m).
- [ ] Documentation utilisateur dans `README.md` mise à jour.
- [ ] Premier circuit installé via Content Manager et rouler dedans.
- [ ] Production de `specs/reviews/1-end-of-iteration.md` à la fin.

### Critères go/no-go

| Critère | Cible |
|---|---|
| Tronçon supporté | 1 km |
| Temps de traitement | < 6 h sur RTX 4090 (à confirmer ou assouplir selon mesures POC) |
| Détection circuit/spéciale | Fonctionne sur 5 cas de test |
| Format de sortie | Package CM installable |
| Roulabilité | On peut faire un tour, l'AI line est cohérente |
| Lint CI workflows/adapters | Aucun import interdit détecté |
| Couverture tests | ≥ 80% sur `core`, `geo` ; ≥ 60% sur `pipeline` |

### Risques principaux

- **Compilation KN5** : ksEditor CLI peut être finicky, prévoir buffer.
- **Format AC** : nécessite tests et calibration sur des templates fonctionnels.
- **Bake multi-vue performance** : peut être lent, optimisation CUDA/PyTorch3D nécessaire.

---

## Itération 2 — Capture multi-segment + app iOS

**Durée estimée** : 4 à 5 semaines.

### Objectif unique

Permettre à l'utilisateur de capturer en **plusieurs sessions / passes**, avec **pause/reprise** et **multi-passe qualité**, via une **application iOS native**.

### Périmètre

Inclus :
- App iOS minimaliste (SwiftUI + ARKit + AVFoundation + CoreLocation + CoreMotion).
- Capture pause/reprise intra-session (cas A).
- Reprise différée avec relocalisation (cas B).
- Multi-passe sur zone existante (cas C).
- Heatmap de couverture en temps réel sur l'app.
- Barre de progression à 3 niveaux.
- Upload chunké et resumable vers le backend.
- API HTTP FastAPI sur Tailscale : création projet, ajout session, statut, download.
- Synchronisation timestamps précise au niveau frame entre LiDAR/RGB/IMU/GPS.
- Activités backend : `relocalize`, `coverage_update`, `merge_segments`.
- Détection automatique du mode A/B/C par le backend selon proximité.
- Distribution iOS via TestFlight ou ad-hoc (pas d'App Store).

Exclu :
- Pas encore de tuilage (le projet reste limité à 1-2 km au max).
- Pas de stitching.
- Pas de cloud RunPod.
- Pas d'amélioration qualité ML (NeILF++ etc.) — c'est l'It. 3.

### Livrables

- [ ] App iOS sur ton iPhone Pro.
- [ ] API FastAPI fonctionnelle sur Tailscale.
- [ ] Capture en 2 sessions à 1 jour d'écart, ré-aligné automatiquement.
- [ ] Multi-passe qui améliore une zone testée mesurablement (PSNR + visuel).
- [ ] Worker `windows-tools` exposant aussi des activités plus riches si besoin.
- [ ] Documentation iOS dans `apps/ios/README.md`.
- [ ] **Continue-from-checkpoint pour le multi-passe** (cf. [ADR-022](./08-decisions.md#adr-022--stratégie-doptimisation-de-coût-sans-perte-de-qualité), levier #3) : training de la passe N+1 reprend du checkpoint de la passe N. Gain attendu : -65% sur les passes additionnelles.
- [ ] Production de `specs/reviews/2-end-of-iteration.md` à la fin.
- [ ] Couverture tests : maintien ≥ 80% sur `core`, `geo` ; ≥ 60% sur `pipeline` ; nouveaux modules couverts à ces seuils.

### Critères go/no-go

| Critère | Cible |
|---|---|
| Pause/reprise intra-session | Fonctionne sans relocalisation |
| Reprise différée | < 30 s pour relocaliser |
| Multi-passe | Une 2e passe améliore le PSNR d'au moins 1 dB |
| Stabilité de l'app | Pas de crash sur 30 min de capture |
| Synchronisation | Erreur < 50 ms entre flux |

---

## Itération 3 — Qualité texturale V2

**Durée estimée** : 3 à 4 semaines.

### Objectif unique

Atteindre la promesse "**photoréalisme à vitesse de jeu**". Pousser la qualité texturale au-delà du seuil "acceptable" du POC vers "convaincant en mouvement".

### Périmètre

Inclus :
- Intégration **NeILF++** (ou alternative validée) pour la PBR réelle (delight, normales, roughness).
- Bake multi-vue **robuste** : rejet d'occluders amélioré, médiane pondérée optimisée, gestion ombres dures.
- Atlas de textures global cohérent (vs par-tuile).
- Asphalte procédural calibré par roughness LiDAR (élimine le "flat plastique").
- Skybox HDRi capturée par l'iPhone (mode photo HDR pano) → utilisée comme env map AC.
- Detection et inpainting des passants/voitures restants après bake.
- Validation comparée : pre-It.3 vs post-It.3 sur le même dataset (PSNR, LPIPS, jugement humain).

Exclu :
- Toujours pas de tuilage massif (limite restera ~1-2 km).
- Pas d'autres jeux (rFactor, BeamNG).

### Livrables

- [ ] PBR pipeline production-ready.
- [ ] Méthodologie de validation qualitative documentée.
- [ ] 3 circuits de référence générés et catalogués.
- [ ] Article de blog/post privé décrivant la méthode (interne, pas de publication).
- [ ] Production de `specs/reviews/3-end-of-iteration.md` à la fin.
- [ ] Couverture tests maintenue aux seuils de 02-architecture.md §8.

### Critères go/no-go

| Critère | Cible |
|---|---|
| PSNR sur frames de validation | > 28 dB (vs > 25 dB MVP) |
| LPIPS | < 0.15 |
| Jugement utilisateur | "convaincant en jeu" sur 5 utilisateurs |
| Coût : pas plus de 30% de temps en plus vs It. 1 |  |

---

## Itération 4 — Passage à l'échelle 10-15 km

**Durée estimée** : variable (probablement 4-6 semaines avec polishing).

### Objectif unique

Supporter des tronçons jusqu'à **15 km** via tuilage et compute cloud.

### Périmètre

Inclus :
- Tuilage spatial complet ([`04-pipeline-ml.md#stratégie-de-tuilage`](./04-pipeline-ml.md#stratégie-de-tuilage)).
- Stitching de tuiles avec ICP local + blending.
- Provider RunPod opérationnel (provisioning, shutdown, logging).
- Provider abstraction prête à accueillir vast.ai et autres.
- Optimisation coût : caching modèles HF, partage de pré-traitement entre tuiles.
- Streaming pipeline : début de stitching dès que tuiles consécutives sont prêtes.
- Gestion robuste des retries cloud (pods qui meurent, réseaux instables).
- Web UI status (consultable sur le Mac).
- Compteur de coûts cloud en temps réel.

Exclu (peut-être V2) :
- Pas encore d'anonymisation.
- Pas encore d'édition légère.
- Pas encore de météo dynamique.

### Livrables

- [ ] Pipeline 12 km validé (tronçon de référence : Col du Galibier descente p.ex.).
- [ ] Compteur de coûts intégré au CLI.
- [ ] Web UI status fonctionnelle (choix du stack frontend tranché — cf. QO-011).
- [ ] Documentation de provisioning RunPod.
- [ ] **Optimisations cloud avancées** (cf. [ADR-022](./08-decisions.md#adr-022--stratégie-doptimisation-de-coût-sans-perte-de-qualité)) : leviers #4 (multi-provider), #5 (GPU tiering), #6 (cache image), #7 (compression Zstd), #8 (auto-shutdown), #9 (pipeline parallelism). Gain cumulé attendu : passer de ~14 € à ~10 € sur 12 km.
- [ ] **Review finale** transverse du projet, audit complet : production de `specs/reviews/final-review.md`. Lie chaque constat aux exigences de `01-cahier-des-charges.md` et aux ADRs.
- [ ] Couverture tests maintenue.

### Critères go/no-go

| Critère | Cible |
|---|---|
| Tronçon supporté | 15 km |
| Temps total (12 km, 4 GPU // ) | < 8 h wall-clock |
| Coût | < 20 € par run 12 km |
| Stabilité | 95% de runs réussissent du premier coup |

---

## Au-delà (V2)

Après l'It. 4, le produit est **stable et complet** pour le persona. Pas d'itération de stabilisation supplémentaire entre It. 4 et V2 : la qualité doit être atteinte au fil de l'eau, à chaque itération, en respectant les couvertures de tests et les reviews de qualité. La V2 démarre directement sur les nouvelles features.

Évolutions possibles :

- **Anonymisation automatique** (CH-PRI-1 du cahier des charges).
- **Édition légère** post-génération (CH-EDI-1).
- **Météo dynamique** (CH-MET-1, CH-MET-2).
- **Génération d'assets de bord de route** (CH-AST-1).
- **Support d'autres jeux** (CH-MUL-1).
- **Optimisations coût** drastiques (CH-OPT-1).

Chaque évolution sera évaluée à l'aune des critères MoSCoW dans [`01-cahier-des-charges.md`](./01-cahier-des-charges.md) au moment opportun.

---

## Notes transverses

### Critères de qualité par itération

À chaque transition d'itération, les critères ne se substituent pas, ils **s'ajoutent**. Une régression sur un critère antérieur **bloque** la sortie de l'itération en cours.

### Taille des PRs

Les PRs doivent être **focalisées** : une seule activité ou un seul package par PR. Pas de "big bang" qui touche 20 fichiers.

### Tests

À partir de l'It. 1, **toute nouvelle activité** doit avoir :
- Un test unitaire sur sa logique pure (s'il y en a).
- Un test d'intégration mockant ses I/O.
- Un cas inclus dans le test E2E sur le dataset jouet.

### Reviews

Le projet prévoit des reviews :
- **Fin de chaque itération** : review de qualité + détection de failles. Un document `specs/reviews/N-end-of-iteration.md` est produit.
- **Review finale** : audit complet à la fin de l'It. 4.
