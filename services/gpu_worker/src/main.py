"""Entry point du gpu_worker — Temporal worker sur queue 'gpu'.

À implémenter à l'It. 0 :
- Vérifier CUDA dispo + version driver compatible.
- Vérifier VRAM minimum (16 Go).
- Connexion Temporal frontend via Tailscale (TEMPORAL_HOST).
- Health checks (MinIO accessible).
- Register des activités GPU (segment, train_gs, extract_mesh, bake, estimate_pbr).
- Boucle de polling.

Cf. specs/02-architecture.md §6 et specs/04-pipeline-ml.md §3.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("gpu_worker à implémenter à l'It. 0")


if __name__ == "__main__":
    main()
