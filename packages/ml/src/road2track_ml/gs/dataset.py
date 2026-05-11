"""Dataset Gaussian Splatting : load keyframes JPEG + poses + intrinsics.

Pure Python / NumPy / PIL — pas de torch ici (on rend des arrays NumPy).
La conversion en torch.Tensor se fait dans `training.py` pour permettre les
tests sans CUDA.

Convention de pose (cf. specs/04-pipeline-ml.md §2.2) :
- `pose` = matrice 4×4 `T_world_camera` (world ← camera).
- gsplat attend `viewmat` = `T_camera_world` (inverse). La conversion vit
  dans `training.py`.

Le manifest `keyframes.json` est produit par l'activité `select_keyframes`
(cf. specs/06-modele-donnees.md).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from scipy.spatial.transform import Rotation

from road2track_ml.gs.intrinsics import CameraIntrinsics


def _quat_wxyz_to_matrix(quat_wxyz: NDArray[np.float64]) -> NDArray[np.float64]:
    quat_xyzw = quat_wxyz[[1, 2, 3, 0]]
    return Rotation.from_quat(quat_xyzw).as_matrix()


@dataclass(frozen=True)
class KeyframeSample:
    """Une frame chargée en mémoire : image + pose + intrinsics."""

    idx: int
    image: NDArray[np.uint8]  # (H, W, 3) RGB
    pose_world_from_camera: NDArray[np.float64]  # (4, 4)
    intrinsics: CameraIntrinsics


class KeyframesDataset:
    """Charge à la demande les keyframes depuis un dossier local.

    Layout attendu :
        <dir>/keyframes.json
        <dir>/keyframes/0000.jpg
        <dir>/keyframes/0001.jpg
        ...

    Toutes les images ont les mêmes intrinsics (caméra fixe iPhone).
    """

    def __init__(
        self,
        local_dir: Path,
        intrinsics: CameraIntrinsics,
        manifest_filename: str = "keyframes.json",
    ) -> None:
        self._local_dir = local_dir
        self._intrinsics = intrinsics
        manifest_path = local_dir / manifest_filename
        if not manifest_path.is_file():
            raise FileNotFoundError(
                f"manifest keyframes introuvable : {manifest_path}"
            )
        manifest: dict[str, Any] = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        self._entries: list[dict[str, Any]] = list(manifest.get("keyframes", []))
        if not self._entries:
            raise ValueError(f"manifest {manifest_path} ne contient aucune keyframe")

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def intrinsics(self) -> CameraIntrinsics:
        return self._intrinsics

    def positions_world(self) -> NDArray[np.float64]:
        """Toutes les positions monde des keyframes (utile pour init point cloud)."""
        return np.asarray(
            [entry["pos"] for entry in self._entries], dtype=np.float64
        )

    def __getitem__(self, idx: int) -> KeyframeSample:
        entry = self._entries[idx]
        image_path = self._local_dir / Path(entry["image_key"]).name
        if not image_path.is_file():
            # Tolère un chemin absolu inscrit dans le manifest si jamais.
            image_path = self._local_dir / "keyframes" / Path(entry["image_key"]).name
        with Image.open(image_path) as img:
            image = np.asarray(img.convert("RGB"), dtype=np.uint8)

        pos = np.asarray(entry["pos"], dtype=np.float64)
        quat_wxyz = np.asarray(entry["quat"], dtype=np.float64)
        rotation = _quat_wxyz_to_matrix(quat_wxyz)
        pose = np.eye(4, dtype=np.float64)
        pose[0:3, 0:3] = rotation
        pose[0:3, 3] = pos

        intrinsics = self._intrinsics
        if image.shape[1] != intrinsics.width or image.shape[0] != intrinsics.height:
            intrinsics = intrinsics.scale_to(image.shape[1], image.shape[0])

        return KeyframeSample(
            idx=int(entry.get("idx", idx)),
            image=image,
            pose_world_from_camera=pose,
            intrinsics=intrinsics,
        )
