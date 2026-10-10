#!/usr/bin/env python3
import argparse
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from scipy.io import wavfile

RATE = 48000
FRAME_RATE = 30
FFMPEG = __import__("os").environ.get("FFMPEG", "/opt/homebrew/bin/ffmpeg")


def command(args):
    result = subprocess.run(args, capture_output=True, check=True)
    return result.stdout


def probe(path):
    return json.loads(
        command(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "stream=codec_type,duration,width,height,r_frame_rate,sample_rate,channels:format=duration",
                "-of", "json", str(path),
            ]
        )
    )


def video_hash(path):
    return command(
        [
            FFMPEG, "-v", "error", "-i", str(path), "-map", "0:v:0",
            "-c:v", "copy", "-f", "hash", "-hash", "sha256", "-",
        ]
    ).decode().strip()


def audio(path):
    raw = command(
        [
            FFMPEG, "-v", "error", "-i", str(path), "-map", "0:a:0",
            "-ac", "2", "-ar", str(RATE), "-f", "f32le", "-",
        ]
    )
    samples = np.frombuffer(raw, dtype="<f4")
    if samples.size == 0 or samples.size % 2:
        raise ValueError(f"Invalid decoded audio shape: {path}")
    return samples.reshape(-1, 2).copy()


def loudness(path):
    result = subprocess.run(
        [
            FFMPEG, "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
            "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True, text=True, check=True,
    )
    text = result.stderr
    report = json.loads(text[text.rindex("{"):text.rindex("}") + 1])
    return {
        "integrated_lufs": float(report["input_i"]),
        "true_peak_dbtp": float(report["input_tp"]),
        "range_lu": float(report["input_lra"]),
    }


def level(samples):
    if samples.size == 0:
        raise ValueError("Cannot measure an empty window")
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    return 20 * math.log10(max(rms, 1e-12))


def pcm_float(samples):
    if np.issubdtype(samples.dtype, np.integer):
        return samples.astype(np.float64) / (2 ** (np.iinfo(samples.dtype).bits - 1))
    return samples.astype(np.float64)


def stereo_pcm(samples):
    samples = pcm_float(samples)
    if samples.ndim == 1:
        return np.repeat(samples[:, None], 2, axis=1) / math.sqrt(2)
    if samples.ndim == 2 and samples.shape[1] == 2:
        return samples
    raise ValueError("Audio must be mono or stereo")


def baseline(path, output):
    report = {
        "source": str(path.resolve()),
        "probe": probe(path),
        "video_hash": video_hash(path),
        "loudness": loudness(path),
        "subjective_listening": "INCONCLUSIVE",
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def inspect_bank(manifest_path):
    manifest = json.loads(manifest_path.read_text())
    checks = []
    for cue in manifest["cues"]:
        rate, samples = wavfile.read(manifest_path.parent / cue["file"])
        assert rate == RATE, f"{cue['id']}: sample rate {rate}"
        assert samples.ndim == 2 and samples.shape[1] == 2, cue["id"]
        assert np.isfinite(samples).all(), cue["id"]
        assert len(samples) == cue["samples"], cue["id"]
        assert 0 <= cue["hit_sample"] < len(samples), cue["id"]
        assert 1e-5 < float(np.max(np.abs(samples))) < 1.0, cue["id"]
        assert abs(cue["scheduled_hit_sample"] / RATE - cue["hit_frame"] / FRAME_RATE) < 1 / RATE
        kernel = np.ones(round(RATE * 0.004)) / round(RATE * 0.004)
        energy = np.convolve(np.mean(np.square(samples.astype(np.float64)), axis=1), kernel, mode="same")
        observed_hit = int(np.argmax(energy))
        if cue.get("family") == "ambience":
            assert 0 <= observed_hit - cue["hit_sample"] <= round(0.08 * RATE), f"{cue['id']}: cut clink is not the loudest moment"
        else:
            assert abs(observed_hit - cue["hit_sample"]) <= 16, f"{cue['id']}: declared hit misses the waveform"
        mono = samples.mean(axis=1)
        stereo_rms = level(samples)
        mono_rms = level(mono)
        loss = mono_rms - stereo_rms
        assert loss >= -1.0, f"{cue['id']}: mono loss {loss:.2f} dB"
        checks.append({
            "id": cue["id"],
            "rate": rate,
            "samples": len(samples),
            "mono_level_change_db": round(loss, 3),
            "peak_dbfs": round(20 * math.log10(max(float(np.max(np.abs(samples))), 1e-12)), 3),
            "observed_hit_sample": observed_hit,
        })
    assert len(checks) <= manifest["limits"]["max_cues"]
    if manifest["limits"].get("unique_families"):
        families = [cue["family"] for cue in manifest["cues"]]
        repeated = sorted({f for f in families if families.count(f) > 1})
        assert not repeated, f"Sound family used more than once: {repeated}"
    return checks


def verify(final_path, baseline_path, manifest_path, output):
    old = json.loads(baseline_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    base = manifest_path.parent
    expected_duration = manifest["duration_seconds"]
    media = probe(final_path)
    actual_loudness = loudness(final_path)
    decoded = audio(final_path)
    checks = []

    def gate(name, passed, evidence):
        checks.append({"name": name, "verdict": "VERIFIED" if passed else "NOT VERIFIED", "evidence": evidence})

    new_hash = video_hash(final_path)
    gate("unchanged_video", new_hash == old["video_hash"], {"old": old["video_hash"], "new": new_hash})
    for kind in ("video", "audio"):
        streams = [s for s in media["streams"] if s["codec_type"] == kind]
        duration = float(streams[0]["duration"]) if streams else -1
        gate(f"{kind}_duration", abs(duration - expected_duration) <= 1 / FRAME_RATE, duration)
    gate("final_loudness", -15.5 <= actual_loudness["integrated_lufs"] <= -13.5, actual_loudness)
    gate("true_peak", actual_loudness["true_peak_dbtp"] <= -1.0, actual_loudness["true_peak_dbtp"])
    gate("finite_audio", bool(np.isfinite(decoded).all()), str(decoded.shape))
    gate("no_hard_clipping", float(np.max(np.abs(decoded))) < 1, float(np.max(np.abs(decoded))))

    cue_checks = inspect_bank(manifest_path)
    rate, effects = wavfile.read(base / manifest["effects_file"])
    mix_rate, mix = wavfile.read(base / manifest["mix_file"])
    voice_rate, voice = wavfile.read(manifest["voice_file"])
    assert rate == mix_rate == voice_rate == RATE
    count = int(round(expected_duration * RATE))
    assert len(effects) == len(mix) == count
    gain = 10 ** (manifest["constant_gain_db"] / 20)
    voice_stereo = stereo_pcm(voice[:count])
    reconstructed = (voice_stereo + effects.astype(np.float64)) * gain
    error = float(np.max(np.abs(mix.astype(np.float64) - reconstructed)))
    gate("unchanged_dialogue_pcm", error < 2e-6, {"maximum_error": error, "constant_gain_db": manifest["constant_gain_db"]})

    expected_effects = np.zeros_like(effects, dtype=np.float64)
    for cue in manifest["cues"]:
        _, rendered = wavfile.read(base / cue["file"])
        start = cue["start_sample"]
        end = start + len(rendered)
        assert start >= 0 and end <= count, cue["id"]
        expected_effects[start:end] += rendered.astype(np.float64)
    placement_error = float(np.max(np.abs(expected_effects - effects.astype(np.float64))))
    gate("exact_cue_placement", placement_error < 2e-6, {"maximum_error": placement_error})

    quiet_checks = []
    for window in manifest["quiet_windows"]:
        a = int(round(window["start"] * RATE))
        b = int(round(window["end"] * RATE))
        maximum = float(np.max(np.abs(effects[a:b])))
        quiet_checks.append({"label": window["label"], "maximum_effect_amplitude": maximum})
    gate("intentional_quiet_windows", all(x["maximum_effect_amplitude"] == 0 for x in quiet_checks), quiet_checks)

    pcm_size = len(mix)
    decoded_trim = decoded[:pcm_size].astype(np.float64)
    difference = decoded_trim - mix[:len(decoded_trim)].astype(np.float64)
    snr = level(mix[:len(decoded_trim)]) - level(difference)
    gate("encoded_audio_matches_pcm", snr >= 26, {"snr_db": round(snr, 2), "decoded_samples": len(decoded)})

    report = {
        "file": str(final_path.resolve()),
        "verdict": "VERIFIED" if all(c["verdict"] == "VERIFIED" for c in checks) else "NOT VERIFIED",
        "scope": "Technical gates only. A human listening review is still required.",
        "checks": checks,
        "cue_checks": cue_checks,
        "subjective_listening": "INCONCLUSIVE",
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"verdict": report["verdict"], "checks": checks}, indent=2))
    if report["verdict"] != "VERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    base = sub.add_parser("baseline")
    base.add_argument("video", type=Path)
    base.add_argument("output", type=Path)
    check = sub.add_parser("verify")
    check.add_argument("video", type=Path)
    check.add_argument("baseline", type=Path)
    check.add_argument("manifest", type=Path)
    check.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.mode == "baseline":
        baseline(args.video, args.output)
    else:
        verify(args.video, args.baseline, args.manifest, args.output)
