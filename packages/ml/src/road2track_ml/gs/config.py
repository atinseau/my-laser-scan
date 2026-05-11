"""Configuration de l'entraînement Gaussian Splatting (gsplat).

Cf. specs/04-pipeline-ml.md §3.3 + ADR-022.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GSTrainConfig(BaseModel):
    """Hyperparamètres d'entraînement Gaussian Splatting.

    Valeurs par défaut alignées sur le tableau de specs/04-pipeline-ml.md §3.3.
    Toute modification ici doit être traçable à un ADR (cf. ADR-022 pour FP16
    et checkpoint).
    """

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1

    # ------------------------------------------------------------------ Training
    n_iterations: int = Field(default=30_000, ge=1)
    sh_degree: int = Field(default=3, ge=0, le=4)
    random_init: bool = Field(
        default=False,
        description="Si False, initialise depuis le nuage LiDAR (cf. spec §3.3).",
    )

    # ------------------------------------------------------------------ Learning rates
    position_lr_init: float = Field(default=1.6e-4, gt=0.0)
    position_lr_final: float = Field(default=1.6e-6, gt=0.0)
    feature_lr: float = Field(default=2.5e-3, gt=0.0)
    opacity_lr: float = Field(default=5e-2, gt=0.0)
    scale_lr: float = Field(default=5e-3, gt=0.0)
    rotation_lr: float = Field(default=1e-3, gt=0.0)

    # ------------------------------------------------------------------ Densification
    densify_from_iter: int = Field(default=500, ge=0)
    densify_until_iter: int = Field(default=15_000, ge=0)
    densify_interval: int = Field(default=100, ge=1)
    densify_grad_threshold: float = Field(default=2e-4, gt=0.0)
    opacity_reset_interval: int = Field(default=3_000, ge=1)

    # ------------------------------------------------------------------ Loss
    lambda_ssim: float = Field(default=0.2, ge=0.0, le=1.0)
    lambda_depth: float = Field(
        default=0.1,
        ge=0.0,
        description="Coefficient de la supervision depth LiDAR (0 = désactivée).",
    )

    # ------------------------------------------------------------------ Optimisation coût (ADR-022)
    use_fp16: bool = Field(
        default=True,
        description="Mixed precision FP16 (ADR-022 levier #2, +30 à +50% vitesse).",
    )
    checkpoint_every: int = Field(
        default=5_000,
        ge=0,
        description="Sauvegarde sur MinIO. 0 = désactivé. ADR-022 levier #1.",
    )
    resume_from_checkpoint_uri: str | None = Field(
        default=None,
        description="URI S3 d'un checkpoint à reprendre (multi-passe ou éviction spot).",
    )

    # ------------------------------------------------------------------ Constraints route
    max_distance_from_trajectory_m: float = Field(
        default=10.0,
        gt=0.0,
        description="Prior route : on prune les gaussiennes plus loin que ça de la trajectoire.",
    )

    def position_lr_at(self, step: int) -> float:
        """Decay exponentiel position_lr_init → position_lr_final sur n_iterations."""
        if self.n_iterations <= 1:
            return self.position_lr_init
        progress = min(max(step / self.n_iterations, 0.0), 1.0)
        ratio = self.position_lr_final / self.position_lr_init
        return self.position_lr_init * (ratio**progress)
