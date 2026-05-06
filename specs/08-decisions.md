# 08 — Décisions d'architecture (ADRs)

> Architecture Decision Records — chaque ADR documente un choix structurant : son contexte, les options considérées, la décision prise, et ses conséquences. Format inspiré de Michael Nygard, simplifié.

## Format

Chaque ADR suit le template :

```
### ADR-XXX — Titre court

- Statut       : proposé | accepté | déprécié | remplacé par ADR-YYY
- Date         : YYYY-MM-DD
- Décideurs    : (auteurs)

Contexte
  Le problème, les contraintes, ce qui force une décision.

Options considérées
  - Option A : ... pros/cons
  - Option B : ...

Décision
  Choix retenu et justification courte.

Conséquences
  - Positives : …
  - Négatives : …
  - Suivi : …
```

---

## ADR-001 — Stack Python (vs TypeScript + Bun)

- **Statut** : accepté
- **Date** : 2026-05-05
- **Décideurs** : utilisateur, Claude

### Contexte

Le projet consomme un écosystème ML/3D (gsplat, 2DGS, Mask2Former, NeILF++, Open3D, Blender bpy) **exclusivement Python+CUDA**. La question s'est posée d'écrire la couche métier en TypeScript+Bun avec Python uniquement pour les workers ML.

### Options considérées

- **A. Full Python.** Stack unique, écosystème ML natif, communauté large.
- **B. TypeScript+Bun pour la couche métier, Python pour les workers ML.** Architecture en deux langages, double maintenance, contrats CLI/IPC à concevoir, gain marginal sur le confort dev d'un solo dev.

### Décision

**A — Full Python.** Le ratio coût/bénéfice penche fortement contre B pour un MVP solo.

### Conséquences

- ✅ Une seule stack à maîtriser.
- ✅ Pas de friction de coordination entre TS et Python.
- ✅ Réutilisation directe de l'écosystème ML.
- ❌ Perte du confort de développement TS (typing strict, tooling moderne) dans la couche métier.
- 🔧 **Mitigation** : pyright strict + Pydantic v2 pour atteindre un niveau de safety équivalent en Python.

---

## ADR-002 — Temporal comme orchestrateur

- **Statut** : accepté
- **Date** : 2026-05-05
- **Décideurs** : utilisateur, Claude

### Contexte

Le pipeline implique 15+ étapes, dont plusieurs durent des heures sur GPU. Il faut un orchestrateur capable de :
- Survivre à des crashs et redémarrages sans perdre l'état.
- Routage activités CPU vs GPU sur des workers différents.
- Reprise fine sur erreur.
- Workflows enfants pour parallélisme (tuilage).

### Options considérées

- **A. Temporal.** Durable execution, multi-queue natif, web UI, autoréhébergeable. Plus complexe à opérer.
- **B. Prefect 3.** Plus simple, Python natif, mais durabilité moindre, moins fort sur les workflows long-runs.
- **C. Dagster.** Orienté data assets, mauvais paradigme pour orchestration de jobs ML.
- **D. Airflow.** Trop batch-oriented, mal adapté.
- **E. Maison sur Redis/SQS.** Réinvention de la roue.

### Décision

**A — Temporal.** Les garanties de durabilité et le multi-queue justifient le surcoût d'opération.

### Conséquences

- ✅ Reprise robuste sur les longs workflows.
- ✅ Workers spécialisés par capacité (CPU/GPU) via task queues.
- ✅ Web UI gratuite pour debug.
- ❌ Stack docker-compose plus lourde (Temporal + 1 Postgres dédié).
- ❌ Workflows doivent être déterministes (contrainte de design).
- 🔧 **Mitigation** : conventions strictes documentées dans `02-architecture.md`.

---

## ADR-003 — Infra locale-first

- **Statut** : accepté
- **Date** : 2026-05-05

### Contexte

Le produit doit pouvoir fonctionner intégralement sur les machines de l'utilisateur, sans dépendance cloud obligatoire. Le cloud doit être un **opt-in**, pas un prérequis.

### Options considérées

- **A. Local-first, cloud opt-in.**
- **B. Cloud-native (SaaS).** Plus simple à déployer mais coût récurrent et perte de contrôle.
- **C. Hybride imposé.** Compromis bâtard.

### Décision

**A — Local-first.** Toute l'infra (Temporal, Postgres, MinIO, NATS, workers CPU) tourne localement. Le cloud GPU est utilisé optionnellement via spillover.

### Conséquences

- ✅ Aucun coût récurrent pour l'utilisateur.
- ✅ Aucune dépendance externe critique.
- ✅ Données sensibles ne quittent pas l'environnement utilisateur (hors compute GPU).
- ❌ Plus de complexité opérationnelle pour l'utilisateur (Docker, Tailscale).
- 🔧 **Mitigation** : `make up` pour démarrer toute l'infra en une commande.

---

## ADR-004 — CUDA only, pas de Metal/MPS

- **Statut** : accepté
- **Date** : 2026-05-05
- **Décideurs** : utilisateur, Claude

### Contexte

Tous les outils ML critiques (gsplat, 2DGS, NeILF++) sont CUDA-first. Des forks MPS existent pour certains mais sont fragiles et 2-3× plus lents. La question s'est posée de supporter le M3 Max comme worker GPU additionnel.

### Options considérées

- **A. CUDA only.** Image Docker unique, code unique.
- **B. CUDA + MPS supporté.** Branches MPS pour gsplat fork, dual maintenance.

### Décision

**A — CUDA only.** Le M3 Max reste pur orchestrateur. Le compute GPU passe toujours par le PC Windows ou le cloud.

### Conséquences

- ✅ Simplification massive du code et des images Docker.
- ✅ Tests reproductibles.
- ✅ Pas de débogage de bugs MPS-specific.
- ❌ Si le PC est offline et qu'il n'y a pas de cloud configuré, le pipeline est bloqué.
- 🔧 **Mitigation** : provider RunPod prêt à l'emploi en fallback.

---

## ADR-005 — Tuilage spatial pour les longs tronçons

- **Statut** : accepté
- **Date** : 2026-05-05

### Contexte

Pour 10-15 km, un seul GPU (même 24 Go) ne tient pas en VRAM. Il faut une stratégie de découpage.

### Options considérées

- **A. Tuilage spatial** par tronçons de 800 m avec chevauchement de 50 m.
- **B. Réduction de qualité** : moins de splats par mètre. Compromet la promesse photoréalisme.
- **C. GPU plus puissants** (H100 80 Go). Cher et n'éliminerait pas le problème à 30+ km.

### Décision

**A — Tuilage spatial.** 800 m / 50 m d'overlap.

### Conséquences

- ✅ Parallélisable sur N workers GPU.
- ✅ Reprise localisée sur erreur.
- ✅ VRAM prévisible.
- ❌ Étape de stitching à concevoir (recoller les tuiles proprement).
- ❌ Atlas de textures plus complexe (par-tuile vs global).

---

## ADR-006 — Content Manager comme cible d'installation

- **Statut** : accepté
- **Date** : 2026-05-05
- **Décideurs** : utilisateur, Claude

### Contexte

AC vanilla et Content Manager (CM) acceptent des formats légèrement différents. CM est utilisé par 90%+ des sim racers et offre des features supplémentaires (drag-drop install, support CSP).

### Options considérées

- **A. CM exclusivement.** Format zip avec `ui_track.json`, dépendance CSP autorisée.
- **B. AC vanilla + CM.** Double cible.
- **C. AC vanilla uniquement.** Pas de spéciale possible (pas de support hillclimb point-à-point).

### Décision

**A — Content Manager.**

### Conséquences

- ✅ Spéciales (point-à-point) supportées via CSP.
- ✅ Installation drag-drop.
- ❌ Dépendance utilisateur sur CSP (mais c'est de facto installé chez le persona).

---

## ADR-007 — Détection automatique circuit/spéciale

- **Statut** : accepté
- **Date** : 2026-05-05
- **Décideurs** : utilisateur, Claude

### Contexte

L'utilisateur ne doit pas avoir à choisir manuellement entre "circuit" et "spéciale". La nature du tracé doit être inférée.

### Options considérées

- **A. Détection automatique** par analyse de la trajectoire (loop closure).
- **B. Choix utilisateur** au moment du traitement.
- **C. Préférence par défaut** (spéciale si pas de loop fermé évident).

### Décision

**A — Détection automatique.** Algorithme dans [`04-pipeline-ml.md#23-détection-circuit-spéciale`](./04-pipeline-ml.md#23-détection-circuit--spéciale).

> **Note** : la portée de cette détection est limitée à la **distinction circuit vs spéciale**. Pour les spéciales, aucune détection supplémentaire (lead-in, lead-out) n'est faite — voir [ADR-016](#adr-016--pas-de-détection-automatique-de-lead-in-en-spéciale) qui complète cet ADR.

### Conséquences

- ✅ Effort utilisateur nul.
- ✅ Algorithme déterministe et auditable.
- ❌ Cas ambigus (circuit avec lead-in long) doivent être bien gérés.
- 🔧 **Mitigation** : tronquage explicite du lead-in dans le pipeline.

---

## ADR-008 — Multi-passe pour amélioration qualité

- **Statut** : accepté
- **Date** : 2026-05-05
- **Décideurs** : utilisateur, Claude

### Contexte

L'utilisateur peut vouloir repasser sur une zone déjà cartographiée pour améliorer la qualité (plus de vues = meilleur GS). Ce comportement doit être supporté nativement.

### Options considérées

- **A. Multi-passe natif** : repasser enrichit les données existantes.
- **B. Multi-passe = remplacement** : on jette l'ancien.
- **C. Multi-projet** : chaque passe = un projet distinct.

### Décision

**A — Multi-passe enrichit les données existantes.** Voxellisation de couverture, ajout de keyframes, retraining GS.

### Conséquences

- ✅ Qualité progresse à chaque passe.
- ✅ Cohérent avec la métaphore "balade itérative".
- ❌ Logique de fusion plus complexe (gestion des conflits, lighting différent).
- 🔧 **Mitigation** : recommandation utilisateur de repasser dans des conditions similaires (même heure du jour, même météo).

---

## ADR-009 — Pas d'app iOS au POC

- **Statut** : accepté
- **Date** : 2026-05-05
- **Décideurs** : utilisateur, Claude

### Contexte

L'app iOS est un investissement de 4-5 semaines. Au POC, on doit valider le risque #1 (qualité texturale) sans dépendre d'un livrable mobile.

### Options considérées

- **A. POC sans app iOS** : capture via Record3D + Sensor Logger.
- **B. POC avec app iOS minimaliste** : retarde le test du risque ML.

### Décision

**A — Pas d'app iOS au POC.** L'app arrive à l'It. 2.

### Conséquences

- ✅ POC livré rapidement.
- ✅ Validation ML sans dépendance mobile.
- ❌ Multi-segment / pause-reprise impossible avant l'It. 2.

---

## ADR-010 — Mac orchestrateur sans GPU compute

- **Statut** : accepté
- **Date** : 2026-05-05
- **Décideurs** : utilisateur, Claude

### Contexte

Cet ADR est le **corollaire topologique** d'[ADR-004](#adr-004--cuda-only-pas-de-metalmps) : puisque le ML est CUDA-only et que le Mac M3 Max n'a pas de GPU NVIDIA, le compute GPU sort par construction de la machine d'orchestration.

Le Mac M3 Max possède toutefois un GPU Apple Silicon performant. La question s'est posée de l'utiliser pour des activités ML compatibles MPS.

### Options considérées

- **A. Mac sans GPU compute** : orchestrateur pur, le ML va toujours sur CUDA externe.
- **B. Mac avec GPU MPS** : second worker compatible Metal pour activités légères.

### Décision

**A — Mac sans GPU.** Décidé par l'utilisateur pour simplifier le process. Voir aussi ADR-004.

### Conséquences

- ✅ Une seule cible compute (CUDA).
- ✅ Pas de variantes Metal du code.
- ❌ Les 36 cœurs GPU du M3 Max ne sont pas utilisés.
- 🔧 **Acceptable** : le M3 Max reste précieux comme orchestrateur (RAM unifiée, perfs CPU).

---

## ADR-011 — Tailscale comme bridge réseau

- **Statut** : accepté
- **Date** : 2026-05-05
- **Décideurs** : utilisateur, Claude

### Contexte

Les workers GPU (PC local, pods cloud) doivent atteindre Temporal et MinIO sur le Mac, sans exposition publique.

### Options considérées

- **A. Tailscale.** Mesh VPN zero-config, MagicDNS, gratuit.
- **B. Cloudflare Tunnel.** Plus orienté "exposer un service web".
- **C. WireGuard manuel.** Plus de contrôle mais coût opérationnel élevé.
- **D. SSH tunnels.** Trop bricolage pour un produit.

### Décision

**A — Tailscale.**

### Conséquences

- ✅ Zero config réseau.
- ✅ Fonctionne identiquement en LAN et WAN.
- ❌ Dépendance à un service tiers (mitigée par la possibilité d'auto-héberger Headscale).

---

## ADR-012 — Architecture hexagonale en couches

- **Statut** : accepté
- **Date** : 2026-05-05
- **Décideurs** : utilisateur, Claude

### Contexte

Le projet a plusieurs couches : domaine (entités), adapters (libs ML, stockage, cloud), orchestration (Temporal), interface (CLI, API). Le risque d'une architecture sale est de coupler la logique métier aux libs ML changeantes.

### Options considérées

- **A. Architecture hexagonale (ports & adapters).**
- **B. Architecture en couches classique** (3-tier).
- **C. Pas d'architecture explicite, organisation par feature.**

### Décision

**A — Hexagonale.** Voir [`02-architecture.md`](./02-architecture.md) pour les détails.

### Conséquences

- ✅ Libs ML remplaçables sans propagation.
- ✅ Tests unitaires faciles sur le domaine.
- ✅ Indépendance vis-à-vis de Temporal (en théorie ; en pratique il y a des couplages).
- ❌ Plus de boilerplate (Protocol classes, DI manuelle).

---

## ADR-013 — uv comme gestionnaire de dépendances

- **Statut** : accepté
- **Date** : 2026-05-05
- **Décideurs** : utilisateur, Claude

### Contexte

Le projet est un workspace multi-package. Plusieurs gestionnaires existent.

### Options considérées

- **A. uv.** Workspace natif, vitesse, lockfile, gestion Python.
- **B. poetry.** Mature mais moins rapide, workspace moins propre.
- **C. pdm.** Correct, moins d'élan communautaire.
- **D. pip-tools + Makefile.** Trop bas niveau.

### Décision

**A — uv.**

### Conséquences

- ✅ Installation rapide.
- ✅ Workspace simple (`[tool.uv.workspace]`).
- ❌ Outil jeune (mais stable et soutenu par Astral).

---

## ADR-014 — MinIO comme stockage objet

- **Statut** : accepté
- **Date** : 2026-05-05

### Contexte

Le pipeline génère beaucoup de fichiers volumineux (vidéos, .ply, mesh, textures). Il faut un stockage objet.

### Options considérées

- **A. MinIO.** S3-compatible, déployable local, performant.
- **B. Filesystem local + presigned URLs maison.** Marginal mais perd les avantages d'un objet store.
- **C. AWS S3 directement.** Coût récurrent, contraire à local-first.
- **D. SeaweedFS / Garage.** Alternatives intéressantes mais moins de support.

### Décision

**A — MinIO.**

### Conséquences

- ✅ Compat S3 → swap trivial vers du cloud plus tard.
- ✅ Local-first conforme.
- ✅ Presigned URLs pour les workers cloud.

---

## ADR-015 — Tests E2E sur dataset jouet

- **Statut** : accepté
- **Date** : 2026-05-05

### Contexte

Le pipeline est complexe et coûteux à tester. Les tests E2E doivent être économes mais représentatifs.

### Options considérées

- **A. Dataset jouet de 100 m**, capturé une fois, versionné dans MinIO.
- **B. Datasets synthétiques** (Blender renders).
- **C. Pas de tests E2E**, juste unitaires + intégration.

### Décision

**A — Dataset jouet.**

### Conséquences

- ✅ Tests réalistes.
- ✅ Reproduction de bugs réels.
- ❌ Volume de données à versionner (~quelques Go).
- 🔧 **Mitigation** : stockage MinIO local, hash dans `tests/e2e/dataset.json`.

---

## ADR-016 — Pas de détection automatique de lead-in en spéciale

- **Statut** : accepté
- **Date** : 2026-05-06
- **Décideurs** : utilisateur, Claude
- **Contexte de décision** : Review 1.

### Contexte

Pour un **circuit**, la détection automatique d'un lead-in (portion avant la boucle) est légitime parce que la boucle est une **propriété géométrique** identifiable (loop closure). Pour une **spéciale** (point-à-point), aucune propriété géométrique ne marque les bornes. La question s'est posée d'utiliser des heuristiques (stationarité prolongée, changement de régime de vitesse) pour détecter un éventuel lead-in/lead-out en spéciale.

### Options considérées

- **A. Détection automatique heuristique** (stationarité, vitesse moyenne). Risque d'erreurs silencieuses, complexité de tuning.
- **B. L'utilisateur définit les bornes** par les actions start/stop de l'enregistrement. Fait foi.
- **C. Markers explicites en V1** dans l'app native (boutons "marquer début / fin").

### Décision

**B au MVP**, **C en V1** (optionnel, opt-in). Aucune détection automatique de lead-in en spéciale.

### Justification

L'utilisateur sait quand commence et finit son stage. L'auto-détection ajoute de la complexité pour un gain incertain et des erreurs silencieuses possibles. La règle est : "circuit = propriété géométrique, spéciale = utilisateur fait foi".

### Conséquences

- ✅ Pipeline plus simple.
- ✅ Comportement prévisible.
- ❌ Si l'utilisateur démarre l'enregistrement trop tôt, la trajectoire entière est traitée (lead-in inclus).
- 🔧 **Mitigation** : documentation utilisateur claire ; markers explicites en V1.

---

## ADR-017 — Synchronisation Record3D ↔ Sensor Logger via timestamps UTC

- **Statut** : accepté
- **Date** : 2026-05-06
- **Décideurs** : utilisateur, Claude
- **Contexte de décision** : Review 1.

### Contexte

Au POC, on agrège les flux de deux apps iOS distinctes (Record3D et Sensor Logger) parce qu'aucune ne capture tout ce dont on a besoin. La question s'est posée de la **synchronisation temporelle** entre ces deux flux.

### Options considérées

- **A. Alignement par timestamps UTC** : les deux apps partagent l'horloge système iPhone (sub-ms), donc les timestamps wall-clock sont alignés par construction.
- **B. Calibration manuelle par "clap des mains"** : l'utilisateur produit un signal détectable dans les deux flux. UX bizarre.
- **C. Cross-corrélation IMU/ARKit** comme procédure systématique : robuste mais coûteux.

### Décision

**A en premier lieu, C en fallback**. Si une dérive > 100 ms est détectée à l'ingestion, on calcule un offset constant par cross-corrélation entre les pics IMU (Sensor Logger) et les pics d'accélération extraits des poses ARKit (Record3D). Cas C n'est jamais demandé à l'utilisateur, c'est automatique.

### Conséquences

- ✅ UX triviale pour l'utilisateur (rien à faire).
- ✅ Robustesse via le fallback.
- ❌ Une étape de validation à coder dans `ingest_session`.
- 🔧 À l'It. 2 (app native), le problème disparaît : un seul flux unifié.

---

## ADR-018 — Pas de provisioning cloud automatique au MVP

- **Statut** : accepté
- **Date** : 2026-05-06
- **Décideurs** : utilisateur, Claude
- **Contexte de décision** : Review 1.

### Contexte

Quand l'utilisateur lance `uv run road2track process` alors que le PC GPU est offline et qu'aucun pod cloud n'est actif, deux comportements sont possibles : provisionner automatiquement un pod cloud, ou retourner une erreur explicite et laisser l'utilisateur déclencher manuellement.

### Options considérées

- **A. Provisioning automatique** (transparent, magique) : confort maximal mais engage de l'argent sans confirmation.
- **B. Erreur explicite avec commande à lancer** : l'utilisateur garde le contrôle financier.
- **C. Confirmation interactive** (`--yes` requis) : compromis, mais ajoute friction sur chaque run.

### Décision

**B au MVP. Option A en V1+ via `--auto-spawn` (opt-in, avec budget plafonné).**

### Justification

Au MVP solo, la **prudence financière** prime sur le confort. Un coût cloud non anticipé est plus dommageable qu'une erreur claire. L'auto-spawn deviendra envisageable quand on aura : (a) une UX mature pour les budgets, (b) des limites configurables, (c) un suivi temps réel des dépenses.

### Conséquences

- ✅ Aucun coût engagé sans action explicite.
- ✅ Erreur informative et actionnable (cf. [`05-infrastructure.md#65-comportement-en-labsence-de-worker-gpu`](./05-infrastructure.md#65-comportement-en-labsence-de-worker-gpu)).
- ❌ Une commande supplémentaire à connaître.
- 🔧 **Mitigation** : la CLI affiche directement la commande à copier-coller dans le message d'erreur.

---

## ADR-019 — Session activities pour chaîner le pipeline GPU d'une tuile

- **Statut** : accepté
- **Date** : 2026-05-06
- **Décideurs** : utilisateur, Claude
- **Contexte de décision** : Review 2.

### Contexte

Le pipeline GPU enchaîne pour chaque tuile : `train_gs` (sortie 2-5 Go) → `extract_mesh` → `bake` → `estimate_pbr`. Si chaque activité tourne sur un worker distinct, chaque étape doit télécharger l'output de la précédente depuis MinIO et ré-uploader le sien. Pour des fichiers de plusieurs Go, ces transferts doublent ou triplent le temps de traitement, surtout quand le worker est en cloud (bande passante limitée vers MinIO local).

### Options considérées

- **A. Session activities Temporal** : on "fixe" la séquence sur un même worker via le mécanisme de session du SDK Temporal. Les fichiers intermédiaires (`scene.ply`, `mesh.obj`) restent dans le cache local du worker entre les étapes.
- **B. Activité monolithique** `process_tile_gpu` : on fusionne les 4 étapes en une seule activité. Simple mais reprise grossière (si `bake` échoue, on rejoue tout `train_gs`).
- **C. Statu quo** : tout via MinIO entre chaque activité. Lent et coûteux.

### Décision

**A — Session activities** au MVP, avec validation technique au POC.

**Critère de bascule vers B (fallback)** : si après **3 jours d'effort** sur le POC, les sessions Temporal Python ne s'exécutent pas de manière fiable (échec de stickiness sur le worker, perte des fichiers locaux entre activités, bugs SDK), on bascule sur **B** (activité monolithique `process_tile_gpu`) et on crée un ADR de remplacement qui acte le changement.

### Conséquences

- ✅ Élimine les transferts MinIO redondants entre étapes GPU consécutives.
- ✅ Garde la granularité fine de reprise (chaque activité reste retournable séparément).
- ✅ Logs et métriques par étape conservés.
- ❌ Si le worker meurt en cours de session, les fichiers locaux sont perdus → on rejoue depuis MinIO.
- ❌ Plus complexe à coder qu'une activité monolithique.
- 🔧 **Mitigation** : le résultat de chaque activité est aussi persisté en MinIO (asynchrone après la session) pour qu'on puisse rejouer sans perte.

### Suivi

- POC : valider techniquement le pattern session avec le SDK Python.
- It. 1 : si OK, déployer en production. Si KO, basculer sur B et documenter dans un ADR de remplacement.

---

## ADR-020 — Stratégie de cache des modèles ML (mix pré-bake + MinIO)

- **Statut** : accepté
- **Date** : 2026-05-06
- **Décideurs** : utilisateur, Claude
- **Contexte de décision** : Review 5.

### Contexte

Le pipeline ML utilise plusieurs modèles pré-entraînés volumineux (Mask2Former ~500 Mo, gsplat checkpoints, NeILF++…). À chaque démarrage d'un worker — surtout un pod RunPod neuf — il faut éviter de retélécharger tous les modèles depuis Internet (5-10 min de cold start, consommation de bande passante).

### Options considérées

- **A. Volume Docker partagé** : persistant entre redémarrages du container. Simple sur PC, ne marche pas pour pods cloud éphémères.
- **B. Pré-bake dans l'image Docker** : modèles téléchargés au build, inclus dans l'image. Démarrage très rapide, mais image énorme (5-10 Go) et rebuild à chaque update.
- **C. Cache MinIO** : workers téléchargent depuis MinIO via Tailscale. Centralisé mais dépend de la connectivité Tailscale au boot.
- **D. Mix** : pré-bake les modèles essentiels (toujours nécessaires, peu changeants), cache MinIO pour les modèles plus volumineux ou variables.

### Décision

**D — Mix.**

Pré-bakés dans l'image `gpu_worker` :
- Mask2Former (segmentation de base, toujours utilisée).
- gsplat checkpoints d'init (petits).

Cachés dans MinIO sous `s3://intermediates/models/` :
- NeILF++ (lourd, susceptible de changer entre versions).
- Modèles spécifiques de finetuning futur.

Les workers téléchargent depuis MinIO via Tailscale au premier usage et gardent un cache local pour la durée de vie du worker.

### Conséquences

- ✅ Cold start rapide : les modèles essentiels sont déjà là.
- ✅ Image Docker raisonnable (~3 Go au lieu de 10 Go).
- ✅ Mise à jour des modèles "lourds" sans rebuild d'image (juste push vers MinIO).
- ❌ Logique de cache à coder dans `packages/ml/`.
- ❌ Dépend de Tailscale au boot pour le cache MinIO.
- 🔧 **Mitigation** : si MinIO inaccessible, fallback automatique téléchargement HuggingFace en dernier recours.

---

## ADR-021 — Stockage des secrets via `.env` au MVP

- **Statut** : accepté
- **Date** : 2026-05-06
- **Décideurs** : utilisateur, Claude
- **Contexte de décision** : Review 5.

### Contexte

Le projet manipule plusieurs credentials sensibles : access keys MinIO, API key RunPod, auth key Tailscale, mots de passe Postgres. Au MVP solo, il faut une solution simple, sécurisée, sans surdimensionnement.

### Options considérées

- **A. Fichier `.env` non versionné** + `.env.example` versionné comme template.
- **B. 1Password CLI (`op`)** : secrets jamais en plain text sur disque, lookup à la volée.
- **C. HashiCorp Vault local** : pour multi-utilisateurs, surdimensionné solo.

### Décision

**A au MVP.** Migration vers **B** envisageable en V1+ si plusieurs machines ou utilisateurs sont impliqués.

Convention :
- `.env` à la racine, jamais committé.
- `.env.example` committé, contient toutes les clés avec des valeurs vides ou explicatives.
- `.gitignore` strict sur `.env`.
- Secrets aussi en variables d'environnement injectées dans les containers Docker via `env_file:`.

### Conséquences

- ✅ Simplicité maximale.
- ✅ Compatible avec docker-compose et Tailscale.
- ❌ Si le `.env` fuit (commit accidentel, partage), tous les secrets sont compromis simultanément.
- 🔧 **Mitigation** : pre-commit hook qui détecte les patterns secrets et bloque le commit.

---

## Index

| ADR | Titre | Statut | Origine |
|---|---|---|---|
| 001 | Stack Python (vs TypeScript+Bun) | accepté | initial |
| 002 | Temporal comme orchestrateur | accepté | initial |
| 003 | Infra locale-first | accepté | initial |
| 004 | CUDA only, pas de Metal/MPS | accepté | initial |
| 005 | Tuilage spatial pour les longs tronçons | accepté | initial |
| 006 | Content Manager comme cible d'installation | accepté | initial |
| 007 | Détection automatique circuit/spéciale | accepté | initial |
| 008 | Multi-passe pour amélioration qualité | accepté | initial |
| 009 | Pas d'app iOS au POC | accepté | initial |
| 010 | Mac orchestrateur sans GPU compute | accepté | initial |
| 011 | Tailscale comme bridge réseau | accepté | initial |
| 012 | Architecture hexagonale en couches | accepté | initial |
| 013 | uv comme gestionnaire de dépendances | accepté | initial |
| 014 | MinIO comme stockage objet | accepté | initial |
| 015 | Tests E2E sur dataset jouet | accepté | initial |
| 016 | Pas de détection automatique de lead-in en spéciale | accepté | Review 1 |
| 017 | Synchronisation Record3D ↔ Sensor Logger via timestamps UTC | accepté | Review 1 |
| 018 | Pas de provisioning cloud automatique au MVP | accepté | Review 1 |
| 019 | Session activities pour chaîner le pipeline GPU d'une tuile | accepté | Review 2 |
| 020 | Stratégie de cache des modèles ML (mix pré-bake + MinIO) | accepté | Review 5 |
| 021 | Stockage des secrets via `.env` au MVP | accepté | Review 5 |

---

## Procédure pour ajouter un ADR

1. Identifier une décision **structurante** (qui changerait l'architecture si reverte).
2. Créer un nouvel ADR avec le numéro suivant disponible.
3. Documenter contexte, options, décision, conséquences.
4. Soumettre en PR. Review + merge = `statut: accepté`.
5. Si une nouvelle décision **annule** un ancien ADR : nouveau ADR `statut: accepté` qui remplace, l'ancien passe en `statut: remplacé par ADR-XXX`.
