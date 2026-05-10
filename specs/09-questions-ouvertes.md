# 09 — Questions ouvertes

> Liste vivante de décisions techniques à trancher au fil des itérations. Quand une question est tranchée, elle quitte ce document et devient un ADR dans [`08-decisions.md`](./08-decisions.md).

## État du suivi

| État | Nombre | Détail |
|---|---|---|
| 🟢 Ouvertes | 12 | Décisions encore à prendre |
| 🟡 En cours | 1 | QO-007 (validation Wine) |
| ✅ Tranchées | 4 | QO-002a → POC, QO-005 → ADR-020, QO-008 → ADR-019, QO-015 → ADR-021 |
| **Total** | **17** | |

Mis à jour : Review finale (2026-05-06).

## Convention

Chaque question a :
- Un **identifiant** stable (`QO-XXX`).
- Un **statut** : `ouverte` | `en cours` | `tranchée → ADR-YYY`.
- L'**itération cible** où elle doit être tranchée.
- Le **contexte** et les **options** envisagées.

---

## Questions actives

### QO-001 — Implémentation 2DGS exacte

- **Statut** : ouverte
- **Itération cible** : 0
- **Bloque** : `train_gs` activity, `extract_mesh` activity

**Contexte** : plusieurs forks/implémentations de 2D Gaussian Splatting existent (repo officiel hbb1/2d-gaussian-splatting, intégrations Nerfstudio, etc.). Performance et qualité variables.

**Options** :
- A. Repo officiel `hbb1/2d-gaussian-splatting`.
- B. Variante Nerfstudio si intégrée.
- C. SuGaR (alternative basée mesh-from-splats).
- D. Mip-Splatting + extraction custom.

**À tester au POC** sur un dataset commun.

---

### QO-002a — Format des poses iPhone (POC)

- **Statut** : tranchée → on prend Record3D format JSON tel quel (poses 6DoF translation + quaternion par frame).
- **Date** : 2026-05-06

**Décision** : au POC et au MVP, on consomme directement le format de poses produit par Record3D (cf. [`06-modele-donnees.md §4.2`](./06-modele-donnees.md#42-données-de-capture-segment-record3d--sensor-logger)). Pas de transformation amont nécessaire.

### QO-002b — Format des poses iPhone (app native It. 2)

- **Statut** : ouverte
- **Itération cible** : 2
- **Bloque** : conception du format de capture de l'app native

**Contexte** : pour l'app iOS native (It. 2), on aura le choix sur le format de stockage des poses :

**Options** :
- A. Toujours poses brutes (translation + quaternion) ; relocalisation via matching de features visuelles côté backend.
- B. **ARWorldMap** ARKit stocké + poses dérivées ; relocalisation via ARKit lui-même.
- C. Hybride.

**À trancher** lors de l'It. 2 quand on conçoit l'app native.

---

### QO-003 — EKF custom vs lib existante

- **Statut** : ouverte
- **Itération cible** : 1
- **Bloque** : `fuse_sensors` activity

**Contexte** : la fusion VIO+GPS+IMU peut être faite avec un EKF custom (~500 lignes) ou via une lib existante (filterpy, robotic-toolbox, ou une partie de OpenVINS).

**Options** :
- A. EKF custom Python (full control, tuning facile).
- B. filterpy (lib mature, mais peut être limitée).
- C. OpenVINS (puissant mais C++, intégration via Python lourde).
- D. Approche minimaliste : moyenne pondérée + smoothing, sans EKF.

**À trancher** au début de l'It. 1.

---

### QO-004 — Stratégie de relocalisation visuelle

- **Statut** : ouverte
- **Itération cible** : 2
- **Bloque** : reprise différée multi-session

**Contexte** : pour reprendre une capture le lendemain, on doit replacer le repère. Plusieurs approches.

**Options** :
- A. **ARWorldMap** d'ARKit (limité dans le temps et nécessite stocker le map).
- B. **Matching de features** (ORB, SIFT) entre frames courantes et keyframes existants.
- C. **Place recognition** (NetVLAD ou similaire).
- D. **Re-localisation par GPS** brute (imprécise mais simple).

**À trancher** au démarrage de l'It. 2.

---

### QO-005 — Cache des modèles ML

- **Statut** : tranchée → [ADR-020](./08-decisions.md#adr-020--stratégie-de-cache-des-modèles-ml-mix-pré-bake--minio)
- **Décision** : option D — pré-bake des modèles essentiels (Mask2Former, gsplat init) dans l'image `gpu_worker` ; cache MinIO pour les modèles plus volumineux ou variables (NeILF++).

---

### QO-006 — Atlas de textures par-tuile vs global

- **Statut** : ouverte
- **Itération cible** : 4
- **Bloque** : `stitch_tiles` activity

**Contexte** : après stitching, on a deux options pour les textures.

**Options** :
- A. **Par-tuile** : chaque tuile garde son atlas, on a un mesh multi-matériaux. AC le supporte.
- B. **Global** : repacker tous les atlases en un (ou quelques) atlas final. Plus uniforme visuellement, mais coûteux.

**Compromis** : A est plus simple, B donne un meilleur résultat à long terme.

---

### QO-007 — Validation de Wine pour `compile_kn5`

- **Statut** : en cours (prototype dès It. 1)
- **Itération cible** : 1 ou 2
- **Bloque** : portabilité totale (suppression de la dépendance PC Windows)

**Contexte** : `ksEditor.exe` est Windows-only. L'option A (worker Windows natif sur le PC) est retenue pour le MVP/V1 (cf. [`05-infrastructure.md §5.4`](./05-infrastructure.md#54-compilation-kn5--cas-particulier)). En parallèle, on prototype l'option B : container Docker Linux avec Wine + ksEditor packagés.

**Critères d'acceptation pour valider Wine** :
- Au moins **5 KN5 différents** générés via Wine doivent être **bit-à-bit identiques** ou fonctionnellement équivalents en jeu à ceux générés via Windows natif.
- Pas de régression observée sur :
  - Les textures (albedo, normal, roughness).
  - L'AI line.
  - Les surfaces (frictions correctes).
  - Le chargement dans Content Manager.
- Performance acceptable : compilation Wine ≤ 2× le temps natif.

**Si validé** → ADR (probablement ADR-020+) qui acte Wine comme principal. Le PC est rétrogradé en secours optionnel. Migration progressive en V2.

**Si invalidé** → on garde le PC comme dépendance et on continue avec l'option A.

---

### QO-008 — Format intermédiaire entre activités GPU

- **Statut** : tranchée → [ADR-019](./08-decisions.md#adr-019--session-activities-pour-chaîner-le-pipeline-gpu-dune-tuile)
- **Décision** : option C — **session activities Temporal** chaînées sur un même worker GPU. Validation technique à faire au POC, fallback sur option B (activité monolithique) si frictions techniques.

---

### QO-009 — Stratégie de génération AI line

- **Statut** : ouverte
- **Itération cible** : 1
- **Bloque** : qualité de roulage

**Contexte** : la `fast_lane.ai` doit donner une trajectoire roulable. Algorithme variable.

**Options** :
- A. **Centerline brute** (B-spline du centre). Marche, sous-optimal.
- B. **Optimisation simple** : minimisation de courbure + contraintes de largeur.
- C. **Solveur racing line** (algorithmes type "racing line optimization" basés sur courbure et adhérence).
- D. **Génération in-game** par AC après un tour utilisateur (manuel).

**MVP** : A → C en V1.

---

### QO-010 — Distribution iOS sans App Store

- **Statut** : ouverte
- **Itération cible** : 2
- **Bloque** : déploiement de l'app

**Contexte** : pas de soumission App Store. Comment distribuer ?

**Options** :
- A. **TestFlight** avec compte Apple Developer (~99€/an).
- B. **Ad hoc** via Xcode (mais limité à 100 devices et expire après 1 an).
- C. **Sideloading via AltStore** ou similaire (pas de coût mais expérience utilisateur dégradée).
- D. **Pas de distribution publique** : install depuis Xcode sur l'iPhone du dev uniquement.

**Préférence MVP** : D. V1 : A si on élargit.

---

### QO-011 — Choix du frontend web (status UI)

- **Statut** : ouverte
- **Itération cible** : 4 (au plus tôt)
- **Bloque** : UI status

**Options** :
- A. **Astro** (static + islands, léger).
- B. **Next.js** (mature, plus lourd).
- C. **HTMX + FastAPI templates** (zéro JS, parfait pour un dashboard simple).
- D. **SvelteKit** (entre les deux).

**À trancher** au démarrage de l'It. 4.

---

### QO-012 — Outil de monitoring de coût cloud

- **Statut** : ouverte
- **Itération cible** : 4
- **Bloque** : production cloud

**Contexte** : à mesure qu'on rent des GPUs cloud, il faut suivre le coût en temps réel.

**Options** :
- A. **Polling de l'API RunPod** + agrégation interne. Simple.
- B. **Outil tiers** (Vantage, Infracost). Overkill pour un perso.
- C. **Estimation a priori** + log des durées. Approximatif.

**Préférence** : A.

---

### QO-013 — Stockage long-terme des `outputs`

- **Statut** : ouverte
- **Itération cible** : 4

**Contexte** : si l'utilisateur génère 30 circuits, ça fait 30 zip de quelques centaines de Mo. Stocker indéfiniment dans MinIO local peut saturer.

**Options** :
- A. **MinIO local** sans politique d'expiration. Simple.
- B. **Tiering** : déplacer les anciens vers un disque externe ou S3 Glacier.
- C. **Suppression manuelle** par l'utilisateur via CLI.

**Préférence** : A puis C si volume devient problématique.

---

### QO-014 — Anonymisation : modèle exact

- **Statut** : ouverte
- **Itération cible** : V2 (post It. 4)
- **Bloque** : feature CH-PRI-1

**Options** :
- A. **YOLO** (détection plaques + visages) + flou Gaussian.
- B. **Stable Diffusion inpainting** : remplacement complet des zones identifiables.
- C. **Approche hybride** : YOLO pour détection, inpainting pour remplacement.

**À trancher** quand on attaque V2.

---

### QO-015 — Stockage des secrets

- **Statut** : tranchée → [ADR-021](./08-decisions.md#adr-021--stockage-des-secrets-via-env-au-mvp)
- **Décision** : option A — `.env` non versionné + `.env.example` versionné au MVP. Migration vers 1Password CLI envisageable en V1+ si plusieurs machines/utilisateurs.

---

### QO-016 — Plan B si la validation Wine échoue

- **Statut** : ouverte
- **Itération cible** : V2 (déclenchée seulement si QO-007 invalide Wine)
- **Bloque** : portabilité totale du projet à long terme

**Contexte** : si la validation de Wine pour `compile_kn5` (cf. [QO-007](#qo-007--validation-de-wine-pour-compile_kn5)) **échoue**, on reste avec le PC Windows comme dépendance permanente. Acceptable au MVP/V1, mais bloque l'objectif "portabilité totale" en V2.

**Options** (à explorer si le moment vient) :
- A. **Garder le PC Windows** en dépendance permanente. Statu quo.
- B. **Reverse-engineer du format KN5** (long, risqué, propriétaire).
- C. **Format alternatif AC** : exporter en FBX direct + `.ini` sans compilation KN5, en s'appuyant sur Custom Shaders Patch qui peut charger des modèles non-compilés. À étudier.
- D. **VM Windows persistante sur cloud** (Azure/AWS), pour les utilisateurs sans PC. Cher mais transparent.
- E. **Communauté Kunos / Content Manager** : demander à la communauté un compileur KN5 maison existant.

**À déclencher** uniquement si QO-007 conclut négativement à l'It. 1 ou 2.

## Procédure pour fermer une question

1. Quand on a tranché, créer un ADR dans [`08-decisions.md`](./08-decisions.md).
2. Mettre à jour le statut ici : `tranchée → ADR-YYY`.
3. Au bout de 3 questions tranchées, on peut les retirer définitivement de ce document (elles vivent dans les ADRs).

## Comment ajouter une question

1. Identifiant : `QO-XXX` avec le prochain numéro.
2. Itération cible (ne pas trancher trop tôt — les contraintes évoluent).
3. Lister 2-4 options réalistes.
4. **Ne pas conclure** à la place du moment de la décision.
