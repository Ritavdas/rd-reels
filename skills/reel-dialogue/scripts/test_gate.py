import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gate import verdict


def report():
    return {
        "comparison": {
            "truth_sha256": "fixed-truth",
            "windows_sha256": "fixed-windows",
            "asr_model": "fixed-asr",
            "sample_rate": 16000,
            "has_music": True,
            "estoi_reference_sha256": "fixed-reference",
        },
        "mean_wer": 0.1,
        "mean_squim_stoi": 0.8,
        "lufs": -14,
        "true_peak_dbtp": -1,
        "duration_seconds": 45,
        "offset_seconds": 0,
        "min_gap_lu": 6,
        "clicks_at_cuts": [],
        "loudness_jumps": [],
        "segments": [
            {"seg": "01", "start": 0, "end": 2, "wer": 0.1, "squim_stoi": 0.8, "gap_lu": 6, "lag_ms": 0},
            {"seg": "02", "start": 3, "end": 5, "wer": 0.1, "squim_stoi": 0.8, "gap_lu": 6, "lag_ms": 0},
        ],
    }


class GateTests(unittest.TestCase):
    def setUp(self):
        self.base = report()
        self.candidate = copy.deepcopy(self.base)
        self.candidate["mean_squim_stoi"] = 0.85
        for row in self.candidate["segments"]:
            row["squim_stoi"] = 0.85

    def rejected(self):
        result, reasons = verdict(self.base, self.candidate)
        self.assertEqual(result, "NOT VERIFIED")
        self.assertTrue(reasons)

    def test_real_improvement_passes(self):
        self.assertEqual(verdict(self.base, self.candidate), ("VERIFIED", []))

    def test_equal_mix_fails(self):
        self.candidate = copy.deepcopy(self.base)
        self.rejected()

    def test_cleaner_score_with_damaged_words_fails(self):
        self.candidate["mean_wer"] = 0.2
        self.rejected()

    def test_individual_word_or_clarity_regression_fails(self):
        for key, value in (("wer", 0.201), ("squim_stoi", 0.749)):
            with self.subTest(key=key):
                self.candidate["segments"][0][key] = value
                self.rejected()
                self.candidate["segments"][0][key] = self.base["segments"][0][key]

    def test_missing_or_nonfinite_metrics_fail(self):
        for key in ("mean_wer", "mean_squim_stoi", "true_peak_dbtp", "min_gap_lu"):
            for value in (None, float("nan"), float("inf")):
                with self.subTest(key=key, value=value):
                    candidate = copy.deepcopy(self.candidate)
                    candidate[key] = value
                    self.assertEqual(verdict(self.base, candidate)[0], "NOT VERIFIED")

    def test_missing_context_truth_or_flags_fail(self):
        for key in ("comparison", "clicks_at_cuts", "loudness_jumps", "segments"):
            with self.subTest(key=key):
                candidate = copy.deepcopy(self.candidate)
                del candidate[key]
                self.assertEqual(verdict(self.base, candidate)[0], "NOT VERIFIED")
        self.candidate["comparison"]["truth_sha256"] = None
        self.rejected()

    def test_changed_comparison_inputs_fail(self):
        for key in self.candidate["comparison"]:
            with self.subTest(key=key):
                candidate = copy.deepcopy(self.candidate)
                candidate["comparison"][key] = "different"
                self.assertEqual(verdict(self.base, candidate)[0], "NOT VERIFIED")

    def test_missing_duplicate_or_retimed_segments_fail(self):
        candidates = [
            self.candidate["segments"][:1],
            [self.candidate["segments"][0]] * 2,
            [dict(self.candidate["segments"][0], start=0.1), self.candidate["segments"][1]],
        ]
        for segments in candidates:
            with self.subTest(segments=segments):
                candidate = dict(self.candidate, segments=segments)
                self.assertEqual(verdict(self.base, candidate)[0], "NOT VERIFIED")

    def test_bad_loudness_peak_gap_sync_and_artifacts_fail(self):
        for key, value in (
            ("lufs", -15.51), ("lufs", -13.49), ("true_peak_dbtp", -0.99),
            ("min_gap_lu", 5.99), ("duration_seconds", 45.034),
            ("offset_seconds", 0.01), ("clicks_at_cuts", [{"ratio": 5}]),
            ("loudness_jumps", [{"jump_lu": 7}]),
        ):
            with self.subTest(key=key):
                candidate = dict(self.candidate, **{key: value})
                self.assertEqual(verdict(self.base, candidate)[0], "NOT VERIFIED")
        self.candidate["segments"][0]["lag_ms"] = 33.34
        self.rejected()

    def test_missing_segment_score_or_gap_fails(self):
        for key in ("wer", "squim_stoi", "gap_lu", "lag_ms"):
            with self.subTest(key=key):
                candidate = copy.deepcopy(self.candidate)
                del candidate["segments"][0][key]
                self.assertEqual(verdict(self.base, candidate)[0], "NOT VERIFIED")

    def test_dialogue_only_does_not_need_music_gap(self):
        for r in (self.base, self.candidate):
            r["comparison"]["has_music"] = False
            del r["min_gap_lu"]
            for row in r["segments"]:
                del row["gap_lu"]
                del row["lag_ms"]
        self.assertEqual(verdict(self.base, self.candidate)[0], "VERIFIED")

    def test_cli_returns_failure_for_equal_mix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(self.base))
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("gate.py")), str(path), str(path)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("NOT VERIFIED", result.stdout)


if __name__ == "__main__":
    unittest.main()
