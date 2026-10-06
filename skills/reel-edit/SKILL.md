---
name: reel-edit
description: Edit a talking-head take plus b-roll and screenshots into a 1080x1920 reel with graded face, beat-based motion graphics, and burned captions, using the reelkit library. Use for "edit this reel", "build the preview", "change beat X", or as steps 4-5 of the reel skill. Picture and voice only; sound is reel-sound.
---

# Reel edit

Everything is code on `scripts/reelkit.py`. A reel is one Python file of beats.
Python: `~/.cache/rd-reels/venv/bin/python`. If it is missing, run `scripts/setup.sh`.

## Steps
1. **Gather assets** into `<out>/assets/`. Screenshots at 2x or 3x. Video b-roll as mp4 or webm. Public domain or credited only. No third-party watermarks.
2. **Transcribe**: `transcribe_words.py TAKE.mov <out>/words.json`. Then fix misheard names and numbers in the `word` field only. Merge split tokens. Never change times.
3. **Find the speech range**: the first and last kept word times. Drop false starts and the pre-roll.
4. **Find the face crop**: grab a frame (`ffmpeg -ss 5 -i TAKE -frames:v 1 f.png`), look at it, and choose `(w, h, x, y)` as a 9:16 box around the head and shoulders with headroom. Leave it out to auto-center.
5. **Copy** `examples/asd_ste100.py` to `<out>/build_<name>.py`. Replace ASSETS, MARKS, and BEATS. Keep the setup and render lines.
6. **Preview**: `python build_<name>.py --take ... --words ... --assets ... --out <out> --preview`. This writes `<name>_preview.mp4` and `<name>_preview.timeline.json`. Extract 4 to 6 stills at beat midpoints and look at them before showing the user.
7. **Final**: the same command without `--preview`.

## Timing
Beat times are **source seconds in the take**. Use `rk.t_of("phrase")` to find when a phrase starts, or read words.json.
Start a beat on the first word of the line it illustrates. Start b-roll 2 to 4 frames before the word.

## Beat API
`rk.beat(t, name, render, into=("cut", 2), blur_in=False, silent=False, captions=True)`
- `into`: transition into this beat. Kinds: cut, fade, zoomin, slideup, slideleft, slideright. About 8 to 10 frames for slides and zooms.
- `blur_in`: directional motion blur on the slide.
- `silent=True`: reel-sound places nothing in this beat. Use it on the catch and the CTA.
- `captions=False` on the hook and the CTA, where the on-screen text already says the line.

`rk.mark(name, t)` names a spoken moment. `rk.quiet(label, t0, t1)` keeps a window inside a beat free of effects.

## Beat helpers
| Helper | Use for |
|---|---|
| `face(lines, pill_text, zoom, punch_at, stamp)` | Talking head. `lines=[(text, accent)]`. `stamp=("The catch", frame)` |
| `footage(src, ss, crop, title, credit, mode)` | Video b-roll. `mode="card"` for wide footage |
| `doc_card(img, box, tile_h, title, highlights, callout_img, ...)` | A post, article, or chart with highlight sweeps and a callout |
| `prompt_pair(bg, title, a_label, a_img, b_label, b_img)` | Two prompts side by side |
| `scroll_card(col, label, para, accent)` | Show how long an answer is, then pop its first paragraph |
| `bars(rows, caption, bg)` | One number comparison, counting up |
| `verdict(meter_label, heading, cards)` | A rule with good and bad sides |
| `chat_test(title, prompt, reply_label, reply, reply_frame, stamp, stamp_frame)` | The user's own test |
| `quote_fix(bg, title, callout_img, label, quote)` | The fix in the source's own words |

Need something new? Add a helper to reelkit.py that returns a renderer, in the same style. Keep it general and add it to this table.

## Style
Defaults come from `brand.json`. For a one-line override from intake, pass `brand={...}` to `rk.setup`, for example `brand={"colors": {"accent": "#7CF7C5"}}` or `brand={"speed": 1.1}`. Don't edit brand.json for a single reel.

## Rules learned the hard way
- The face appears 3 times: hook, catch, CTA. Everything else is b-roll or a graphic.
- Text must be readable on a phone: at least 44 px at 1080 wide. Pop out a callout rather than shrinking a screenshot.
- Keep captions and key text above the bottom 600 px, out of the Instagram UI.
- 1.15x speed with 0.22 s pause trimming. Faster read as rushed.
- Credit every b-roll source on screen.
- Never re-encode the voice in this step. reel-sound depends on it being unchanged.
