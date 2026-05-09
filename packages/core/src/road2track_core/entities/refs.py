"""Refs légères et inputs/outputs des activités, transitant entre workflows et activités.

Pas de gros payloads en mémoire : on échange juste des clés MinIO + métadonnées
(cf. specs/02-architecture.md §7).

Ces classes vivent dans `core` (pas dans `pipeline.activities`) pour que les
workflows puissent les importer sans tirer d'adapter (règle dure ADR-012).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from road2track_core.ids import ProjectId, SegmentId


class IngestInput(BaseModel):
    """Input de l'activité `ingest_session`."""

    schema_version: Literal[1] = 1
    project_id: ProjectId
    local_dir: str = Field(description="Chemin absolu local du dossier de capture")
    segment_id: SegmentId | None = Field(
        default=None,
        description="ID de segment à utiliser ; si None, on en génère un nouveau",
    )


class SegmentRef(BaseModel):
    """Référence à un segment ingéré, échangée entre activités."""

    schema_version: Literal[1] = 1
    project_id: ProjectId
    segment_id: SegmentId
    raw_uri_prefix: str = Field(description="Ex. s3://raw/<project_id>/<segment_id>/")
    file_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
