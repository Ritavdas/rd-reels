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
6. **Report** a table: claim, verdict (true, false, can't tell), evidence. Suggest changes only from true claims. Ask before acting on any of them.

## Known failure
In the first reel, Gemini praised a "thud on Why?" that does not exist. That window was silent. Treat confident audio praise as unverified until checked.
