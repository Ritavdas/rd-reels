# rd-reels

A private Copilot plugin for making 45-60 s vertical AI explainer reels: a talking head with motion graphics, b-roll, burned captions, and a few original sound cues.

## Skills
| Skill | What it does |
|---|---|
| `reel` | The whole flow: intake questions, script, beat plan, 540p preview, final render, sound, checks. Stops for approval at each gate. |
| `reel-script` | Hook, one caveat, sourced facts, 130-170 words, teleprompter version. |
| `reel-edit` | The reelkit library: graded face, beat helpers (doc card, bars, verdict, chat test...), captions, timeline.json. |
| `reel-sound` | About 5 synthesized cues, one family each, J-cut ambience, silence on the catch and CTA, plus technical checks. |
| `reel-review` | On request only: send a draft to Gemini in Arc, then fact-check what it says against the real audio. |

Defaults live in `skills/reel/template.md` and `skills/reel-edit/brand.json`.

## Install
```bash
git clone git@github.com:Ritavdas/rd-reels.git
copilot plugin install ./rd-reels
bash rd-reels/skills/reel-edit/scripts/setup.sh   # ffmpeg + ~/.cache/rd-reels/venv
```
Reinstall after changing the repo, since Copilot caches installed plugins.

## Worked example
`skills/reel-edit/examples/asd_ste100.py` and `skills/reel-sound/examples/asd_ste100_cues.json` rebuild the first reel (ASD-STE100, 44.8 s) frame for frame.

## Tests
```bash
cd skills/reel-sound/scripts && ~/.cache/rd-reels/venv/bin/python -m unittest test_check_audio
```
