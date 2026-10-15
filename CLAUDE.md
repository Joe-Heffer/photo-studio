# Photo retouching workspace

Purpose: remove unwanted objects and blemishes from JPEG photos with LaMa inpainting (CPU),
using the scripts in `tools/`. See README.md for the user-facing guide.
After changing anything in `tools/`, run `uv run python tests/smoke.py`.

## Rules

- **Never modify, move or overwrite original photos.** Put photos in `input/` as symlinks
  (`ln -s /path/to/photo.jpg input/`). Write results only to `output/`.
- Run everything from this folder with `uv run tools/<script>.py`. If `.venv` is missing,
  run `./setup.sh`.
- Coordinates are always pixels of the full-size **upright** image (EXIF rotation applied).
- Look at previews with the Read tool. Never Read a full-size original: they are up to
  8192×5464 px.
- Before running `remove.py`, show the user the mask overlay. After running it, show a
  `--compare` crop. Don't overwrite a result the user hasn't seen.

## Workflow for "remove X from photo Y"

1. **Overview:** `uv run tools/preview.py input/Y.jpg --grid`, then Read the preview. The
   gridlines are labelled in full-image pixels (x yellow along the top, y cyan down the left).
2. **Locate precisely:** `uv run tools/preview.py input/Y.jpg --crop X,Y,W,H --grid`, then
   Read it. Zoom repeatedly until the object's edges are clear. For blemishes, zoom to about
   300–600 px crops, which are enlarged with nearest-neighbour sampling.
3. **Mask:** `uv run tools/mask.py input/Y.jpg --ellipse ... --rect ... --stroke ...:R --grow N`
   - Cover shadows, reflections and soft blur halos. Out-of-focus objects need
     `--grow 20–40`; sharp ones need 4–8.
   - Use `--polygon` for irregular shapes and `--stroke` for cables and wires.
   - Use a separate `-o masks/<name>.png` per edit if you'll iterate.
4. **Check the mask:** `uv run tools/preview.py input/Y.jpg --mask masks/Y.png --crop ...`
   and Read it. Every part of the object should be tinted red.
5. **Remove:** `uv run tools/remove.py input/Y.jpg masks/Y.png`, which writes
   `output/Y_edited.jpg`. The first call loads the model (about 3 s).
6. **Verify:** `uv run tools/preview.py input/Y.jpg --compare output/Y_edited.jpg --crop ...`
   and Read it. Look for ghosts (enlarge the mask) and smears or repeated texture (see tuning).
7. **More edits on the same photo:** mask relative to the edited file, then
   `remove.py output/Y_edited.jpg masks/next.png -o output/Y_edited.jpg --overwrite`.
   Alternatively, combine all the shapes into one mask from the start.

## Tuning remove.py

- `--max-size` (default 512) caps the working resolution per region. LaMa smears holes that
  are large at its working size.
  - If a big fill is smeared or blotchy: lower it (384).
  - If a mid-size fill in a sharp, in-focus area looks too soft: raise it (768–1024).
- `--pad` sets the minimum context around each region (default 128, and automatically at
  least 0.75× the hole size).
- `--feather` sets the blend width at the mask edge (default 3 px).
- Large objects overlapping detailed structure: split them into several smaller masks and
  run them one after another. Tell the user honestly when LaMa can't do a convincing job,
  and suggest GIMP's Heal tool.

## Browser-editor results

Files saved from the IOPaint UI (`./ui.sh`) must go through
`uv run tools/finalize.py input/Y.jpg output/Y.jpg`. That restores metadata, fixes rotation
and keeps unretouched pixels from the original.

## Implementation notes

- `iopaint` pins `pillow==9.5.0`, which has no Python 3.12 wheels. `pyproject.toml`
  overrides the pin. IOPaint 1.6 works with current Pillow.
- For security, `pyproject.toml` excludes `gradio`, which is only used by `iopaint start-web-config`,
  and overrides iopaint's pins on `fastapi`, `starlette` and `python-socketio`. `diffusers` and
  `transformers` stay on iopaint's old pins: iopaint imports their internals, and the LaMa path never
  loads HF models. Their Dependabot alerts are dismissed for that reason.
- PyTorch comes from the CPU wheel index; the toolkit is CPU-only by design (LaMa is fast enough
  without a GPU, and it avoids CUDA/ROCm setup).
