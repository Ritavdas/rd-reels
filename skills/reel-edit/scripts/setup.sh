#!/usr/bin/env bash
# One-time setup for rd-reels. Creates ~/.cache/rd-reels/venv with everything the scripts need.
set -euo pipefail
VENV="${RD_REELS_VENV:-$HOME/.cache/rd-reels/venv}"
command -v ffmpeg >/dev/null || { echo "ffmpeg is missing: brew install ffmpeg"; exit 1; }
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q numpy scipy Pillow websocket-client mlx-whisper
"$VENV/bin/python" -c "import numpy, scipy, PIL, websocket, mlx_whisper; print('rd-reels venv ready:', '$VENV')"
