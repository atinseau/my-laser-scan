"""Activité Temporal : `extract_mesh` (étape 3.4, queue `gpu`).

Stub à l'It. 0. L'implémentation utilisera 2DGS / NeRF2Mesh ou
poisson reconstruction selon les résultats du POC
(cf. specs/04-pipeline-ml.md §3.4).
"""

from __future__ import annotations

import structlog
from road2track_core.entities.refs import MeshRef, SceneRef
from temporalio import activity

logger = structlog.get_logger(__name__)


@activity.defn(name="extract_mesh")
async def extract_mesh(scene: SceneRef) -> MeshRef:
    """Stub — lève NotImplementedError tant que la phase GPU n'est pas câblée."""
    logger.warning(
        "extract_mesh stub appelé",
        project_id=scene.project_id,
        segment_id=scene.segment_id,
        scene_uri=scene.scene_uri,
    )
    raise NotImplementedError(
        "extract_mesh : implémentation 2DGS/Poisson à venir "
        "(cf. specs/04-pipeline-ml.md §3.4)."
    )
