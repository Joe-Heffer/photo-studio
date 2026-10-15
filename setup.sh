#!/usr/bin/env bash
# One-time setup: create the Python environment and download the LaMa model (~200 MB).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p input output masks previews
uv sync
uv run iopaint download --model lama
echo "Setup complete. Run ./ui.sh for the browser editor, or see README.md."
