---
name: reel
description: Make a 45-60 s vertical AI explainer reel for Ritav's Instagram, from idea to final MP4 with sound. Use when the user says "make a reel", "new reel", "/reel", or hands over a face take and sources for a reel. Runs intake, script, beat plan, 540p preview, full render, sound, and checks, with an approval at each gate.
---

# Reel

The orchestrator. It runs the other rd-reels skills in order and stops for approval between stages.
`template.md` (next to this file) holds the defaults. Read it first.

## Talking to the user
- Start each reply with a 1 to 3 line TL;DR. Follow unslop: no em dashes, plain words.
- Ask questions as a numbered list in plain chat text. Do not use the ask_user tool for intake or design talk.
- Show what you found or made first, then ask.
- Talk about content, not apps or tools, unless the user asks.

## 1. Intake
Ask all ten in one message. Show the default in brackets so the user can answer "defaults" for any of them.
1. Topic or source link
2. The one takeaway a viewer should remember
3. Did you test it yourself? (yes adds a "my test" beat)
4. Target length [45 s] or 60 s
5. Paths to footage you have (face take, screen recordings, screenshots)
6. Footage still missing that I should find (public domain or credited only)
7. Speed [1.15x]
8. Style override, one line [none]
9. Any moment that must have a sound, or must stay silent [catch, question, CTA are silent]
10. Output folder [~/Downloads/<topic>]

Before scripting, run `setup.sh` from the reel-edit skill once if `~/.cache/rd-reels/venv` does not exist.

## 2. Script (reel-script skill)
If there is no face take yet, write the script, the teleprompter version, and the recording notes. Stop until the user records.
If there is a take, transcribe it and work from what was actually said.

## 3. Beat plan (gate 1)
Show a table: beat, spoken line, source time, picture, transition, sound or silent.
Write every claim's source next to it. Wait for approval.

## 4. Preview (gate 2)
Build the reel script with the reel-edit skill and render `--preview` (540p, picture and voice only).
Report the duration, the beat starts, and the preview path. Wait for approval or changes.
Change only what the user asked for. Render the preview again after each round.

## 5. Final (gate 3)
1. Full render (1080x1920).
2. If the reel has a music bed and/or more than one raw dialogue clip, mix dialogue first with
   reel-dialogue: level each clip, remove competing song vocals, carve EQ and duck music.
   Keep the exact picture duration and check sync after muxing. Preserve the approved audio
   as the fixed mix for effects; do not fall back to the raw voice in the sound timeline.
3. Sound with reel-sound: cue plan, baseline on the approved audio/video, design, verify.
   Keep about five distinct story-beat cues and deliberate silence.
4. Inspect the actual final video: transcription against fixed correct words, speech/music
   gap where applicable, loudness/true peak, clicks/jumps/sync, waveform and spectrogram.
   Keep comparison references fixed. Processing upgrades must beat the current best with
   reel-dialogue's gate; missing evidence or a cleaner score alone is not approval.
5. Report the final path, duration, loudness, cue list with reasons, and technical verdict.
   Keep failed experiments in the run log. DeepFilterNet3 and BS-RoFormer are not defaults.
Only report technical completion when verify is VERIFIED and word/sync checks pass.
The user's listening remains the final check for natural sound and music fit.

## 6. Review (only on request)
Use the reel-review skill. Ask before uploading anything.

## Files in the output folder
`<name>_preview.mp4`, `<name>.mp4` (picture and voice), `<name>_final.mp4` (with sound, the deliverable), `<name>.timeline.json`, `<name>_final_sfx/`, `cues.json`, `verification.json`, `script.md`, `build_<name>.py`, `words.json`.
Keep earlier versions as `<name>_v2.mp4` and so on. Never overwrite a version the user has seen.
For audio inspection, keep `truth.json`, `windows.json`, baseline/final measurement reports,
`listen_map.png`, dialogue/music stems, and the processing experiment log.
