"""Lint custom : vérifie que les workflows Temporal n'importent aucun adapter.

Conforme à specs/02-architecture.md §2 (règles d'inclusion) et ADR-012.

Un workflow ne peut importer que :
- la stdlib
- pydantic
- temporalio
- road2track_core (entités, ports, types partagés)
- les signatures (types) d'activités

Tout import d'un adapter (ml, storage, ac_export, cloud_bridge, geo) est interdit
dans un workflow car il casserait le déterminisme Temporal.

Échec → exit code 1, blocage CI/PR.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

WORKFLOWS_DIR = Path("packages/pipeline/src/road2track_pipeline/workflows")

FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "road2track_ml",
    "road2track_storage",
    "road2track_ac_export",
    "road2track_cloud_bridge",
    "road2track_geo",  # geo est exclus par défaut pour rester strict
)


def check_file(path: Path) -> list[str]:
    """Retourne la liste des imports interdits dans un fichier workflow."""
    violations: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for prefix in FORBIDDEN_PREFIXES:
                if node.module.startswith(prefix):
                    violations.append(f"{path}: from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in FORBIDDEN_PREFIXES:
                    if alias.name.startswith(prefix):
                        violations.append(f"{path}: import {alias.name}")
    return violations


def main() -> int:
    if not WORKFLOWS_DIR.exists():
        # Pas encore créé (early bootstrap au POC), on passe.
        print(f"[check_workflow_imports] {WORKFLOWS_DIR} n'existe pas encore, OK.")
        return 0

    all_violations: list[str] = []
    for path in WORKFLOWS_DIR.rglob("*.py"):
        all_violations.extend(check_file(path))

    if all_violations:
        print("[check_workflow_imports] ❌ imports interdits dans des workflows :")
        for v in all_violations:
            print(f"  {v}")
        print(
            "\nLes workflows Temporal doivent être déterministes et ne dépendre que "
            "de road2track_core + signatures d'activités.\n"
            "Cf. specs/02-architecture.md §2 et ADR-012."
        )
        return 1

    print("[check_workflow_imports] ✅ aucun import d'adapter dans les workflows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
