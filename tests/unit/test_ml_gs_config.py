"""Tests sur la config d'entraînement Gaussian Splatting."""

from __future__ import annotations

import pytest
from road2track_ml.gs import GSTrainConfig


def test_gs_train_config_defaults_match_spec() -> None:
    """Les valeurs par défaut doivent correspondre au tableau de specs §3.3."""
    config = GSTrainConfig()
    assert config.n_iterations == 30_000
    assert config.sh_degree == 3
    assert config.random_init is False
    assert config.position_lr_init == 1.6e-4
    assert config.position_lr_final == 1.6e-6
    assert config.densify_interval == 100
    assert config.densify_until_iter == 15_000
    assert config.lambda_ssim == 0.2
    assert config.use_fp16 is True
    assert config.checkpoint_every == 5_000
    assert config.schema_version == 1


def test_gs_train_config_position_lr_decay_endpoints() -> None:
    config = GSTrainConfig()
    assert config.position_lr_at(0) == pytest.approx(config.position_lr_init)
    assert config.position_lr_at(config.n_iterations) == pytest.approx(
        config.position_lr_final
    )


def test_gs_train_config_position_lr_decay_monotonic() -> None:
    config = GSTrainConfig()
    prev = float("inf")
    for step in (0, 1_000, 5_000, 15_000, 30_000):
        lr = config.position_lr_at(step)
        assert lr <= prev
        prev = lr


def test_gs_train_config_frozen() -> None:
    from pydantic import ValidationError

    config = GSTrainConfig()
    with pytest.raises(ValidationError):
        config.n_iterations = 100  # type: ignore[misc]


def test_gs_train_config_validation_positive_lr() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GSTrainConfig(position_lr_init=-1.0)
