# Documentation opérationnelle

Guides pratiques **complémentaires** aux specs (`specs/` est la référence ; `docs/` est l'application pas-à-pas).

| Guide | Quand l'utiliser |
|---|---|
| [`setup-gpu-windows.md`](./setup-gpu-windows.md) | Démarrer le `gpu_worker` sur ton PC Windows RTX 4090, le relier au Mac via Tailscale. |
| [`setup-gpu-cloud.md`](./setup-gpu-cloud.md) | Lancer un `gpu_worker` sur RunPod (spillover ou parallélisation, spot pricing + checkpointing). |

Pour le setup initial du Mac orchestrateur (`docker-compose up`, MinIO, Temporal, Postgres), voir [`specs/05-infrastructure.md`](../specs/05-infrastructure.md) §4.
