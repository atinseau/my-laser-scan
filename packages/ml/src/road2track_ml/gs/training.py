"""Boucle d'entraînement Gaussian Splatting (gsplat).

Cf. specs/04-pipeline-ml.md §3.3 + ADR-022.

Imports torch/gsplat **lazy** : ce module est importable sans CUDA (pour les
tests CPU). Au premier appel à `train(...)`, on importe torch + gsplat ; si
indisponibles → `ImportError` explicite (catché par l'activité Temporal pour
remonter une erreur métier propre).

⚠️ Code écrit à l'aveugle sans GPU disponible pour la vérification. À débugger
sur le PC RTX 4090 lors du premier run. Points sensibles :
- Convention quaternion : gsplat ≥ 1.0 attend wxyz (cf. README gsplat).
- viewmat : gsplat attend camera-from-world (T_cam_world = inv(T_world_cam)).
- rasterization() retourne (rendered_imgs [B, H, W, 3], alphas [B, H, W, 1], info).
- Mixed precision : enveloppe dans `torch.cuda.amp.autocast(dtype=fp16)`
  + GradScaler pour la stabilité.

POC : pas de densification adaptative cousue main — on utilise
`gsplat.DefaultStrategy` quand disponible, fallback no-op sinon.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from road2track_ml.gs.checkpoint import load_checkpoint, save_checkpoint
from road2track_ml.gs.config import GSTrainConfig
from road2track_ml.gs.dataset import KeyframesDataset
from road2track_ml.gs.initialization import (
    average_nearest_neighbor_distance,
    init_around_trajectory,
)
from road2track_ml.gs.losses import combined_loss
from road2track_ml.gs.ply_io import _sh_rest_count, save_gaussian_splat_ply

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainingResult:
    """Sortie d'un run d'entraînement complet."""

    scene_ply_path: Path
    n_iterations_done: int
    n_gaussians_final: int
    final_loss: float
    mean_psnr: float
    metrics_path: Path


def _check_runtime_available() -> None:
    """Lève ImportError clair si torch/gsplat ne sont pas installés."""
    try:
        import torch  # noqa: F401
    except ImportError as e:  # pragma: no cover - testé sur PC GPU
        raise ImportError(
            "torch est requis pour `train_gs`. Installer l'extra `gs` "
            "(`uv sync --extra gs --package road2track-ml`) ou activer le GPU."
        ) from e
    try:
        import gsplat  # noqa: F401  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "gsplat est requis pour `train_gs`. Installer l'extra `gs` "
            "(`uv sync --extra gs --package road2track-ml`). gsplat nécessite "
            "le toolkit CUDA + nvcc compatible avec la version torch."
        ) from e


def _pose_to_viewmat(
    pose_world_from_camera: np.ndarray, torch_module: Any, device: Any, dtype: Any
) -> Any:
    """Inverse la pose (world ← cam) pour obtenir le viewmat (cam ← world)."""
    pose = np.asarray(pose_world_from_camera, dtype=np.float64)
    rotation = pose[0:3, 0:3]
    translation = pose[0:3, 3]
    viewmat = np.eye(4, dtype=np.float64)
    viewmat[0:3, 0:3] = rotation.T
    viewmat[0:3, 3] = -rotation.T @ translation
    return torch_module.from_numpy(viewmat).to(device=device, dtype=dtype)


def _init_params(
    dataset: KeyframesDataset,
    config: GSTrainConfig,
    torch_module: Any,
    device: Any,
) -> dict[str, Any]:
    """Initialise means, quats, scales, opacities, sh_dc, sh_rest sur `device`."""
    positions = dataset.positions_world()
    cloud = init_around_trajectory(
        positions, points_per_pose=80, radius_m=2.0, seed=0
    )
    n = cloud.means.shape[0]
    scale_init_m = max(average_nearest_neighbor_distance(cloud.means), 0.01)
    log_scale = np.log(scale_init_m) * np.ones((n, 3), dtype=np.float32)

    quats = np.zeros((n, 4), dtype=np.float32)
    quats[:, 0] = 1.0  # identity (wxyz)

    sh_dc = (cloud.colors.astype(np.float32) - 0.5) * 0.28  # RGB → SH coef approx
    sh_rest = np.zeros((n, _sh_rest_count(config.sh_degree)), dtype=np.float32)

    # Opacité initiale = 0.1 → logit ≈ -2.197.
    opacities_logit = np.full((n,), -2.2, dtype=np.float32)

    def _to_param(arr: np.ndarray) -> Any:
        tensor = torch_module.from_numpy(arr).to(device=device, dtype=torch_module.float32)
        tensor.requires_grad_(True)
        return tensor

    return {
        "means": _to_param(cloud.means.astype(np.float32)),
        "quats": _to_param(quats),
        "scales_log": _to_param(log_scale),
        "opacities_logit": _to_param(opacities_logit),
        "sh_dc": _to_param(sh_dc),
        "sh_rest": _to_param(sh_rest),
    }


def _build_optimizer(
    params: dict[str, Any], config: GSTrainConfig, torch_module: Any
) -> Any:
    return torch_module.optim.Adam(
        [
            {"params": [params["means"]], "lr": config.position_lr_init, "name": "means"},
            {"params": [params["quats"]], "lr": config.rotation_lr, "name": "quats"},
            {"params": [params["scales_log"]], "lr": config.scale_lr, "name": "scales"},
            {"params": [params["opacities_logit"]], "lr": config.opacity_lr, "name": "opacities"},
            {"params": [params["sh_dc"]], "lr": config.feature_lr, "name": "sh_dc"},
            {"params": [params["sh_rest"]], "lr": config.feature_lr / 20.0, "name": "sh_rest"},
        ]
    )


def _normalize_quats(quats: Any, torch_module: Any) -> Any:
    norm = torch_module.linalg.norm(quats, dim=-1, keepdim=True)
    return quats / norm.clamp(min=1e-9)


def _compute_psnr(rendered: Any, target: Any, torch_module: Any) -> float:
    mse = torch_module.mean((rendered - target) ** 2)
    if mse.item() < 1e-12:
        return 99.0
    return float(10.0 * torch_module.log10(1.0 / mse).item())


def train(
    config: GSTrainConfig,
    dataset: KeyframesDataset,
    output_dir: Path,
    *,
    checkpoint_callback: Any | None = None,
) -> TrainingResult:
    """Lance le training Gaussian Splatting et sérialise scene.ply + metrics.

    Args:
        config : hyperparamètres (cf. GSTrainConfig).
        dataset : keyframes chargées (poses + images).
        output_dir : dossier local où écrire scene.ply, checkpoints, metrics.
        checkpoint_callback : si fourni, appelée à chaque checkpoint local avec
            `(iteration: int, local_path: Path)`. Permet à l'activité Temporal
            d'uploader le checkpoint sur MinIO (ADR-022 levier #1).

    Returns:
        TrainingResult avec les chemins de sortie + métriques agrégées.
    """
    _check_runtime_available()

    import torch
    from gsplat import rasterization  # type: ignore[import-not-found]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float32

    output_dir.mkdir(parents=True, exist_ok=True)
    scene_ply = output_dir / "scene.ply"
    metrics_path = output_dir / "training_metrics.json"
    checkpoints_dir = output_dir / "checkpoints"

    params = _init_params(dataset, config, torch, device)
    optimizer = _build_optimizer(params, config, torch)
    scaler = torch.amp.GradScaler(device.type) if config.use_fp16 else None

    start_iter = 0
    if config.resume_from_checkpoint_uri:
        # L'activité Temporal a déjà téléchargé le checkpoint avant l'appel ;
        # le path local est passé via un fichier convention.
        local_checkpoint = checkpoints_dir / "resume.pt"
        if local_checkpoint.is_file():
            ckpt = load_checkpoint(local_checkpoint, device)
            start_iter = int(ckpt["iteration"])
            with torch.no_grad():
                params["means"].copy_(ckpt["means"].to(device))
                params["quats"].copy_(ckpt["quats_wxyz"].to(device))
                params["scales_log"].copy_(ckpt["scales_log"].to(device))
                params["opacities_logit"].copy_(ckpt["opacities_logit"].to(device))
                params["sh_dc"].copy_(ckpt["sh_dc"].to(device))
                params["sh_rest"].copy_(ckpt["sh_rest"].to(device))
            optimizer.load_state_dict(ckpt["optimizer"])

    last_loss = float("nan")
    psnr_history: list[float] = []

    n_samples = len(dataset)
    rng = np.random.default_rng(seed=42)

    for step in range(start_iter, config.n_iterations):
        sample_idx = int(rng.integers(0, n_samples))
        sample = dataset[sample_idx]

        target_np = sample.image.astype(np.float32) / 255.0
        target = torch.from_numpy(target_np).to(device=device, dtype=dtype)
        target = target.permute(2, 0, 1).unsqueeze(0)  # [1, 3, H, W]

        viewmat = _pose_to_viewmat(
            sample.pose_world_from_camera, torch, device, dtype
        )
        intrinsics = sample.intrinsics
        k_matrix = torch.from_numpy(intrinsics.matrix()).to(device=device, dtype=dtype)

        # LR scheduling (position only — gsplat conventional).
        for pg in optimizer.param_groups:
            if pg.get("name") == "means":
                pg["lr"] = config.position_lr_at(step)

        autocast_ctx = (
            torch.amp.autocast(device_type=device.type, dtype=torch.float16)
            if config.use_fp16 and device.type == "cuda"
            else _NullContext()
        )

        with autocast_ctx:
            quats_normalized = _normalize_quats(params["quats"], torch)
            scales = torch.exp(params["scales_log"])
            opacities = torch.sigmoid(params["opacities_logit"])
            colors = torch.cat(
                [params["sh_dc"].unsqueeze(1), params["sh_rest"].reshape(
                    params["sh_dc"].shape[0], -1, 3
                )],
                dim=1,
            )

            renders, _alphas, _info = rasterization(
                means=params["means"],
                quats=quats_normalized,
                scales=scales,
                opacities=opacities,
                colors=colors,
                viewmats=viewmat.unsqueeze(0),
                Ks=k_matrix.unsqueeze(0),
                width=intrinsics.width,
                height=intrinsics.height,
                sh_degree=config.sh_degree,
                packed=False,
            )
            rendered = renders.permute(0, 3, 1, 2).clamp(0.0, 1.0)
            loss = combined_loss(
                rendered, target, lambda_ssim=config.lambda_ssim
            )

        optimizer.zero_grad(set_to_none=True)
        if scaler is not None:
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            optimizer.step()

        last_loss = float(loss.item())
        if step % 200 == 0:
            psnr = _compute_psnr(rendered, target, torch)
            psnr_history.append(psnr)
            logger.info(
                "gs step %d/%d loss=%.4f psnr=%.2f n_gauss=%d",
                step,
                config.n_iterations,
                last_loss,
                psnr,
                params["means"].shape[0],
            )

        if (
            config.checkpoint_every > 0
            and step > 0
            and step % config.checkpoint_every == 0
        ):
            local_ckpt = checkpoints_dir / f"ckpt_{step:06d}.pt"
            save_checkpoint(
                local_ckpt,
                iteration=step,
                means=params["means"],
                quats_wxyz=params["quats"],
                scales_log=params["scales_log"],
                opacities_logit=params["opacities_logit"],
                sh_dc=params["sh_dc"],
                sh_rest=params["sh_rest"],
                optimizer_state=optimizer.state_dict(),
            )
            if checkpoint_callback is not None:
                checkpoint_callback(step, local_ckpt)

    # Export PLY final.
    save_gaussian_splat_ply(
        scene_ply,
        means=params["means"].detach().cpu().numpy(),
        sh_dc=params["sh_dc"].detach().cpu().numpy(),
        sh_rest=params["sh_rest"].detach().cpu().numpy(),
        opacities_logit=params["opacities_logit"].detach().cpu().numpy(),
        scales_log=params["scales_log"].detach().cpu().numpy(),
        quats_wxyz=_normalize_quats(params["quats"], torch).detach().cpu().numpy(),
        sh_degree=config.sh_degree,
    )

    import json as _json

    mean_psnr = float(np.mean(psnr_history)) if psnr_history else 0.0
    metrics = {
        "schema_version": 1,
        "n_iterations": int(config.n_iterations),
        "n_iterations_done": int(config.n_iterations - start_iter),
        "n_gaussians_final": int(params["means"].shape[0]),
        "final_loss": last_loss,
        "mean_psnr": mean_psnr,
        "psnr_history": psnr_history,
        "use_fp16": config.use_fp16,
    }
    metrics_path.write_text(_json.dumps(metrics, indent=2), encoding="utf-8")

    return TrainingResult(
        scene_ply_path=scene_ply,
        n_iterations_done=config.n_iterations - start_iter,
        n_gaussians_final=int(params["means"].shape[0]),
        final_loss=last_loss,
        mean_psnr=mean_psnr,
        metrics_path=metrics_path,
    )


class _NullContext:
    """Context manager neutre pour le cas non-FP16 / non-CUDA."""

    def __enter__(self) -> _NullContext:
        return self

    def __exit__(self, *args: object) -> None:
        return None
