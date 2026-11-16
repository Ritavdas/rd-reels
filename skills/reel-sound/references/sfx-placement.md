# Matching sounds to picture events

Use this when choosing a family and frame for each cue. The spotting rules in SKILL.md
still win: about 5 cues per 45 s, one family once, silence on quiet beats. This file only
answers "this beat has a visual event; which family, and where does `at` point?"

## How placement works
`design_sounds.py` lines up each cue's loudest point with the frame in `at`. So `at` is the
frame the eye lands on: the cut, the first visible frame of a card, the press, the final
number. Do not shift `at` earlier to "start the whoosh early"; the slide already builds
toward its peak. Ambience is the one exception: it uses `lead` to start before the cut.

## Event to family
| Visual event | Family | `at` points to | `frames` | `gap_db` |
|-|-|-|-|-|
| Clip, card or highlight moves across frame, swipe or push transition | `slide` | the frame the move lands | 10-16 | 10-12 |
| Text, card, sticker or icon appears | `tap` | first frame it is visible | 5-8 | 12-13 |
| Positive result, check mark, "this works" | `confirm` | the frame the result appears | 5-8 | 11-13 |
| Wrong answer, cross, "this fails" | `reject` | the frame the cross appears | 6-9 | 11-13 |
| Something is let go, unlocked, or opens up | `release` | the frame it opens | 6-10 | 11-13 |
| Underline, circle or highlight is drawn on text | `marker` | the frame the stroke starts; add `pan`/`pan_end` to follow it | 12-18 | 12-13 |
| A number counts up or down | `counter` | the frame the final number lands (the last tick is the loudest); set `frames` to the count length | 18-30 | 12-13 |
| Reveal, resolution, the answer lands softly | `bloom` | the reveal frame | 12-20 | 10-12 |
| New place (first b-roll world) | `ambience` | the cut; set `lead` to about 12 | length of the shot | n/a |

If an event is not in this table, it gets no cue.

## Choosing which events get a cue
Most reels have more visual events than the ~5 cue budget. Pick in this order:
1. The hook's main event.
2. The first new place (ambience J-cut).
3. The proof or number.
4. The fix or resolution.
5. One more only if it carries story; otherwise leave silence.

Text pop-ups and caption changes are the first to drop. A pop on every caption is the
"every graphic gets a whoosh" mistake.

## Material
Use `--material paper` when the picture is paper, cards, hand-drawn or crumpled transitions.
Use the default `digital` for UI, screens and charts. It applies to the whole set.

## Mix order
Voice, then cues, then music. Keep `gap_db` between 6 and 13 as SKILL.md says; use the low
end only for a cue that must read over speech, and check the words afterwards (see
"Inspect the rendered audio"). The final loudness gates in SKILL.md still apply.

## No family yet
These come up in saved references, but there is no synthesized family for them. Skip the
cue or pick the nearest event above. Do not download a sample to fill the gap.
- Riser into a drop (2 s build). Nearest: `bloom` on the reveal frame.
- Hard impact or hit on a flash cut. Nearest: `slide` landing or `confirm`.
- Glitch stutter. No substitute; leave it silent.
- Typing ticks per character. Use `counter` only if it reads as one short burst.

## Sources
Placement rules taken from saved references (17 Nov 2026):
- @charmainelwj, matching sound to each transition (slide, glitch, paper): https://www.instagram.com/reel/Ddg0WVEJ9m3/
- @Voxyz_ai, one sound per cut, pop for things appearing, voice above SFX above music: https://x.com/Voxyz_ai/status/2111140116572049485
- @notdwd, whooshes peaking on each cut, transition hits, clicks, cut on the music drop: https://x.com/notdwd/status/2104401208958230764
- @mangoster, risers, whooshes and impacts in a finished edit: https://x.com/mangoster/status/2036389593206182019
