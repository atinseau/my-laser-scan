"""Workflow `ExportAssettoCorsa` (It. 1) — `TexturedMeshRef` → `TrackPackageRef`.

Cf. ADR-023 (workflows distincts par target).

Pipeline complet :
1. `generate_ac_files`     (cpu) → AcFilesRef     — Jinja .ini + ui_track.json
2. `generate_fbx`          (cpu) → FbxRef          — UV unwrap xatlas + OBJ/MTL
3. `generate_ai_line`      (cpu) → AiLineRef       — fast_lane.ai binaire
4. `compile_kn5`           (windows-tools) → Kn5Ref — ksEditor.exe ou placeholder
5. `package_content_manager` (cpu) → TrackPackageRef — zip CM final

Les 5 activités tournent en série au POC. En It. 4+ on pourra paralléliser
(1, 2, 3 indépendants).

⚠️ Imports : uniquement `road2track_core` (règle dure ADR-012).
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel
from road2track_core.entities.refs import (
    AcFilesRef,
    AiLineRef,
    ExportAcInput,
    FbxRef,
    Kn5Input,
    Kn5Ref,
    PackageContentManagerInput,
    TrackPackageRef,
)
from road2track_core.queues import TaskQueue
from temporalio import workflow
from temporalio.common import RetryPolicy


class ExportAssettoCorsaResult(BaseModel):
    """Refs produits à chaque étape — traçabilité pour debug + re-run partiel."""

    ac_files: AcFilesRef
    fbx: FbxRef
    ai_line: AiLineRef
    kn5: Kn5Ref
    track_package: TrackPackageRef


@workflow.defn(name="ExportAssettoCorsa")
class ExportAssettoCorsa:
    """TexturedMeshRef → zip Content Manager installable (ADR-023)."""

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

        fbx: FbxRef = await workflow.execute_activity(
            "generate_fbx",
            payload.textured_mesh,
            task_queue=TaskQueue.CPU.value,
            schedule_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry,
        )

        ai_line: AiLineRef = await workflow.execute_activity(
            "generate_ai_line",
            payload.detected,
            task_queue=TaskQueue.CPU.value,
            schedule_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry,
        )

        kn5: Kn5Ref = await workflow.execute_activity(
            "compile_kn5",
            Kn5Input(fbx=fbx, ac_files=ac_files),
            task_queue=TaskQueue.WINDOWS_TOOLS.value,
            schedule_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry,
        )

        package_input = PackageContentManagerInput(
            project_id=payload.project_id,
            segment_id=payload.segment_id,
            track_name=payload.track_name,
            ac_files=ac_files,
            kn5=kn5,
            ai_line=ai_line,
        )
        track_package: TrackPackageRef = await workflow.execute_activity(
            "package_content_manager",
            package_input,
            task_queue=TaskQueue.CPU.value,
            schedule_to_close_timeout=timedelta(minutes=10),
            retry_policy=retry,
        )

        return ExportAssettoCorsaResult(
            ac_files=ac_files,
            fbx=fbx,
            ai_line=ai_line,
            kn5=kn5,
            track_package=track_package,
        )
