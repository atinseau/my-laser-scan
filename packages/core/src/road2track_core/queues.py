"""Task queues centrales.

Définition unique des task queues Temporal du projet.
Cf. specs/02-architecture.md §3 et specs/04-pipeline-ml.md.
"""

from __future__ import annotations

from enum import StrEnum


class TaskQueue(StrEnum):
    """Task queues Temporal du projet.

    - CPU            : workers Mac (orchestrateur), agnostique hardware.
    - GPU            : workers CUDA externes (PC Windows + cloud spillover).
    - WINDOWS_TOOLS  : workers Windows natifs (ksEditor.exe pour la compilation KN5)
                       ou workers Linux + Wine (image distincte, validation à l'It. 1).
    """

    CPU = "cpu"
    GPU = "gpu"
    WINDOWS_TOOLS = "windows-tools"
