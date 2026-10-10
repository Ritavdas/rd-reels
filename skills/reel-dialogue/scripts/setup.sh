#!/usr/bin/env bash
# Adds reel-dialogue's dependencies to the shared rd-reels venv. Run once.
set -euo pipefail
VENV="${RD_REELS_VENV:-$HOME/.cache/rd-reels/venv}"
command -v ffmpeg >/dev/null || { echo "ffmpeg is missing: brew install ffmpeg"; exit 1; }
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q demucs pyloudnorm pystoi torch torchaudio soundfile librosa matplotlib scipy mlx-whisper
"$VENV/bin/python" -c "
import demucs, pyloudnorm, pystoi, torch, torchaudio, soundfile, librosa, matplotlib, scipy, mlx_whisper
print('reel-dialogue deps ready:', '$VENV')
"
