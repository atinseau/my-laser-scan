"""Entry point du cpu_worker — Temporal worker sur queue 'cpu'.

Cf. specs/02-architecture.md §6 et specs/04-pipeline-ml.md.

Étapes au démarrage :
1. Charge les Settings depuis l'environnement / .env.
2. Configure le logging structuré (JSON, structlog).
3. Exécute les health checks (Temporal, Postgres, MinIO, NATS).
4. Ouvre une connexion Temporal.
5. Démarre la boucle de polling sur la task queue 'cpu'.

Activités enregistrées : `ingest_session`. D'autres viendront au fur et à mesure
de l'It. 0 et It. 1 (fuse_sensors, detect_kind_and_trim, tile, etc.).
Workflows : `ProcessProject`.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys

import structlog
from road2track_core.config import Settings
from road2track_core.queues import TaskQueue
from road2track_pipeline.activities import (
    detect_kind_and_trim,
    fuse_sensors,
    ingest_session,
    select_keyframes,
)
from road2track_pipeline.health import all_ok, run_health_checks
from road2track_pipeline.logging_setup import configure_logging
from road2track_pipeline.workflows import (
    ProcessProject,
    RunBakeTextures,
    RunExtractMesh,
    RunTrainGs,
)
from temporalio.client import Client
from temporalio.worker import Worker


async def main_async() -> None:
    settings = Settings()
    configure_logging(level=settings.log_level, worker_name="cpu_worker")
    logger = structlog.get_logger("cpu_worker")

    logger.info(
        "cpu_worker booting",
        temporal_host=settings.temporal_host,
        task_queue=TaskQueue.CPU.value,
        log_level=settings.log_level,
    )

    # Health checks pré-démarrage
    results = await run_health_checks(settings)
    for r in results:
        if r.ok:
            logger.info("health check ok", check=r.name, detail=r.detail)
        else:
            logger.error("health check failed", check=r.name, detail=r.detail)

    if not all_ok(results):
        logger.error("aborting boot due to failing health checks")
        sys.exit(1)

    # Connexion Temporal
    client = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
    logger.info("temporal connected", namespace=settings.temporal_namespace)

    worker = Worker(
        client,
        task_queue=TaskQueue.CPU.value,
        workflows=[ProcessProject, RunTrainGs, RunExtractMesh, RunBakeTextures],
        activities=[
            ingest_session,
            fuse_sensors,
            detect_kind_and_trim,
            select_keyframes,
        ],
    )

    logger.info(
        "cpu_worker registered, polling task queue",
        workflows=[
            "ProcessProject",
            "RunTrainGs",
            "RunExtractMesh",
            "RunBakeTextures",
        ],
        activities=[
            "ingest_session",
            "fuse_sensors",
            "detect_kind_and_trim",
            "select_keyframes",
        ],
    )
    await worker.run()


def main() -> None:
    """Synchronous entry point. Sortie propre sur Ctrl+C."""
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main_async())


if __name__ == "__main__":
    main()
