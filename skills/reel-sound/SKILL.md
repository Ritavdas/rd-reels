---
name: reel-sound
description: Spot and design a few original sound effects for a finished reel picture, mix them under the voice, and prove the mix with technical checks. Use for "add sound", "sound design this reel", "the sounds feel AI", or as the sound step of the reel skill. Needs the <name>.mp4 and <name>.timeline.json from reel-edit.
---

# Reel sound

Sound marks story beats. It is not decoration. Viewers notice when every graphic gets a whoosh.
Python: `~/.cache/rd-reels/venv/bin/python`.

## Before adding effects
If there is music or more than one raw speech clip, run reel-dialogue first. Remove the song's
vocals under speech, level each clip, and duck the bed. Do not guess a fixed music volume.
Keep the approved mix as the baseline; effects must not replace it with the old raw voice.
For a dialogue+music mix, set the sound timeline's `voice` to the 48 kHz stereo `mix.wav`,
`dialogue` to `stem_dialogue.wav` (cue-level reference), and `picture` to the video carrying
that mix. Preserve the original picture duration, beat frames and quiet windows.

## Spotting rules
- About 5 cues per 45 s. Each cue uses a different family. Never repeat a family.
- One cue per story beat: hook, the first b-roll world, the proof, the number, the fix.
- Silence on the catch, the question beat, the CTA, and anything marked `silent` or `quiet` in the timeline.
- One off-screen **ambience** as a J-cut: it starts about 12 frames before the first b-roll cut, so the ear enters the new place before the eye.
- Pan with the picture. If a highlight sweeps left to right, set `pan` and `pan_end`.
- Closer camera means a more detailed sound. Distant things get darker and more reverb.
- Write a one-line reason for every cue. No reason, no cue.

## Families
confirm, tap, reject, release, slide, marker, counter, bloom, ambience. All are synthesized here. No downloaded effects.
`--material digital` (default) or `paper` changes the timbre of the whole set.

## Cue plan
Write `<out>/cues.json`. See `examples/asd_ste100_cues.json`.
```json
{"id": "count_up", "family": "counter", "at": {"beat": "bars", "offset": 19}, "frames": 25, "gap_db": 13, "reason": "..."}
```
`at` is `{"beat": name, "offset": frames}`, `{"mark": name, "offset": frames}`, or `{"frame": n}`. `gap_db` is how far under the voice the cue sits (6 to 13). Ambience also takes `lead` (frames before the cut).

Show the cue table (time, family, reason) to the user before rendering if they asked to see sound choices.

## Run
```bash
PY=~/.cache/rd-reels/venv/bin/python; S=<this skill>/scripts
$PY $S/check_audio.py baseline <out>/<name>.mp4 <out>/baseline.json
$PY $S/design_sounds.py <out>/cues.json <out>/<name>.timeline.json <out> --name <name>_final
$PY $S/check_audio.py verify <out>/<name>_final.mp4 <out>/baseline.json <out>/<name>_final_sfx/manifest.json <out>/verification.json
```
Run `baseline` on the approved picture and audio file before adding effects.

## Inspect the rendered audio
Use all three forms of evidence, including when `/reel-sound` runs on its own:
1. **Words:** use reel-dialogue's `measure.py --truth truth.json` on the actual encoded final
   video, with fixed, corrected text and the same speech windows and ASR model as the baseline.
   Inspect disagreements, especially names, numbers and short words. Never rewrite truth
   from a candidate's transcript to make it pass.
2. **Measurements:** check loudness, true peak, cue placement, clicks, adjacent-clip volume
   jumps and sync. For music, pass dialogue and music stems to measure the speech-to-music gap.
   Aim for at least 6 LU, usually 12-20 LU for noisy phone clips. Stems must come from this
   version, not an earlier edit. Stem measurements describe masking, not encoded mix quality.
3. **Pictures:** run reel-dialogue's `listen_map.py` on the final video for waveform, momentary
   loudness and a log-mel spectrogram. Add aligned stems for a speech-band masking map.
   Inspect suspicious time ranges with reel-review's `audio_facts.py --spectrogram`.
   Images locate overlap and transients; they do not prove natural sound or intelligible words.

Compare final transcription with the pre-effects baseline. If effects bury or damage a word,
reduce, move or remove the cue and render again. SQUIM estimates support this comparison;
a cleaner score alone is not approval. The strict improvement gate in reel-dialogue is for
proposed processing upgrades, not a requirement that adding an effect raise STOI.

## Gates (verify)
Video stream unchanged. Same duration. -15.5 to -13.5 LUFS. True peak at or below -1 dBTP. No clipping. Dialogue PCM unchanged. Each cue lands on its frame. Quiet windows have no effects. Families are unique. Each declared hit matches the waveform.
If any gate fails, fix the cause and run again. Don't report the sound as finished until the verdict is VERIFIED.

## What checks cannot prove
They check technical mix hygiene, not taste. Transcription and clarity scores are proxies,
not proof a human can follow every word. The user's listening is the final check.
If a reviewer model comments on sound, check its claims with reel-review's `audio_facts.py`.
Gemini has described nonexistent effects and misjudged their levels; never use its praise
as the audio pass/fail gate.
