---
name: reel-dialogue
description: Level speech clips, remove competing song vocals, duck music, and inspect rendered reel audio using fixed-text transcription, loudness, clarity estimates and masking maps. Use before reel-sound when there is music or multiple raw speech clips, or when speech is buried, uneven or out of sync.
---

# Reel dialogue

reel-sound adds effects to a single clean voice track and never touches it. That breaks down the
moment a reel has **a music bed with vocals**, or **more than one raw phone-recorded clip** cut
together at different volumes. This skill is that missing step: level the clips, separate the
song so its singer stops competing with your speaker, duck it, and prove the result with numbers
instead of a guess.

Python: `~/.cache/rd-reels/venv/bin/python`. Run `scripts/setup.sh` once if imports fail.

## Why this is its own skill
Three mistakes happened before this skill existed, in order:
1. A fixed music volume was picked by ear-level guessing. It was never measured, so it was wrong.
2. The music's own singer was left in the bed under the speech. A duck lowers volume, it doesn't
   remove a competing voice. Separate the song into vocals and instrumental with Demucs, and put
   only the instrumental under speech.
3. A second version was shipped as "fixed" based on reasoning alone, with no re-check. It was
   still wrong, and worse than before, in a different way (the audio drifted out of sync).
That's why every step needs evidence from the rendered video. The A/B gate below applies to
proposed upgrades of the current best mix, not to an initial mix with no comparison baseline.

## 1. Level each dialogue clip
Phone clips in one reel can be 20+ dB apart (far mic vs close mic). Normalizing the whole mix
to one target does nothing for that; normalize **per clip**, before mixing:
```
highpass=f=90,lowpass=f=11000,afftdn=nr=12:nf=-42:tn=1,
acompressor=threshold=-26dB:ratio=3:attack=5:release=90:makeup=1
```
then gain each clip to a common integrated loudness (default -16 LUFS), limit, and apply a
10-15 ms linear fade at both edges so cuts don't click.

## 2. Separate the music, don't just duck it
```
PY=~/.cache/rd-reels/venv/bin/python
$PY -m demucs --two-stems=vocals -n htdemucs -o <out>/sep <music>
```
Use `<out>/sep/htdemucs/<name>/no_vocals.wav` (the instrumental) under every speech window.
Use the **original full song** (with vocals) only where nobody is talking. Also carve the
instrumental's 1.2 kHz and 3 kHz bands down 5-6 dB — that's where consonants live.

## 3. Build the mix
```
$PY scripts/dialogue_mix.py --clips clips.json --duration <picture-seconds> --out <dir> \
    [--music <song>] [--dialogue-lufs -16] [--gap-lu 18]
```
`clips.json`: `{"clips": [{"id": "01", "path": "...", "start": 2.6, "in": 67.95, "out": 69.45}, ...]}`.
`start` is where this clip lands in the final timeline (seconds); `in`/`out` trim the source.
Writes `<dir>/mix.wav`, `<dir>/stem_dialogue.wav`, `<dir>/stem_music.wav`, `<dir>/windows.json`.
Duck envelope: music drops to the bed level 120 ms before the first word and recovers over
350 ms after the last one, so it doesn't pump audibly on every cut. It stays instrumental
between the first and last speech windows; do not promise full-song vocals in every pause.
Omit `--music` for dialogue-only leveling. Always pass the exact picture duration to avoid an
added tail. Mux with video stream copy, then check duration and lip sync on the rendered video.
Limiter latency is compensated, and intermediate mixes/stems use float PCM to avoid clipping
before the limiter.

## 4. Measure before you trust it
Never report "it's clearer" from reasoning. Measure the actual rendered file:
```
$PY scripts/measure.py <final.mp4> <dir>/windows.json <dir>/report.json \
    --truth truth.json [--dialogue <dir>/stem_dialogue.wav --music <dir>/stem_music.wav] \
    [--reference-dialogue <fixed-clean-dialogue.wav>] [--offset S]
```
`truth.json`: `{"01": "no, let's just vote.", ...}` — the words each segment is supposed to say
(corrected captions, or a checked clean-take transcript). Keep this text, window IDs/times,
ASR model and sample rate fixed across comparisons. Use windows at least 400 ms long, and
merge shorter phrases before scoring. Reports include comparison hashes to detect mismatches.
Reports per segment and overall:
- **WER** against truth (required for an upgrade verdict): catches damaged or buried words.
  Check each transcript disagreement manually, especially names and numbers; ASR can be wrong.
- **SQUIM STOI / SI-SDR** (torchaudio, reference-free) — works even with only the final mix.
- **ESTOI** and **gap_lu** (dialogue stem vs music stem, if given) — masking-aware intelligibility
  and the K-weighted loudness gap. Aim for gap_lu >= 6, target 12-20 for noisy phone clips.
  ESTOI comparisons require the same clean dialogue reference: pass `--reference-dialogue`
  for every candidate. Candidate-specific dialogue stems are appropriate for gap/masking
  measurements, but changing the ESTOI reference makes its scores incomparable.
- **glimpse** — share of the 300-4000 Hz speech band where local SNR beats the music.
- Clicks at cuts (waveform 2nd-derivative vs local noise floor) and loudness jumps between
  adjacent segments (BS.1770-gated, so a pause isn't mistaken for a jump).
- `--offset` corrects for audio/video drift if you muxed the mix onto a different source edit;
  find it with cross-correlation, don't guess it. This is an inspection aid, not a sync fix.
  Fix the mux/timeline, confirm lip sync with the picture, and remeasure at zero before shipping.
  Do not use shifted scoring to hide drift in the deliverable.

Also look, don't only read numbers: `scripts/listen_map.py <mix> <out.png> [--dialogue ... --music ...]`
renders a waveform + momentary LUFS strip, a log-mel spectrogram, and (with stems) a per-segment
masking map — share of the speech band where music is louder than speech, red is bad. Picture
cuts are marked. Use time-labeled, log-amplitude/log-mel plots to locate overlap, clicks and
level jumps. These images support inspection; no visual model can prove the audio sounds
natural or the words are correct from a plot alone. Align stems to this exact render.

## 5. The A/B gate: never swap a tool on vibes
If you consider a "better" tool mid-project (a different denoiser, a different separator, a
different duck curve), it must clear this gate against the **current best**, not against nothing:
```
$PY scripts/gate.py baseline.json candidate.json [candidate2.json ...]
```
VERIFIED requires: mean WER does not rise, mean SQUIM STOI strictly rises, no single segment's
WER rises by more than 0.10 or STOI drops by more than 0.05, min gap_lu >= 6, no click/jump
flags, -15.5 to -13.5 LUFS, true peak <= -1 dBTP, unchanged duration within one frame,
and zero inspection offset. With music, measured stem lag must stay within one frame.
Missing/non-finite scores, changed truth/ASR/reference, or missing segments fail closed.
A candidate equal to the baseline is NOT VERIFIED
(it must be better, not merely not-worse) — that also catches a gate that would rubber-stamp
"no change". If it fails, say which clause failed and keep the current mix. Candidates that lose
are evidence, not waste — log them (see `references/runlog-example.md`) so the same "upgrade"
isn't re-tried blind next time.

## Known dead ends (don't re-try without new evidence)
- Spectral-subtraction denoise (`afftdn`) plus a stronger neural denoiser rarely compounds; if a
  neural model already runs, drop `afftdn` from its input rather than stacking both.
- A learned denoiser (e.g. DeepFilterNet3) can raise STOI/SDR while still mishearing short,
  unusual tokens ("6x", "4-3") that a WER check catches and a loudness/STOI check won't. Always
  score WER too, not STOI alone, when words/numbers matter.
- On the tested event footage, DeepFilterNet3 failed at full strength, reduced strength and
  a 50/50 dry blend. Keep per-clip leveling, modest EQ/denoise, Demucs and ducking as the tested
  baseline. Do not apply a neural denoiser by default.
- A better separator doesn't help if the current one already fully removed the song's vocals
  from the bed (check first with a VAD pass on the bed itself: near-zero speech-active share
  is supporting evidence, not proof the bed is vocal-free). BS-RoFormer did not improve the
  tested Demucs bed. Re-test only with new evidence, not because the model is newer.
- `DeepFilterNet` / `audio-separator` need Rust + a C toolchain and often don't build on the
  newest Python. See `scripts/setup_experimental.sh` for a side Python 3.12 env, and set
  `DEVELOPER_DIR=/Library/Developer/CommandLineTools` on macOS if `cc` fails with exit 69
  (Xcode license not accepted) — don't accept the Xcode license as a workaround.

## What checks cannot prove
They provide evidence about intelligibility and mix hygiene, not proof of natural sound or
music fit. SQUIM alone missed damaged words in the tested denoiser; pair it with fixed-text
transcription. Gemini's sound descriptions are not an audio gate. Let the user listen.
