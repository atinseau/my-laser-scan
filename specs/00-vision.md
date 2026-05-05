# 00 — Vision

## Mission

> **Transformer une simple balade en voiture, à vélo ou à pied avec un iPhone en un circuit jouable dans Assetto Corsa, avec un effort utilisateur trivial et un rendu visuel photoréaliste.**

Le produit n'a pas vocation à concurrencer les outils de modélisation 3D professionnels. Il vise à **ouvrir le sim racing à la création de circuits issus du monde réel** sans aucune compétence en modélisation, scan 3D ou édition de tracé.

## Métaphore directrice

**Strava pour le sim racing.** L'utilisateur active la capture, va se balader, arrête. Quelques heures plus tard, il télécharge un circuit prêt à rouler. La complexité technique (LiDAR, photogrammétrie, Gaussian Splatting, conversion AC) est entièrement masquée.

## Persona unique (pour l'instant)

**Sim racer technicien.** Il possède :

- Un iPhone Pro (12 Pro ou plus récent) équipé de LiDAR.
- Une machine de développement (Mac M3 Max dans le cas de référence).
- Un PC sous Windows avec une GPU NVIDIA récente (RTX 4090 dans le cas de référence).
- Assetto Corsa + Content Manager + Custom Shaders Patch installés.
- Tailscale configuré sur ses machines.
- Un compte cloud GPU (RunPod ou équivalent) pour les longs runs.

Le produit est volontairement conçu pour ce profil au démarrage. **Aucune ambition multi-utilisateur, multi-tenant, ou grand public** au stade actuel. L'élargissement viendra après validation technique.

## Parcours utilisateur cible (golden path)

1. **Préparation** — l'utilisateur ouvre Record3D et Sensor Logger sur son iPhone. (Itérations futures : application native unique.)
2. **Capture** — il démarre l'enregistrement, roule/marche le long du tronçon visé (jusqu'à 15 km), peut **mettre en pause** et **reprendre** plus tard, peut **repasser sur une zone déjà capturée** pour améliorer la qualité.
3. **Transfert** — les fichiers de capture arrivent sur la machine Mac (USB, AirDrop, ou plus tard upload via app).
4. **Ingestion** — `uv run road2track ingest <chemin>` enregistre la session dans le projet.
5. **Traitement** — `uv run road2track process <project-id>` lance le workflow Temporal. Les activités GPU partent vers le PC Windows ou un pod cloud, selon disponibilité.
6. **Récupération** — quand le workflow termine, un package zip Content Manager est disponible.
7. **Installation** — l'utilisateur glisse le zip dans Content Manager, qui détecte et installe le track.
8. **Jeu** — il lance Assetto Corsa et roule sur son circuit.

## Ce que le produit **n'est pas**

- ❌ Un outil de modélisation manuelle.
- ❌ Un éditeur de tracé.
- ❌ Une marketplace de circuits.
- ❌ Une plateforme multi-utilisateur.
- ❌ Un produit grand public packagé (pas d'App Store, pas d'installeur Windows).
- ❌ Compatible avec d'autres simulateurs (rFactor, iRacing, BeamNG, AC Evo) au MVP.
- ❌ Compatible Android.
- ❌ Un service avec authentification, paiement, comptes.

Toutes ces directions sont éventuellement explorables en V2+. Elles sont **explicitement exclues du périmètre actuel**.

## Promesse qualité

Trois engagements non négociables qui pilotent toutes les décisions techniques :

1. **Photoréalisme à vitesse de jeu.** Le rendu doit être convaincant en mouvement, pas seulement en screenshot statique. Pas de textures stylisées, pas de "low-poly artistique".
2. **Effort utilisateur < 5 minutes hors capture.** Du transfert des fichiers à la disponibilité du circuit dans AC, l'utilisateur passe moins de 5 minutes à interagir avec le système (la majorité du temps de traitement est invisible, en arrière-plan).
3. **Reproductibilité.** Une même balade donne deux fois le même circuit (à l'aléa des modèles ML près). Pas de pipeline non-déterministe sans contrôle.

## Hypothèses de travail

- L'utilisateur capture **dans des conditions raisonnables** (éclairage diurne stable, météo non extrême).
- L'utilisateur capture à **vitesse modérée** (< 30 km/h au MVP, voiture classique en V1).
- L'utilisateur **possède le matériel** décrit dans le persona.
- Le réseau Tailscale entre Mac et PC est fonctionnel.
- Le PC GPU est **allumé** quand l'utilisateur lance un traitement (sinon, fallback cloud GPU).

## Critères globaux de succès

| Niveau | Critère |
|---|---|
| POC | Un mesh texturé visuellement reconnaissable est généré sur 200 m de capture, sans intervention manuelle après l'ingestion. |
| MVP | Un circuit installable et roulable dans AC est généré sur 1 km, sans intervention manuelle après l'ingestion. |
| V1 | Le pipeline supporte 10-15 km via tuilage, capture multi-segments avec pause/reprise/multi-passe via app iOS native. |
| V2 | Anonymisation, édition légère, optimisations de coût, multi-jeux. |

Ces critères sont déclinés en livrables précis dans [`07-roadmap.md`](./07-roadmap.md) et en exigences fonctionnelles dans [`01-cahier-des-charges.md`](./01-cahier-des-charges.md).
