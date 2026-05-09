"""Ports (interfaces abstraites) du domaine.

Les adapters concrets vivent dans storage/, ml/, ac_export/, cloud_bridge/.
Cf. specs/02-architecture.md §5.1.
"""

from road2track_core.ports.object_storage_port import ObjectStoragePort

__all__ = ["ObjectStoragePort"]
