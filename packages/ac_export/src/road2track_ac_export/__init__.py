"""Génération track Assetto Corsa Road2Track — KN5, .ini, AI line, packaging Content Manager.

Cf. specs/02-architecture.md §4.5 et specs/06-modele-donnees.md §5.
ADR-023 : composition par workflow distinct par target jeu.
"""

from road2track_ac_export.ac_files import (
    AcFilesResult,
    render_all_ac_files,
    render_models_ini,
    render_surfaces_ini,
    render_ui_track_json,
)

__version__ = "0.1.0"

__all__ = [
    "AcFilesResult",
    "render_all_ac_files",
    "render_models_ini",
    "render_surfaces_ini",
    "render_ui_track_json",
]
