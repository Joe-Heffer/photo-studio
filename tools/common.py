"""Shared helpers: loading/saving JPEGs without losing metadata, paths, coordinates.

Images are always handled *upright*: EXIF orientation is applied on load, and the
saved file gets Orientation=1, so every tool and every coordinate refers to the
picture as it is displayed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
MASK_DIR = ROOT / "masks"
PREVIEW_DIR = ROOT / "previews"

ORIENTATION_TAG = 0x0112
JPEG_QUALITY = 95


@dataclass
class Meta:
    exif: bytes | None
    icc_profile: bytes | None


def load_image(path: str | Path) -> tuple[Image.Image, Meta]:
    """Load an image upright as RGB, along with its EXIF (orientation reset) and ICC profile."""
    img = Image.open(path)
    img.load()
    icc = img.info.get("icc_profile")
    # Rotate first: getexif() is cached, so resetting the tag beforehand would stop the rotation.
    upright = ImageOps.exif_transpose(img).convert("RGB")
    exif = img.getexif()
    if exif.get(ORIENTATION_TAG, 1) != 1:
        exif[ORIENTATION_TAG] = 1
    meta = Meta(exif=exif.tobytes() if len(exif) else None, icc_profile=icc)
    return upright, meta


def load_mask(path: str | Path, size: tuple[int, int] | None = None) -> np.ndarray:
    """Load a mask as a bool array (True = area to repaint)."""
    m = Image.open(path).convert("L")
    if size and m.size != size:
        raise SystemExit(f"Mask {path} is {m.size[0]}x{m.size[1]}, image is {size[0]}x{size[1]}")
    return np.asarray(m) > 127


def save_jpeg(img: Image.Image, path: str | Path, meta: Meta) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"quality": JPEG_QUALITY, "subsampling": 0, "optimize": True}
    if meta.exif:
        kwargs["exif"] = meta.exif
    if meta.icc_profile:
        kwargs["icc_profile"] = meta.icc_profile
    img.save(path, "JPEG", **kwargs)
    return path


def is_inside(path: Path, folder: Path) -> bool:
    return path.resolve().is_relative_to(folder.resolve())


def unique_path(path: Path) -> Path:
    """Return path, or path with _2, _3... appended if it already exists."""
    if not path.exists():
        return path
    n = 2
    while (p := path.with_name(f"{path.stem}_{n}{path.suffix}")).exists():
        n += 1
    return p


def default_output(image_path: Path, suffix: str = "_edited") -> Path:
    stem = image_path.stem
    if is_inside(image_path, OUTPUT_DIR):
        # Already an edited copy: keep building on the same name.
        return unique_path(OUTPUT_DIR / f"{stem}.jpg")
    return unique_path(OUTPUT_DIR / f"{stem}{suffix}.jpg")


def check_output_target(out: Path, image_path: Path, overwrite: bool) -> None:
    """Refuse to clobber originals; only files inside output/ may be overwritten."""
    if out.exists():
        if not overwrite:
            raise SystemExit(f"{out} exists. Pass --overwrite, or omit -o to get a new name.")
        if not is_inside(out, OUTPUT_DIR):
            raise SystemExit(f"Refusing to overwrite {out}: only files inside {OUTPUT_DIR} may be overwritten.")
    if out.resolve() == image_path.resolve() and not is_inside(out, OUTPUT_DIR):
        raise SystemExit("Refusing to write over the original photo.")


def parse_numbers(spec: str, size: tuple[int, int] | None = None, axes: str = "") -> list[float]:
    """Parse '10,20,30' into numbers. If every value is <= 1 and at least one has a decimal
    point (e.g. '0.25,0.5'), treat them as fractions of the image and scale per axis
    ('x' = width, 'y' = height, 'm' = shorter side)."""
    parts = [v for v in spec.replace(" ", "").split(",") if v]
    vals = [float(v) for v in parts]
    if size and vals and all(0 <= v <= 1 for v in vals) and any("." in v for v in parts):
        w, h = size
        scale = {"x": w, "y": h, "m": min(w, h)}
        vals = [v * scale[axes[i % len(axes)]] for i, v in enumerate(vals)]
    return vals
