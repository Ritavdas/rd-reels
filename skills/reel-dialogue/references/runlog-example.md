# Run-log example: keep a candidate's rejection, don't just discard it

This summarizes the event-audio experiments that motivated this skill.
Write one of these whenever a pipeline change is tried mid-project, win or lose, so the
next session doesn't re-try a dead end on reasoning alone.

## Predicate
Ship the new mix only if `gate.py` says VERIFIED against the current best. Otherwise keep
the current best.

## Log
| Step | Hypothesis | Result | Verdict |
|---|---|---|---|
| DeepFilterNet3, full strength | cleaner audio raises intelligibility | STOI/SI-SDR both rose, but 2 short/unusual words were misheard ("6x-ing" -> "take sex in") that WER caught and STOI did not | NOT VERIFIED |
| DeepFilterNet3, gentler limit | less aggressive keeps consonants | same two words still wrong | NOT VERIFIED |
| 50/50 blend with the dry signal | restores some consonant detail | same two words still wrong | NOT VERIFIED |
| Premise check | three fixes failed the same two words, so it's the tool on this footage, not the setting | denoiser rejected for this reel | decision |
| BS-RoFormer instead of Demucs | cleaner instrumental helps | no improvement on the tested bed; a VAD pass showed ~0% speech-active share in the Demucs bed, supporting the premise that competing vocals were already removed | NOT VERIFIED, no gain |

## Outcome
Current best mix kept. Rejected candidates kept on disk with their scores, so "try the
better denoiser" isn't re-proposed blind on the next reel without new evidence (e.g. a
different mic, a different model version).
The tested chain was per-clip speech leveling, modest EQ/denoise, Demucs vocal removal and
music ducking. These results are cautions from this footage, not proof a tool always fails.

## Record for each new experiment
Keep baseline/candidate paths, processing settings/tool versions, fixed truth and window
hashes, ASR model, clean reference identity, per-segment WER/SQUIM, comparable ESTOI where
available, gap, loudness/true peak, click/jump flags, duration/sync, gate failure clauses,
and the listening decision. Do not rewrite the correct words from a candidate's ASR.
Reject incomparable evidence rather than calling an upgrade verified.
