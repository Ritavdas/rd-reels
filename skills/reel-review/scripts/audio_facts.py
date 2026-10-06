#!/usr/bin/env python3
"""Fact-sheet of a reel's sound, for checking what a reviewer claims to hear.

Prints what is actually in the effects track around each moment, whether any effect plays inside
each quiet window, and writes a spectrogram image of a time range.

Usage:
  audio_facts.py SFX_MANIFEST.json                     -> per-cue table + quiet-window check
  audio_facts.py SFX_MANIFEST.json --at 32.4           -> what effect (if any) plays at that second
  audio_facts.py --spectrogram VIDEO START END OUT.png -> spectrogram of the final mix
"""
import argparse
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from scipy.io import wavfile


def rms_db(x):
    return 20 * math.log10(max(float(np.sqrt(np.mean(np.square(x.astype(np.float64))))), 1e-12))


def facts(manifest_path, at=None):
    m = json.loads(Path(manifest_path).read_text())
    base = Path(manifest_path).parent
    rate, fx = wavfile.read(base / m["effects_file"])
    if at is not None:
        hits = [c for c in m["cues"] if c["start_seconds"] <= at <= c["end_seconds"]]
        a, b = int((at - 0.15) * rate), int((at + 0.15) * rate)
        peak = float(np.max(np.abs(fx[max(0, a):b]))) if b > a else 0.0
        print(f"at {at:.2f}s: {', '.join(c['id'] + ' (' + c['family'] + ')' for c in hits) or 'no effect'}; "
              f"effects peak within +/-150 ms = {20 * math.log10(max(peak, 1e-12)):.1f} dBFS")
        return
    print(f"{len(m['cues'])} effects. Families: {sorted({c['family'] for c in m['cues']})}")
    for c in m["cues"]:
        print(f"  {c['hit_frame'] / 30:6.2f}s  {c['id']:20s} {c['family']:9s} {c['start_seconds']:6.2f}-{c['end_seconds']:6.2f}s  {c.get('reason', '')}")
    for w in m.get("quiet_windows", []):
        seg = fx[int(w["start"] * rate):int(w["end"] * rate)]
        print(f"  quiet {w['label']:24s} {w['start']:6.2f}-{w['end']:6.2f}s  max effect amplitude {float(np.max(np.abs(seg))) if len(seg) else 0:.6f}")


def spectrogram(video, start, end, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(end - start), "-i", video,
                    "-lavfi", "showspectrumpic=s=1200x500:legend=1:color=intensity:scale=log", out], check=True)
    print(f"wrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", nargs="?")
    ap.add_argument("--at", type=float)
    ap.add_argument("--spectrogram", nargs=4, metavar=("VIDEO", "START", "END", "OUT"))
    a = ap.parse_args()
    if a.spectrogram:
        v, s, e, o = a.spectrogram
        spectrogram(v, float(s), float(e), o)
    else:
        facts(a.manifest, a.at)
