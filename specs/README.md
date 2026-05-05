# Spécifications — my-laser-scan

> Index des documents de spécification du projet. Avant de coder, lire au minimum `00-vision.md`, `01-cahier-des-charges.md` et `07-roadmap.md`.

Ce dossier contient l'**ensemble du cahier des charges** du projet. Il sert de source de vérité pour toutes les décisions de design, l'architecture, la roadmap et les conventions. Tout désaccord entre le code et ces documents doit être résolu **soit en mettant à jour le code, soit en mettant à jour les specs**, jamais en laissant la divergence.

## Comment lire ce dossier

| Si tu es… | Lis dans cet ordre |
|---|---|
| Nouveau dev qui rejoint | `00` → `01` → `02` → `07` → `03` |
| En train de coder une feature | `01` → la section concernée de `02`/`04`/`05` → `08` |
| En train d'arbitrer un choix technique | `08` (ADR existants) → `09` (questions ouvertes) |
| En train de planifier un sprint | `07` → `01` (MoSCoW) |
| Auditeur / reviewer | tout, dans l'ordre |

## Documents

| # | Fichier | Sujet | Public principal |
|---|---|---|---|
| 00 | [`00-vision.md`](./00-vision.md) | Mission, persona, parcours utilisateur, hors-périmètre | Tous |
| 01 | [`01-cahier-des-charges.md`](./01-cahier-des-charges.md) | Fonctionnalités MoSCoW, contraintes, critères de succès | Tous |
| 02 | [`02-architecture.md`](./02-architecture.md) | Architecture en couches, workspace `uv`, règles de dépendance | Devs back |
| 03 | [`03-stack-technique.md`](./03-stack-technique.md) | Technologies retenues, versions, alternatives rejetées | Devs back, ops |
| 04 | [`04-pipeline-ml.md`](./04-pipeline-ml.md) | Étapes du pipeline ML, tuilage, détection circuit/spéciale | Devs ML |
| 05 | [`05-infrastructure.md`](./05-infrastructure.md) | Topologie machines, Docker, Tailscale, providers GPU | Devs back, ops |
| 06 | [`06-modele-donnees.md`](./06-modele-donnees.md) | Entités, schemas Pydantic, formats intermédiaires | Devs back, ML |
| 07 | [`07-roadmap.md`](./07-roadmap.md) | Itérations, jalons, livrables | Tous |
| 08 | [`08-decisions.md`](./08-decisions.md) | ADRs (Architecture Decision Records) | Devs, architectes |
| 09 | [`09-questions-ouvertes.md`](./09-questions-ouvertes.md) | Décisions encore à prendre | Tous |

## Conventions de mise à jour

- **Toute décision technique structurante** → un ADR dans `08-decisions.md`.
- **Toute question non tranchée** → une entrée dans `09-questions-ouvertes.md`. Quand tranchée, déplacée vers un ADR et retirée de `09`.
- **Toute nouvelle feature** → ajustement de `01-cahier-des-charges.md` (MoSCoW) + impact sur `07-roadmap.md`.
- **Tout changement d'architecture** → `02-architecture.md` mis à jour + ADR si non-trivial.
- **Tout changement de pipeline ML** → `04-pipeline-ml.md` mis à jour.

## Statut du projet

🚧 **Pré-POC**. Aucune ligne de code applicatif n'est encore écrite. Le projet est en phase de cadrage. Voir [`07-roadmap.md`](./07-roadmap.md) pour le plan d'attaque.
