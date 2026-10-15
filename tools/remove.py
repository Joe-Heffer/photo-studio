"""Remove whatever is under a mask using LaMa inpainting (CPU), at full resolution.

Each masked region is cropped out with surrounding context, inpainted, and blended
back through a feathered edge. Pixels outside the mask come straight from the source,
and EXIF + ICC metadata are kept. Originals are never modified.

Examples:
  uv run tools/remove.py input/IMG_1.jpg masks/IMG_1.png          # -> output/IMG_1_edited.jpg
  uv run tools/remove.py output/IMG_1_edited.jpg masks/IMG_1b.png \\
      -o output/IMG_1_edited.jpg --overwrite                       # stack another edit
"""

from __future__ import annotations

import argparse
import logging
import time
import warnings
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from common import check_output_target, default_output, load_image, load_mask, save_jpeg


def region_boxes(mask: np.ndarray, pad_min: int) -> list[tuple[int, int, int, int]]:
    """Group nearby mask blobs and return padded crop boxes (x1, y1, x2, y2)."""
    h, w = mask.shape
    # Merge blobs that are close together so they share one crop.
    joined = cv2.dilate(mask.astype(np.uint8), np.ones((pad_min, pad_min), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    boxes = []
    for i in range(1, n):
        x, y, bw, bh, _ = stats[i]
        # Shrink back to the real blob extent, then add context: LaMa needs to see
        # surroundings at least about as large as the hole itself.
        sub = mask[y:y + bh, x:x + bw]
        ys, xs = np.nonzero(sub)
        if len(xs) == 0:
            continue
        x1, x2 = x + xs.min(), x + xs.max() + 1
        y1, y2 = y + ys.min(), y + ys.max() + 1
        pad = max(pad_min, int(0.75 * max(x2 - x1, y2 - y1)))
        boxes.append((max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + pad)))
    return boxes


def feather_alpha(mask: np.ndarray, feather: int) -> np.ndarray:
    """Alpha that is 1 everywhere inside the mask and fades to 0 over `feather` px outside it."""
    m = mask.astype(np.float32)
    if feather <= 0:
        return m
    k = 2 * feather + 1
    grown = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    alpha = cv2.GaussianBlur(grown, (0, 0), sigmaX=feather / 2)
    return np.maximum(alpha, m)


def estimate_grain(crop: np.ndarray, known: np.ndarray) -> np.ndarray:
    """Per-channel std of fine sensor noise/grain in the unmasked part of a crop."""
    f = crop.astype(np.float32)
    hp = f - cv2.GaussianBlur(f, (0, 0), 1.5)
    if known.sum() < 1000:
        return np.zeros(3, np.float32)
    return hp[known].std(axis=0)


def inpaint_region(model, config, crop: np.ndarray, cmask: np.ndarray, max_size: int,
                   grain: bool) -> tuple[np.ndarray, float]:
    """Inpaint one crop. Large crops are processed at reduced size (LaMa was trained on
    ~512 px images and smears big holes at full resolution), then upscaled; grain
    lost in the upscale is re-synthesised to match the surroundings."""
    h, w = cmask.shape
    scale = min(1.0, max_size / max(h, w))
    if scale < 1:
        sw, sh = max(8, round(w * scale)), max(8, round(h * scale))
        small = cv2.resize(crop, (sw, sh), interpolation=cv2.INTER_AREA)
        smask = (cv2.resize(cmask, (sw, sh), interpolation=cv2.INTER_AREA) > 0).astype(np.uint8) * 255
        filled = model(small, smask, config)[:, :, ::-1]
        filled = cv2.resize(filled, (w, h), interpolation=cv2.INTER_CUBIC).astype(np.float32)
        if grain:
            std = estimate_grain(crop, cmask == 0)
            noise = np.random.default_rng(0).normal(size=(h, w, 3)).astype(np.float32)
            noise = cv2.GaussianBlur(noise, (0, 0), 0.6)
            noise /= noise.std() + 1e-6
            filled += noise * std
    else:
        filled = model(crop, cmask, config)[:, :, ::-1].astype(np.float32)
    return filled, scale


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("mask", type=Path, help="white = remove; same size as the (upright) image")
    ap.add_argument("-o", "--output", type=Path, help="default: output/<stem>_edited.jpg (never overwrites)")
    ap.add_argument("--overwrite", action="store_true", help="allow replacing an existing file in output/")
    ap.add_argument("--pad", type=int, default=128, help="minimum context around each region in px (default 128)")
    ap.add_argument("--feather", type=int, default=3, help="blend width in px at the mask edge (default 3)")
    ap.add_argument("--max-size", type=int, default=512,
                    help="work at most at this many px per crop side; bigger crops are downscaled for "
                         "inference (default 512). LaMa works best on holes of a few hundred px; raise for sharper fills of mid-size areas in sharp parts of the photo, lower if a fill looks smeared")
    ap.add_argument("--no-grain", action="store_true", help="don't add matching grain to downscaled fills")
    args = ap.parse_args()

    out = args.output or default_output(args.image)
    check_output_target(out, args.image, args.overwrite)

    img, meta = load_image(args.image)
    mask = load_mask(args.mask, img.size)
    if not mask.any():
        raise SystemExit("Mask is empty; nothing to do.")

    logging.getLogger().setLevel(logging.WARNING)
    warnings.filterwarnings("ignore", category=FutureWarning)
    import torch
    from loguru import logger
    logger.remove()
    from iopaint.model_manager import ModelManager
    from iopaint.schema import HDStrategy, InpaintRequest

    t0 = time.time()
    model = ModelManager(name="lama", device=torch.device("cpu"))
    config = InpaintRequest(hd_strategy=HDStrategy.ORIGINAL)

    src = np.asarray(img)
    result = src.astype(np.float32)
    boxes = region_boxes(mask, args.pad)
    for i, (x1, y1, x2, y2) in enumerate(boxes, 1):
        crop = np.ascontiguousarray(src[y1:y2, x1:x2])
        cmask = mask[y1:y2, x1:x2].astype(np.uint8) * 255
        t = time.time()
        inpainted, scale = inpaint_region(model, config, crop, cmask, args.max_size, not args.no_grain)
        alpha = feather_alpha(mask[y1:y2, x1:x2], args.feather)[:, :, None]
        region = result[y1:y2, x1:x2]
        result[y1:y2, x1:x2] = alpha * inpainted + (1 - alpha) * region
        print(f"  region {i}/{len(boxes)}: {x2 - x1}x{y2 - y1} px at ({x1},{y1}) in {time.time() - t:.1f}s"
              + (f" (worked at {scale:.0%})" if scale < 1 else ""))

    out_img = Image.fromarray(np.clip(np.rint(result), 0, 255).astype(np.uint8))
    save_jpeg(out_img, out, meta)
    print(f"Wrote {out} ({img.size[0]}x{img.size[1]}) in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
