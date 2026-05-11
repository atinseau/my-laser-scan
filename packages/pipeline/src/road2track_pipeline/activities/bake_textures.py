"""Activité Temporal : `bake_textures` (étape 3.5, queue `gpu`).

Stub à l'It. 0. L'implémentation projettera les keyframes sur le mesh + UV
unwrap + atlas, et estimera des PBR maps via fallback procédural au POC,
NeILF++ en V1 (cf. specs/04-pipeline-ml.md §3.5 + ADR-022).
"""

from __future__ import annotations

import structlog
from road2track_core.entities.refs import MeshRef, TexturedMeshRef
from temporalio import activity

logger = structlog.get_logger(__name__)


@activity.defn(name="bake_textures")
async def bake_textures(mesh: MeshRef) -> TexturedMeshRef:
    """Stub — lève NotImplementedError tant que la phase GPU n'est pas câblée."""
    logger.warning(
        "bake_textures stub appelé",
        project_id=mesh.project_id,
        segment_id=mesh.segment_id,
        mesh_uri=mesh.mesh_uri,
    )
    raise NotImplementedError(
        "bake_textures : implémentation projection + atlas + PBR à venir "
        "(cf. specs/04-pipeline-ml.md §3.5)."
    )
