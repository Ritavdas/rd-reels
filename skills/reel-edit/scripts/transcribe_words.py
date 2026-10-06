#!/usr/bin/env python3
"""Word-level transcript for a face take.

Writes a JSON list of {word, start, end} in source seconds. Read it, fix misheard words
(names, numbers, jargon) by editing the "word" field only, and merge tokens the model split
("ASD" + "-STE100" -> one "ASD-STE100" spanning both). Never change timings.
Usage: transcribe_words.py TAKE.mov OUT.json [--language en]
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("take")
ap.add_argument("out")
ap.add_argument("--language", default="en")
ap.add_argument("--model", default="mlx-community/whisper-large-v3-turbo")
a = ap.parse_args()

try:
    import mlx_whisper
except ImportError:
    sys.exit("mlx_whisper is missing. Run skills/reel-edit/scripts/setup.sh first, then use ~/.cache/rd-reels/venv/bin/python.")

with tempfile.TemporaryDirectory() as tmp:
    wav = Path(tmp) / "a16.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.take, "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
    r = mlx_whisper.transcribe(str(wav), path_or_hf_repo=a.model, language=a.language, word_timestamps=True,
                               condition_on_previous_text=False)
words = [{"word": w["word"].strip(), "start": round(w["start"], 3), "end": round(w["end"], 3)}
         for s in r["segments"] for w in s.get("words", [])]
Path(a.out).write_text(json.dumps(words, indent=1) + "\n")
gaps = [round(b["start"] - x["end"], 2) for x, b in zip(words, words[1:]) if b["start"] - x["end"] > 0.6]
print(f"{len(words)} words, speech {words[0]['start']:.2f}-{words[-1]['end']:.2f}s, {len(gaps)} pauses over 0.6s")
print(" ".join(w["word"] for w in words))
