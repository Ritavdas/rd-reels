import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from check_audio import RATE, inspect_bank, pcm_float


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


if __name__ == "__main__":
    unittest.main()
