"""Sauvegarde / reprise de checkpoint Gaussian Splatting (cf. ADR-022).

Format `.pt` torch.save avec un dict :
    {
      "iteration": int,
      "means": Tensor,
      "quats_wxyz": Tensor,        # convention wxyz
      "scales_log": Tensor,
      "opacities_logit": Tensor,
      "sh_dc": Tensor,
      "sh_rest": Tensor,
      "optimizer": dict,
      "config_schema_version": 1,
    }

Le upload/download MinIO est géré par l'activité Temporal (cf. `train_gs`),
pas ici — on travaille sur des chemins locaux.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import torch


def save_checkpoint(
    path: Path,
    *,
    iteration: int,
    means: torch.Tensor,
    quats_wxyz: torch.Tensor,
    scales_log: torch.Tensor,
    opacities_logit: torch.Tensor,
    sh_dc: torch.Tensor,
    sh_rest: torch.Tensor,
    optimizer_state: dict[str, Any],
) -> int:
    """Sauvegarde un checkpoint local. Retourne la taille en bytes."""
    import torch

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "iteration": int(iteration),
        "means": means.detach().cpu(),
        "quats_wxyz": quats_wxyz.detach().cpu(),
        "scales_log": scales_log.detach().cpu(),
        "opacities_logit": opacities_logit.detach().cpu(),
        "sh_dc": sh_dc.detach().cpu(),
        "sh_rest": sh_rest.detach().cpu(),
        "optimizer": optimizer_state,
    }
    torch.save(payload, path)
    return path.stat().st_size


def load_checkpoint(path: Path, device: Any) -> dict[str, Any]:
    """Recharge un checkpoint vers `device` ('cuda' ou 'cpu')."""
    import torch

    return torch.load(path, map_location=device, weights_only=False)
