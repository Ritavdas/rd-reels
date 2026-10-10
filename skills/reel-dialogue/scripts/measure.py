#!/usr/bin/env python3
"""measure.py: objective "can a viewer hear this" scoring for a dialogue+music mix.

Per segment: WER vs truth text (if given), SQUIM STOI/SI-SDR (reference-free, always),
ESTOI + K-weighted speech-to-music gap + glimpse score (if stems are given).
Plus clicks at segment boundaries and gated loudness jumps between adjacent segments.

usage: measure.py MIX WINDOWS.json OUT.json
       [--truth truth.json] [--dialogue stem.wav --music stem.wav] [--offset 0.0]
       [--asr-model mlx-community/whisper-large-v3-turbo]

WINDOWS.json: {"windows": [[id, start_s, end_s], ...]}
truth.json:   {"01": "no, let's just vote.", ...}  -- one entry per window id
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
from pystoi import stoi

SR = 16000


def load(path: str, sr: int = SR) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], check=True, capture_output=True).stdout
    y = np.frombuffer(raw, dtype="<f4").astype(np.float64)
    if not len(y) or not np.isfinite(y).all():
        raise ValueError(f"Empty or non-finite audio: {path}")
    return y


def words(s: str) -> list[str]:
    s = re.sub(r"(\d)\s*[-\u2013]\s*(\d)", r"\1\2", s.lower())
    return re.sub(r"[^a-z0-9 ]", " ", s).split()


def wer(ref: str, hyp: str) -> float:
    r, h = words(ref), words(hyp)
    if not r:
        raise ValueError("Truth text must contain words")
    d = np.arange(len(h) + 1)
    for i, rw in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hw in enumerate(h, 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (rw != hw))
            prev, d[j] = d[j], cur
    return d[len(h)] / len(r)


def align(ref: np.ndarray, x: np.ndarray, max_lag: float = 0.15) -> int:
    """Lag in samples that best aligns x to ref, by envelope cross-correlation."""
    from scipy.signal import correlate
    L = min(int(max_lag * SR), len(ref) - 1, len(x) - 1)
    c = correlate(x, ref, mode="full", method="fft")
    mid = len(ref) - 1
    seg = c[mid - L: mid + L + 1]
    return int(np.argmax(np.abs(seg)) - L)


def asr(x: np.ndarray, model: str) -> str:
    import mlx_whisper
    return mlx_whisper.transcribe(x.astype(np.float32), path_or_hf_repo=model, language="en")["text"].strip()


def squim(x: np.ndarray) -> tuple[float, float]:
    import torch
    from torchaudio.pipelines import SQUIM_OBJECTIVE
    global _SQ
    try:
        _SQ
    except NameError:
        _SQ = SQUIM_OBJECTIVE.get_model()
    with torch.no_grad():
        s, _, sdr = _SQ(torch.tensor(x, dtype=torch.float32)[None])
    return float(s[0]), float(sdr[0])


def glimpse_score(d: np.ndarray, m: np.ndarray, lo=300, hi=4000, thr=3.0) -> float:
    import librosa
    D = np.abs(librosa.stft(d, n_fft=512, hop_length=160)) ** 2
    M = np.abs(librosa.stft(m, n_fft=512, hop_length=160)) ** 2
    f = librosa.fft_frequencies(sr=SR, n_fft=512)
    band = (f >= lo) & (f <= hi)
    D, M = D[band], M[band]
    active = 10 * np.log10(D.sum(0) + 1e-12) > 10 * np.log10(D.sum(0).max() + 1e-12) - 30
    snr = 10 * np.log10((D + 1e-12) / (M + 1e-12))
    return float((snr[:, active] > thr).mean()) if active.any() else float("nan")


def lu(x: np.ndarray) -> float:
    if len(x) < int(0.4 * SR):
        raise ValueError("Loudness windows must be at least 400 ms")
    return pyln.Meter(SR, block_size=0.4).integrated_loudness(x)


def clicks(y: np.ndarray, times: list[float]) -> list[dict]:
    out = []
    for t in times:
        k = int(t * SR)
        if k < 2500 or k > len(y) - 500:
            continue
        d2 = np.abs(np.diff(y[k - 160:k + 160], 2))
        ref = np.abs(np.diff(y[k - 2400:k - 400], 2))
        out.append({"t": round(t, 3), "ratio": round(float(d2.max() / (np.percentile(ref, 99) + 1e-9)), 2)})
    return out


def loudness_jumps(y: np.ndarray, win: list) -> list[dict]:
    """Gated loudness of each segment vs the previous one, so a pause isn't a 'jump'."""
    out, prev = [], None
    for wid, s, e in win:
        cur = lu(y[int(s * SR):int(e * SR)])
        if prev is not None and not (np.isnan(cur) or np.isnan(prev)):
            out.append({"t": round(s, 3), "jump_lu": round(cur - prev, 1)})
        prev = cur
    return out


def gated_lufs_peak(path: str, offset: float) -> tuple[float, float]:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(offset), "-i", path, "-vn", "-af",
                          "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
    lines = err.splitlines()
    i = float([l for l in lines if l.strip().startswith("I:")][-1].split()[1])
    pk = [l for l in lines if "Peak:" in l]
    tp = float(pk[-1].split()[1]) if pk else float("nan")
    return i, tp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mix")
    ap.add_argument("windows")
    ap.add_argument("out")
    ap.add_argument("--truth", type=Path)
    ap.add_argument("--dialogue")
    ap.add_argument("--music")
    ap.add_argument("--reference-dialogue", type=Path, help="fixed clean dialogue reference for ESTOI across candidates")
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--asr-model", default="mlx-community/whisper-large-v3-turbo")
    a = ap.parse_args()
    if bool(a.dialogue) != bool(a.music):
        ap.error("--dialogue and --music must be supplied together")
    if a.reference_dialogue and not a.dialogue:
        ap.error("--reference-dialogue requires --dialogue and --music")
    if not np.isfinite(a.offset) or a.offset < 0:
        ap.error("--offset must be finite and non-negative")

    full = load(a.mix)
    y = full[int(a.offset * SR):]
    win = json.loads(Path(a.windows).read_text())["windows"]
    truth = json.loads(a.truth.read_text()) if a.truth else None
    d = load(a.dialogue) if a.dialogue else None
    m = load(a.music) if a.music else None
    ref = load(a.reference_dialogue) if a.reference_dialogue else d
    ids = [w[0] for w in win]
    if not win or len(set(ids)) != len(ids):
        raise ValueError("Windows must have unique IDs and cannot be empty")
    if truth is not None and set(truth) != set(ids):
        raise ValueError("Truth must cover exactly the window IDs")
    for wid, s, e in win:
        if not np.isfinite([s, e]).all() or s < 0 or e - s < 0.4:
            raise ValueError(f"{wid}: invalid window (minimum duration 400 ms)")
        if int(e * SR) > len(y) or any(stem is not None and int(e * SR) > len(stem) for stem in (d, m, ref)):
            raise ValueError(f"{wid}: window extends beyond audio")
    win = sorted(win, key=lambda w: w[1])

    rows = []
    for wid, s, e in win:
        x = y[int(s * SR):int(e * SR)]
        r = {"seg": wid, "start": s, "end": e}
        st, sdr = squim(x)
        r["squim_stoi"], r["squim_sisdr"] = round(st, 3), round(sdr, 2)
        if truth is not None:
            heard = asr(x, a.asr_model)
            r["wer"], r["heard"] = round(wer(truth[wid], heard), 3), heard
        if d is not None and m is not None:
            ds = d[int(s * SR):int(e * SR)]
            ms = m[int(s * SR):int(e * SR)]
            rs = ref[int(s * SR):int(e * SR)]
            lag = align(rs, x)
            start, end = int(s * SR) + lag, int(e * SR) + lag
            left, right = max(0, -start), max(0, end - len(y))
            xs = y[max(0, start):min(len(y), end)]
            rs = rs[left:len(rs) - right]
            r["estoi"] = round(float(stoi(rs, xs, SR, extended=True)), 3)
            r["gap_lu"] = round(lu(ds) - lu(ms), 1)
            r["glimpse"] = round(glimpse_score(ds, ms), 3)
            r["lag_ms"] = round(lag / SR * 1000, 1)
        rows.append(r)

    cut_times = sorted({w[1] for w in win} | {w[2] for w in win})
    i_lufs, tp = gated_lufs_peak(a.mix, a.offset)
    rep = {
        "mix": a.mix,
        "segments": rows,
        "clicks_at_cuts": [c for c in clicks(y, cut_times) if c["ratio"] > 4],
        "loudness_jumps": [j for j in loudness_jumps(y, win) if abs(j["jump_lu"]) > 6],
        "lufs": round(i_lufs, 2),
        "true_peak_dbtp": round(tp, 2),
        "duration_seconds": len(full) / SR,
        "offset_seconds": a.offset,
        "comparison": {
            "truth_sha256": hashlib.sha256(a.truth.read_bytes()).hexdigest() if a.truth else None,
            "windows_sha256": hashlib.sha256(Path(a.windows).read_bytes()).hexdigest(),
            "asr_model": a.asr_model,
            "sample_rate": SR,
            "has_music": d is not None,
            "estoi_reference_sha256": hashlib.sha256(a.reference_dialogue.read_bytes()).hexdigest()
            if a.reference_dialogue else None,
        },
    }
    for key in ("wer", "squim_stoi", "squim_sisdr", "estoi", "gap_lu", "glimpse"):
        vals = [r[key] for r in rows if key in r]
        if vals:
            rep[f"mean_{key}"] = round(float(np.nanmean(vals)), 3)
    if any("gap_lu" in r for r in rows):
        rep["min_gap_lu"] = min(r["gap_lu"] for r in rows if "gap_lu" in r)
    Path(a.out).write_text(json.dumps(rep, indent=1, allow_nan=False))

    print(Path(a.out).name, {k: v for k, v in rep.items() if k.startswith(("mean_", "min_", "lufs", "true_peak"))})
    for r in rows:
        bits = [f"{k} {r[k]:.2f}" for k in ("wer", "squim_stoi", "estoi", "gap_lu", "glimpse") if k in r]
        print(f"   {r['seg']:>4} {r['start']:>6}-{r['end']:<6} " + "  ".join(bits) +
              (f" | {r['heard'][:55]}" if "heard" in r else ""))
    if rep["clicks_at_cuts"] or rep["loudness_jumps"]:
        print("   flags:", rep["clicks_at_cuts"] + rep["loudness_jumps"])


if __name__ == "__main__":
    main()
