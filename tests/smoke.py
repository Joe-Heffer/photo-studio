"""End-to-end smoke test: run every tool on a synthetic photo and check the results.

    uv run python tests/smoke.py

Needs the LaMa model (`uv run iopaint download --model lama`). Everything is written to a
temporary folder, except finalize.py's detected mask, which is removed afterwards.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
W, H = 1200, 800
BLOB = (700, 300, 60)  # cx, cy, r of the red "object" to remove, in upright pixels
ORIENTATION_TAG = 0x0112


def run(tool: str, *args: object) -> str:
    cmd = [sys.executable, str(TOOLS / f"{tool}.py"), *map(str, args)]
    print("$", " ".join(cmd[1:]), flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout + res.stderr, end="", flush=True)
    if res.returncode:
        raise SystemExit(f"FAIL: {tool}.py exited with {res.returncode}")
    return res.stdout


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")
    print(f"ok: {msg}")


def make_photo(path: Path) -> np.ndarray:
    """Write a textured landscape JPEG stored sideways (EXIF orientation 6) with a red blob."""
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:H, 0:W]
    base = np.stack([90 + 60 * xx / W, 130 + 50 * yy / H, 170 - 40 * xx / W], axis=2)
    base += rng.normal(0, 4, base.shape)
    upright = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    cx, cy, r = BLOB
    ImageDraw.Draw(upright).ellipse([cx - r, cy - r, cx + r, cy + r], fill=(220, 20, 20))
    stored = upright.transpose(Image.Transpose.ROTATE_90)  # undone by orientation 6
    exif = Image.Exif()
    exif[ORIENTATION_TAG] = 6
    stored.save(path, "JPEG", quality=95, exif=exif.tobytes())
    with Image.open(path) as im:  # compare against the decoded JPEG, not the pre-encode pixels
        return np.asarray(ImageOps.exif_transpose(im).convert("RGB")).astype(np.int16)


def redness(arr: np.ndarray) -> float:
    cx, cy, r = BLOB
    patch = arr[cy - r // 2:cy + r // 2, cx - r // 2:cx + r // 2].astype(np.float32)
    return float((patch[..., 0] - patch[..., 1]).mean())


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        photo = tmp / "smoke.jpg"
        mask = tmp / "smoke_mask.png"
        edited = tmp / "smoke_edited.jpg"
        final = tmp / "smoke_final.jpg"
        upright = make_photo(photo)
        cx, cy, r = BLOB

        run("preview", photo, "--grid", "-o", tmp / "grid.jpg")
        run("preview", photo, "--crop", f"{cx - 150},{cy - 150},300,300", "--grid", "-o", tmp / "crop.jpg")
        out = run("mask", photo, "--ellipse", f"{cx},{cy},{r}", "--stroke", "100,700,300,650:6",
                  "--grow", 6, "-o", mask)
        check(f"{W}x{H}" in out, "mask.py sees the upright size")
        with Image.open(mask) as m:
            check(m.size == (W, H), "mask has the upright size")
        run("preview", photo, "--mask", mask, "-o", tmp / "mask_view.jpg")

        run("remove", photo, mask, "-o", edited)
        with Image.open(edited) as im:
            check(im.size == (W, H), "result has the upright size")
            check(im.getexif().get(ORIENTATION_TAG, 1) == 1, "result has orientation 1")
            result = np.asarray(im.convert("RGB")).astype(np.int16)
        check(redness(upright) > 150 and redness(result) < 40, "red blob was removed")
        outside = np.ones((H, W), bool)
        outside[cy - 2 * r:cy + 2 * r, cx - 2 * r:cx + 2 * r] = False
        outside[600:760, 50:350] = False
        diff = np.abs(result - upright)[outside].mean()
        check(diff < 3, f"pixels outside the mask are unchanged (mean diff {diff:.2f})")

        res = subprocess.run([sys.executable, str(TOOLS / "remove.py"), photo, mask, "-o", edited],
                             capture_output=True, text=True)
        check(res.returncode != 0 and "exists" in res.stderr, "remove.py refuses to overwrite")

        run("preview", photo, "--compare", edited, "--crop", f"{cx - 150},{cy - 150},300,300",
            "-o", tmp / "compare.jpg")

        detected = ROOT / "masks" / "smoke_ui_detected.png"
        try:
            out = run("finalize", photo, edited, "-o", final)
        finally:
            detected.unlink(missing_ok=True)
        check("Found" in out and final.exists(), "finalize.py found the retouched area")

    print("All smoke tests passed.")


if __name__ == "__main__":
    main()
