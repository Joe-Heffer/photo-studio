# Photo Studio

[![CI](https://github.com/Joe-Heffer/photo-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Joe-Heffer/photo-studio/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Remove unwanted objects and blemishes from JPEG photos, entirely on your own machine.

Photo Studio is a small toolkit built on [LaMa](https://github.com/advimman/lama) inpainting
(via [IOPaint](https://github.com/Sanster/IOPaint)). It runs on the CPU, so you don't need a GPU.
You can paint edits in a browser, script them from the command line, or describe them to an AI
coding agent such as [Claude Code](https://claude.com/claude-code), which locates, masks and
removes them for you.

- **Local and private:** no uploads, no accounts, no API keys.
- **Full resolution:** works on large camera files (tested up to 45 MP).
- **Non-destructive:** originals are never modified. Results keep the original EXIF and
  colour profile, and pixels outside the retouched areas are carried over unchanged. The only
  loss is one JPEG save at quality 95 with 4:4:4 chroma.
- **Rotation-safe:** every tool works in upright coordinates, with EXIF orientation applied.

## Requirements

- Linux or macOS (Windows should work under WSL)
- [uv](https://docs.astral.sh/uv/). It installs Python 3.12 and all dependencies for you.
- About 2 GB of disk for the environment, plus the ~200 MB LaMa model

## Quick start

```bash
git clone https://github.com/Joe-Heffer/photo-studio.git
cd photo-studio
./setup.sh                        # creates .venv (CPU-only PyTorch) and downloads LaMa
ln -s ~/Pictures/holiday/ input/  # put photos (or symlinks to them) in input/
```

Results are written to `output/`.

## Three ways to work

| | Browser editor | Command line | AI agent |
|---|---|---|---|
| How | Paint over the item | Describe masks with shapes and coordinates | Describe the edit in words |
| Best for | Many small spots, judging by eye | Precise, repeatable or scripted edits | Hands-off work and batches |
| Start | `./ui.sh` | `uv run tools/...` | `claude` in this folder |

### Browser editor

```bash
./ui.sh         # opens http://localhost:8080 (set PORT=... to change it, NO_BROWSER=1 to not open it)
```

1. Press `F` (or click the folder icon) and choose a photo from `input/`, or drag a file in.
2. Paint over the thing to remove. Use `[` and `]` to change brush size, and Space+drag to pan.
   Release the mouse and the area is filled in a few seconds.
3. Repeat for other spots. Ctrl+Z / Ctrl+Shift+Z undo and redo, holding `Tab` shows the
   original, and `H` lists all shortcuts.
4. Click **Save**. The result is written to `output/<same name>.jpg`.
5. **Finalize it.** The browser editor re-encodes the whole image on every stroke and can leave a
   wrong rotation tag on portrait shots. This step pastes only the retouched areas onto your
   untouched original and restores the metadata:

   ```bash
   uv run tools/finalize.py input/IMG.jpg output/IMG.jpg     # -> output/IMG_final.jpg
   ```

   It lists the areas it found. If an edit is missing, try `--threshold 6`.

### Command line

```bash
uv run tools/preview.py input/IMG.jpg --grid                           # overview with a pixel grid
uv run tools/preview.py input/IMG.jpg --crop 1100,950,1100,1000 --grid  # zoom in on a region
uv run tools/mask.py    input/IMG.jpg --ellipse 1595,1450,400,345 --grow 30   # -> masks/IMG.png
uv run tools/preview.py input/IMG.jpg --mask masks/IMG.png --crop ...   # check the mask (tinted red)
uv run tools/remove.py  input/IMG.jpg masks/IMG.png                     # -> output/IMG_edited.jpg
uv run tools/preview.py input/IMG.jpg --compare output/IMG_edited.jpg --crop ...   # before/after
```

Previews go to `previews/`. Every tool has `--help`.

### AI agent (Claude Code)

[`CLAUDE.md`](CLAUDE.md) teaches an agent the workflow: preview with a grid, zoom in, draw a
mask, show it to you, remove, then show a before/after crop. Run `claude` in this folder and ask,
for example:

- "Remove the paper lantern in the top left of `input/IMG_0420.jpg`."
- "Remove the red cable at the bottom left, and the exit sign on the back wall."
- "Clean up dust spots in the sky on every photo in `input/`, and show me each one before saving."
- "Remove the blemish on the left cheek of the person in the middle."

The agent reads the low-resolution previews, so the full-size photos never need to fit in its context.

## Tool reference

| Tool | Purpose |
|---|---|
| `preview.py` | Downscaled views and zoomed crops, with a labelled pixel grid, mask overlay or side-by-side comparison |
| `mask.py` | Builds a mask PNG from shapes |
| `remove.py` | Inpaints the masked areas with LaMa and writes a full-resolution JPEG |
| `finalize.py` | Merges a browser-editor result back onto the original |

**`mask.py` shapes** (each can be repeated):

- `--rect X,Y,W,H`
- `--ellipse CX,CY,RX,RY`, or `CX,CY,R` for a circle
- `--polygon X1,Y1,X2,Y2,...`
- `--stroke X1,Y1,X2,Y2,...:RADIUS` for wires and lines
- `--add MASK.png` to merge an existing mask
- `--grow N` to dilate the mask (default 4 px)

Coordinates are pixels of the upright photo, or fractions of it if written with a decimal point (`0.25`).

**`remove.py` options:**

- `--max-size` (default 512) caps the working resolution per region. Lower it (384) if a big
  fill looks smeared. Raise it (768–1024) if a mid-size fill in a sharp area looks soft.
- `--pad` (default 128) is the minimum context around each region.
- `--feather` (default 3) is the blend width at the mask edge.
- `--no-grain` skips the matching grain added to downscaled fills.

`remove.py` never overwrites by default. To stack more edits onto a result, run it on the output:
`remove.py output/IMG_edited.jpg masks/more.png -o output/IMG_edited.jpg --overwrite`.
Only files inside `output/` can ever be overwritten.

## Tips and limits

- **Mask generously.** Cover the item's shadow, reflection and any soft glow or blur halo.
  Anything outside the mask stays, often as a faint ghost. Out-of-focus objects need
  `--grow 20–40`; sharp ones need 4–8.
- **LaMa does well on** dust, blemishes, stray hairs, wires, signs, small objects, and anything
  on walls, sky, floors, foliage or out-of-focus backgrounds.
- **LaMa does poorly on** large objects overlapping faces, hands, text or other detailed
  structure. It fills with plausible texture; it doesn't reconstruct what was hidden. Remove
  large items in two or three smaller passes, and use a healing brush (for example GIMP's Heal
  tool) for final polish.
- **Speed:** on a mid-range desktop CPU, a blemish takes a second or two and a large object
  5–10 s. Loading a 45 MP photo adds a few seconds.
- **Large areas are processed at reduced resolution.** LaMa was trained on ~512 px images and
  smears big holes at full resolution. `remove.py` works on each region at up to `--max-size`,
  upscales only the filled-in pixels and adds matching grain.
- Outputs are a bit larger than typical camera exports because they're saved at quality 95 with
  full colour resolution.

## Project layout

```
setup.sh, ui.sh      setup and browser editor
tools/               preview.py, mask.py, remove.py, finalize.py, common.py
tests/smoke.py       end-to-end test on a synthetic photo
CLAUDE.md            instructions for AI coding agents
input/               your photos or symlinks to them (git-ignored, never modified)
output/              results (git-ignored)
masks/, previews/    working files (git-ignored, safe to delete)
```

## Development

```bash
uv run python tests/smoke.py    # runs every tool on a generated photo (needs the LaMa model)
```

CI runs the same test on every push and pull request.

## Credits and licence

- [LaMa](https://github.com/advimman/lama) by Suvorov et al. (Apache-2.0) does the inpainting.
- [IOPaint](https://github.com/Sanster/IOPaint) (Apache-2.0) provides the model runtime and browser editor.

Photo Studio is released under the [MIT License](LICENSE).
