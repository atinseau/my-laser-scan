"""Loss functions pour le training Gaussian Splatting.

Toutes les fonctions importent torch en lazy local pour permettre l'import du
module sans torch installé (utile en CI CPU-only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import torch


def l1_loss(pred: Any, target: Any) -> Any:
    """L1 mean — `pred` et `target` sont des tensors `[..., C, H, W]` ou similaires."""
    import torch

    return torch.abs(pred - target).mean()


def _gaussian_window(window_size: int, sigma: float, device: Any) -> Any:
    import torch

    coords = torch.arange(window_size, dtype=torch.float32, device=device)
    coords -= (window_size - 1) / 2.0
    g = torch.exp(-(coords**2) / (2.0 * sigma**2))
    g = g / g.sum()
    return g[:, None] * g[None, :]


def ssim(pred: Any, target: Any, window_size: int = 11, sigma: float = 1.5) -> Any:
    """SSIM 2D (Wang et al. 2004) entre deux images `[B, C, H, W]` dans [0, 1].

    Renvoie un scalaire (mean sur toutes les fenêtres). Pour la loss, utiliser
    `1 - ssim(...)`.
    """
    from torch.nn import functional as functional_module

    if pred.shape != target.shape:
        raise ValueError(f"pred {pred.shape} ≠ target {target.shape}")
    c = pred.shape[-3]
    window = _gaussian_window(window_size, sigma, pred.device)
    window = window.expand(c, 1, window_size, window_size)
    pad = window_size // 2

    mu_p = functional_module.conv2d(pred, window, padding=pad, groups=c)
    mu_t = functional_module.conv2d(target, window, padding=pad, groups=c)
    mu_p2 = mu_p * mu_p
    mu_t2 = mu_t * mu_t
    mu_pt = mu_p * mu_t

    sigma_p2 = functional_module.conv2d(pred * pred, window, padding=pad, groups=c) - mu_p2
    sigma_t2 = functional_module.conv2d(target * target, window, padding=pad, groups=c) - mu_t2
    sigma_pt = functional_module.conv2d(pred * target, window, padding=pad, groups=c) - mu_pt

    c1 = 0.01**2
    c2 = 0.03**2
    num = (2 * mu_pt + c1) * (2 * sigma_pt + c2)
    den = (mu_p2 + mu_t2 + c1) * (sigma_p2 + sigma_t2 + c2)
    return (num / den).mean()


def depth_l1_loss(pred_depth: Any, target_depth: Any, valid_mask: Any | None = None) -> Any:
    """L1 sur la depth — masque optionnel pour ignorer les pixels invalides."""
    import torch

    diff = torch.abs(pred_depth - target_depth)
    if valid_mask is not None:
        diff = diff * valid_mask
        return diff.sum() / (valid_mask.sum() + 1e-9)
    return diff.mean()


def combined_loss(
    rendered: torch.Tensor,
    target: torch.Tensor,
    *,
    lambda_ssim: float,
    rendered_depth: torch.Tensor | None = None,
    target_depth: torch.Tensor | None = None,
    lambda_depth: float = 0.0,
    depth_mask: torch.Tensor | None = None,
) -> torch.Tensor:
    """L = L1 + λ_ssim · (1 - SSIM) + λ_depth · L1_depth (optionnel)."""
    loss = l1_loss(rendered, target)
    if lambda_ssim > 0.0:
        loss = (1.0 - lambda_ssim) * loss + lambda_ssim * (1.0 - ssim(rendered, target))
    if (
        rendered_depth is not None
        and target_depth is not None
        and lambda_depth > 0.0
    ):
        loss = loss + lambda_depth * depth_l1_loss(
            rendered_depth, target_depth, depth_mask
        )
    return loss
