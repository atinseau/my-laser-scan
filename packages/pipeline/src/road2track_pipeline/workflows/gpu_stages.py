"""Workflows debug pour invoquer une seule activité GPU à la fois.

Pas chaînés dans `ProcessProject` — ces workflows servent uniquement à
**débugger pas-à-pas** une activité GPU pendant la validation hardware
(premier run sur ton PC RTX 4090). Une fois `ProcessProject` validé en
end-to-end, on n'en aura plus besoin pour la production.

Cf. ADR-023 (composition des workflows par target) et l'outil
`tools/run_gpu_pipeline.py`.

⚠️ Imports : uniquement `road2track_core` (règle dure ADR-012).
"""

from __future__ import annotations

from datetime import timedelta

from road2track_core.entities.refs import (
    BakeTexturesInput,
    KeyframesRef,
    MeshRef,
    SceneRef,
    TexturedMeshRef,
)
from road2track_core.queues import TaskQueue
from temporalio import workflow
from temporalio.common import RetryPolicy

_RETRY = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=2)


@workflow.defn(name="RunTrainGs")
class RunTrainGs:
    """Lance uniquement `train_gs` (étape 3.3)."""

    @workflow.run
    async def run(self, keyframes: KeyframesRef) -> SceneRef:
        return await workflow.execute_activity(
            "train_gs",
            keyframes,
            task_queue=TaskQueue.GPU.value,
            schedule_to_close_timeout=timedelta(hours=8),
            retry_policy=_RETRY,
        )


@workflow.defn(name="RunExtractMesh")
class RunExtractMesh:
    """Lance uniquement `extract_mesh` (étape 3.4)."""

    @workflow.run
    async def run(self, scene: SceneRef) -> MeshRef:
        return await workflow.execute_activity(
            "extract_mesh",
            scene,
            task_queue=TaskQueue.GPU.value,
            schedule_to_close_timeout=timedelta(minutes=30),
            retry_policy=_RETRY,
        )


@workflow.defn(name="RunBakeTextures")
class RunBakeTextures:
    """Lance uniquement `bake_textures` (étape 3.5)."""

    @workflow.run
    async def run(self, payload: BakeTexturesInput) -> TexturedMeshRef:
        return await workflow.execute_activity(
            "bake_textures",
            payload,
            task_queue=TaskQueue.GPU.value,
            schedule_to_close_timeout=timedelta(hours=2),
            retry_policy=_RETRY,
        )
