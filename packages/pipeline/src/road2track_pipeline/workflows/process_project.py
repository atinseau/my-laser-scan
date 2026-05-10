"""Workflow racine : `ProcessProject`.

Au bootstrap (It. 0), enchaîne :
1. `ingest_session` → SegmentRef (capture validée + uploadée + persistée)
2. `fuse_sensors` → TrajectoryRef (trajectoire fusionnée ENU + uploadée)

Étapes amont/aval (`detect_kind_and_trim`, `tile`, ProcessTile, etc.) viendront
au fur et à mesure de l'It. 0.

⚠️ Imports : uniquement `road2track_core` (règle dure ADR-012). Les activités sont
référencées par leur **nom string** pour ne pas tirer les adapters.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel
from road2track_core.entities.refs import IngestInput, SegmentRef, TrajectoryRef
from temporalio import workflow
from temporalio.common import RetryPolicy


class ProcessProjectResult(BaseModel):
    """Résultat agrégé du workflow."""

    segment: SegmentRef
    trajectory: TrajectoryRef


@workflow.defn(name="ProcessProject")
class ProcessProject:
    """Workflow Temporal de traitement d'un projet (mono-segment au POC)."""

    @workflow.run
    async def run(self, payload: IngestInput) -> ProcessProjectResult:
        retry = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=3)

        segment: SegmentRef = await workflow.execute_activity(
            "ingest_session",
            payload,
            schedule_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry,
        )

        trajectory: TrajectoryRef = await workflow.execute_activity(
            "fuse_sensors",
            segment,
            schedule_to_close_timeout=timedelta(minutes=15),
            retry_policy=retry,
        )

        return ProcessProjectResult(segment=segment, trajectory=trajectory)
