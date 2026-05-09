"""Workflow racine : `ProcessProject`.

Au bootstrap (It. 0), le workflow se contente d'appeler `ingest_session`. Les
activités amont/aval (fuse_sensors, detect_kind_and_trim, tile, ProcessTile, etc.)
viendront au fur et à mesure de l'It. 0 puis It. 1.

Imports : uniquement `road2track_core` (règle dure ADR-012). Les activités sont
référencées par leur **nom string** pour ne pas tirer les adapters.
"""

from __future__ import annotations

from datetime import timedelta

from road2track_core.entities.refs import IngestInput, SegmentRef
from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ProcessProject")
class ProcessProject:
    """Workflow Temporal de traitement d'un projet (mono-segment au POC)."""

    @workflow.run
    async def run(self, payload: IngestInput) -> SegmentRef:
        return await workflow.execute_activity(
            "ingest_session",
            payload,
            schedule_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )
