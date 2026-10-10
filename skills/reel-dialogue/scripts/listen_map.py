#!/usr/bin/env python3
"""listen_map.py: render a mix as pictures a vision-capable reviewer can actually read.

Waveform + momentary LUFS, a log-mel spectrogram, and (with stems) a per-segment masking
map: share of the 300-4000 Hz speech band where music is louder than speech. Picture cuts
are marked as vertical lines so a reviewer can see whether a problem lines up with an edit.

usage: listen_map.py MEDIA OUT.png [--dialogue stem.wav --music stem.wav] [--title T]
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import librosa
import librosa.display
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.signal import lfilter  # noqa: E402

SR = 22050


def load(path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], check=True, capture_output=True).stdout
    y = np.frombuffer(raw, dtype="<f4")
    if not len(y) or not np.isfinite(y).all():
        raise ValueError(f"Empty or non-finite audio: {path}")
    return y


def scene_cuts(media) -> list[float]:
    if not str(media).lower().endswith((".mp4", ".mov", ".m4v")):
        return []
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(media), "-vf", "select='gt(scene,0.3)',showinfo",
                          "-an", "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
    return [float(x) for x in re.findall(r"pts_time:([0-9.]+)", err)]


def momentary_lufs(y: np.ndarray, hop=0.1):
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585]
    b2, a2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]
    yk = librosa.resample(y, orig_sr=SR, target_sr=48000)
    yk = lfilter(b2, a2, lfilter(b1, a1, yk))
    win, step = int(0.4 * 48000), int(hop * 48000)
    t, v = [], []
    for i in range(0, max(1, len(yk) - win), step):
        ms = np.mean(yk[i:i + win] ** 2)
        t.append((i + win / 2) / 48000)
        v.append(-0.691 + 10 * np.log10(ms + 1e-12))
    return np.array(t), np.array(v)


def band_db(y: np.ndarray, lo=300, hi=4000):
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=256)) ** 2
    f = librosa.fft_frequencies(sr=SR, n_fft=1024)
    m = (f >= lo) & (f <= hi)
    return 10 * np.log10(S[m] + 1e-12), f[m]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("media")
    ap.add_argument("out")
    ap.add_argument("--dialogue")
    ap.add_argument("--music")
    ap.add_argument("--title", default="")
    a = ap.parse_args()
    if bool(a.dialogue) != bool(a.music):
        ap.error("--dialogue and --music must be supplied together")

    y = load(a.media)
    dur = len(y) / SR
    cuts = scene_cuts(a.media)
    rows = 4 if a.dialogue and a.music else 2
    fig, ax = plt.subplots(rows, 1, figsize=(16, 3.2 * rows), sharex=True,
                           gridspec_kw={"height_ratios": [1, 2.2] + ([1.6, 1] if rows == 4 else [])})
    t = np.arange(len(y)) / SR
    ax[0].plot(t, y, lw=0.3, color="#444")
    tl, vl = momentary_lufs(y)
    ax0b = ax[0].twinx()
    ax0b.plot(tl, vl, color="#d62728", lw=1.2)
    ax0b.set_ylim(-50, -5)
    ax0b.set_ylabel("momentary LUFS", color="#d62728")
    ax[0].set_title(a.title or Path(a.media).name)

    M = librosa.power_to_db(librosa.feature.melspectrogram(y=y, sr=SR, n_fft=2048, hop_length=256, n_mels=128,
                                                           fmax=8000), ref=np.max)
    librosa.display.specshow(M, sr=SR, hop_length=256, x_axis="time", y_axis="mel", fmax=8000, ax=ax[1],
                             vmin=-70, vmax=0, cmap="magma")
    ax[1].set_ylabel("Hz (mel)")

    if rows == 4:
        d, m = load(a.dialogue), load(a.music)
        if abs(len(d) - len(y)) > SR / 30 or abs(len(m) - len(y)) > SR / 30:
            raise ValueError("Stems must match the rendered mix duration within one frame")
        n = min(len(d), len(m), len(y))
        Dd, f = band_db(d[:n])
        Dm, _ = band_db(m[:n])
        margin = Dd - Dm
        speech_active = (Dd.max(axis=0) > Dd.max() - 45)
        masked = np.where(speech_active[None, :], np.clip(margin, -20, 30), np.nan)
        tt = np.arange(Dd.shape[1]) * 256 / SR
        im = ax[2].pcolormesh(tt, f, masked, cmap="RdYlGn", vmin=-20, vmax=30, shading="auto")
        ax[2].set_ylabel("speech minus music, dB\n(300-4k Hz, speech frames)")
        cax = ax[2].inset_axes([1.003, 0, 0.008, 1])
        fig.colorbar(im, cax=cax)
        frac = np.where(speech_active, (margin < 0).mean(axis=0), np.nan)
        ax[3].fill_between(tt, 0, frac, color="#d62728", step="mid")
        ax[3].set_ylim(0, 1)
        ax[3].set_ylabel("share of speech band\nwhere music is louder")
        if not speech_active.any():
            raise ValueError("No active dialogue frames; cannot inspect music masking")
        print(f"speech-band bins masked by music (speech frames): {np.nanmean(frac) * 100:.1f}%")

    for c in cuts:
        for axis in ax:
            axis.axvline(c, color="#1f77b4", lw=0.8, alpha=0.7)
    ax[-1].set_xlim(0, dur)
    ax[-1].set_xlabel("seconds  (blue lines = picture cuts)")
    fig.tight_layout()
    fig.savefig(a.out, dpi=90)
    plt.close(fig)
    print(a.out, f"{dur:.2f}s", "cuts:", [round(c, 2) for c in cuts])


if __name__ == "__main__":
    main()
