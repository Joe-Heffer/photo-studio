#!/usr/bin/env bash
# Launch the IOPaint browser editor on http://localhost:8080 (LaMa model, CPU).
# Photos in input/ appear in the file browser; saved results go to output/.
# Afterwards run tools/finalize.py on each result (see README.md).
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8080}"
echo "Opening IOPaint at http://localhost:$PORT  (Ctrl+C to stop)"
[ -z "${NO_BROWSER:-}" ] && ( sleep 6 && xdg-open "http://localhost:$PORT" >/dev/null 2>&1 || true ) &
exec uv run iopaint start --model=lama --device=cpu --port="$PORT" \
  --input=input --output-dir=output --quality=100
