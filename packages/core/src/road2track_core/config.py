"""Configuration applicative chargée depuis l'environnement.

Toutes les valeurs viennent de variables d'environnement (ou .env non versionné).
Aucun secret en dur. Cf. ADR-021.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration runtime de tout service Road2Track.

    Charge depuis (par ordre de priorité) :
    1. Variables d'environnement.
    2. Fichier .env à la racine du projet.
    3. Valeurs par défaut ci-dessous (utiles pour les tests).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Temporal ---
    temporal_host: str = Field(default="127.0.0.1:7233")
    temporal_namespace: str = Field(default="default")

    # --- Postgres applicatif ---
    postgres_user: str = Field(default="road2track")
    postgres_password: str = Field(default="")
    postgres_db: str = Field(default="road2track")
    postgres_host: str = Field(default="127.0.0.1")
    postgres_port: int = Field(default=5432)

    # --- MinIO ---
    minio_endpoint: str = Field(default="127.0.0.1:9000")
    minio_access_key: str = Field(default="")
    minio_secret_key: str = Field(default="")
    minio_bucket_raw: str = Field(default="raw")
    minio_bucket_intermediates: str = Field(default="intermediates")
    minio_bucket_outputs: str = Field(default="outputs")

    # --- NATS ---
    nats_url: str = Field(default="nats://127.0.0.1:4222")

    # --- Tailscale ---
    ts_authkey: str = Field(default="")

    # --- RunPod ---
    runpod_api_key: str = Field(default="")

    # --- Worker ---
    task_queue: str = Field(default="cpu")
    log_level: str = Field(default="INFO")

    @property
    def postgres_dsn(self) -> str:
        """DSN PostgreSQL au format SQLAlchemy / asyncpg."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def temporal_host_port(self) -> tuple[str, int]:
        """Parse temporal_host '127.0.0.1:7233' en (host, port)."""
        host, _, port = self.temporal_host.partition(":")
        return host, int(port or 7233)

    @property
    def minio_host_port(self) -> tuple[str, int]:
        """Parse minio_endpoint '127.0.0.1:9000' en (host, port)."""
        host, _, port = self.minio_endpoint.partition(":")
        return host, int(port or 9000)

    @property
    def nats_host_port(self) -> tuple[str, int]:
        """Parse nats_url 'nats://127.0.0.1:4222' en (host, port)."""
        url = self.nats_url.removeprefix("nats://")
        host, _, port = url.partition(":")
        return host, int(port or 4222)
