"""Configuration structlog partagée par tous les workers et services.

Format JSON, champs minimaux requis par specs/02-architecture.md §6 (logging convention).
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", *, worker_name: str | None = None) -> None:
    """Configure structlog en JSON sur stdout.

    Champs ajoutés à chaque log :
    - timestamp_utc, level, logger
    - worker_name si fourni (cf. specs/02-architecture.md §6).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp_utc"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    if worker_name:
        structlog.contextvars.bind_contextvars(worker_name=worker_name)
