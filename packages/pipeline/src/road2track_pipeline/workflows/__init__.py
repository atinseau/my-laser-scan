"""Workflows Temporal du pipeline.

⚠️ Règle dure : les workflows ne peuvent importer **que** road2track_core et les
signatures (types) d'activités. Aucun import d'adapter (cf. specs/02-architecture.md §2,
ADR-012, lint CI scripts/check_workflow_imports.py).
"""

from road2track_pipeline.workflows.process_project import ProcessProject

__all__ = ["ProcessProject"]
