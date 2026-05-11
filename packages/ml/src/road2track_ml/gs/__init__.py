"""Gaussian Splatting (gsplat) — entraînement + I/O scene.ply.

Cf. specs/04-pipeline-ml.md §3.3 et ADR-022.
"""

from road2track_ml.gs.config import GSTrainConfig
from road2track_ml.gs.dataset import KeyframeSample, KeyframesDataset
from road2track_ml.gs.initialization import (
    InitialPointCloud,
    average_nearest_neighbor_distance,
    init_around_trajectory,
)
from road2track_ml.gs.intrinsics import (
    DEFAULT_IPHONE_14_PRO,
    CameraIntrinsics,
    load_intrinsics_or_default,
    parse_record3d_metadata,
)
from road2track_ml.gs.ply_io import (
    read_gaussian_splat_ply,
    save_gaussian_splat_ply,
)
from road2track_ml.gs.training import TrainingResult, train

__all__ = [
    "DEFAULT_IPHONE_14_PRO",
    "CameraIntrinsics",
    "GSTrainConfig",
    "InitialPointCloud",
    "KeyframeSample",
    "KeyframesDataset",
    "TrainingResult",
    "average_nearest_neighbor_distance",
    "init_around_trajectory",
    "load_intrinsics_or_default",
    "parse_record3d_metadata",
    "read_gaussian_splat_ply",
    "save_gaussian_splat_ply",
    "train",
]
