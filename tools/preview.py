"""Make small preview images for inspecting a photo, a mask, or a before/after.

All coordinates shown/accepted are pixels of the full-size upright image.
Results go to previews/ and are sized to be easy to view (default max 1600 px).

Examples:
  uv run tools/preview.py input/IMG_1.jpg --grid                  # whole photo + labelled grid
  uv run tools/preview.py input/IMG_1.jpg --crop 1800,1200,600,400 --grid   # zoom on a region
  uv run tools/preview.py input/IMG_1.jpg --mask masks/IMG_1.png --crop 1800,1200,600,400
  uv run tools/preview.py input/IMG_1.jpg --compare output/IMG_1_edited.jpg --crop 1800,1200,600,400
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from common import PREVIEW_DIR, load_image, load_mask, parse_numbers


def font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def nice_step(span: float, target_lines: int = 10) -> int:
    raw = span / target_lines
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return max(1, int(m * mag))
    return int(10 * mag)


def render(img: Image.Image, box: tuple[int, int, int, int], max_size: int, grid: bool,
           mask: np.ndarray | None) -> Image.Image:
    x1, y1, x2, y2 = box
    view = img.crop(box)
    if mask is not None:
        m = mask[y1:y2, x1:x2]
        arr = np.asarray(view).astype(np.float32)
        arr[m] = arr[m] * 0.45 + np.array([255, 0, 0]) * 0.55
        view = Image.fromarray(arr.astype(np.uint8))
    scale = min(1.0, max_size / max(view.size))
    if scale < 1:
        view = view.resize((round(view.width * scale), round(view.height * scale)), Image.Resampling.LANCZOS)
    else:
        # Small crops: enlarge (nearest neighbour keeps pixels honest) up to 4x.
        up = min(4, max_size // max(view.size))
        if up > 1:
            view = view.resize((view.width * up, view.height * up), Image.Resampling.NEAREST)
            scale = up
    if grid:
        draw = ImageDraw.Draw(view, "RGBA")
        f = font(max(12, view.width // 90))
        step = nice_step(max(x2 - x1, y2 - y1))
        for gx in range((x1 // step + 1) * step, x2, step):
            px = (gx - x1) * scale
            draw.line([(px, 0), (px, view.height)], fill=(255, 255, 0, 150), width=1)
            draw.text((px + 3, 3), str(gx), fill=(255, 255, 0, 255), font=f, stroke_width=2, stroke_fill=(0, 0, 0, 255))
        for gy in range((y1 // step + 1) * step, y2, step):
            py = (gy - y1) * scale
            draw.line([(0, py), (view.width, py)], fill=(0, 255, 255, 150), width=1)
            draw.text((3, py + 3), str(gy), fill=(0, 255, 255, 255), font=f, stroke_width=2, stroke_fill=(0, 0, 0, 255))
    return view


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--crop", metavar="X,Y,W,H", help="only show this region (zoomed)")
    ap.add_argument("--grid", action="store_true", help="overlay gridlines labelled in image pixels (x yellow, y cyan)")
    ap.add_argument("--mask", type=Path, help="tint this mask red on top of the image")
    ap.add_argument("--compare", type=Path, metavar="EDITED", help="side-by-side: image (left) vs EDITED (right)")
    ap.add_argument("--size", type=int, default=1600, help="max preview edge in px (default 1600)")
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args()

    img, _ = load_image(args.image)
    w, h = img.size
    if args.crop:
        x, y, cw, ch = (int(round(v)) for v in parse_numbers(args.crop, img.size, "xyxy"))
        box = (max(0, x), max(0, y), min(w, x + cw), min(h, y + ch))
    else:
        box = (0, 0, w, h)
    mask = load_mask(args.mask, img.size) if args.mask else None

    if args.compare:
        other, _ = load_image(args.compare)
        if other.size != img.size:
            raise SystemExit(f"Sizes differ: {img.size} vs {other.size}")
        half = args.size // 2 if box[2] - box[0] >= box[3] - box[1] else args.size
        a = render(img, box, half, args.grid, mask)
        b = render(other, box, half, args.grid, None)
        gap = 12
        view = Image.new("RGB", (a.width + b.width + gap, max(a.height, b.height)), (40, 40, 40))
        view.paste(a, (0, 0))
        view.paste(b, (a.width + gap, 0))
        tag = "compare"
    else:
        view = render(img, box, args.size, args.grid, mask)
        tag = "mask" if mask is not None else "grid" if args.grid else "view"

    suffix = f"_{box[0]}_{box[1]}_{box[2] - box[0]}x{box[3] - box[1]}" if args.crop else ""
    out = args.output or PREVIEW_DIR / f"{args.image.stem}_{tag}{suffix}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    view.save(out, quality=90)
    print(f"Wrote {out} ({view.width}x{view.height}) showing x {box[0]}-{box[2]}, y {box[1]}-{box[3]} of {w}x{h}")


if __name__ == "__main__":
    main()
