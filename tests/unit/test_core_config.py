"""Tests unitaires sur road2track_core.config.Settings."""

from __future__ import annotations

import pytest
from road2track_core.config import Settings


@pytest.fixture
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Évite que le .env de la machine de dev pollue les tests."""
    for key in [
        "TEMPORAL_HOST",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "MINIO_ENDPOINT",
        "NATS_URL",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_defaults(base_env: None) -> None:
    s = Settings(_env_file=None)
    assert s.temporal_host == "127.0.0.1:7233"
    assert s.postgres_port == 5432
    assert s.minio_endpoint == "127.0.0.1:9000"


def test_postgres_dsn_format(base_env: None) -> None:
    s = Settings(
        _env_file=None,
        postgres_user="alice",
        postgres_password="secret",
        postgres_db="mydb",
        postgres_host="db.example",
        postgres_port=6543,
    )
    assert s.postgres_dsn == "postgresql://alice:secret@db.example:6543/mydb"


def test_temporal_host_port_parsing(base_env: None) -> None:
    s = Settings(_env_file=None, temporal_host="my-mac.tail-xxx.ts.net:7233")
    host, port = s.temporal_host_port
    assert host == "my-mac.tail-xxx.ts.net"
    assert port == 7233


def test_nats_url_parsing(base_env: None) -> None:
    s = Settings(_env_file=None, nats_url="nats://10.0.0.1:4222")
    host, port = s.nats_host_port
    assert host == "10.0.0.1"
    assert port == 4222


def test_env_var_override(monkeypatch: pytest.MonkeyPatch, base_env: None) -> None:
    monkeypatch.setenv("TEMPORAL_HOST", "remote:9999")
    s = Settings(_env_file=None)
    assert s.temporal_host == "remote:9999"
