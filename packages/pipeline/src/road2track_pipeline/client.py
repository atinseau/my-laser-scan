"""Helpers pour démarrer un workflow Temporal depuis l'API ou la CLI.

Cf. specs/02-architecture.md §4.7.
"""

from __future__ import annotations

from road2track_core.config import Settings
from road2track_core.entities.refs import ExportAcInput, IngestInput
from road2track_core.queues import TaskQueue
from temporalio.client import Client, WorkflowHandle


async def get_temporal_client(settings: Settings | None = None) -> Client:
    settings = settings or Settings()
    return await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )


async def start_process_project(
    payload: IngestInput,
    workflow_id: str,
    *,
    client: Client | None = None,
) -> WorkflowHandle[object, object]:
    """Démarre un workflow `ProcessProject`. Retourne un handle pour suivre l'exécution.

    Le workflow retourne un `ProcessProjectResult` (cf. `workflows/process_project.py`).
    """
    if client is None:
        client = await get_temporal_client()
    return await client.start_workflow(
        "ProcessProject",
        payload,
        id=workflow_id,
        task_queue=TaskQueue.CPU.value,
    )


async def start_export_assetto_corsa(
    payload: ExportAcInput,
    workflow_id: str,
    *,
    client: Client | None = None,
) -> WorkflowHandle[object, object]:
    """Démarre le workflow `ExportAssettoCorsa` (It. 1, ADR-023)."""
    if client is None:
        client = await get_temporal_client()
    return await client.start_workflow(
        "ExportAssettoCorsa",
        payload,
        id=workflow_id,
        task_queue=TaskQueue.CPU.value,
    )
