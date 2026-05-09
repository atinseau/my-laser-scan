"""Activités Temporal du pipeline.

Effets de bord, appels externes, peuvent être ré-tentés par Temporal.
Cf. specs/02-architecture.md §4.7.

Les inputs/outputs Pydantic vivent dans `road2track_core.entities.refs`
pour pouvoir être importés par les workflows sans tirer d'adapter.
"""

from road2track_pipeline.activities.ingest import ingest_session

__all__ = ["ingest_session"]
