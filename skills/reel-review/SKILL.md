---
name: reel-review
description: Get an outside review of a reel draft from Gemini in the user's signed-in Arc browser, then fact-check its claims against the real audio and timeline. Use only when the user asks for a review, a second opinion, or "ask Gemini". Never runs on its own.
---

# Reel review

Only run when the user asks. Every upload needs the user's approval in this conversation, naming the files and the chat.

## Steps
1. **Write the prompt** to `<out>/review_prompt.txt`. Ask for specific, timestamped notes on hook, pacing, readability, and sound. Ask it to say "can't tell" when unsure. Show the prompt and the file list, then ask to upload. Wait for a yes.
2. **Open Arc with a debug port.** Ask before restarting Arc, because it closes the user's windows for a moment. Quit Arc, then start it with `open -a Arc --args --remote-debugging-port=9333`. Open the Gemini chat the user names.
3. **Send**:
   `~/.cache/rd-reels/venv/bin/python scripts/gemini_review.py --chat <chat url> --prompt <out>/review_prompt.txt --out <out>/review_reply.txt <videos...>`
   The script refuses to send if the typed prompt differs from the approved file.
4. **Restart Arc normally** right after (quit, then `open -a Arc`). Don't leave the debug port open.
5. **Fact-check.** Models cannot reliably hear audio. For every sound claim, run:
   - `scripts/audio_facts.py <out>/<name>_final_sfx/manifest.json` for the cue list and quiet windows
   - `scripts/audio_facts.py <manifest> --at <seconds>` for a specific moment
   - `scripts/audio_facts.py --spectrogram <video> <start> <end> <png>`, then look at the image
   For picture claims, extract the frame at that time and look at it.
   For claims about buried words, clarity or music masking, use reel-dialogue's `measure.py`
   on the actual rendered video with fixed correct text, identical windows/ASR and aligned
   stems. Compare WER with SQUIM, never SQUIM alone. ESTOI comparisons need one fixed clean
   dialogue reference, not a newly denoised reference per candidate.
   Use `listen_map.py` for the waveform, momentary loudness, log-mel spectrogram and
   speech-band masking map. A plot can locate overlap or a transient, not prove natural sound.
   Check cue levels against the waveform/manifest and technical report, not model adjectives.
   Use these local checks without uploading; an outside review still requires approval.
6. **Report** a table: claim, verdict (true, false, can't tell), evidence. Suggest changes only from true claims. Ask before acting on any of them.

## Known failure
In the first reel, Gemini praised a "thud on Why?" that does not exist. That window was silent.
It also made incorrect claims about effect levels. Treat sound descriptions as unverified,
not as a pass/fail gate. Classify unsupported claims as "can't tell"; do not change audio on
their strength. Listening by the user remains the final check for taste and natural sound.
