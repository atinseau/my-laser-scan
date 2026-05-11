"""Fixtures pour les tests d'intégration pipeline.

On lance un MinIO réel via testcontainers (image officielle `minio/minio`).
Skip automatique si Docker ou ffmpeg ne sont pas disponibles dans
l'environnement de test.
"""

from __future__ import annotations

import shutil
from collections.abc import Generator

import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


needs_docker = pytest.mark.skipif(
    not _docker_available(), reason="docker indisponible dans l'env de test"
)
needs_ffmpeg = pytest.mark.skipif(
    not _ffmpeg_available(), reason="ffmpeg/ffprobe indisponibles dans l'env de test"
)


@pytest.fixture(scope="module")
def minio_container() -> Generator[dict[str, str], None, None]:
    """Démarre un MinIO sur un port aléatoire et retourne ses credentials."""
    if not _docker_available():
        pytest.skip("docker indisponible")

    container = (
        DockerContainer("minio/minio:latest")
        .with_env("MINIO_ROOT_USER", "testminio")
        .with_env("MINIO_ROOT_PASSWORD", "testminio-secret")
        .with_command("server /data")
        .with_exposed_ports(9000)
    )
    container.start()
    try:
        wait_for_logs(container, "API:", timeout=30)
        host = container.get_container_host_ip()
        port = container.get_exposed_port(9000)
        yield {
            "endpoint_url": f"http://{host}:{port}",
            "access_key": "testminio",
            "secret_key": "testminio-secret",
        }
    finally:
        container.stop()
