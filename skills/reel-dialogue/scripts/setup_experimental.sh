#!/usr/bin/env bash
# Optional, experimental: a separate Python 3.12 env for Rust/C-extension audio tools
# (DeepFilterNet3, audio-separator/BS-RoFormer) that don't build cleanly on the main
# rd-reels venv's Python version. Tested against the gate in SKILL.md; neither beat a
# properly-separated + per-clip-leveled baseline on real phone-recorded footage, so
# treat this as "worth re-testing on a new reel", not "apply by default".
#
# On macOS, if `cc` fails with "exit status 69" / an Xcode license message, export
# DEVELOPER_DIR=/Library/Developer/CommandLineTools instead of accepting the license.
set -euo pipefail
command -v cargo >/dev/null || { curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --no-modify-path; }
export PATH="$HOME/.cargo/bin:$PATH"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Library/Developer/CommandLineTools}"

V="${RD_REELS_AUDIO312_VENV:-$HOME/.cache/rd-reels/audio312}"
PY312="$(command -v python3.12 || true)"
if [ -z "$PY312" ] && command -v uv >/dev/null; then PY312="$(uv python find 3.12)"; fi
[ -n "$PY312" ] || { echo "Need Python 3.12 (brew install python@3.12, or: uv python install 3.12)"; exit 1; }

"$PY312" -m venv "$V"
"$V/bin/pip" install -q --upgrade pip
"$V/bin/pip" install -q deepfilternet "audio-separator[cpu]" torch==2.4.1 torchaudio==2.4.1 soundfile audioread
"$V/bin/python" -c "import df, audio_separator; print('experimental audio env ready:', '$V')"
