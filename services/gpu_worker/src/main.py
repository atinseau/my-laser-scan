"""Entry point du gpu_worker — Temporal worker sur queue 'gpu'.

Cf. specs/02-architecture.md §6 et specs/04-pipeline-ml.md §3.

Au scaffold (It. 0) :
- Charge les Settings depuis l'environnement / .env.
- Configure le logging structuré JSON.
- Exécute les health checks (Temporal + MinIO uniquement — pas de Postgres
  ni NATS pour le gpu_worker).
- Ouvre une connexion Temporal.
- Démarre la boucle de polling sur la task queue 'gpu'.

Activités enregistrées (stubs au POC, implémentations à venir) :
- `train_gs`        — étape 3.3, gsplat + checkpoint MinIO + FP16.
- `extract_mesh`    — étape 3.4, 2DGS / Poisson.
- `bake_textures`   — étape 3.5, projection + atlas + PBR.

Les activités lèvent `NotImplementedError` tant que `packages/ml/` n'expose
pas les entrées d'exécution. Elles ne sont **pas encore chaînées** dans
`ProcessProject` — ce sera l'objet d'un commit dédié quand le GS sera prêt.

⚠️ Vérifications CUDA (driver, VRAM ≥ 16 Go) à ajouter en même temps que
la première implémentation GPU réelle.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys

import structlog
from road2track_core.config import Settings
from road2track_core.queues import TaskQueue
from road2track_pipeline.activities import bake_textures, extract_mesh, train_gs
from road2track_pipeline.health import all_ok, gpu_worker_checks, run_health_checks
from road2track_pipeline.logging_setup import configure_logging
from temporalio.client import Client
from temporalio.worker import Worker


async def main_async() -> None:
    settings = Settings()
    configure_logging(level=settings.log_level, worker_name="gpu_worker")
    logger = structlog.get_logger("gpu_worker")

    logger.info(
        "gpu_worker booting",
        temporal_host=settings.temporal_host,
        task_queue=TaskQueue.GPU.value,
        log_level=settings.log_level,
    )

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
        task_queue=TaskQueue.GPU.value,
        activities=[train_gs, extract_mesh, bake_textures],
    )

    logger.info(
        "gpu_worker registered, polling task queue",
        activities=["train_gs", "extract_mesh", "bake_textures"],
        note="stubs — implémentations GPU à venir",
    )
    await worker.run()


def main() -> None:
    """Synchronous entry point. Sortie propre sur Ctrl+C."""
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main_async())


if __name__ == "__main__":
    main()
