---
name: reel-sound
description: Spot and design a few original sound effects for a finished reel picture, mix them under the voice, and prove the mix with technical checks. Use for "add sound", "sound design this reel", "the sounds feel AI", or as the sound step of the reel skill. Needs the <name>.mp4 and <name>.timeline.json from reel-edit.
---

# Reel sound

Sound marks story beats. It is not decoration. Viewers notice when every graphic gets a whoosh.
Python: `~/.cache/rd-reels/venv/bin/python`.

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
Run `baseline` on the picture-only file before you add sound.

## Gates (verify)
Video stream unchanged. Same duration. -15.5 to -13.5 LUFS. True peak at or below -1 dBTP. No clipping. Dialogue PCM unchanged. Each cue lands on its frame. Quiet windows have no effects. Families are unique. Each declared hit matches the waveform.
If any gate fails, fix the cause and run again. Don't report the sound as finished until the verdict is VERIFIED.

## What checks cannot prove
They show the mix is correct. They do not show it feels right. Say so, and let the user listen. If a reviewer model comments on the sound, check its claims with the reel-review skill's `audio_facts.py`.
