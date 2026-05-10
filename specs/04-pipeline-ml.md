# 04 — Pipeline ML

> Description détaillée du pipeline qui transforme les données brutes capturées par l'iPhone en track Assetto Corsa. Pour la mise en place du tooling ML voir [`03-stack-technique.md`](./03-stack-technique.md), pour le modèle de données entre étapes voir [`06-modele-donnees.md`](./06-modele-donnees.md).

## 1. Vue d'ensemble

Le pipeline est divisé en **3 grandes phases** :

1. **Pré-traitement** (CPU) : ingestion, fusion capteurs, détection circuit/spéciale, tuilage.
2. **Reconstruction 3D** (GPU) : segmentation, Gaussian Splatting, extraction mesh, bake textures, PBR.
3. **Post-traitement & livraison** (CPU) : recollage tuiles, génération AC, packaging Content Manager.

Chaque phase est modélisée par un workflow Temporal. Voir [`02-architecture.md#10-diagramme-de-flux`](./02-architecture.md#10-diagramme-de-flux-dun-traitement-complet).

## 2. Phase 1 — Pré-traitement (CPU)

### 2.1 Ingestion

**Activité** : `ingest_session`
**Queue** : `cpu`
**Input** : dossier ou archive de capture (Record3D + Sensor Logger au POC).
**Output** : `Segment` enregistré en base, fichiers déposés en MinIO.

Étapes :
1. Validation du contenu : vidéo HEVC/MP4, dossier `depth/` LiDAR, fichier de poses ARKit, JSON Sensor Logger.
2. **Synchronisation des deux flux Record3D + Sensor Logger** (POC uniquement, voir MH-CAP-1bis) :
   1. Extraction des timestamps UTC depuis les deux exports.
   2. Vérification que les deux flux référencent la même horloge (même ordre de grandeur d'epoch).
   3. Si les timestamps UTC sont cohérents (cas par défaut), alignement direct.
   4. Si une dérive est détectée (offset > 100 ms), calcul d'un **offset constant** par cross-corrélation entre les pics de l'IMU (Sensor Logger) et les pics d'accélération extraits des poses ARKit (Record3D). Application de l'offset.
   5. À partir de l'It. 2 (app native), cette étape devient triviale car un seul flux unifié.
3. Vérification de cohérence temporelle : tous les flux ont des timestamps qui se chevauchent après alignement.
4. Extraction des métadonnées : durée, FPS, résolution, type d'iPhone, version iOS.
5. **Drop du track audio** de la vidéo Record3D (on ne l'utilise pas, mais il pèse ~10% du fichier vidéo) — re-multiplexage HEVC vidéo seule.
6. Upload des fichiers bruts vers MinIO sous `s3://raw/<project_id>/<segment_id>/`.
7. Insertion d'une entrée `Segment` dans Postgres avec `status=ingested`.

#### Détail de la cross-corrélation IMU/ARKit (étape 2.4)

Si l'offset entre timestamps UTC dépasse 100 ms :

1. On extrait la **magnitude** de l'accélération du flux Sensor Logger : `||a_imu(t)||`.
2. On extrait la **dérivée seconde de la position** des poses ARKit : `||d²p_arkit(t)/dt²||`.
3. On rééchantillonne les deux à 100 Hz par interpolation linéaire.
4. Cross-corrélation via `scipy.signal.correlate(..., mode='same')`.
5. L'offset = position du max de la corrélation.
6. **Si l'amplitude max < seuil (0.3)** (utilisateur statique, pas de pic identifiable) → log warning, on continue avec offset = 0 et on assume les UTC alignés.
7. **Si l'offset trouvé est > 5 s** → erreur fatale (incohérence majeure entre les flux), l'utilisateur doit re-capturer.

### 2.2 Fusion capteurs

**Activité** : `fuse_sensors`
**Queue** : `cpu`
**Input** : `SegmentRef`
**Output** : `TrajectoryRef` (poses 6DoF géoréférencées à 100 Hz)

Étapes :
1. Chargement des poses ARKit (50 Hz typique), IMU (100-200 Hz), GPS (1-10 Hz), baromètre.
2. Synchronisation temporelle au timestamp de référence (ARKit).
3. **Filtre de Kalman étendu** (EKF) qui fusionne :
   - État : position (ENU local), orientation (quaternion), vitesse linéaire/angulaire, biais IMU.
   - Mesures : ARKit pose (mesure relative), GPS (mesure absolue WGS84 → ENU), IMU (prédiction), baromètre (z).
4. Détection des outliers GPS (jumps > 10 m) avec rejet par chi² test.
5. Lissage backward (RTS smoother) pour améliorer la cohérence temporelle.
6. Géoréférencement : choix d'un point d'origine ENU local. Le **premier fix GPS dont la précision est < 10 m** (HDOP raisonnable) est choisi. Pendant la période de cold start GPS (typiquement 30-60 s après démarrage), les poses ARKit sont conservées en repère relatif et l'origine ENU est calculée **a posteriori** par alignement (résolution moindre carré sur les segments où GPS valide et ARKit coexistent). Si aucun fix GPS valide n'est obtenu sur toute la session, l'activité échoue avec un message demandant de capturer en environnement plus ouvert.
7. Sauvegarde de la trajectoire en MinIO sous `s3://intermediates/<project_id>/<segment_id>/trajectory.parquet`.

**Implémentation** : `packages/geo/fusion/ekf.py`. Voir aussi [`09-questions-ouvertes.md`](./09-questions-ouvertes.md) pour le choix entre EKF custom et lib existante.

### 2.3 Détection circuit / spéciale + troncature lead-in (circuit uniquement)

**Activité** : `detect_kind_and_trim`
**Queue** : `cpu`
**Input** : `TrajectoryRef`
**Output** : `TrackKind` (`circuit` ou `speciale`), `TrajectoryRef` éventuellement tronqué

#### Principe

| Cas | Comportement |
|---|---|
| **Circuit** (loop closure détectée) | Détection automatique de la boucle. Si lead-in présent, **troncature automatique**. La trajectoire conservée = la boucle uniquement. |
| **Spéciale** (aucune loop closure) | **Trajectoire conservée = trajectoire ingérée**. Pas de détection de lead-in/lead-out. L'utilisateur est responsable d'avoir démarré et arrêté l'enregistrement aux bornes effectives du stage (cf. MH-DET-3 dans [`01-cahier-des-charges.md`](./01-cahier-des-charges.md)). En It. 2+, l'app native pourra exposer des markers explicites pour flagger les bornes après-coup (SH-IOS-2bis), mais l'algorithme reste passif. Voir [ADR-016](./08-decisions.md#adr-016--pas-de-détection-automatique-de-lead-in-en-spéciale). |

#### Algorithme — détection loop closure (cas circuit)

```python
# packages/geo/loop_detection/detect.py
R_LOOP = 15.0              # mètres
HEADING_TOLERANCE = 60     # degrés
T_MIN = 60                 # secondes minimum entre deux points pour considérer un loop
N = len(trajectory)

best = None
for i in range(0, N - 1):
    for j in range(i + 1, N):
        if trajectory[j].t - trajectory[i].t < T_MIN:
            continue
        if geodesic(trajectory[i].pos, trajectory[j].pos) > R_LOOP:
            continue
        if abs(angle_diff(trajectory[i].heading, trajectory[j].heading)) > HEADING_TOLERANCE:
            continue
        # match trouvé
        best = (i, j)
        break
    if best:
        break

if best is None:
    return TrackKind.SPECIALE, trajectory  # trajectoire ingérée fait foi
else:
    i, j = best
    return TrackKind.CIRCUIT, trajectory[i:j]  # tronquer à [i, j]
```

Cas gérés :

| Cas | Description | Résultat |
|---|---|---|
| A | Capture revient au point de départ | `circuit`, garde tout `[0, N]` (premier match `i=0`) |
| B | Lead-in puis boucle (départ pas dans la boucle) | `circuit`, garde `[i, j]`, lead-in jeté |
| C | Aucun croisement | `speciale`, garde la trajectoire telle quelle |

### 2.4 Tuilage

**Activité** : `tile`
**Queue** : `cpu`
**Input** : `TrajectoryRef` (post-troncature lead-in si circuit)
**Output** : liste de `TileRef`, chacun avec ses bornes spatiales et temporelles

#### Stratégie de tuilage

- **Critère de découpage** : longueur de trajectoire le long de la courbe ≈ **800 m** par tuile.
- **Chevauchement** : **50 m** entre tuiles consécutives (zone qu'on traite deux fois pour le stitching).
- **Découpage par index temporel** sur la trajectoire (pas par grille spatiale, pour rester linéaire au sens du tracé).
- **Cas particulier circuit** : la dernière tuile chevauche la première (pour fermer la boucle proprement).

```python
TILE_LEN_M = 800.0
OVERLAP_M  = 50.0
STEP_M     = TILE_LEN_M - OVERLAP_M  # 750 m

cumulative_distance = compute_arc_length(trajectory)
tile_starts = arange(0, cumulative_distance[-1], STEP_M)

tiles = []
for s in tile_starts:
    e = s + TILE_LEN_M
    i = bisect_left(cumulative_distance, s)
    j = bisect_left(cumulative_distance, e)
    tiles.append(Tile(start_idx=i, end_idx=j, ...))

if track_kind == CIRCUIT:
    tiles[-1].overlap_with_first = True
```

Bénéfices :
- Chaque tuile tient en VRAM d'une RTX 4090 (24 Go).
- Parallélisable sur N workers.
- Reprise sur échec localisée.

## 3. Phase 2 — Reconstruction 3D (GPU)

Pour chaque tuile, un **child workflow** `ProcessTile` exécute la séquence ci-dessous. Tous les workflows enfants tournent en parallèle (limité par le nombre de workers GPU disponibles).

### 3.1 Sélection des keyframes

**Activité** : `select_keyframes`
**Queue** : `cpu` (légère, juste de la sélection)
**Input** : `TileRef`
**Output** : `KeyframesRef` — liste de frames retenues + leurs poses

Stratégie :
- Décodage de la vidéo (ffmpeg) à FPS d'origine.
- Filtre par **diversité spatiale** : on garde une frame tous les **0.5 m** de déplacement.
- Filtre par **netteté** : variance du Laplacien > seuil (rejette les blurs de motion).
- Filtre par **diversité angulaire** : on évite que toutes les frames d'une zone aient la même orientation.
- Cible : **800-1500 keyframes par tuile**.

### 3.2 Segmentation sémantique

**Activité** : `segment`
**Queue** : `gpu`
**Input** : `KeyframesRef`
**Output** : `SegmentationRef` (masques par classe pour chaque frame)

Modèle : **Mask2Former** pré-entraîné sur Cityscapes ou Mapillary Vistas (classes utiles : route, trottoir, voiture, personne, ciel, végétation, bâtiment).

Usages aval :
- **Masquer les passants et véhicules** lors du training GS (sinon ils apparaissent comme fantômes dans la scène).
- **Identifier la route** pour l'extraction du centerline et la segmentation finale du mesh.
- **Identifier le ciel** pour ne pas le bake (skybox HDRi à la place).

### 3.3 Entraînement Gaussian Splatting

**Activité** : `train_gs`
**Queue** : `gpu`
**Input** : `KeyframesRef`, `SegmentationRef`, depth LiDAR
**Output** : `SceneRef` (`scene.ply` + métadonnées d'entraînement)

Configuration cible (à raffiner au POC) :

| Paramètre | Valeur |
|---|---|
| Implémentation | gsplat (Nerfstudio) |
| Itérations | 30 000 |
| Densification interval | 100 |
| Densification stop | 15 000 |
| Position learning rate | 1.6e-4 → 1.6e-6 (decay) |
| SH degree | 3 |
| Random init | Non — on initialise à partir du nuage LiDAR |
| Loss | L1 + SSIM (lambda=0.2) + depth supervision LiDAR |
| Mask passants/véhicules | Oui (issu de la segmentation) |
| **Mixed precision (FP16)** | **Activée** (cf. [ADR-022](./08-decisions.md#adr-022--stratégie-doptimisation-de-coût-sans-perte-de-qualité)). Gain de vitesse +30 à +50% sans dégradation qualité. À valider au POC. |
| **Checkpointing MinIO** | **Toutes les 5 000 itérations** (cf. [ADR-022](./08-decisions.md#adr-022--stratégie-doptimisation-de-coût-sans-perte-de-qualité)). Permet la reprise après éviction d'un pod spot, perte max 15 min. |
| **Reprise depuis checkpoint** (multi-passe) | À partir de l'It. 2, le training d'une passe N+1 reprend du checkpoint de la passe N au lieu de redémarrer (cf. [ADR-008](./08-decisions.md#adr-008--multi-passe-pour-amélioration-qualité) + ADR-022). |

**Spécificité route** : on contraint la majorité des splats à rester proches de la surface route (priors géométriques du LiDAR), évitant le foisonnement de gaussiennes "flottantes" dans le ciel ou hors de la zone d'intérêt.

VRAM observée : ~16-20 Go pour 1500 keyframes.

#### Validation empirique du nombre d'itérations au POC

Le chiffre de 30 000 itérations est un **point de départ** issu de la littérature gsplat. Au POC, on **mesure** :
- Le temps total de training pour 30k iter sur RTX 4090.
- Les métriques PSNR/LPIPS atteintes.
- Le rapport qualité/temps si on s'arrête à 15k, 20k, 25k.

**Décision** : si 30k iter dépasse manifestement la cible "< 6 h pour 1 km" du MVP (cf. `01 §7.2`), on **réduit à 15-20k au MVP** et on remonte progressivement en V1+. Le critère de succès (qualité visuelle acceptable) reste prioritaire sur le critère de temps.

#### Gestion VRAM et OOM

Le worker monitore la VRAM toutes les 1000 itérations. **En cas d'OOM** (Out Of Memory) pendant le training :
- L'activité **échoue** avec un message d'erreur clair indiquant la tuile concernée et la VRAM consommée au moment du crash.
- Temporal réessaie une fois (avec backoff). Si re-échec → l'activité reste en `failed`.
- Le message recommande à l'utilisateur de **réduire la taille des tuiles** dans la config (`TILE_LEN_M`) et de relancer.

Pas d'auto-split au MVP — la simplicité prime. Auto-split envisageable en V1+ si le besoin se confirme.

### 3.4 Extraction de mesh

**Activité** : `extract_mesh`
**Queue** : `gpu`
**Input** : `SceneRef`
**Output** : `MeshRef` (`mesh.obj` + `vertex_attributes.npz`)

Méthode : **2DGS** (2D Gaussian Splatting) qui produit nativement un mesh propre depuis des splats.

Étapes :
1. Conversion des splats 3D en disques orientés.
2. Marching Cubes ou TSDF fusion sur les surfaces inférées.
3. Cleaning : suppression des composantes connexes < seuil, lissage Taubin.
4. Decimation initiale à ~500k triangles par tuile (sera redécimé en aval).

Alternative envisagée : SuGaR. À évaluer au POC, voir [`09-questions-ouvertes.md`](./09-questions-ouvertes.md).

### 3.5 Segmentation du mesh

**Activité** : `segment_mesh`
**Queue** : `cpu`
**Input** : `MeshRef`, `SegmentationRef`
**Output** : `LabeledMeshRef` (chaque triangle a un label)

Méthode :
1. Pour chaque triangle, projection vers les keyframes proches.
2. Vote majoritaire des labels de pixels couverts.
3. Lissage des labels (graph cut sur le mesh).
4. Classes finales : **route, bordure, herbe, mur, autre**.

### 3.6 Décimation et UV unwrap

**Activité** : `decimate_uv`
**Queue** : `cpu`
**Input** : `LabeledMeshRef`
**Output** : `GameMeshRef`

- Decimation **non-uniforme** : on préserve la densité sur la route, on agresse l'environnement lointain.
  - Route : densité ~1 triangle / 30 cm².
  - Bordures : densité moyenne.
  - Lointain (>50 m du tracé) : très basse densité.
- UV unwrap : **xatlas** ou son équivalent dans Blender.
- Cible : **mesh ≤ 250k triangles par tuile** après stitching final.

### 3.7 Bake multi-vue

**Activité** : `bake_textures`
**Queue** : `gpu`
**Input** : `GameMeshRef`, `KeyframesRef`, `SceneRef`
**Output** : `TexturesRef` (albedo, possibly normal et roughness)

#### Algorithme

Pour chaque texel `t` du mesh game-ready :

1. Calculer la position 3D `P` correspondant à `t` (interpolation barycentrique).
2. Lister les keyframes `F = {f_1, ..., f_k}` qui voient `P` (visibilité testée par projection + depth check).
3. Pour chaque `f_i`, échantillonner la couleur observée `c_i` au pixel projeté.
4. **Rejet d'occluders** : ignorer les `c_i` masquées comme passant/véhicule par la segmentation.
5. **Pondération** par :
   - Cosinus de l'angle entre normale du triangle et direction de la caméra.
   - Distance caméra-point (préférer les vues proches).
   - Confiance du splat (issue du training GS).
6. **Agrégation** : médiane robuste pondérée → couleur finale.
7. Inscrire dans la map albedo.

Avantages :
- **Photoréalisme préservé** : on lit directement les pixels d'origine.
- **Robustesse aux occluders** : médiane + masques.
- **Pas de lissage abusif** : on n'invente pas de pixels.

Implémentation : custom dans `packages/ml/bake/multiview.py`, accéléré CUDA via PyTorch3D pour la projection/visibilité.

#### Résolution et atlas

| Surface | Résolution texture | Densité texels |
|---|---|---|
| Route (`ROAD`) | 8192×8192 par tuile | ~512 px/m linéaire |
| Bordures (`KERB`) | 4096×4096 par tuile | ~256 px/m |
| Environnement (herbe, mur, lointain) | 4096×4096 par tuile | variable |

**Atlas par tuile au MVP** (1 atlas = 1 mesh = 1 tuile). Atlas global considéré en V2 pour réduire le draw call count dans AC. Choix tracé dans [`09-questions-ouvertes.md QO-006`](./09-questions-ouvertes.md#qo-006--atlas-de-textures-par-tuile-vs-global).

### 3.8 Estimation PBR

**Activité** : `estimate_pbr`
**Queue** : `gpu`
**Input** : `GameMeshRef`, `KeyframesRef`, albedo brut
**Output** : `PBRTexturesRef` (albedo PBR, normal, roughness)

Méthode : **NeILF++** ou variante.
- Sépare l'illumination de l'albedo (delight) à partir de multi-vue avec lumière différente.
- Estime les normales et la rugosité plausibles.

**Fallback** si NeILF++ trop coûteux ou instable :
- Albedo = albedo bruts (déjà bon en jour clair sans ombres dures).
- Normal : tile d'asphalte procédural multipliée pour la route, valeurs neutres ailleurs (calibré par rugosité LiDAR).
- Roughness : valeurs constantes par classe (route = 0.85, herbe = 0.95, métal détecté = 0.4).

Le fallback est documenté comme acceptable au POC et MVP. NeILF++ devient cible en V1.

## 4. Phase 3 — Post-traitement & livraison (CPU)

### 4.1 Stitching de tuiles

**Activité** : `stitch_tiles`
**Queue** : `cpu`
**Input** : liste de `(GameMeshRef, PBRTexturesRef)` par tuile
**Output** : `StitchedTrackRef` (mesh + textures unifiées)

Étapes :
1. Pour chaque paire de tuiles adjacentes, récupérer la zone de chevauchement (50 m).
2. ICP local pour aligner finement les meshs (les bords devraient déjà coïncider grâce à la trajectoire commune).
3. Coupe des triangles dans la zone de chevauchement, blending dans la transition (10-20 m de fondu).
4. Texture atlas global ou conservation par tuile (à arbitrer, voir [`09-questions-ouvertes.md`](./09-questions-ouvertes.md)).
5. Validation : continuité C0/C1 sur la route (pas de "marche" entre tuiles).

### 4.2 Extraction du centerline route

**Activité** : `extract_centerline`
**Queue** : `cpu`
**Input** : `StitchedTrackRef`
**Output** : `CenterlineRef` (polyligne 3D)

Méthode :
1. Extraction des triangles labellisés "route".
2. Squelettisation 3D (medial axis).
3. Lissage par B-spline.
4. Échantillonnage régulier (1 point tous les 1 m).

### 4.3 Génération AI line

**Activité** : `generate_ai_line`
**Queue** : `cpu`
**Input** : `CenterlineRef`, mesh route, kind
**Output** : `fast_lane.ai`, `pit_lane.ai`

Étapes :
1. Calcul de la **largeur de route** à chaque sample (par projection latérale sur le mesh).
2. Calcul d'une trajectoire optimale simple : minimisation de courbure + rester proche du centre.
3. Format binaire `fast_lane.ai` selon spec AC.

(Pour la V1, on pourra utiliser des outils comme **AI Line Helper** ou un solveur plus sophistiqué.)

### 4.3bis Pit lane et timings (start/finish, hot_lap_start)

AC requiert une `pit_lane.ai` valide et au moins **un pit box** pour qu'une track se charge. Comme la capture vient d'une balade publique, il n'y a pas de vraie pit lane → on en génère une **synthétique minimale**.

#### Pit lane

- **Tracé** : centerline shifté latéralement de **4 m** côté droit (configurable selon le pays / sens de circulation détecté via le magnétomètre).
- **Sample** : 1 point tous les 1 m, comme la `fast_lane.ai`.
- **Format** : `pit_lane.ai` binaire AC.

#### Pit box

- **Position** : 1 pit box au point de départ détecté (origine de la trajectoire pour spéciale, point `i` de la loop closure pour circuit).
- **Orientation** : alignée sur le heading de la trajectoire au point.
- **Dimensions** : 6 × 16 m standard AC.

#### Hot lap start

- **Pour circuit** : `hot_lap_start` est positionné **30 m avant la ligne de départ** (côté entrée de la boucle), pour donner un élan d'avant-tour.
- **Pour spéciale** : pas de `hot_lap_start`. À la place, CSP gère un `START_POINT` (déclencheur début de timing) au point A, et un `FINISH_LINE` (déclencheur fin de timing) au point B. Voir `extension/hill_climb.ini` dans le format Content Manager (cf. [`06-modele-donnees.md §5.5`](./06-modele-donnees.md#55-cas-spéciale--extensionhill_climbini)).

### 4.4 Génération des fichiers AC

**Activité** : `generate_ac_track`
**Queue** : `cpu`
**Input** : `StitchedTrackRef`, `CenterlineRef`, AI lines, kind
**Output** : dossier track non zippé

Génère :
- `surfaces.ini` (frictions par classe)
- `models.ini` (objets et leur visibilité)
- `camera.ini` (caméras de TV)
- `track.ini` (géo, météo)
- `data/sections.ini` (secteurs)
- `ui/ui_track.json`
- Dépendances CSP si spéciale (`extension/`)

Templates dans `packages/ac_export/ini/templates/`.

### 4.5 Compilation KN5

**Activité** : `compile_kn5`
**Queue** : `cpu` (mais doit tourner sur Windows ou Wine)
**Input** : dossier track + FBX
**Output** : `*.kn5`

Compilation via `ksEditor.exe` en mode CLI. Voir [`05-infrastructure.md`](./05-infrastructure.md) pour le détail d'exécution (Wine sur Linux ou worker dédié Windows).

### 4.6 Packaging Content Manager

**Activité** : `package_content_manager`
**Queue** : `cpu`
**Input** : dossier track final
**Output** : `track.zip` prêt pour Content Manager

Étapes :
1. Génération de `preview.png` (rendu de profil) et `outline.png` (vue de dessus du tracé).
2. Construction du `ui_track.json` final.
3. Zip avec la structure attendue par CM.
4. Dépôt sur MinIO sous `s3://outputs/<project_id>/track.zip`.
5. Génération d'une URL de téléchargement.

### 4.7 Notification

**Activité** : `notify`
**Queue** : `cpu`
**Input** : URL de téléchargement
**Output** : event NATS, log structuré

## 5. Stratégie de tuilage — détails

Voir [`02-architecture.md`](./02-architecture.md) pour le diagramme global. Détails complémentaires :

- **Coût mémoire** : une tuile de 800 m × ~10 m de large = ~8000 m² couvert, gérable en VRAM 24 Go.
- **Parallélisme** : N tuiles → N workers GPU simultanés. Pour 12 km, 15 tuiles → 4 workers en 4 vagues, ou 8 workers en 2 vagues.
- **Failure recovery** : si la tuile #7 échoue, on relance uniquement `ProcessTile(#7)`. Les autres tuiles restent comme elles sont.
- **Streaming** : à partir de V1, on peut commencer le stitching dès que des tuiles consécutives sont prêtes (pipeline streaming).

## 6. Multi-passe qualité

L'utilisateur peut repasser sur une zone pour enrichir la qualité. Trois sous-cas :

### A. Pause courte intra-session
- L'utilisateur s'arrête (feu, photo) puis reprend.
- L'app maintient la session ARKit, pas de relocalisation nécessaire.
- Marqueur de pause dans le manifest, mais traitement continu.

### B. Reprise différée
- L'utilisateur reprend une session quelques heures/jours plus tard.
- L'app demande à se positionner près de la fin précédente.
- **Relocalisation visuelle** : ARKit ARWorldMap ou matching de features visuelles avec les keyframes existants.
- Une fois recalé, la trajectoire est étendue.

### C. Multi-passe sur zone existante
- L'utilisateur passe une 2e fois sur une portion déjà cartographiée.
- Détection : pour chaque keyframe nouvelle, on vérifie si sa position tombe dans un voxel déjà couvert (heatmap `coverage.geojson`).
- Si oui → **observation supplémentaire** ajoutée au dataset GS de la tuile concernée.
- Plus de vues = meilleure GS = meilleur bake.

Implémentation détaillée différée à l'itération 2 (cf. [`07-roadmap.md`](./07-roadmap.md)).

## 7. Métriques de qualité

À tracker pour valider chaque itération :

| Métrique | Mesure | Seuil acceptable |
|---|---|---|
| PSNR sur frames de validation | Comparaison render GS vs photo | > 25 dB |
| LPIPS sur frames de validation | Distance perceptuelle | < 0.20 (MVP), < 0.15 (V1) |
| Cohérence centerline | Écart au centerline OSM (si dispo) | < 1 m |
| Continuité inter-tuiles | Discontinuité moyenne sur la zone fondue | < 5 cm |
| Couverture de la route | % de la trajectoire couverte par >= 5 keyframes | > 90% |
| Latence pipeline (1 km) | Temps d'horloge bout-en-bout | < 6 h MVP (à valider au POC, possible assouplissement) |
| Roulabilité subjective | Test utilisateur | "convaincant en jeu" |

### Construction du validation set

Le calcul de PSNR/LPIPS exige un **held-out set** de frames non vues pendant le training GS :

- À l'étape `select_keyframes` (§3.1), **1 frame sur 10** est marquée `is_validation: true` dans le `keyframes.json`.
- Le training GS exclut ces frames de son dataset.
- Après training, on **render** le GS depuis les poses des frames de validation et on compare aux images réelles.
- Les métriques sont sauvegardées avec le `SceneRef` (champ `metrics: {psnr_mean, lpips_mean, ...}`).

## 8. Limitations connues

1. **Vitesse de capture > 30 km/h** : motion blur dégrade la GS, le LiDAR perd ses points. À gérer en V1+ via OIS et compensation rolling shutter.
2. **Surfaces réfléchissantes** (eau, vitres) : violent les hypothèses Lambertiennes du bake. Acceptable car peu fréquent sur route.
3. **Occlusions massives** (camion devant) : peuvent laisser des trous. Atténué par multi-passe.
4. **Conditions météo extrêmes** : pluie/brouillard cassent la fusion. Hors-périmètre actuel.
5. **Tunnels** : pas de GPS, dérive VIO. Cas non géré au MVP.
