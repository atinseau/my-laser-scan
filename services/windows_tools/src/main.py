"""Entry point du `windows-tools` worker — Temporal worker sur queue 'windows-tools'.

Cf. specs/02-architecture.md §6 et ADR-006/ADR-023.

Au scaffold (It. 1 B4) :
- Tourne idéalement en natif Windows (sur ton PC RTX 4090) avec accès direct
  à `ksEditor.exe` du SDK Assetto Corsa.
- Alternative en parallèle (cf. QO-007) : container Linux + Wine + ksEditor.

Activité enregistrée : `compile_kn5` (étape 3.6 export AC).

⚠️ Si `KSEDITOR_PATH` n'est pas défini OU pointe sur un chemin inexistant,
l'activité produit un **placeholder .kn5** (zip des inputs) pour permettre aux
étapes aval (package_content_manager) de tourner. Le package CM produit ne
sera pas un vrai circuit jouable, mais le pipeline reste validable.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys

import structlog
from road2track_core.config import Settings
from road2track_core.queues import TaskQueue
from road2track_pipeline.activities import compile_kn5
from road2track_pipeline.health import all_ok, gpu_worker_checks, run_health_checks
from road2track_pipeline.logging_setup import configure_logging
from temporalio.client import Client
from temporalio.worker import Worker


async def main_async() -> None:
    settings = Settings()
    configure_logging(level=settings.log_level, worker_name="windows_tools")
    logger = structlog.get_logger("windows_tools")

    logger.info(
        "windows_tools booting",
        temporal_host=settings.temporal_host,
        task_queue=TaskQueue.WINDOWS_TOOLS.value,
        log_level=settings.log_level,
    )

    # Health checks : Temporal + MinIO suffisent (pas de Postgres ni NATS).
    results = await run_health_checks(settings, checks=gpu_worker_checks(settings))
    for r in results:
        if r.ok:
            logger.info("health check ok", check=r.name, detail=r.detail)
        else:
            logger.error("health check failed", check=r.name, detail=r.detail)

    if not all_ok(results):
        logger.error("aborting boot due to failing health checks")
        sys.exit(1)

    client = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
    logger.info("temporal connected", namespace=settings.temporal_namespace)

    worker = Worker(
        client,
        task_queue=TaskQueue.WINDOWS_TOOLS.value,
        activities=[compile_kn5],
    )

    logger.info(
        "windows_tools registered, polling task queue",
        activities=["compile_kn5"],
    )
    await worker.run()


def main() -> None:
    """Synchronous entry point. Sortie propre sur Ctrl+C."""
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main_async())


if __name__ == "__main__":
    main()
