# Matching sounds to picture events

Use this when choosing the sound and frame for each cue. The spotting rules in SKILL.md
still win: about 5 cues per 45 s, each family once, silence on quiet beats. This file
answers "this beat has a visual event; which sound, and where does `at` point?"

## How placement works
`design_sounds.py` lines up each cue's loudest moment with the frame in `at`. So `at` is the
frame the eye lands on: the cut, the first visible frame of a card, the press, the reveal.
Do not shift `at` earlier to "start the whoosh early". A whoosh or riser file already builds
toward its peak, so it starts on its own before the frame. Ambience is the one exception: it
uses `lead` to start before the cut.

Real files go in `<out>/sfx/` with `file`, `source` and `license` (see SKILL.md). Before using a
file, listen to it or check its waveform: its loudest moment must be the moment you want on
the frame. Use `trim` to cut off a tail or a second hit.

## Event to sound
| Visual event | Real file (preferred) | Synthesized fallback | `at` points to | `gap_db` |
|-|-|-|-|-|
| Clip, card or camera moves across frame, swipe or push transition | whoosh (deep for slow moves, short and airy for fast ones) | `slide` | the frame the move lands | 8-12 |
| Hard cut, flash or punch zoom | impact / hit | `confirm` | the cut frame | 6-10 |
| Build-up into a reveal or the music drop | riser, 1-2 s | `bloom` | the reveal frame | 8-12 |
| Text, sticker or icon pops on screen | pop | `tap` | first frame it is visible | 11-13 |
| Glitch transition or effect | glitch / digital stutter | none, leave silent | the glitch frame | 10-12 |
| Paper, crumple or page transition | paper crinkle | `slide` with `--material paper` | the frame the paper lands | 10-12 |
| Text typed on screen | keyboard typing, trimmed so its loudest key is the last one | `counter` | the last character frame | 12-13 |
| Cursor click, button press, toggle | UI click | `tap` | the press frame | 12-13 |
| Underline, circle or highlight drawn on text | marker or pen scratch | `marker` with `pan`/`pan_end` | the frame the stroke starts | 12-13 |
| A number counts up or down | ticks | `counter` (set `frames` to the count length) | the frame the final number lands | 12-13 |
| Positive or negative result (check mark, cross) | short chime or buzz | `confirm` / `reject` | the frame the result appears | 11-13 |
| Logo settles, end card glows | soft shimmer | `bloom` | the frame the glow peaks | 10-12 |
| New place (first b-roll world) | room tone or location ambience | `ambience` | the cut; set `lead` to about 12 | n/a |

If an event is not in this table, it gets no cue.

## Choosing which events get a cue
Most reels have more visual events than the ~5 cue budget. Pick in this order:
1. The hook's main event.
2. The first new place (ambience J-cut).
3. The proof or number.
4. The fix or resolution (a riser into it works well).
5. One more only if it carries story; otherwise leave silence.

Text pop-ups and caption changes are the first to drop. A pop on every caption is the
"every graphic gets a whoosh" mistake.

## Where to find files
- Openverse (openverse.org/audio): about 590K free sounds. Search by the sound name in the
  table. Prefer CC0 or CC BY and put the license in the cue.
- earshot (from @LexnLin): open-source tool that lets an agent search, score and generate SFX.
- Ritav's own library or a pack he has bought.

## Mix order
Voice, then cues, then music. Keep `gap_db` between 6 and 13 as SKILL.md says; use the low
end only for an impact or a cue that must read over speech, and check the words afterwards
(see "Inspect the rendered audio"). The final loudness gates in SKILL.md still apply.

## Sources
Placement rules taken from saved references (17 Nov 2026):
- @charmainelwj, matching sound to each transition (slide, glitch, paper): https://www.instagram.com/reel/Ddg0WVEJ9m3/
- @Voxyz_ai, one sound per cut, pop for things appearing, voice above SFX above music, Openverse as a source: https://x.com/Voxyz_ai/status/2111140116572049485
- @notdwd, whooshes peaking on each cut, transition hits, clicks, cut on the music drop: https://x.com/notdwd/status/2104401208958230764
- @mangoster, risers, whooshes and impacts in a finished edit: https://x.com/mangoster/status/2036389593206182019
- @LexnLin, earshot SFX tool: https://x.com/LexnLin/status/2110878523728556518
