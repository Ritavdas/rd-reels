import json
import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from check_audio import FFMPEG, RATE, baseline, inspect_bank, pcm_float, stereo_pcm, verify
from design_sounds import build, resolve


class AudioGateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        samples = np.zeros((4800, 2), dtype=np.float32)
        samples[240:600] = 0.04
        wavfile.write(self.path / "tap.wav", RATE, samples)
        self.manifest = {
            "limits": {"max_cues": 14},
            "cues": [{
                "id": "tap",
                "file": "tap.wav",
                "samples": len(samples),
                "hit_sample": 336,
                "scheduled_hit_sample": 48000,
                "hit_frame": 30,
            }],
        }
        self.write_manifest()

    def write_manifest(self):
        self.manifest_path = self.path / "manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest))

    def test_real_stereo_wav_passes(self):
        report = inspect_bank(self.manifest_path)
        self.assertEqual(report[0]["rate"], RATE)
        self.assertEqual(report[0]["mono_level_change_db"], 0)

    def test_wrong_rate_is_not_accepted(self):
        _, samples = wavfile.read(self.path / "tap.wav")
        wavfile.write(self.path / "tap.wav", 44100, samples)
        with self.assertRaises(AssertionError):
            inspect_bank(self.manifest_path)

    def test_silent_cue_is_not_accepted(self):
        wavfile.write(self.path / "tap.wav", RATE, np.zeros((4800, 2), dtype=np.float32))
        with self.assertRaises(AssertionError):
            inspect_bank(self.manifest_path)

    def test_wrong_frame_alignment_is_not_accepted(self):
        self.manifest["cues"][0]["scheduled_hit_sample"] += 100
        self.write_manifest()
        with self.assertRaises(AssertionError):
            inspect_bank(self.manifest_path)

    def test_invented_waveform_hit_is_not_accepted(self):
        self.manifest["cues"][0]["hit_sample"] = 4000
        self.write_manifest()
        with self.assertRaises(AssertionError):
            inspect_bank(self.manifest_path)

    def test_repeated_sound_family_is_not_accepted(self):
        second = dict(self.manifest["cues"][0], id="tap_again")
        self.manifest["cues"].append(second)
        self.manifest["limits"] = {"max_cues": 5, "unique_families": True}
        self.manifest["cues"][0]["family"] = second["family"] = "tap"
        self.write_manifest()
        with self.assertRaises(AssertionError):
            inspect_bank(self.manifest_path)

    def test_phase_cancelled_mono_is_not_accepted(self):
        _, samples = wavfile.read(self.path / "tap.wav")
        samples[:, 1] *= -1
        wavfile.write(self.path / "tap.wav", RATE, samples)
        with self.assertRaises(AssertionError):
            inspect_bank(self.manifest_path)

    def test_integer_pcm_is_normalized(self):
        actual = pcm_float(np.array([-32768, 0, 16384], dtype=np.int16))
        np.testing.assert_allclose(actual, [-1.0, 0.0, 0.5], rtol=0, atol=0)

    def test_stereo_mix_preserves_both_channels(self):
        samples = np.array([[0.1, 0.3], [-0.2, 0.4]], dtype=np.float32)
        np.testing.assert_array_equal(stereo_pcm(samples), samples)

    def test_mono_keeps_existing_equal_power_mapping(self):
        samples = np.array([0.2, -0.1], dtype=np.float32)
        expected = np.repeat(samples.astype(np.float64)[:, None], 2, axis=1) / np.sqrt(2)
        np.testing.assert_array_equal(stereo_pcm(samples), expected)

    def test_more_than_two_channels_is_rejected(self):
        with self.assertRaises(ValueError):
            stereo_pcm(np.zeros((10, 3)))


class StereoPipelineTests(unittest.TestCase):
    def test_effects_preserve_stereo_music_mix_and_verify_encoded_video(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            time = np.arange(3 * RATE) / RATE
            fixed = np.column_stack((0.2 * np.sin(2 * np.pi * 440 * time),
                                     0.15 * np.sin(2 * np.pi * 660 * time))).astype(np.float32)
            raw = root / "raw.wav"
            wavfile.write(raw, RATE, fixed)
            mix = root / "fixed.wav"
            subprocess.run([
                FFMPEG, "-v", "error", "-i", str(raw), "-af", "loudnorm=I=-14:TP=-2:LRA=11",
                "-ar", str(RATE), "-c:a", "pcm_f32le", str(mix),
            ], check=True)
            picture = root / "picture.mp4"
            subprocess.run([
                FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=3",
                "-i", str(mix), "-c:v", "libx264", "-c:a", "aac", "-b:a", "256k", "-t", "3",
                str(picture),
            ], check=True)
            timeline = root / "timeline.json"
            timeline.write_text(json.dumps({
                "voice": str(mix), "dialogue": str(raw), "picture": str(picture),
                "duration_seconds": 3, "quiet_windows": [{"label": "CTA", "start": 2, "end": 3}],
            }))
            plan = root / "cues.json"
            plan.write_text(json.dumps([{
                "id": "proof", "family": "tap", "at": {"frame": 30},
                "frames": 8, "gap_db": 13, "reason": "Mark the proof beat",
            }]))
            old = root / "baseline.json"
            report = root / "verification.json"
            with contextlib.redirect_stdout(io.StringIO()):
                baseline(picture, old)
                final, manifest = build(plan, timeline, root, "final")
                verify(final, old, manifest, report)
            result = json.loads(report.read_text())
            self.assertEqual(result["verdict"], "VERIFIED")
            _, rendered = wavfile.read(manifest.parent / "mix.wav")
            _, effects = wavfile.read(manifest.parent / "effects.wav")
            _, original = wavfile.read(mix)
            gain = 10 ** (-0.35 / 20)
            np.testing.assert_allclose(rendered / gain - effects, original, atol=5e-8)

    def test_real_sound_files_peak_on_their_frame_and_verify(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            time = np.arange(3 * RATE) / RATE
            voice = np.column_stack((0.2 * np.sin(2 * np.pi * 440 * time),) * 2).astype(np.float32)
            raw = root / "raw.wav"
            wavfile.write(raw, RATE, voice)
            mix = root / "fixed.wav"
            subprocess.run([FFMPEG, "-v", "error", "-i", str(raw), "-af", "loudnorm=I=-14:TP=-2:LRA=11",
                            "-ar", str(RATE), "-c:a", "pcm_f32le", str(mix)], check=True)
            picture = root / "picture.mp4"
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=3",
                            "-i", str(mix), "-c:v", "libx264", "-c:a", "aac", "-b:a", "256k", "-t", "3", str(picture)], check=True)
            timeline = root / "timeline.json"
            timeline.write_text(json.dumps({"voice": str(mix), "picture": str(picture), "duration_seconds": 3, "quiet_windows": []}))
            # A 44.1 kHz stereo riser that builds for 1 s, and an impact that hits 50 ms in.
            sfx = root / "sfx"
            sfx.mkdir()
            rng = np.random.default_rng(3)
            n = 44100
            riser = (rng.standard_normal(n) * np.linspace(0, 1, n) ** 3).astype(np.float32)
            wavfile.write(sfx / "riser.wav", 44100, np.column_stack((riser, riser)))
            impact = np.zeros(n // 2, dtype=np.float32)
            impact[2205:] = (rng.standard_normal(n // 2 - 2205) * np.exp(-np.arange(n // 2 - 2205) / 3000)).astype(np.float32)
            wavfile.write(sfx / "impact.wav", 44100, impact)
            plan = root / "cues.json"
            plan.write_text(json.dumps([
                {"id": "build", "family": "riser", "file": "sfx/riser.wav", "source": "test", "at": {"frame": 45}, "gap_db": 10, "reason": "Build into the reveal"},
                {"id": "hit", "family": "impact", "file": "sfx/impact.wav", "source": "test", "license": "CC0", "at": {"frame": 70}, "gap_db": 8, "reason": "Flash cut"},
            ]))
            old = root / "baseline.json"
            report = root / "verification.json"
            with contextlib.redirect_stdout(io.StringIO()):
                baseline(picture, old)
                final, manifest = build(plan, timeline, root, "final")
                verify(final, old, manifest, report)
            self.assertEqual(json.loads(report.read_text())["verdict"], "VERIFIED")
            cues = {c["id"]: c for c in json.loads(manifest.read_text())["cues"]}
            self.assertLess(cues["build"]["start_seconds"], 45 / 30 - 0.8)  # the build starts well before the reveal
            self.assertAlmostEqual(cues["hit"]["start_seconds"], 70 / 30 - 0.05, delta=0.01)
            self.assertEqual(cues["hit"]["license"], "CC0")

    def test_file_cue_without_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wavfile.write(root / "pop.wav", RATE, np.ones(RATE // 10, dtype=np.float32) * 0.5)
            plan = [{"id": "pop", "family": "pop", "file": "pop.wav", "at": {"frame": 10}}]
            with self.assertRaisesRegex(ValueError, "source"):
                resolve(plan, {}, root)


if __name__ == "__main__":
    unittest.main()
