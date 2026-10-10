#!/usr/bin/env python3
"""dialogue_mix.py: level N raw speech clips, separate a music bed, duck it, mix.

usage: dialogue_mix.py --clips clips.json --music SONG --out DIR
       [--dialogue-lufs -16] [--gap-lu 18] [--full-song-lufs -15]
       [--duck-attack 0.12] [--duck-release 0.35] [--edge-fade 0.012]

clips.json: {"clips": [{"id": "01", "path": "clip.mp4", "start": 2.6, "in": 67.95, "out": 69.45}, ...]}
  start = where this clip lands in the output timeline (seconds)
  in/out = trim window in the source file's own timeline
Writes: <out>/mix.wav, stem_dialogue.wav, stem_music.wav, windows.json, manifest.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 48000


def sh(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def lufs_of(path) -> float:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True, check=True).stderr
    return float([l for l in err.splitlines() if l.strip().startswith("I:")][-1].split()[1])


def lufs_arr(x: np.ndarray, tmp: Path) -> float:
    sf.write(tmp, x, SR, subtype="FLOAT")
    v = lufs_of(tmp)
    tmp.unlink(missing_ok=True)
    return v


def load_wav(path: Path, stereo=True) -> np.ndarray:
    y, sr = sf.read(path, always_2d=True)
    assert sr == SR, f"{path} is {sr} Hz, expected {SR}"
    if stereo and y.shape[1] == 1:
        y = np.repeat(y, 2, axis=1)
    return y


def process_clip(spec: dict, out_dir: Path, dialogue_lufs: float, edge_fade: float) -> tuple[np.ndarray, float]:
    cid = spec["id"]
    raw = out_dir / f"_clip_{cid}_raw.wav"
    sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{spec['in']:.3f}", "-to", f"{spec['out']:.3f}",
        "-i", spec["path"], "-ac", "1", "-ar", str(SR), str(raw)])
    pre = out_dir / f"_clip_{cid}_pre.wav"
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af",
        "highpass=f=90,lowpass=f=11000,afftdn=nr=12:nf=-42:tn=1,"
        "acompressor=threshold=-26dB:ratio=3:attack=5:release=90:makeup=1",
        str(pre)])
    gain_db = dialogue_lufs - lufs_of(pre)
    leveled = out_dir / f"_clip_{cid}.wav"
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(pre), "-af",
        f"volume={gain_db:.2f}dB,alimiter=limit=0.70:attack=2:release=40:level=disabled:latency=1", str(leveled)])
    y, _ = sf.read(leveled)
    n = min(len(y), max(1, int(edge_fade * SR)))
    ramp = np.linspace(0, 1, n)
    y[:n] *= ramp
    y[-n:] *= ramp[::-1]
    for p in (raw, pre, leveled):
        p.unlink(missing_ok=True)
    dur = spec["out"] - spec["in"]
    return y[: int(dur * SR)], dur


def separate_music(music: Path, out_dir: Path) -> Path:
    stem = f"_{music.stem}"
    cache = out_dir / "sep" / "htdemucs" / stem / "no_vocals.wav"
    if cache.exists():
        return cache
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(music), str(out_dir / f"{stem}.wav")])
    sh([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-o", str(out_dir / "sep"),
        str(out_dir / f"{stem}.wav")])
    return cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True, type=Path)
    ap.add_argument("--music", type=Path)
    ap.add_argument("--duration", type=float, help="exact picture duration in seconds; no added tail")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--dialogue-lufs", type=float, default=-16.0)
    ap.add_argument("--gap-lu", type=float, default=18.0, help="music bed target = dialogue LUFS - this")
    ap.add_argument("--full-song-lufs", type=float, default=-15.0)
    ap.add_argument("--duck-attack", type=float, default=0.12)
    ap.add_argument("--duck-release", type=float, default=0.35)
    ap.add_argument("--edge-fade", type=float, default=0.012)
    ap.add_argument("--carve-eq", action="store_true", default=True)
    a = ap.parse_args()
    clips = json.loads(a.clips.read_text())["clips"]
    if not clips or len({c["id"] for c in clips}) != len(clips):
        raise ValueError("Clips must be nonempty with unique IDs")
    clips = sorted(clips, key=lambda c: c["start"])
    for c in clips:
        if not np.isfinite([c["start"], c["in"], c["out"]]).all() or c["start"] < 0 or c["in"] < 0 or c["out"] <= c["in"]:
            raise ValueError(f"Invalid clip timing: {c['id']}")
    last_word = max(c["start"] + (c["out"] - c["in"]) for c in clips)
    total = a.duration if a.duration is not None else last_word + 1.0
    if not np.isfinite(total) or total <= 0 or total < last_word:
        raise ValueError("Duration must cover every dialogue clip")
    if a.edge_fade <= 0 or a.duck_attack <= 0 or a.duck_release <= 0:
        raise ValueError("Fade, attack and release must be positive")
    a.out.mkdir(parents=True, exist_ok=True)
    total_n = round(total * SR)
    dlg = np.zeros(total_n)
    windows = []
    for c in clips:
        y, dur = process_clip(c, a.out, a.dialogue_lufs, a.edge_fade)
        s = int(c["start"] * SR)
        e = min(total_n, s + len(y))
        dlg[s:e] += y[: e - s]
        windows.append([c["id"], c["start"], c["start"] + dur])

    music = build_music(a, total, total_n, windows) if a.music else np.zeros((total_n, 2))
    dlg_st = np.repeat(dlg[:, None], 2, axis=1)
    mix = dlg_st + music
    pre_gain = 10 ** ((-14.0 - lufs_arr(mix, a.out / "_m.wav")) / 20)
    mix *= pre_gain
    sf.write(a.out / "_mix_pre.wav", mix, SR, subtype="FLOAT")
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(a.out / "_mix_pre.wav"), "-af",
        "alimiter=limit=0.84:attack=1:release=50:level=disabled:latency=1", "-ar", str(SR),
        "-c:a", "pcm_f32le", str(a.out / "mix.wav")])
    (a.out / "_mix_pre.wav").unlink(missing_ok=True)
    sf.write(a.out / "stem_dialogue.wav", dlg_st * pre_gain, SR, subtype="FLOAT")
    sf.write(a.out / "stem_music.wav", music * pre_gain, SR, subtype="FLOAT")
    (a.out / "windows.json").write_text(json.dumps({"windows": windows}, indent=1) + "\n")
    (a.out / "manifest.json").write_text(json.dumps(
        vars(a) | {"clips": str(a.clips), "music": str(a.music) if a.music else None, "out": str(a.out)},
        indent=1, default=str,
    ) + "\n")
    print(a.out / "mix.wav")
    for w in windows:
        print("  ", w)


def build_music(a, total, total_n, windows):
    no_vocals = separate_music(a.music, a.out)
    nv = out = a.out / "_nv48.wav"
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(no_vocals), "-ar", str(SR), "-ac", "2", str(nv)])
    song_full = a.out / "_song48.wav"
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(a.music), "-ar", str(SR), "-ac", "2", str(song_full)])
    song, inst = load_wav(song_full), load_wav(nv)
    n = min(len(song), len(inst))
    song, inst = song[:n], inst[:n]
    if n < total_n:
        reps = int(np.ceil(total_n / n))
        song = np.tile(song, (reps, 1))[:total_n]
        inst = np.tile(inst, (reps, 1))[:total_n]
    song, inst = song[:total_n], inst[:total_n]
    nv.unlink(missing_ok=True)
    song_full.unlink(missing_ok=True)

    if a.carve_eq:
        carved = a.out / "_inst_carved.wav"
        sf.write(a.out / "_inst.wav", inst, SR, subtype="FLOAT")
        sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(a.out / "_inst.wav"), "-af",
            "equalizer=f=1200:t=o:w=1.2:g=-5,equalizer=f=3000:t=o:w=1.2:g=-6", str(carved)])
        inst = load_wav(carved)[:total_n]
        (a.out / "_inst.wav").unlink(missing_ok=True)
        carved.unlink(missing_ok=True)

    song_gain = 10 ** ((a.full_song_lufs - lufs_arr(song, a.out / "_s.wav")) / 20)
    bed_target = a.dialogue_lufs - a.gap_lu
    bed_gain = 10 ** ((bed_target - lufs_arr(inst, a.out / "_i.wav")) / 20)

    t = np.arange(total_n) / SR
    s0, s1 = min(w[1] for w in windows), max(w[2] for w in windows)
    duck = np.ones(total_n)
    duck[(t >= s0) & (t <= s1)] = 0.0
    down = (t >= s0 - a.duck_attack) & (t < s0)
    duck[down] = 0.5 + 0.5 * np.cos(np.pi * (t[down] - (s0 - a.duck_attack)) / a.duck_attack)
    up = (t > s1) & (t <= s1 + a.duck_release)
    duck[up] = 0.5 - 0.5 * np.cos(np.pi * (t[up] - s1) / a.duck_release)
    music = (song * song_gain) * duck[:, None] + (inst * bed_gain) * (1 - duck[:, None])
    fade = t > total - 0.8
    if fade.any():
        music[fade] *= np.linspace(1, 0, fade.sum())[:, None]

    return music


if __name__ == "__main__":
    main()
