# 09 — Questions ouvertes

> Liste vivante de décisions techniques à trancher au fil des itérations. Quand une question est tranchée, elle quitte ce document et devient un ADR dans [`08-decisions.md`](./08-decisions.md).

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

### QO-002 — Format des poses iPhone

- **Statut** : ouverte
- **Itération cible** : 0 (POC) puis 2 (app native)
- **Bloque** : ingestion

**Contexte** : Record3D exporte les poses ARKit dans un format propre (JSON simple). En V1+ (app native), on aura le choix entre :
- Stocker des poses 6DoF brutes (translation + quaternion).
- Stocker un **ARWorldMap** ARKit qui inclut les anchors visuels (utile pour la relocalisation cas B).

**Options** :
- A. Toujours poses brutes ; relocalisation via matching de features visuelles côté backend.
- B. ARWorldMap stocké + poses dérivées ; relocalisation via ARKit lui-même.
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

- **Statut** : ouverte
- **Itération cible** : 1
- **Bloque** : démarrage à froid des workers

**Contexte** : Mask2Former et autres modèles HF font plusieurs Go. Au démarrage d'un pod cloud, télécharger ces modèles ralentit considérablement.

**Options** :
- A. Volume Docker partagé (pour le PC local).
- B. **Pré-bake** des modèles dans l'image Docker `gpu_worker`.
- C. **Cache MinIO** : les workers téléchargent depuis le MinIO local (rapide via Tailscale).
- D. Mix : pré-bake du minimum, le reste via MinIO.

**À trancher** quand on construit le Dockerfile final.

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

### QO-007 — Compilation KN5 sur Linux/Mac

- **Statut** : ouverte
- **Itération cible** : 1
- **Bloque** : déploiement de production sans Windows

**Contexte** : `ksEditor` est Windows-only. Au MVP on a un worker dédié Windows. Idéalement on devrait pouvoir compiler depuis Linux pour homogénéiser.

**Options** :
- A. **Worker Windows dédié** sur le PC. Choix MVP.
- B. **Wine** dans une image Docker Linux. À tester.
- C. **Reverse-engineer** du format KN5 et écrire un compileur Python. Risqué (format propriétaire).

**Préfèrence** : maintenir A pour MVP, explorer B en parallèle.

---

### QO-008 — Format intermédiaire entre activités GPU

- **Statut** : ouverte
- **Itération cible** : 1
- **Bloque** : performance des workflows

**Contexte** : entre les activités GPU successives (train_gs → extract_mesh → bake), on transfère des fichiers via MinIO. Pour des tuiles de plusieurs Go, c'est lent.

**Options** :
- A. **Tout via MinIO**. Simple, robuste, permet aux activités de tourner sur des workers différents.
- B. **Activités combinées** : un seul GPU traite une tuile de bout en bout. Réduit transferts mais perd de la granularité.
- C. **Stockage local au worker** + activités enchaînées sur le même worker (Temporal supporte les session activities).

**À trancher** après mesure du coût de transfert au POC.

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

- **Statut** : ouverte
- **Itération cible** : 1
- **Bloque** : opérations multi-machines

**Contexte** : credentials MinIO, RunPod API key, Tailscale auth key, Postgres passwords.

**Options** :
- A. **`.env` non versionné** + `.env.example` versionné. Simple, suffisant pour solo.
- B. **1Password CLI** intégré. Plus sécurisé, ajoute une dépendance.
- C. **HashiCorp Vault** local. Overkill.

**Préférence MVP** : A. Migrer vers B en V1+ si plusieurs utilisateurs.

---

## Procédure pour fermer une question

1. Quand on a tranché, créer un ADR dans [`08-decisions.md`](./08-decisions.md).
2. Mettre à jour le statut ici : `tranchée → ADR-YYY`.
3. Au bout de 3 questions tranchées, on peut les retirer définitivement de ce document (elles vivent dans les ADRs).

## Comment ajouter une question

1. Identifiant : `QO-XXX` avec le prochain numéro.
2. Itération cible (ne pas trancher trop tôt — les contraintes évoluent).
3. Lister 2-4 options réalistes.
4. **Ne pas conclure** à la place du moment de la décision.
