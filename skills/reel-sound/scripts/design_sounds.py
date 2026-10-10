#!/usr/bin/env python3
"""rd-reels sound designer.

Reads <reel>.timeline.json (written by reel-edit) and a cue plan, synthesizes one original sound per
story beat, mixes them under the unchanged voice, and remuxes the picture with stream copy.

Cue plan (JSON list). Each cue:
  {"id": "hook_tap", "family": "confirm", "at": {"beat": "face_hook", "offset": 15},
   "frames": 6, "pan": 0.0, "pan_end": null, "gap_db": 12, "reason": "Hook lands the prompt."}
"at" is either {"beat": NAME, "offset": FRAMES} (offset from the beat start), {"mark": NAME, "offset": FRAMES},
or {"frame": N}. Families: confirm, tap, reject, release, slide, marker, counter, bloom, ambience.
For "ambience" (an off-screen world-sound J-cut) the hit is the cut frame, "frames" is total length, and
"lead" (frames, default 12) is how early it starts before the cut.

Usage: design_sounds.py PLAN.json TIMELINE.json OUT_DIR [--name NAME] [--material paper|digital] [--allow-repeats]
"""
import argparse
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

from check_audio import FRAME_RATE, RATE, inspect_bank, level, stereo_pcm

FFMPEG = "/opt/homebrew/bin/ffmpeg"
ROOM = {"rt60": 0.32, "wet": 0.22}
AMBIENCE = {"rt60": 1.1, "wet": 0.55, "lowpass_hz": 2800, "level_dbfs": -40.0, "lead_frames": 12}
FAMILIES = ("confirm", "tap", "reject", "release", "slide", "marker", "counter", "bloom", "ambience")


@dataclass(frozen=True)
class Cue:
    id: str
    family: str
    hit_frame: int
    duration_frames: int
    pan: float
    gap_db: float
    reason: str
    pan_end: float | None = None
    lead_frames: int = AMBIENCE["lead_frames"]


def resolve(plan, timeline):
    cues = []
    for c in plan:
        where = c["at"]
        if "beat" in where:
            base = timeline["beats"][where["beat"]]["start"]
        elif "mark" in where:
            base = timeline["marks"][where["mark"]]
        else:
            base = 0
        hit = base + int(where.get("offset", where.get("frame", 0)))
        if c["family"] not in FAMILIES:
            raise ValueError(f"{c['id']}: unknown family {c['family']}")
        cues.append(Cue(c["id"], c["family"], hit, int(c["frames"]), float(c.get("pan", 0.0)), float(c.get("gap_db", 12)),
                        c.get("reason", ""), c.get("pan_end"), int(c.get("lead", AMBIENCE["lead_frames"]))))
    return cues


def shaped_noise(rng, count, low, high):
    noise = rng.standard_normal(count)
    filtered = signal.sosfilt(signal.butter(3, [low, high], btype="bandpass", fs=RATE, output="sos"), noise)
    return filtered / max(float(np.std(filtered)), 1e-8)


def fade_edges(samples, attack_ms=1.2, release_ms=12):
    result = samples.copy()
    attack = min(len(result) // 2, round(RATE * attack_ms / 1000))
    release = min(len(result) // 2, round(RATE * release_ms / 1000))
    if attack:
        result[:attack] *= np.sin(np.linspace(0, math.pi / 2, attack)) ** 2
    if release:
        result[-release:] *= np.cos(np.linspace(0, math.pi / 2, release)) ** 2
    return result


def modal_tap(rng, count, material, character="tap"):
    """A struck object: noise excitation through three damped resonant modes."""
    t = np.arange(count) / RATE
    frequency_scale = 1.0 if material == "paper" else 1.24
    damping_scale = 1.0 if material == "paper" else 1.4
    if character == "reject":
        frequency_scale *= 0.72
        damping_scale *= 1.65
    elif character == "release":
        frequency_scale *= 1.07
        damping_scale *= 0.65
    elif character == "confirm":
        frequency_scale *= 1.05
    excitation = shaped_noise(rng, count, 280, 2600) * np.exp(-t * 720)
    body = np.zeros(count)
    for frequency, weight, decay in [(640, 1.0, 23), (1390, 0.35, 35), (2510, 0.1, 60)]:
        theta = 2 * math.pi * frequency * frequency_scale / RATE
        radius = math.exp(-decay * damping_scale / RATE)
        mode = signal.lfilter([1.0], [1.0, -2 * radius * math.cos(theta), radius * radius], excitation)
        mode /= max(float(np.max(np.abs(mode))), 1e-8)
        body += mode * weight
    texture = shaped_noise(rng, count, 350, 2800) * np.exp(-t * 180)
    texture_weight = 0.15 if material == "paper" else 0.07
    attack = 1 - np.exp(-t * 1600)
    return fade_edges((body + texture * texture_weight) * attack, 0.8, 18)


def room(samples, rng, rt60, wet, lowpass_hz=None):
    """Synthetic room: 4 ms predelay, exponential tail, damped highs. Pads so the tail is not cut."""
    n = int(RATE * rt60 * 1.1)
    t = np.arange(n) / RATE
    ir = rng.standard_normal(n) * np.exp(-6.9 * t / rt60)
    ir[:int(0.004 * RATE)] = 0
    ir = signal.sosfilt(signal.butter(1, 5000, fs=RATE, output="sos"), ir)
    ir /= math.sqrt(float(np.sum(ir * ir)))
    padded = np.concatenate([samples, np.zeros(n)])
    tail = signal.fftconvolve(padded, ir)[:len(padded)]
    tail *= float(np.std(samples)) / max(float(np.std(tail)), 1e-9)
    out = (1 - wet) * padded + wet * tail
    if lowpass_hz:
        out = signal.sosfilt(signal.butter(2, lowpass_hz, fs=RATE, output="sos"), out)
    return out


def synthesize(cue, material, rng):
    count = round(cue.duration_frames / FRAME_RATE * RATE)
    t = np.arange(count) / RATE
    if cue.family in ("tap", "confirm", "reject", "release"):
        samples = modal_tap(rng, count, material, cue.family)
    elif cue.family == "slide":
        texture = shaped_noise(rng, count, 280 if material == "paper" else 600, 2550 if material == "paper" else 3500)
        p = np.linspace(0, 1, count)
        movement = np.exp(-0.5 * ((p - 0.46) / 0.19) ** 2)
        roughness = 0.82 + 0.12 * np.sin(2 * math.pi * 37 * t) + 0.06 * np.sin(2 * math.pi * 71 * t)
        samples = texture * movement * roughness
        landing = modal_tap(rng, round(RATE * 0.09), material)
        index = round(count * 0.46)
        available = min(len(landing), count - index)
        samples[index:index + available] += landing[:available] * (0.25 if material == "paper" else 0.4)
        samples = fade_edges(samples, 8, 25)
    elif cue.family == "marker":
        texture = shaped_noise(rng, count, 650, 2800 if material == "paper" else 3900)
        p = np.linspace(0, 1, count)
        nib = np.exp(-p * 3.4) * np.sin(np.minimum(p * 12, 1) * math.pi / 2)
        second_line = 0.44 * np.exp(-0.5 * ((p - 0.36) / 0.095) ** 2)
        grains = 0.73 + 0.18 * np.sin(2 * math.pi * 89 * t) + 0.09 * np.sin(2 * math.pi * 143 * t)
        samples = fade_edges(texture * (nib + second_line) * grains, 7, 35)
    elif cue.family == "counter":
        samples = np.zeros(count)
        usable = cue.duration_frames / FRAME_RATE - 0.14
        pulse_times = np.array([0.007, 0.048, 0.098, 0.160, 0.235, 0.325, 0.435, 0.555]) * usable / 0.555
        for index, position in enumerate(pulse_times):
            pulse = signal.sosfilt(signal.butter(2, 2400, fs=RATE, output="sos"), modal_tap(rng, round(RATE * 0.085), material))
            pulse *= (0.16 + 0.035 * index) * (2.5 if index == len(pulse_times) - 1 else 1)
            start = round(position * RATE)
            available = min(len(pulse), count - start)
            samples[start:start + available] += pulse[:available]
        samples = fade_edges(samples, 1, 16)
    elif cue.family == "bloom":
        p = np.linspace(0, 1, count)
        swell = np.sin(np.minimum(p / 0.35, 1) * math.pi / 2) ** 2 * np.exp(-np.maximum(p - 0.35, 0) * 5)
        air = shaped_noise(rng, count, 300, 1400) * 0.35
        tone = (np.sin(2 * math.pi * 196 * t) + 0.45 * np.sin(2 * math.pi * 294 * t + 0.6)) * 0.8
        samples = fade_edges((air + tone) * swell, 25, 60)
    elif cue.family == "ambience":
        lead = cue.lead_frames / FRAME_RATE
        bed = signal.sosfilt(signal.butter(2, [60, 500], btype="bandpass", fs=RATE, output="sos"), rng.standard_normal(count))
        bed /= max(float(np.std(bed)), 1e-8)
        envelope = np.clip(np.minimum(t / lead, 1.0) * np.minimum((t[-1] - t) / 1.2, 1.0), 0, 1)
        samples = bed * 0.07 * envelope
        for position, weight in [(lead, 1.0), (lead + 1.35, 0.4), (lead + 2.7, 0.32)]:
            clink = signal.sosfilt(signal.butter(2, 2500, fs=RATE, output="sos"), modal_tap(rng, round(RATE * 0.25), "digital", "tap"))
            clink = clink / max(float(np.max(np.abs(clink))), 1e-8) * weight
            start = round(position * RATE)
            available = min(len(clink), count - start)
            if available > 0:
                samples[start:start + available] += clink[:available]
        samples = room(samples, rng, AMBIENCE["rt60"], AMBIENCE["wet"], AMBIENCE["lowpass_hz"])
    if cue.family != "ambience":
        samples = room(samples, rng, ROOM["rt60"], ROOM["wet"])
    speech_band = signal.sosfilt(signal.butter(2, [1000, 4000], btype="bandpass", fs=RATE, output="sos"), samples)
    samples = samples - 0.5 * speech_band
    samples = signal.sosfilt(signal.butter(2, 170, btype="highpass", fs=RATE, output="sos"), samples)
    samples = fade_edges(samples, 0.8, 10)
    maximum = float(np.max(np.abs(samples)))
    if not math.isfinite(maximum) or maximum <= 1e-8:
        raise ValueError(f"Invalid synthesis for {cue.id}")
    samples /= maximum
    energy = np.convolve(np.square(samples), np.ones(round(RATE * 0.004)) / round(RATE * 0.004), mode="same")
    hit_sample = int(np.argmax(energy))
    if cue.family == "ambience":
        expected = round(cue.lead_frames / FRAME_RATE * RATE)
        if not 0 <= hit_sample - expected <= round(0.08 * RATE):
            raise ValueError(f"{cue.id}: loudest point at {hit_sample / RATE:.2f}s, not within 80 ms after the cut clink at {expected / RATE:.2f}s")
        hit_sample = expected
    return samples, hit_sample


def build(plan_path, timeline_path, out_dir, name, material="digital", allow_repeats=False, max_cues=None):
    timeline = json.loads(Path(timeline_path).read_text())
    plan = json.loads(Path(plan_path).read_text())
    cues = resolve(plan, timeline)
    out = Path(out_dir)
    if (out / f"{name}.mp4").resolve() == Path(timeline["picture"]).resolve():
        raise SystemExit(f"--name {name} would overwrite the picture. Use a different name, e.g. {name}_final.")
    bank = out / f"{name}_sfx"
    bank.mkdir(parents=True, exist_ok=True)
    duration = timeline["duration_seconds"]
    count = round(duration * RATE)
    rate, voice = wavfile.read(timeline["voice"])
    if rate != RATE or len(voice) < count:
        raise ValueError("The fixed audio must be 48 kHz and cover the full reel")
    voice_stereo = stereo_pcm(voice[:count])
    reference = voice_stereo
    if timeline.get("dialogue"):
        reference_rate, dialogue = wavfile.read(timeline["dialogue"])
        if reference_rate != RATE or len(dialogue) < count:
            raise ValueError("The dialogue reference must be 48 kHz and cover the full reel")
        reference = stereo_pcm(dialogue[:count])
    effects = np.zeros((count, 2), dtype=np.float64)
    records = []
    for cue in cues:
        seed = int.from_bytes(hashlib.sha256((cue.id + material).encode()).digest()[:4], "little")
        raw, hit_sample = synthesize(cue, material, np.random.default_rng(seed))
        scheduled_hit = round(cue.hit_frame / FRAME_RATE * RATE)
        start = scheduled_hit - hit_sample
        end = start + len(raw)
        if start < 0 or end > count:
            raise ValueError(f"Cue outside the reel: {cue.id} ({start / RATE:.2f}-{end / RATE:.2f}s of {duration:.2f}s)")
        angle = (cue.pan + 1) * math.pi / 4 if cue.pan_end is None else (np.linspace(cue.pan, cue.pan_end, len(raw)) + 1) * math.pi / 4
        stereo = np.column_stack((raw * np.cos(angle), raw * np.sin(angle)))
        window_start = max(start, scheduled_hit - round(RATE * 0.060))
        window_end = min(end, scheduled_hit + round(RATE * 0.100))
        reference_db = level(reference[window_start:window_end])
        if cue.family == "ambience":
            gain_db = AMBIENCE["level_dbfs"] - level(stereo)
        else:
            target_db = min(-23.0, max(-32.0, max(reference_db, -25) - cue.gap_db))
            gain_db = target_db - level(stereo[window_start - start:window_end - start])
        scaled = stereo * 10 ** (gain_db / 20)
        peak_limit = 10 ** (-12 / 20)
        if float(np.max(np.abs(scaled))) > peak_limit:
            reduction = peak_limit / float(np.max(np.abs(scaled)))
            scaled *= reduction
            gain_db += 20 * math.log10(reduction)
        rendered = scaled.astype(np.float32)
        wavfile.write(bank / f"{cue.id}.wav", RATE, rendered)
        effects[start:end] += rendered
        records.append({
            "id": cue.id, "family": cue.family, "file": f"{cue.id}.wav", "samples": len(rendered), "sample_rate": RATE,
            "hit_sample": hit_sample, "scheduled_hit_sample": scheduled_hit, "hit_frame": cue.hit_frame,
            "start_sample": start, "start_seconds": round(start / RATE, 6), "end_seconds": round(end / RATE, 6),
            "applied_gain_db": round(gain_db, 4), "voice_window_rms_dbfs": round(reference_db, 3),
            "pan": cue.pan, "pan_end": cue.pan_end, "gap_db": cue.gap_db, "material": material,
            "reason": cue.reason, "seed": seed, "provenance": "Original deterministic local synthesis. No samples or external generators.",
        })
    wavfile.write(bank / "effects.wav", RATE, effects.astype(np.float32))
    gain_db = -0.35
    wavfile.write(bank / "mix.wav", RATE, ((voice_stereo + effects) * 10 ** (gain_db / 20)).astype(np.float32))
    manifest = {
        "name": name, "source_video": timeline["picture"], "voice_file": timeline["voice"], "duration_seconds": duration,
        "sample_rate": RATE, "effects_file": "effects.wav", "mix_file": "mix.wav", "constant_gain_db": gain_db,
        "limits": {"max_cues": max_cues or max(len(records), 1), "unique_families": not allow_repeats},
        "quiet_windows": timeline.get("quiet_windows", []), "cues": records, "subjective_listening": "INCONCLUSIVE",
    }
    mpath = bank / "manifest.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n")
    inspect_bank(mpath)
    final = out / f"{name}.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", timeline["picture"], "-i", str(bank / "mix.wav"), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-t", f"{duration:.3f}", "-movflags", "+faststart", str(final)], check=True)
    print(f"{name}: {len(records)} cues, bank checks VERIFIED -> {final}")
    for r in records:
        print(f"  {r['id']:20s} {r['family']:9s} hit {r['hit_frame'] / FRAME_RATE:6.2f}s  {r['reason']}")
    return final, mpath


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("timeline")
    ap.add_argument("out_dir")
    ap.add_argument("--name", default="final")
    ap.add_argument("--material", choices=("paper", "digital"), default="digital")
    ap.add_argument("--allow-repeats", action="store_true")
    a = ap.parse_args()
    build(a.plan, a.timeline, a.out_dir, a.name, a.material, a.allow_repeats)
