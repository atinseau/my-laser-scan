"""Activité Temporal : `train_gs` (étape 3.3, queue `gpu`).

Stub à l'It. 0 : signature + enregistrement Temporal en place. L'implémentation
réelle (gsplat + densification + checkpoint MinIO + FP16 + loss L1+SSIM+depth)
arrive plus tard (cf. specs/04-pipeline-ml.md §3.3 et ADR-022).

L'activité tourne sur `road2track_ml` (à compléter dans `packages/ml/`).
"""

from __future__ import annotations

import structlog
from road2track_core.entities.refs import KeyframesRef, SceneRef
from temporalio import activity

logger = structlog.get_logger(__name__)


@activity.defn(name="train_gs")
async def train_gs(keyframes: KeyframesRef) -> SceneRef:
    """Stub — lève NotImplementedError tant que la phase GPU n'est pas câblée."""
    logger.warning(
        "train_gs stub appelé",
        project_id=keyframes.project_id,
        segment_id=keyframes.segment_id,
        n_keyframes=keyframes.n_keyframes,
    )
    raise NotImplementedError(
        "train_gs : implémentation gsplat à venir (cf. specs/04-pipeline-ml.md §3.3 + ADR-022). "
        "Bloquant tant que `packages/ml/` n'expose pas l'entrée d'entraînement."
    )
