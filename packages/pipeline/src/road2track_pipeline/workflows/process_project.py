"""Workflow racine : `ProcessProject`.

Workflow It. 0 — produit un **mesh texturé** comme endpoint stable, point d'arrêt
naturel du POC. Tout ce qui vient après (export AC, autres jeux) est traité par
des workflows séparés qui consomment un `TexturedMeshRef` (cf. ADR-023).

Étapes chaînées :
1. `ingest_session` → SegmentRef (capture validée + uploadée + persistée)
2. `fuse_sensors` → TrajectoryRef (trajectoire fusionnée ENU + uploadée)
3. `detect_kind_and_trim` → DetectedTrackRef (circuit/spéciale + trim lead-in)
4. `select_keyframes` → KeyframesRef (frames JPEG + manifest sur MinIO)
5. `train_gs` (gpu) → SceneRef (scene.ply + métriques)
6. `extract_mesh` (gpu) → MeshRef (mesh.obj reconstruit)
7. `bake_textures` (gpu) → TexturedMeshRef (mesh + atlas + materials)

⚠️ Imports : uniquement `road2track_core` (règle dure ADR-012). Les activités sont
référencées par leur **nom string** pour ne pas tirer les adapters.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel
from road2track_core.entities.refs import (
    BakeTexturesInput,
    DetectedTrackRef,
    IngestInput,
    KeyframesRef,
    MeshRef,
    SceneRef,
    SegmentRef,
    SelectKeyframesInput,
    TexturedMeshRef,
    TrajectoryRef,
)
from road2track_core.queues import TaskQueue
from temporalio import workflow
from temporalio.common import RetryPolicy


class ProcessProjectResult(BaseModel):
    """Résultat agrégé du workflow.

    L'**endpoint stable** est `textured_mesh` (TexturedMeshRef). Les autres
    refs sont conservées pour la traçabilité et le re-run partiel.
    """

    segment: SegmentRef
    trajectory: TrajectoryRef
    detected: DetectedTrackRef
    keyframes: KeyframesRef
    scene: SceneRef
    mesh: MeshRef
    textured_mesh: TexturedMeshRef


@workflow.defn(name="ProcessProject")
class ProcessProject:
    """Workflow Temporal de traitement d'un projet (mono-segment au POC)."""

    @workflow.run
    async def run(self, payload: IngestInput) -> ProcessProjectResult:
        retry = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=3)

        segment: SegmentRef = await workflow.execute_activity(
            "ingest_session",
            payload,
            task_queue=TaskQueue.CPU.value,
            schedule_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry,
        )

        trajectory: TrajectoryRef = await workflow.execute_activity(
            "fuse_sensors",
            segment,
            task_queue=TaskQueue.CPU.value,
            schedule_to_close_timeout=timedelta(minutes=15),
            retry_policy=retry,
        )

        detected: DetectedTrackRef = await workflow.execute_activity(
            "detect_kind_and_trim",
            trajectory,
            task_queue=TaskQueue.CPU.value,
            schedule_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry,
        )

        keyframes: KeyframesRef = await workflow.execute_activity(
            "select_keyframes",
            SelectKeyframesInput(segment=segment, detected=detected),
            task_queue=TaskQueue.CPU.value,
            schedule_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry,
        )

        # Phase GPU — workers sur la queue `gpu` (cf. exigence MH-PIP-4).
        scene: SceneRef = await workflow.execute_activity(
            "train_gs",
            keyframes,
            task_queue=TaskQueue.GPU.value,
            schedule_to_close_timeout=timedelta(hours=8),
            retry_policy=retry,
        )

        mesh: MeshRef = await workflow.execute_activity(
            "extract_mesh",
            scene,
            task_queue=TaskQueue.GPU.value,
            schedule_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry,
        )

        textured_mesh: TexturedMeshRef = await workflow.execute_activity(
            "bake_textures",
            BakeTexturesInput(mesh=mesh, keyframes=keyframes),
            task_queue=TaskQueue.GPU.value,
            schedule_to_close_timeout=timedelta(hours=2),
            retry_policy=retry,
        )

        return ProcessProjectResult(
            segment=segment,
            trajectory=trajectory,
            detected=detected,
            keyframes=keyframes,
            scene=scene,
            mesh=mesh,
            textured_mesh=textured_mesh,
        )
