import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

import dialogue_mix
import listen_map
import measure


class InspectionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.audio = self.root / "speech.wav"
        rng = np.random.default_rng(42)
        self.samples = rng.normal(0, 0.08, 3 * 48000)
        sf.write(self.audio, self.samples, 48000, subtype="FLOAT")
        self.windows = self.root / "windows.json"
        self.windows.write_text(json.dumps({"windows": [["01", 0, 1], ["02", 1, 2]]}))
        self.truth = self.root / "truth.json"
        self.truth.write_text(json.dumps({"01": "six times", "02": "four three"}))

    def run_measure(self, *extra):
        out = self.root / "report.json"
        args = ["measure.py", str(self.audio), str(self.windows), str(out),
                "--truth", str(self.truth), *map(str, extra)]
        with patch("sys.argv", args), patch.object(measure, "squim", return_value=(0.8, 12)), \
                patch.object(measure, "asr", side_effect=["six times", "four three"]), \
                contextlib.redirect_stdout(io.StringIO()):
            measure.main()
        return json.loads(out.read_text())

    def test_measurement_decodes_render_and_records_fixed_inputs(self):
        report = self.run_measure()
        self.assertEqual(report["mean_wer"], 0)
        self.assertEqual(report["duration_seconds"], 3)
        self.assertTrue(np.isfinite(report["true_peak_dbtp"]))
        self.assertEqual(report["offset_seconds"], 0)
        self.assertEqual(report["comparison"]["sample_rate"], 16000)
        self.assertEqual(len(report["comparison"]["truth_sha256"]), 64)
        self.assertEqual(report["segments"][1]["end"], 2)

    def test_missing_truth_window_fails(self):
        self.truth.write_text(json.dumps({"01": "six times"}))
        with self.assertRaisesRegex(ValueError, "exactly"):
            self.run_measure()

    def test_short_or_out_of_range_window_fails(self):
        for end in (0.2, 4):
            with self.subTest(end=end):
                self.windows.write_text(json.dumps({"windows": [["01", 0, end], ["02", 1, 2]]}))
                with self.assertRaises(ValueError):
                    self.run_measure()

    def test_partial_stems_fail(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_measure("--dialogue", self.audio)

    def test_negative_offset_fails(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_measure("--offset", -0.1)

    def test_music_measurements_use_fixed_estoi_reference(self):
        music = self.root / "music.wav"
        sf.write(music, self.samples * 0.05, 48000, subtype="FLOAT")
        report = self.run_measure(
            "--dialogue", self.audio, "--music", music, "--reference-dialogue", self.audio,
        )
        self.assertTrue(report["comparison"]["has_music"])
        self.assertEqual(len(report["comparison"]["estoi_reference_sha256"]), 64)
        self.assertGreater(report["min_gap_lu"], 20)
        self.assertEqual(report["segments"][0]["lag_ms"], 0)
        self.assertGreater(report["segments"][0]["estoi"], 0.99)

    def test_wer_catches_changed_words_and_rejects_empty_truth(self):
        self.assertGreater(measure.wer("six times", "take sex in"), 0)
        self.assertEqual(measure.wer("Hello, WORLD!", "hello world"), 0)
        with self.assertRaises(ValueError):
            measure.wer("", "something")

    def test_bad_audio_and_short_loudness_fail_explicitly(self):
        with self.assertRaises(subprocess.CalledProcessError):
            measure.load(self.root / "missing.wav")
        with self.assertRaisesRegex(ValueError, "400"):
            measure.lu(np.zeros(100))

    def test_map_renders_waveform_spectrogram_and_masking(self):
        music = self.root / "music.wav"
        sf.write(music, self.samples * 0.05, 48000, subtype="FLOAT")
        out = self.root / "map.png"
        with patch("sys.argv", ["listen_map.py", str(self.audio), str(out),
                                "--dialogue", str(self.audio), "--music", str(music)]), \
                contextlib.redirect_stdout(io.StringIO()):
            listen_map.main()
        self.assertEqual(out.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertGreater(out.stat().st_size, 10000)

    def test_map_rejects_misaligned_stems(self):
        short = self.root / "short.wav"
        sf.write(short, self.samples[:48000], 48000, subtype="FLOAT")
        with patch("sys.argv", ["listen_map.py", str(self.audio), str(self.root / "map.png"),
                                "--dialogue", str(short), "--music", str(self.audio)]):
            with self.assertRaisesRegex(ValueError, "duration"):
                listen_map.main()
        listen_map.plt.close("all")

    def test_leveling_preserves_exact_duration_and_float_stems(self):
        clips = self.root / "clips.json"
        clips.write_text(json.dumps({"clips": [
            {"id": "02", "path": str(self.audio), "start": 1, "in": 1, "out": 2},
            {"id": "01", "path": str(self.audio), "start": 0, "in": 0, "out": 1},
        ]}))
        out = self.root / "mix"
        with patch("sys.argv", ["dialogue_mix.py", "--clips", str(clips),
                                "--duration", "3", "--out", str(out)]), \
                contextlib.redirect_stdout(io.StringIO()):
            dialogue_mix.main()
        data, rate = sf.read(out / "mix.wav")
        self.assertEqual(data.shape, (3 * 48000, 2))
        self.assertEqual(rate, 48000)
        self.assertEqual(sf.info(out / "stem_dialogue.wav").subtype, "FLOAT")
        self.assertEqual(sf.info(out / "mix.wav").subtype, "FLOAT")
        self.assertLess(np.max(np.abs(data)), 1)
        windows = json.loads((out / "windows.json").read_text())["windows"]
        self.assertEqual([row[0] for row in windows], ["01", "02"])
        lag = measure.align(measure.load(out / "stem_dialogue.wav"), measure.load(out / "mix.wav"))
        self.assertLessEqual(abs(lag), 1)


if __name__ == "__main__":
    unittest.main()
