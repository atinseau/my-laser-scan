"""Workflow `ExportAssettoCorsa` (It. 1) — export d'un TexturedMeshRef vers un
zip Content Manager installable.

Cf. ADR-023 — workflows distincts par target jeu, plugés sur l'endpoint stable
de `ProcessProject` (`TexturedMeshRef`).

Pipeline cible (It. 1) :
1. `generate_ac_files` (CPU) → surfaces.ini / models.ini / ui_track.json
2. `generate_fbx` (CPU lourd) → .fbx avec UV unwrap (xatlas) — **stub**
3. `generate_ai_line` (CPU) → fast_lane.ai — **stub**
4. `compile_kn5` (windows-tools queue) → .kn5 via ksEditor — **stub**
5. `package_content_manager` (CPU) → zip final — **stub**

Au moment de ce commit, seule la 1ère activité est câblée ; les 4 autres
suivront par incréments. Le workflow lève `NotImplementedError` après la 1ère
étape jusqu'à ce qu'elles soient implémentées.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel
from road2track_core.entities.refs import (
    AcFilesRef,
    ExportAcInput,
    TrackPackageRef,
)
from road2track_core.queues import TaskQueue
from temporalio import workflow
from temporalio.common import RetryPolicy


class ExportAssettoCorsaResult(BaseModel):
    """Résultat agrégé.

    Au B1, seul `ac_files` est rempli ; `track_package` arrive en B2-B4.
    """

    ac_files: AcFilesRef
    track_package: TrackPackageRef | None = None


@workflow.defn(name="ExportAssettoCorsa")
class ExportAssettoCorsa:
    """Workflow Temporal — TexturedMeshRef → TrackPackageRef (zip CM)."""

    @workflow.run
    async def run(self, payload: ExportAcInput) -> ExportAssettoCorsaResult:
        retry = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=3)

        ac_files: AcFilesRef = await workflow.execute_activity(
            "generate_ac_files",
            payload,
            task_queue=TaskQueue.CPU.value,
            schedule_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry,
        )

        # TODO B2-B4 : generate_fbx, generate_ai_line, compile_kn5,
        # package_content_manager → TrackPackageRef.
        return ExportAssettoCorsaResult(ac_files=ac_files, track_package=None)
