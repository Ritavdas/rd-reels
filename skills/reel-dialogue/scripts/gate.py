#!/usr/bin/env python3
"""gate.py: apply the ship predicate from reel-dialogue/SKILL.md to measure.py reports.

A candidate is VERIFIED only if it is strictly better than the baseline, never merely
equal -- a baseline compared against itself must print NOT VERIFIED, which is also how
this script tests itself.

usage: gate.py BASELINE.json CANDIDATE.json [CANDIDATE.json ...]
"""
import json
import math
import sys


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def verdict(base: dict, cand: dict) -> tuple[str, list[str]]:
    fails = []
    context = base.get("comparison")
    if (not context or not context.get("truth_sha256")
            or not context.get("windows_sha256") or not context.get("asr_model")
            or context != cand.get("comparison")):
        fails.append("missing or different comparison context (truth, windows, ASR, reference)")
    for label, report in (("baseline", base), ("candidate", cand)):
        for key in ("mean_wer", "mean_squim_stoi", "lufs", "true_peak_dbtp", "duration_seconds", "offset_seconds"):
            if not finite(report.get(key)):
                fails.append(f"{label}: missing/non-finite {key}")
        if not report.get("segments"):
            fails.append(f"{label}: no segments")
        for key in ("clicks_at_cuts", "loudness_jumps"):
            if not isinstance(report.get(key), list):
                fails.append(f"{label}: missing {key}")
    if fails:
        return "NOT VERIFIED", fails
    if "mean_wer" in base and "mean_wer" in cand and cand["mean_wer"] > base["mean_wer"]:
        fails.append(f"mean WER {cand['mean_wer']} > {base['mean_wer']}")
    if "mean_squim_stoi" in base and cand.get("mean_squim_stoi", -1) <= base["mean_squim_stoi"]:
        fails.append(f"mean STOI {cand.get('mean_squim_stoi')} not > {base['mean_squim_stoi']}")
    base_by_seg = {r["seg"]: r for r in base["segments"]}
    cand_by_seg = {r["seg"]: r for r in cand["segments"]}
    if (base_by_seg.keys() != cand_by_seg.keys()
            or len(base_by_seg) != len(base["segments"])
            or len(cand_by_seg) != len(cand["segments"])):
        fails.append("segment coverage differs or IDs repeat")
    for r in cand["segments"]:
        b = base_by_seg.get(r["seg"])
        if not b:
            continue
        if (r.get("start"), r.get("end")) != (b.get("start"), b.get("end")):
            fails.append(f"seg {r['seg']} timing differs")
        if not all(finite(row.get(key)) for row in (b, r) for key in ("wer", "squim_stoi")):
            fails.append(f"seg {r['seg']} missing/non-finite WER or STOI")
            continue
        if "wer" in b and "wer" in r and r["wer"] - b["wer"] > 0.10:
            fails.append(f"seg {r['seg']} WER {b['wer']}->{r['wer']}")
        if "squim_stoi" in b and b["squim_stoi"] - r.get("squim_stoi", 0) > 0.05:
            fails.append(f"seg {r['seg']} STOI {b['squim_stoi']}->{r['squim_stoi']}")
        if context.get("has_music"):
            if not finite(r.get("gap_lu")) or r["gap_lu"] < 6:
                fails.append(f"seg {r['seg']} missing/low speech-to-music gap")
            if not finite(r.get("lag_ms")) or abs(r["lag_ms"]) > 1000 / 30:
                fails.append(f"seg {r['seg']} missing/excessive audio lag")
    if context.get("has_music") and (
            not finite(cand.get("min_gap_lu")) or cand["min_gap_lu"] < 6):
        fails.append("missing/low minimum speech-to-music gap")
    if cand.get("clicks_at_cuts") or cand.get("loudness_jumps"):
        fails.append("click/jump flags")
    if not -15.5 <= cand["lufs"] <= -13.5:
        fails.append(f"LUFS {cand.get('lufs')}")
    if cand["true_peak_dbtp"] > -1:
        fails.append(f"true peak {cand['true_peak_dbtp']} dBTP")
    if abs(cand["duration_seconds"] - base["duration_seconds"]) > 1 / 30:
        fails.append("render duration changed by more than one frame")
    if cand["offset_seconds"] != 0 or base["offset_seconds"] != 0:
        fails.append("inspection offset used; fix render sync and remeasure at zero")
    return ("VERIFIED" if not fails else "NOT VERIFIED"), fails


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: gate.py BASELINE.json CANDIDATE.json [CANDIDATE.json ...]")
    from pathlib import Path
    base = json.loads(Path(sys.argv[1]).read_text())
    failed = False
    for path in sys.argv[2:]:
        cand = json.loads(Path(path).read_text())
        v, why = verdict(base, cand)
        print(f"{path.split('/')[-1]:22s} {v:13s} " + "; ".join(why or ["all gates pass"]))
        failed |= v != "VERIFIED"
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
