"""Camera intrinsics — extraction depuis Record3D + défauts iPhone 14 Pro.

Format Record3D `metadata.json` (observé sur Record3D Pro ≥ 1.10) :
    {
      "fps": 30,
      "w": 1920,
      "h": 1440,
      "K": [fx, 0, cx, 0, fy, cy, 0, 0, 1]  # row-major
    }

Si `metadata.json` est absent ou tronqué, on retombe sur les valeurs typiques
de l'iPhone 14 Pro (lentille principale 26 mm équivalent, sensor ~5.7 × 4.3 mm).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int

    def matrix(self) -> NDArray[np.float64]:
        return np.array(
            [
                [self.fx, 0.0, self.cx],
                [0.0, self.fy, self.cy],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

    def scale_to(self, width: int, height: int) -> CameraIntrinsics:
        """Renvoie les intrinsics adaptés à une résolution différente."""
        sx = width / self.width
        sy = height / self.height
        return CameraIntrinsics(
            fx=self.fx * sx,
            fy=self.fy * sy,
            cx=self.cx * sx,
            cy=self.cy * sy,
            width=width,
            height=height,
        )


DEFAULT_IPHONE_14_PRO = CameraIntrinsics(
    fx=1500.0,
    fy=1500.0,
    cx=960.0,
    cy=720.0,
    width=1920,
    height=1440,
)


def parse_record3d_metadata(path: Path) -> CameraIntrinsics:
    """Parse `record3d/metadata.json` ; lève FileNotFoundError si absent.

    Tolérant aux variantes : `K` peut être 3×3 imbriqué ou flat 9-list.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    width = int(data.get("w", data.get("width", 0)))
    height = int(data.get("h", data.get("height", 0)))
    k_raw = data.get("K")
    if k_raw is None or width == 0 or height == 0:
        raise ValueError(
            f"metadata.json incomplet : K/w/h manquants dans {path}"
        )
    k = np.asarray(k_raw, dtype=float).reshape(3, 3)
    return CameraIntrinsics(
        fx=float(k[0, 0]),
        fy=float(k[1, 1]),
        cx=float(k[0, 2]),
        cy=float(k[1, 2]),
        width=width,
        height=height,
    )


def load_intrinsics_or_default(record3d_dir: Path) -> CameraIntrinsics:
    """Cherche `metadata.json` dans `record3d_dir` ; fallback iPhone 14 Pro."""
    metadata = record3d_dir / "metadata.json"
    if metadata.is_file():
        try:
            return parse_record3d_metadata(metadata)
        except (ValueError, json.JSONDecodeError, KeyError):
            return DEFAULT_IPHONE_14_PRO
    return DEFAULT_IPHONE_14_PRO
