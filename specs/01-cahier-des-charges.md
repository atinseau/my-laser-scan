# 01 — Cahier des charges

> Document central des **exigences** du projet. Toute modification de fonctionnalité, de contrainte ou de critère de succès se fait ici. Les itérations dans [`07-roadmap.md`](./07-roadmap.md) **réalisent** ces exigences.

## 1. Méthode MoSCoW

Les fonctionnalités sont classées en quatre catégories :

| Catégorie | Définition |
|---|---|
| **Must have** | Indispensable pour considérer le produit utile. Sans ça, on ne livre pas. |
| **Should have** | Important mais peut être différé sans tuer la valeur. |
| **Could have** | Souhaitable, ajouté si le temps le permet. |
| **Won't have** (yet) | Hors périmètre actuel et explicitement assumé comme tel. |

## 2. Fonctionnalités MUST HAVE

### 2.1 Capture

- **MH-CAP-1** — La capture s'appuie sur des apps iPhone existantes au POC : **Record3D** (LiDAR + RGB + poses ARKit) et **Sensor Logger** (GPS + IMU + baromètre + magnétomètre). Pas de développement iOS au POC. Voir [`04-pipeline-ml.md`](./04-pipeline-ml.md).
- **MH-CAP-2** — La capture supporte des **tronçons de 100 m à 15 km**.
- **MH-CAP-3** — La capture est **fragmentable** : une session peut être mise en pause et reprise plus tard, ou plusieurs sessions peuvent être ajoutées au même projet (à partir de l'itération 2 avec l'app native). Au POC, une seule session continue suffit.
- **MH-CAP-4** — La capture supporte le **multi-passe qualité** : repasser sur une zone déjà cartographiée enrichit les données plutôt que de les remplacer (à partir de l'itération 2). Voir [`04-pipeline-ml.md#multi-passe`](./04-pipeline-ml.md#multi-passe-qualité).

### 2.2 Détection automatique du type de tracé

- **MH-DET-1** — Le système détermine automatiquement si le tracé est un **circuit** (la trajectoire repasse par un point déjà visité) ou une **spéciale** (point-à-point, sans bouclage).
- **MH-DET-2** — Pour un circuit avec lead-in (l'utilisateur quitte un point puis y revient avant de boucler), le lead-in est tronqué automatiquement et seule la boucle est conservée.
- **MH-DET-3** — Le seuil de détection (distance entre points proches, cap, durée minimale) est configurable mais a des valeurs par défaut documentées dans [`04-pipeline-ml.md`](./04-pipeline-ml.md).

### 2.3 Pipeline de traitement

- **MH-PIP-1** — Le pipeline est **100% automatique** entre l'ingestion et la livraison. Aucune étape manuelle (édition, validation, choix) n'est requise.
- **MH-PIP-2** — Le pipeline est **orchestré par Temporal** avec workflows et activités séparés. Voir [`02-architecture.md`](./02-architecture.md) et [`05-infrastructure.md`](./05-infrastructure.md).
- **MH-PIP-3** — Le pipeline supporte le **tuilage spatial** pour traiter des tronçons longs en parallèle. Voir [`04-pipeline-ml.md#tuilage`](./04-pipeline-ml.md#stratégie-de-tuilage).
- **MH-PIP-4** — Toute activité GPU s'exécute sur la **task queue `gpu`**, jamais sur `cpu`. Toute activité non-ML s'exécute sur `cpu`.
- **MH-PIP-5** — Le pipeline est **résilient** : un échec sur une tuile ne fait pas échouer les autres ; la reprise sur erreur est gérée par Temporal.

### 2.4 Format de sortie

- **MH-OUT-1** — La sortie est un package **compatible Content Manager** (zip avec structure de dossier AC + `ui_track.json`). Voir [`06-modele-donnees.md#format-final`](./06-modele-donnees.md#format-final-content-manager).
- **MH-OUT-2** — Le track inclut : mesh KN5 compilé, fichiers `surfaces.ini`, `models.ini`, `camera.ini`, `fast_lane.ai`, `pit_lane.ai`, `ui_track.json`, miniature, outline.
- **MH-OUT-3** — Pour une **spéciale**, le track est généré au format hillclimb avec dépendance CSP.
- **MH-OUT-4** — Pour un **circuit**, l'AI line est une B-spline fermée et les laps sont activés.

### 2.5 Infrastructure locale-first

- **MH-INF-1** — Toute l'infrastructure (Temporal, Postgres, MinIO, NATS, workers CPU) est **deployable et fonctionnelle en local** via une seule commande (`make up`). Aucune dépendance cloud requise.
- **MH-INF-2** — Le **GPU compute n'est jamais sur la machine d'orchestration** (Mac). Il est toujours déporté sur une machine externe via Tailscale.
- **MH-INF-3** — Deux **providers GPU** sont supportés au minimum : un PC Windows local (permanent) et RunPod (à la demande). L'abstraction permet d'en ajouter d'autres sans modifier le pipeline.
- **MH-INF-4** — Le **bridge cloud** est explicite et auditable : un script CLI provisionne / arrête les pods, le worker s'enregistre auprès du Temporal local via Tailscale.

### 2.6 Qualité visuelle

- **MH-QUA-1** — La texture du mesh final est issue de **photos réelles**, pas générée procéduralement. Voir [`04-pipeline-ml.md#bake-multi-vue`](./04-pipeline-ml.md#bake-multi-vue).
- **MH-QUA-2** — Le rendu doit être **photoréaliste à vitesse de jeu**, pas seulement en screenshot. Critère subjectif validé en jeu.
- **MH-QUA-3** — Les surfaces uniformes (asphalte) reçoivent une **normale procédurale tilée** pour éviter le "flat plastique", calibrée par la rugosité estimée par LiDAR.
- **MH-QUA-4** — Les textures sont en **PBR** (albedo, normal, roughness) pour un rendu correct dans AC + CSP.

## 3. Fonctionnalités SHOULD HAVE (MVP → V1)

### 3.1 App iOS native

- **SH-IOS-1** — Application iOS native (SwiftUI + ARKit + AVFoundation + CoreLocation + CoreMotion) qui remplace Record3D + Sensor Logger.
- **SH-IOS-2** — UI minimaliste : démarrer / pause / reprise / stop / finaliser.
- **SH-IOS-3** — Barre de progression à 3 niveaux : distance brute (`X km / 15 km`), couverture qualitative (% de voxels avec ≥ N keyframes), état local (vert/jaune/rouge selon vitesse, lumière, recouvrement).
- **SH-IOS-4** — Modèle de données segmenté : chaque pause crée un nouveau segment dans le projet en cours.
- **SH-IOS-5** — Synchronisation des timestamps entre LiDAR, vidéo, IMU, GPS au niveau frame (précision ms).
- **SH-IOS-6** — Upload chunké et resumable vers le backend.
- **SH-IOS-7** — Distribution **hors App Store** : ad hoc / TestFlight ou install via Xcode pour le MVP. Pas de soumission App Store.

### 3.2 API backend

- **SH-API-1** — Serveur HTTP **FastAPI** exposant : création de projet, ajout de session, lancement du traitement, récupération du statut, téléchargement du résultat.
- **SH-API-2** — L'API n'est exposée que sur le réseau Tailscale, jamais sur Internet public au MVP.
- **SH-API-3** — Pas d'authentification au MVP. Sécurité = limite réseau Tailscale.

### 3.3 Web UI status

- **SH-WEB-1** — Page web simple (statique ou SSR léger) consultable sur le Mac qui affiche l'état des projets, des workflows en cours, des workers connectés.
- **SH-WEB-2** — La page consomme NATS pour les events temps réel.

## 4. Fonctionnalités COULD HAVE (V1 → V2)

- **CH-PRI-1** — **Anonymisation automatique** des plaques d'immatriculation et des visages dans les textures (YOLO + segmentation + inpainting).
- **CH-EDI-1** — **Édition légère** post-génération : ajustement manuel du start/finish, de la largeur de route, de la météo.
- **CH-MET-1** — **Météo capturée** : utilisation du HDRi sky de l'iPhone pour configurer la skybox du circuit.
- **CH-MET-2** — Plusieurs presets météo (sec, mouillé, brouillard) générés automatiquement.
- **CH-AST-1** — **Génération d'assets de bord de route** (panneaux, glissières, arbres) via outil text-to-3D pour densifier l'environnement.
- **CH-OPT-1** — Optimisation du coût : compression VRAM, pré-entraînements partagés, cache des modèles ML.
- **CH-MUL-1** — Support d'autres jeux : **rFactor 2**, **BeamNG.drive**.

## 5. Fonctionnalités WON'T HAVE (jamais ou très tard)

- **WH-MUL-1** — Multi-tenant. Le système reste mono-utilisateur par instance.
- **WH-AUT-1** — Authentification utilisateur, gestion de comptes.
- **WH-PAY-1** — Paiement, abonnement, plan freemium.
- **WH-MAR-1** — Marketplace de circuits, partage entre utilisateurs.
- **WH-AND-1** — Support Android.
- **WH-WEB-1** — App Store / Play Store.
- **WH-MIM-1** — Reproduction fidèle de propriétés privées, marques commerciales identifiables.

## 6. Contraintes techniques

### 6.1 Matérielles

- **CT-MAT-1** — iPhone Pro avec LiDAR (12 Pro et plus récents).
- **CT-MAT-2** — Machine d'orchestration : macOS, Linux ou Windows. Pas de GPU requise sur cette machine.
- **CT-MAT-3** — Au moins **un worker GPU CUDA** disponible pour le ML (PC local ou cloud).
- **CT-MAT-4** — VRAM minimale par worker : **12 Go** pour POC, **24 Go** recommandé pour 1+ km.

### 6.2 Logicielles

- **CT-LOG-1** — Python 3.12 partout.
- **CT-LOG-2** — `uv` pour la gestion des dépendances et des environnements.
- **CT-LOG-3** — Docker Desktop ou Docker Engine + Docker Compose v2.
- **CT-LOG-4** — Tailscale installé sur toutes les machines participantes.
- **CT-LOG-5** — Assetto Corsa + Content Manager + Custom Shaders Patch côté joueur.

### 6.3 Réseau

- **CT-RES-1** — Tailscale comme overlay réseau. Aucune exposition publique de service au MVP.
- **CT-RES-2** — Bande passante minimale : 50 Mbps en LAN entre Mac et PC pour les transferts de données ML (qui peuvent atteindre plusieurs Go par tuile).

### 6.4 Code

- **CT-COD-1** — Type checking strict avec **pyright**.
- **CT-COD-2** — Linter et formateur : **ruff**.
- **CT-COD-3** — Tests : **pytest** + `temporalio.testing` pour les workflows.
- **CT-COD-4** — Architecture **clean / hexagonale** stricte. Voir [`02-architecture.md`](./02-architecture.md).
- **CT-COD-5** — Pas de logique métier dans les `services/` (workers, API, CLI). Toute la logique vit dans `packages/`.

### 6.5 Réversibilité

- **CT-REV-1** — Toute lib ML doit être derrière une interface stable (`packages/ml/`) pour pouvoir être remplacée sans propagation.
- **CT-REV-2** — Les formats de données intermédiaires sont versionnés (champ `schema_version` dans tous les manifests).

## 7. Critères de succès mesurables

### 7.1 POC (Itération 0)

| Critère | Mesure |
|---|---|
| Pipeline GS → mesh → bake fonctionnel | Le notebook produit un `.obj` + textures sur 200 m capturés en marche. |
| Qualité texturale | Vérification visuelle dans Blender : la route est reconnaissable, les textures sont issues des photos. |
| Reproductibilité | Le même dataset re-traité donne un résultat visuellement équivalent (variance acceptable due au stochastique GS). |
| Stack ML installable | Toutes les dépendances ML s'installent dans un seul `uv sync` + Docker build. |

**Go/No-Go POC** : si la qualité texturale est jugée inacceptable malgré tuning, on ré-évalue la stack ML (Mip-Splatting, Gaussian Frosting, photogrammétrie classique).

### 7.2 MVP (Itération 1)

| Critère | Cible |
|---|---|
| Tronçon supporté | Jusqu'à 1 km en mono-segment |
| Temps de traitement (1 km) | < 6 h sur RTX 4090 |
| Format de sortie | Package CM installable et chargeable dans AC |
| Roulabilité | Le track se charge, l'AI line est cohérente, on peut faire un tour |
| Détection circuit/spéciale | Fonctionne sur 5 cas de test (3 circuits, 2 spéciales) |

### 7.3 V1 (Itération 2 + 3)

| Critère | Cible |
|---|---|
| Tronçon supporté | Jusqu'à 15 km via tuilage |
| Temps de traitement (5 km) | < 8 h avec 4 workers GPU en parallèle |
| Multi-segment | Pause/reprise jusqu'à 7 jours avec relocalisation |
| Multi-passe | Repasser améliore mesurablement la qualité d'une zone (PSNR, LPIPS) |
| App iOS | Fonctionnelle sur iPhone 12 Pro à 16 Pro |
| Qualité visuelle | Validation utilisateur subjective : "convaincant en jeu" |

## 8. Hors-périmètre rappelé

Les fonctionnalités listées dans [`00-vision.md#ce-que-le-produit-nest-pas`](./00-vision.md#ce-que-le-produit-nest-pas) sont **fermes**. Toute demande qui les contredit doit faire l'objet d'un nouvel ADR dans [`08-decisions.md`](./08-decisions.md) et d'une révision de la vision.

## 9. Glossaire

| Terme | Définition |
|---|---|
| **Tronçon** | Portion de route capturée. Peut devenir un circuit fermé ou une spéciale. |
| **Circuit** | Tracé fermé, l'utilisateur revient au point de départ. Permet les laps. |
| **Spéciale** | Tracé point-à-point (rallye, hillclimb), sans bouclage. |
| **Segment** | Plage continue de capture. Une session peut contenir plusieurs segments séparés par des pauses. |
| **Tuile** | Sous-portion d'un tronçon, traitée en parallèle pour les longs parcours. |
| **Multi-passe** | Repasser sur une zone déjà capturée pour enrichir les données et améliorer la qualité. |
| **Lead-in** | Portion de capture avant le début effectif d'un circuit (chemin de l'utilisateur jusqu'à la boucle). |
| **AI line** | Trajectoire optimale calculée pour les voitures pilotées par l'IA. |
| **CM** | Content Manager, gestionnaire tiers d'AC. |
| **CSP** | Custom Shaders Patch, extension graphique d'AC requise pour les spéciales. |
| **GS** | Gaussian Splatting, technique de reconstruction 3D photoréaliste. |
| **2DGS** | 2D Gaussian Splatting, variante optimisée pour l'extraction de mesh. |
| **PBR** | Physically Based Rendering, modèle de matériaux à base d'albedo / normal / roughness / metallic. |
| **VIO** | Visual-Inertial Odometry, fusion vision + IMU pour estimer les poses. |
| **Bake** | Calcul de textures 2D à partir d'une scène 3D source (multi-vue ici). |
