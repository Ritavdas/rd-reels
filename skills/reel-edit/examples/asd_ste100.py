#!/usr/bin/env python3
"""Worked example: the ASD-STE100 reel (v9), written as beats on reelkit.

Copy this file for a new reel and replace the ASSETS and BEATS sections.
Usage: python asd_ste100.py --take TAKE.mov --words words.json --assets DIR --out DIR [--preview]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import reelkit as rk  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--take", required=True)
ap.add_argument("--words", required=True, help="corrected word timestamps")
ap.add_argument("--assets", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--speed", type=float, default=1.15)
ap.add_argument("--preview", action="store_true", help="540p draft")
a = ap.parse_args()

rk.setup(a.take, a.words, a.out, speed=a.speed, speech_range=(9.5, 64.6), scale=0.5 if a.preview else 1.0,
         face_crop=(560, 996, 510, 84))

# ---------------- ASSETS ----------------
A = Path(a.assets)
tweet = Image.open(A / "tweet_3x.png").convert("RGB")
chart = Image.open(A / "tweet_media.png").convert("RGB")
sbs = Image.open(A / "side_by_side.png").convert("RGB")
leftcol, rightcol = sbs.crop((330, 100, 1040, 1310)), sbs.crop((1610, 100, 2320, 1310))
comp = Image.new("RGB", (1430, 1230), (24, 24, 26))
comp.paste(leftcol, (0, 10))
comp.paste(rightcol, (720, 10))
BUB_L, BUB_R = sbs.crop((835, 145, 1040, 205)), sbs.crop((1850, 145, 2320, 205))
CALL_E, CALL_D = chart.crop((1545, 860, 2290, 962)), chart.crop((100, 905, 1310, 1005))
CALL_TWEET = tweet.crop((40, 430, 1600, 590))
ImageDraw.Draw(CALL_TWEET, "RGBA").rectangle((0, 0, CALL_TWEET.width, CALL_TWEET.height), fill=rk.C["accent"] + (70,))
PARA_L, PARA_R = leftcol.crop((25, 120, 690, 213)), rightcol.crop((25, 203, 690, 285))
FX_SRC = sbs.crop((1610, 0, 2320, 1300))
F100, K1, K2 = A / "100th_Mainte.webm", A / "k1.mp4", A / "k2.mp4"
USAF, YC = "U.S. Air Force footage, public domain", "Andrej Karpathy at YC AI Startup School"
TW_HL = [(1150, 440, 1585, 508), (48, 512, 968, 580)]
TA = rk.TILE_W / 690

# ---------------- MARKS (spoken moments the picture or sound hits) ----------------
CATCH = rk.mark("catch", 41.16)
WHAT, WHY_CARD = rk.mark("what_to_do", 44.64), rk.mark("why_card", 45.66)
SAID, WHY = rk.mark("ai_said", 49.46), rk.mark("why_stamp", 52.74)
rk.quiet("why_and_breath", 52.66, 53.72)

# ---------------- BEATS ----------------
rk.beat(None, "face_hook", rk.face([("This one line changed", False), ("how I prompt AI", True)],
                                   pill_text="Explain this in ASD-STE100.", zoom="1.03+0.0009*on"), captions=False)
rk.beat(13.10, "usaf_hands", rk.footage(F100, 19.3, (690, 0, 608, 1080), "Aircraft maintenance manuals", USAF), into=("zoomin", 9))
rk.beat(14.66, "kc135", rk.footage(F100, 18.0, (0, 0, 1920, 840), "Made for aerospace manuals", USAF, mode="card"))
rk.beat(16.02, "karpathy1", rk.footage(K1, 2.0, (660, 0, 608, 1080), "Andrej Karpathy uses it", YC, zoom=0.05))
rk.beat(18.20, "tweet", rk.doc_card(tweet, rk.fit(tweet, 840, 680, 1680, TA), 760, "Karpathy, Oct 2, 2026", TW_HL,
                                    callout_img=CALL_TWEET, callout_at=34, title_px=52), into=("slideup", 10), blur_in=True)
rk.beat(22.10, "chartE", rk.doc_card(chart, rk.fit(chart, 1910, 1150, 820, TA), 690, "Short sentences", callout_img=CALL_E,
                                     callout_at=14, callout_w=900, box_to=rk.fit(chart, 1910, 1110, 720, TA), bg_dark=0.5), into=("zoomin", 10))
rk.beat(24.70, "chartD", rk.doc_card(chart, rk.fit(chart, 520, 1150, 900, TA), 690, "A fixed list of approved words", callout_img=CALL_D,
                                     callout_at=12, box_to=rk.fit(chart, 520, 1130, 800, TA), bg_dark=0.5), into=("slideleft", 9), blur_in=True)
rk.beat(27.00, "prompts", rk.prompt_pair(comp, "Same question, twice", "Normal", BUB_L, "ASD-STE100, 80%", BUB_R), into=("slideup", 10), blur_in=True)
rk.beat(31.05, "left", rk.scroll_card(leftcol, "Normal  ·  2,400 characters", PARA_L), into=("slideright", 9), blur_in=True)
rk.beat(34.85, "right", rk.scroll_card(rightcol, "ASD-STE100  ·  1,300 characters", PARA_R, accent=True), into=("slideleft", 9), blur_in=True)
rk.beat(38.05, "bars", rk.bars([("Normal", 2400, False), ("ASD-STE100", 1300, True)], "characters, same facts", comp), into=("fade", 8))
rk.beat(39.70, "face_catch", rk.face([], punch_at=CATCH, stamp=("The catch", CATCH)), silent=True)
rk.beat(43.38, "strict", rk.verdict("Strictness", "Strict ASD-STE100 tells you", [("What to do", True, WHAT), ("Why", False, WHY_CARD)]),
        into=("slideup", 9), blur_in=True)
rk.beat(46.45, "mytest", rk.chat_test("My test", "Rewrite my channel plan in ASD-STE100.", "The AI's rewrite",
                                      "Remove 20 percent of the script.", SAID, "Why?", WHY), into=("slideleft", 9), blur_in=True)
rk.beat(53.72, "karpathy2", rk.footage(K2, 4.0, (610, 0, 608, 1080), "Karpathy's fix", YC, zoom=0.05))
rk.beat(55.80, "fix", rk.quote_fix(FX_SRC, "Soften it to 80%", BUB_R, "Karpathy's words:", '"80% of the way to ASD-STE100"'),
        into=("slideleft", 9), blur_in=True)
rk.beat(59.72, "face_cta", rk.face([("Send this to someone", False), ("who skips long AI answers", True)], zoom="1.0+0.0011*on",
                                   size=66, gap=85), silent=True, captions=False)

rk.render("asd_ste100")
