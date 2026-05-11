"""Health checks au démarrage des workers.

Vérifie que les services d'infrastructure (Temporal, Postgres, MinIO, NATS) sont
joignables avant de démarrer la boucle de polling. Cf. specs/02-architecture.md §6.

Stratégie : TCP socket connect au port. Pas de validation applicative (auth, version)
car ces vérifications viennent au moment de la première opération réelle.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from road2track_core.config import Settings


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


async def _check_tcp(host: str, port: int, name: str, timeout: float = 5.0) -> CheckResult:
    """Tente une connexion TCP et la ferme immédiatement."""
    try:
        connector = asyncio.open_connection(host, port)
        _, writer = await asyncio.wait_for(connector, timeout=timeout)
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        return CheckResult(name=name, ok=True, detail=f"{host}:{port}")
    except (TimeoutError, OSError) as e:
        return CheckResult(name=name, ok=False, detail=f"{host}:{port} — {e}")


def _temporal_check(settings: Settings) -> Callable[[], Awaitable[CheckResult]]:
    host, port = settings.temporal_host_port
    return lambda: _check_tcp(host, port, "Temporal")


def _postgres_check(settings: Settings) -> Callable[[], Awaitable[CheckResult]]:
    return lambda: _check_tcp(settings.postgres_host, settings.postgres_port, "Postgres")


def _minio_check(settings: Settings) -> Callable[[], Awaitable[CheckResult]]:
    host, port = settings.minio_host_port
    return lambda: _check_tcp(host, port, "MinIO")


def _nats_check(settings: Settings) -> Callable[[], Awaitable[CheckResult]]:
    host, port = settings.nats_host_port
    return lambda: _check_tcp(host, port, "NATS")


def gpu_worker_checks(settings: Settings) -> list[Callable[[], Awaitable[CheckResult]]]:
    """Set de health checks pour le gpu_worker : Temporal + MinIO uniquement.

    Pas de Postgres : le gpu_worker ne touche pas la DB applicative (les
    persistance Postgres se font côté cpu_worker via les activités d'ingest).
    Pas de NATS : on n'a pas (encore) d'event bus inter-workers requis ici.
    """
    return [_temporal_check(settings), _minio_check(settings)]


async def run_health_checks(
    settings: Settings, checks: list[Callable[[], Awaitable[CheckResult]]] | None = None
) -> list[CheckResult]:
    """Exécute la liste de health checks en parallèle.

    Si `checks` est None, on exécute le set par défaut adapté à un cpu_worker
    (Temporal + Postgres + MinIO + NATS).
    """
    if checks is None:
        checks = [
            _temporal_check(settings),
            _postgres_check(settings),
            _minio_check(settings),
            _nats_check(settings),
        ]
    return list(await asyncio.gather(*(check() for check in checks)))


def all_ok(results: list[CheckResult]) -> bool:
    return all(r.ok for r in results)
