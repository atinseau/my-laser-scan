"""Nature d'un tracé : circuit (boucle) ou spéciale (point-à-point)."""

from __future__ import annotations

from enum import StrEnum


class TrackKind(StrEnum):
    CIRCUIT = "circuit"
    SPECIALE = "speciale"
