"""Export PLY au format Gaussian Splatting (3DGS / gsplat).

Format binary little-endian, header type des champs alignés avec
l'écosystème (Inria 3DGS, gsplat, supersplat) :

    x, y, z, nx, ny, nz                     (positions + normals fictifs)
    f_dc_0, f_dc_1, f_dc_2                  (SH DC = 3 floats par gaussienne)
    f_rest_0 ... f_rest_{3*(sh+1)^2 - 3 - 1} (SH rest)
    opacity                                  (1 float — logits, pas sigmoid)
    scale_0, scale_1, scale_2                (log-scale)
    rot_0, rot_1, rot_2, rot_3               (quaternion wxyz)

Ce format est lisible directement par les viewers (Polycam Viewer, etc.).
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


def _sh_rest_count(sh_degree: int) -> int:
    return 3 * ((sh_degree + 1) ** 2 - 1)


def save_gaussian_splat_ply(
    path: Path,
    *,
    means: NDArray[np.float32],
    sh_dc: NDArray[np.float32],
    sh_rest: NDArray[np.float32],
    opacities_logit: NDArray[np.float32],
    scales_log: NDArray[np.float32],
    quats_wxyz: NDArray[np.float32],
    sh_degree: int,
) -> int:
    """Sérialise un splat .ply binary little-endian. Retourne le nombre de bytes écrits."""
    n = means.shape[0]
    if means.shape != (n, 3):
        raise ValueError(f"means must be (N, 3); got {means.shape}")
    if sh_dc.shape != (n, 3):
        raise ValueError(f"sh_dc must be (N, 3); got {sh_dc.shape}")
    expected_rest = _sh_rest_count(sh_degree)
    if sh_rest.shape != (n, expected_rest):
        raise ValueError(
            f"sh_rest must be (N, {expected_rest}) for sh_degree={sh_degree}; "
            f"got {sh_rest.shape}"
        )
    if opacities_logit.shape != (n,):
        raise ValueError(f"opacities_logit must be (N,); got {opacities_logit.shape}")
    if scales_log.shape != (n, 3):
        raise ValueError(f"scales_log must be (N, 3); got {scales_log.shape}")
    if quats_wxyz.shape != (n, 4):
        raise ValueError(f"quats_wxyz must be (N, 4); got {quats_wxyz.shape}")

    path.parent.mkdir(parents=True, exist_ok=True)
    header_lines = [
        "ply",
        "format binary_little_endian 1.0",
        f"element vertex {n}",
        "property float x",
        "property float y",
        "property float z",
        "property float nx",
        "property float ny",
        "property float nz",
        "property float f_dc_0",
        "property float f_dc_1",
        "property float f_dc_2",
    ]
    header_lines += [f"property float f_rest_{i}" for i in range(expected_rest)]
    header_lines += [
        "property float opacity",
        "property float scale_0",
        "property float scale_1",
        "property float scale_2",
        "property float rot_0",
        "property float rot_1",
        "property float rot_2",
        "property float rot_3",
        "end_header",
        "",
    ]
    header = ("\n".join(header_lines)).encode("ascii")

    zeros_normals = np.zeros((n, 3), dtype=np.float32)
    payload = np.concatenate(
        [
            means.astype(np.float32),
            zeros_normals,
            sh_dc.astype(np.float32),
            sh_rest.astype(np.float32),
            opacities_logit.astype(np.float32).reshape(n, 1),
            scales_log.astype(np.float32),
            quats_wxyz.astype(np.float32),
        ],
        axis=1,
    )
    body = payload.astype("<f4").tobytes()

    with path.open("wb") as f:
        f.write(header)
        f.write(body)
    return len(header) + len(body)


def read_gaussian_splat_ply(path: Path) -> dict[str, NDArray[np.float32]]:
    """Relit un fichier .ply écrit par `save_gaussian_splat_ply` (pour tests).

    Retourne un dict avec les mêmes clés que les arguments d'écriture.
    """
    with path.open("rb") as f:
        header_bytes = bytearray()
        while not header_bytes.endswith(b"end_header\n"):
            chunk = f.read(1)
            if not chunk:
                raise ValueError(f"PLY corrompu — pas de end_header dans {path}")
            header_bytes.extend(chunk)
        body = f.read()

    header = header_bytes.decode("ascii").splitlines()
    n_line = next(line for line in header if line.startswith("element vertex"))
    n = int(n_line.split()[-1])
    props = [line.split()[-1] for line in header if line.startswith("property")]
    n_floats_per_vertex = len(props)
    expected_bytes = n * n_floats_per_vertex * 4
    if len(body) < expected_bytes:
        raise ValueError(
            f"PLY tronqué : attendu {expected_bytes} bytes, lu {len(body)}"
        )
    flat = struct.unpack(f"<{n * n_floats_per_vertex}f", body[:expected_bytes])
    arr = np.asarray(flat, dtype=np.float32).reshape(n, n_floats_per_vertex)

    cols = {name: i for i, name in enumerate(props)}
    rest_cols = sorted(
        (i for name, i in cols.items() if name.startswith("f_rest_")),
        key=lambda i: int(props[i].split("_")[-1]),
    )
    return {
        "means": arr[:, [cols["x"], cols["y"], cols["z"]]],
        "sh_dc": arr[:, [cols["f_dc_0"], cols["f_dc_1"], cols["f_dc_2"]]],
        "sh_rest": arr[:, rest_cols] if rest_cols else np.zeros((n, 0), dtype=np.float32),
        "opacities_logit": arr[:, cols["opacity"]],
        "scales_log": arr[:, [cols["scale_0"], cols["scale_1"], cols["scale_2"]]],
        "quats_wxyz": arr[
            :, [cols["rot_0"], cols["rot_1"], cols["rot_2"], cols["rot_3"]]
        ],
    }
