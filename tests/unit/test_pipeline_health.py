"""Tests unitaires sur road2track_pipeline.health.

Tests TCP réels sur ports volontairement fermés/ouverts.
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Iterator

import pytest
from road2track_core.config import Settings
from road2track_pipeline.health import _check_tcp, all_ok, run_health_checks


@pytest.fixture
def open_tcp_port() -> Iterator[int]:
    """Démarre un serveur TCP local éphémère qui accepte les connexions."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        yield port
    finally:
        server.close()


@pytest.mark.asyncio
async def test_check_tcp_succeeds_on_open_port(open_tcp_port: int) -> None:
    result = await _check_tcp("127.0.0.1", open_tcp_port, "test")
    assert result.ok is True
    assert result.name == "test"


@pytest.mark.asyncio
async def test_check_tcp_fails_on_closed_port() -> None:
    # Port très improbablement ouvert (réservé IANA pour usage futur).
    result = await _check_tcp("127.0.0.1", 1, "closed", timeout=1.0)
    assert result.ok is False


@pytest.mark.asyncio
async def test_run_health_checks_with_custom_check_list() -> None:
    async def always_ok() -> Settings:  # noqa: ARG001 — signature volontairement minimaliste
        from road2track_pipeline.health import CheckResult

        return CheckResult(name="dummy", ok=True)

    settings = Settings(_env_file=None)
    results = await run_health_checks(settings, checks=[always_ok])  # type: ignore[arg-type]
    assert all_ok(results)


@pytest.mark.asyncio
async def test_all_ok_returns_false_if_any_fails() -> None:
    from road2track_pipeline.health import CheckResult

    results = [
        CheckResult(name="a", ok=True),
        CheckResult(name="b", ok=False, detail="connection refused"),
    ]
    assert all_ok(results) is False


def test_settings_temporal_host_parsing_does_not_throw_on_bare_host() -> None:
    """Si l'utilisateur tape juste 'host' sans port, on retombe sur le port par défaut."""
    asyncio.set_event_loop(asyncio.new_event_loop())
    s = Settings(_env_file=None, temporal_host="just-a-host")
    host, port = s.temporal_host_port
    assert host == "just-a-host"
    assert port == 7233
