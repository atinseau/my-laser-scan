"""Entry point du cpu_worker — Temporal worker sur queue 'cpu'.

À implémenter à l'It. 0 :
- Connexion Temporal frontend (TEMPORAL_HOST).
- Health checks (Postgres, MinIO, NATS) avant register.
- Register des activités CPU (ingest, fuse_sensors, detect_kind_and_trim, ...).
- Boucle de polling.

Cf. specs/02-architecture.md §6 et specs/04-pipeline-ml.md.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("cpu_worker à implémenter à l'It. 0")


if __name__ == "__main__":
    main()
