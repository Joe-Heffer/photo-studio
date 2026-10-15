"""Finalize a result saved from the IOPaint browser UI.

The UI re-encodes the whole photo on every save and can leave a stale EXIF orientation
tag. This finds the areas you actually retouched (by diffing against the original),
pastes only those onto the untouched original, and restores EXIF + ICC metadata.

Example:
  uv run tools/finalize.py input/IMG_1.jpg output/IMG_1.jpg      # -> output/IMG_1_final.jpg
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from common import MASK_DIR, check_output_target, default_output, load_image, save_jpeg
from remove import feather_alpha


def load_edited_like(path: Path, ref: np.ndarray) -> np.ndarray:
    """Load the UI output, picking whichever orientation (as-stored or EXIF-rotated)
    matches the original; IOPaint saves upright pixels but may keep the old tag."""
    raw = Image.open(path)
    raw.load()
    candidates = [raw.convert("RGB"), ImageOps.exif_transpose(raw).convert("RGB")]
    best, best_err = None, None
    for c in candidates:
        a = np.asarray(c)
        if a.shape != ref.shape:
            continue
        err = float(np.abs(a.astype(np.int16) - ref.astype(np.int16)).mean())
        if best_err is None or err < best_err:
            best, best_err = a, err
    if best is None:
        raise SystemExit(f"{path} is {raw.size[0]}x{raw.size[1]}; it doesn't match the original's size.")
    return best


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("original", type=Path)
    ap.add_argument("edited", type=Path, help="file saved by the IOPaint UI")
    ap.add_argument("-o", "--output", type=Path, help="default: output/<original stem>_final.jpg")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--threshold", type=int, default=12, help="per-channel difference counted as an edit (default 12)")
    ap.add_argument("--grow", type=int, default=6, help="expand detected edit areas by N px (default 6)")
    ap.add_argument("--min-area", type=int, default=100, help="ignore changed specks smaller than N px (default 100)")
    args = ap.parse_args()

    out = args.output or default_output(args.original, "_final")
    check_output_target(out, args.original, args.overwrite)

    img, meta = load_image(args.original)
    orig = np.asarray(img)
    edited = load_edited_like(args.edited, orig)

    diff = np.abs(edited.astype(np.int16) - orig.astype(np.int16)).max(axis=2)
    changed = (diff > args.threshold).astype(np.uint8)
    # Drop isolated re-encoding noise, join nearby strokes, then pad the edges.
    changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(changed)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= args.min_area
    changed = keep[labels].astype(np.uint8)
    k = 2 * args.grow + 1
    changed = cv2.morphologyEx(changed, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    changed = cv2.dilate(changed, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0

    if not changed.any():
        raise SystemExit("No retouched areas found (try a lower --threshold). Nothing written.")

    alpha = feather_alpha(changed, 3)[:, :, None]
    result = alpha * edited.astype(np.float32) + (1 - alpha) * orig.astype(np.float32)
    save_jpeg(Image.fromarray(np.clip(np.rint(result), 0, 255).astype(np.uint8)), out, meta)

    mask_out = MASK_DIR / f"{args.original.stem}_ui_detected.png"
    mask_out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(changed.astype(np.uint8) * 255).save(mask_out)
    n, _, stats, _ = cv2.connectedComponentsWithStats(changed.astype(np.uint8))
    print(f"Found {n - 1} retouched area(s), {100 * changed.mean():.3f}% of the image:")
    for x, y, w, h, _ in stats[1:]:
        print(f"  x={x} y={y} {w}x{h}")
    print(f"Wrote {out} (detected mask: {mask_out})")


if __name__ == "__main__":
    main()
