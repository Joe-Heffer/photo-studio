"""Build a full-size mask (white = remove) for a photo from simple shapes.

Coordinates are pixels of the upright image, or fractions of it when written with a
decimal point and all <= 1 (e.g. 0.25). Shapes can be repeated and combined.

Examples:
  uv run tools/mask.py input/IMG_1.jpg --rect 1200,800,150,90
  uv run tools/mask.py input/IMG_1.jpg --ellipse 2040,1310,18,18 --ellipse 2210,1460,12,12
  uv run tools/mask.py input/IMG_1.jpg --stroke 100,2000,400,1950,700,1990:14 --grow 6
  uv run tools/mask.py input/IMG_1.jpg --add masks/IMG_1.png --rect 0.9,0.05,0.05,0.04
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from common import MASK_DIR, load_mask, parse_numbers


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--rect", action="append", default=[], metavar="X,Y,W,H", help="rectangle (top-left + size)")
    ap.add_argument("--ellipse", action="append", default=[], metavar="CX,CY,RX,RY", help="ellipse (centre + radii); CX,CY,R for a circle")
    ap.add_argument("--stroke", action="append", default=[], metavar="X1,Y1,X2,Y2,...:R", help="brush stroke through points, R = brush radius")
    ap.add_argument("--polygon", action="append", default=[], metavar="X1,Y1,X2,Y2,X3,Y3,...", help="filled polygon")
    ap.add_argument("--add", action="append", default=[], type=Path, metavar="MASK.png", help="start from / merge an existing mask")
    ap.add_argument("--grow", type=int, default=4, help="dilate the mask by N pixels (default 4) so edges/halos are covered")
    ap.add_argument("-o", "--output", type=Path, help="default: masks/<image stem>.png")
    args = ap.parse_args()

    with Image.open(args.image) as im:
        size = ImageOps.exif_transpose(im).size
    w, h = size

    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)

    for spec in args.rect:
        x, y, rw, rh = parse_numbers(spec, size, "xyxy")
        draw.rectangle([x, y, x + rw - 1, y + rh - 1], fill=255)
    for spec in args.ellipse:
        vals = parse_numbers(spec, size, "xymm" if spec.count(",") == 2 else "xyxy")
        cx, cy, rx = vals[:3]
        ry = vals[3] if len(vals) > 3 else rx
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
    for spec in args.stroke:
        pts_spec, _, r_spec = spec.partition(":")
        pts = parse_numbers(pts_spec, size, "xy")
        r = float(r_spec or 10)
        points = list(zip(pts[::2], pts[1::2]))
        if len(points) > 1:
            draw.line(points, fill=255, width=int(round(2 * r)), joint="curve")
        for px, py in points:
            draw.ellipse([px - r, py - r, px + r, py + r], fill=255)
    for spec in args.polygon:
        pts = parse_numbers(spec, size, "xy")
        draw.polygon(list(zip(pts[::2], pts[1::2])), fill=255)

    arr = np.asarray(mask) > 127
    for extra in args.add:
        arr |= load_mask(extra, size)

    arr = arr.astype(np.uint8) * 255
    if args.grow > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * args.grow + 1, 2 * args.grow + 1))
        arr = cv2.dilate(arr, kernel)
    mask = Image.fromarray(arr)

    out = args.output or MASK_DIR / f"{args.image.stem}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    mask.save(out)
    area = int((np.asarray(mask) > 127).sum())
    print(f"Wrote {out} ({w}x{h}, {area} px masked = {100 * area / (w * h):.3f}% of image)")


if __name__ == "__main__":
    main()
