# rd-reels

A private Copilot plugin for making 45-60 s vertical AI explainer reels: a talking head with motion graphics, b-roll, burned captions, and a few original sound cues.

## Skills
| Skill | What it does |
|---|---|
| `reel` | The whole flow: intake questions, script, beat plan, 540p preview, final render, sound, checks. Stops for approval at each gate. |
| `reel-script` | Hook, one caveat, sourced facts, 130-170 words, teleprompter version. |
| `reel-edit` | The reelkit library: graded face, beat helpers (doc card, bars, verdict, chat test...), captions, timeline.json. |
| `reel-dialogue` | Per-clip speech leveling, Demucs vocal removal, EQ and music ducking; fixed-text transcription, clarity estimates, loudness and visual masking checks. Runs before effects. |
| `reel-sound` | About 5 synthesized story-beat cues, distinct families, J-cut ambience and deliberate silence; preserves the approved mono/stereo mix and inspects the final encoded audio. |
| `reel-review` | On request only: outside review, then fact-check audio claims against cues, waveforms, transcripts and measured masking. Model praise is not an audio gate. |

Defaults live in `skills/reel/template.md` and `skills/reel-edit/brand.json`.

## Install
```bash
git clone git@github.com:Ritavdas/rd-reels.git
copilot plugin install ./rd-reels
bash rd-reels/skills/reel-edit/scripts/setup.sh   # ffmpeg + ~/.cache/rd-reels/venv
```
Reinstall after changing the repo, since Copilot caches installed plugins.
For a directly installed GitHub copy, use `copilot plugin update rd-reels` after pushing source
changes. Back up installed-only edits before refreshing, and verify all six skill folders.
Run `skills/reel-dialogue/scripts/setup.sh` only if dialogue dependency imports fail.

## Audio inspection
Check words against a fixed corrected script, measure the actual rendered video, and inspect
waveforms/log-mel spectrograms. With music, use aligned stems for speech-band masking and
a fixed clean dialogue reference for comparable ESTOI. SQUIM alone can miss damaged words.
Processing upgrades must beat the current best mix without worsening transcription; missing
or incomparable evidence fails the gate. Check sync in the deliverable, not just offset-adjusted
scores. Technical checks do not replace the user's listening.

The event experiments rejected DeepFilterNet3 at full/reduced strength and a 50/50 blend,
and found no benefit from BS-RoFormer over the existing Demucs bed. These are recorded in
`skills/reel-dialogue/references/runlog-example.md`, not recommended as default processing.

## Worked example
`skills/reel-edit/examples/asd_ste100.py` and `skills/reel-sound/examples/asd_ste100_cues.json` rebuild the first reel (ASD-STE100, 44.8 s) frame for frame.

## Tests
```bash
# From the repository root:
~/.cache/rd-reels/venv/bin/python -m unittest discover -s skills/reel-sound/scripts -p 'test_*.py'
~/.cache/rd-reels/venv/bin/python -m unittest discover -s skills/reel-dialogue/scripts -p 'test_*.py'
```
