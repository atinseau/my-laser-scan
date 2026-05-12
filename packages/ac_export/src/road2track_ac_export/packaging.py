"""Packaging Content Manager — produit le zip final installable.

Layout d'un track AC pour Content Manager :

    content/tracks/<track_id>/
        ├ ui/
        │   ├ ui_track.json
        │   └ preview.png            (miniature 1024×575)
        ├ ai/
        │   └ fast_lane.ai
        ├ surfaces.ini
        ├ models.ini
        └ track.kn5

CM accepte un zip qui contient `content/tracks/<id>/...` à la racine. On
respecte exactement cette structure.

La miniature est générée procéduralement au POC (PNG gris uniforme avec le
nom du track écrit dessus). Une vraie capture screenshot AC ou Blender
viendra en It. 3.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


@dataclass(frozen=True)
class PackageResult:
    zip_path: Path
    track_id: str
    bytes_size: int


_SLUG_PATTERN = re.compile(r"[^a-z0-9_]+")


def slugify_track_id(track_name: str) -> str:
    """Convertit un nom affiché en ID safe pour le filesystem AC."""
    slug = _SLUG_PATTERN.sub("_", track_name.lower()).strip("_")
    return slug or "road2track_custom"


def render_placeholder_preview(
    output_path: Path,
    *,
    track_name: str,
    width: int = 1024,
    height: int = 575,
) -> Path:
    """Génère une miniature placeholder grise avec le nom du track."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), color=(60, 60, 70))
    draw = ImageDraw.Draw(img)
    text = track_name[:60]
    # Position simple, font par défaut (peut être petit, OK pour POC).
    text_bbox = draw.textbbox((0, 0), text)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    draw.text(
        ((width - text_w) // 2, (height - text_h) // 2),
        text,
        fill=(200, 200, 210),
    )
    img.save(output_path, format="PNG", optimize=True)
    return output_path


def build_content_manager_package(
    output_zip_path: Path,
    *,
    track_name: str,
    surfaces_ini: Path,
    models_ini: Path,
    ui_track_json: Path,
    kn5: Path,
    fast_lane_ai: Path,
    preview: Path | None = None,
) -> PackageResult:
    """Empaquette un track dans un zip Content Manager valide.

    Args:
        output_zip_path : chemin du zip à produire.
        track_name : nom affiché par CM (sert aussi à générer le track_id).
        surfaces_ini / models_ini / ui_track_json / kn5 / fast_lane_ai : chemins locaux.
        preview : miniature optionnelle ; générée si None.

    Returns:
        PackageResult avec le zip + track_id + taille.
    """
    track_id = slugify_track_id(track_name)
    output_zip_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_preview: Path | None = None
    if preview is None:
        tmp_preview = output_zip_path.parent / f"_preview_{track_id}.png"
        render_placeholder_preview(tmp_preview, track_name=track_name)
        preview = tmp_preview

    base = f"content/tracks/{track_id}"
    files_map: list[tuple[Path, str]] = [
        (surfaces_ini, f"{base}/surfaces.ini"),
        (models_ini, f"{base}/models.ini"),
        (ui_track_json, f"{base}/ui/ui_track.json"),
        (preview, f"{base}/ui/preview.png"),
        (kn5, f"{base}/track.kn5"),
        (fast_lane_ai, f"{base}/ai/fast_lane.ai"),
    ]
    with zipfile.ZipFile(
        output_zip_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        for src, arcname in files_map:
            if not src.is_file():
                raise FileNotFoundError(f"input introuvable pour le package : {src}")
            zf.write(src, arcname=arcname)

    if tmp_preview is not None and tmp_preview.is_file():
        tmp_preview.unlink()

    return PackageResult(
        zip_path=output_zip_path,
        track_id=track_id,
        bytes_size=output_zip_path.stat().st_size,
    )
