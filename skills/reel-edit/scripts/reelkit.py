#!/usr/bin/env python3
"""rd-reels edit library.

A reel is a list of beats. Each beat starts at a source time in the face take and renders one
piece of picture. reelkit owns the timeline (pause trim + speed), the graded face track, the
voice, brand primitives, beat helpers, captions and assembly. Sound effects are not added here;
reel-sound reads the timeline.json this writes.
"""
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
FF = os.environ.get("FFMPEG", "/opt/homebrew/bin/ffmpeg")
FPS = 30

# Set by setup().
W = H = 0
SC = 1.0
BRAND = {}
C = {}
SRC = WORDS_PATH = TMP = OUT = None
WORDS = []
SEGS, START = [], []
TOTAL = 0
SPEED = 1.15
FACE = VOICE = None
TILE_W = TILE_CY = 0
_beats, _marks, _quiet = [], {}, []


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        print(" ".join(map(str, cmd))[:600])
        print(r.stderr[-2500:])
        sys.exit(1)
    return r


def S(v):
    return int(round(v * SC))


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


_fc = {}


def font(face, px):
    k = (face, max(8, int(px * SC)))
    if k not in _fc:
        _fc[k] = ImageFont.truetype(BRAND["font"], k[1], index=BRAND["faces"][face])
    return _fc[k]


# ---------------- easing and springs ----------------
def bezier(x1, y1, x2, y2):
    def f(p):
        if p <= 0:
            return 0.0
        if p >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(40):
            m = (lo + hi) / 2
            x = 3 * (1 - m) ** 2 * m * x1 + 3 * (1 - m) * m * m * x2 + m ** 3
            lo, hi = (m, hi) if x < p else (lo, m)
        m = (lo + hi) / 2
        return 3 * (1 - m) ** 2 * m * y1 + 3 * (1 - m) * m * m * y2 + m ** 3
    return f


DEC = bezier(0.05, 0.7, 0.1, 1.0)    # Material 3 emphasized decelerate: entrances
EXPR = bezier(0.4, 0.14, 0.3, 1.0)   # IBM Carbon expressive: large moves


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _spring(k=350.0, c=34.0, m=1.0, n=90, sub=8):
    x, v, out, dt = 0.0, 0.0, [0.0], 1.0 / FPS / sub
    for _ in range(n):
        for _ in range(sub):
            a = (-k * (x - 1) - c * v) / m
            v += a * dt
            x += v * dt
        out.append(x)
    return out


SPR = _spring()
SPR_SOFT = _spring(220, 26)


def spring(t, curve=SPR):
    if t <= 0:
        return 0.0
    if t >= len(curve) - 1:
        return 1.0
    i = int(t)
    f = t - i
    return curve[i] * (1 - f) + curve[i + 1] * f


# ---------------- setup: timeline, face track, voice ----------------
def load_brand(overrides=None):
    brand = json.loads((HERE.parent / "brand.json").read_text())
    for k, v in (overrides or {}).items():
        if isinstance(v, dict) and isinstance(brand.get(k), dict):
            brand[k].update(v)
        else:
            brand[k] = v
    return brand


def setup(take, words, out_dir, speed=None, gap=None, speech_range=None, scale=1.0,
          brand=None, face_crop=None, rebuild=False):
    """take: face recording. words: word-timestamp JSON (list of {word,start,end}), already corrected.
    speech_range: (start, end) seconds of the take to keep. face_crop: (w, h, x, y) in take pixels."""
    global W, H, SC, BRAND, C, SRC, WORDS_PATH, TMP, OUT, WORDS, SEGS, START, TOTAL, SPEED, FACE, VOICE, TILE_W, TILE_CY
    SC = scale
    W, H = int(1080 * SC) // 2 * 2, int(1920 * SC) // 2 * 2
    BRAND = load_brand(brand)
    C = {k: hexrgb(v) for k, v in BRAND["colors"].items()}
    TILE_W, TILE_CY = BRAND["tile_width"], BRAND["tile_center_y"]
    SPEED = speed or BRAND["speed"]
    gap = gap or BRAND["pause_gap"]
    SRC, WORDS_PATH = Path(take), Path(words)
    OUT = Path(out_dir)
    TMP = OUT / ("work_preview" if SC < 1 else "work")
    TMP.mkdir(parents=True, exist_ok=True)
    WORDS = json.loads(WORDS_PATH.read_text())
    if speech_range:
        WORDS = [w for w in WORDS if speech_range[0] <= w["start"] <= speech_range[1]]
    groups, cur = [], [WORDS[0]]
    for w in WORDS[1:]:
        if w["start"] - cur[-1]["end"] > gap:
            groups.append(cur)
            cur = [w]
        else:
            cur.append(w)
    groups.append(cur)
    SEGS = []
    for g in groups:
        a, b = g[0]["start"] - 0.07, g[-1]["end"] + 0.11
        if SEGS and a < SEGS[-1][1]:
            mid = (a + SEGS[-1][1]) / 2
            SEGS[-1] = (SEGS[-1][0], mid)
            a = mid
        SEGS.append((round(a, 3), round(b, 3)))
    cum = [0.0]
    for a, b in SEGS:
        cum.append(cum[-1] + (b - a) / SPEED)
    START = [round(c * FPS) for c in cum]
    TOTAL = START[-1]
    FACE, VOICE = TMP / "face.mp4", TMP / "voice.wav"
    if rebuild or not VOICE.exists():
        _build_face_and_voice(face_crop)
    print(f"timeline: {len(SEGS)} speech segments, {TOTAL / FPS:.2f}s at {SPEED}x", flush=True)


def at(t):
    """Source-take seconds -> output frame."""
    nf = [START[k + 1] - START[k] for k in range(len(SEGS))]
    for k, (a, b) in enumerate(SEGS):
        if a - 0.005 <= t <= b + 0.005:
            return START[k] + round((t - a) / SPEED * FPS)
    nxt = [k for k, (a, b) in enumerate(SEGS) if a > t]
    return START[nxt[0]] if nxt else TOTAL


def t_of(phrase, nth=1):
    """Source time of the first word of `phrase` (case and punctuation ignored)."""
    norm = lambda s: re.sub(r"[^a-z0-9%]", "", s.lower())
    target = [norm(p) for p in phrase.split()]
    toks = [norm(w["word"]) for w in WORDS]
    seen = 0
    for i in range(len(toks) - len(target) + 1):
        if toks[i:i + len(target)] == target:
            seen += 1
            if seen == nth:
                return WORDS[i]["start"]
    raise KeyError(f"phrase not found in transcript: {phrase!r}")


def _probe_size(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", path]).stdout
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


def _aroll_mattes():
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse((W * 0.04, H * 0.24, W * 0.96, H * 1.06), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(S(120)))
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(int(H * 0.38)):
        gd.line((0, y, W, y), fill=(6, 7, 10, int(170 * max(0, 1 - y / (H * 0.38)) ** 1.6)))
    mp, gp = TMP / "aroll_mask.png", TMP / "aroll_topgrad.png"
    mask.save(mp)
    grad.save(gp)
    return mp, gp


def _build_face_and_voice(face_crop):
    iw, ih = _probe_size(SRC)
    if face_crop:
        cw, ch, cx, cy = face_crop
    elif iw / ih > 9 / 16:
        ch = round(ih * 0.922)
        cw = round(ch * 9 / 16) // 2 * 2
        cx, cy = (iw - cw) // 2, ih - ch
    else:
        cw, ch, cx, cy = iw, ih, 0, 0
    mask, topgrad = _aroll_mattes()
    vl, al = [], []
    nf = [START[k + 1] - START[k] for k in range(len(SEGS))]
    for k, (a, b) in enumerate(SEGS):
        d = b - a
        vp, ap = TMP / f"f{k:02d}.mp4", TMP / f"a{k:02d}.wav"
        grade = (f"setpts=(PTS-STARTPTS)/{SPEED},fps={FPS},hqdn3d=2:1.5:4:4,crop={cw}:{ch}:{cx}:{cy},scale={W}:{H}:flags=lanczos,setsar=1,"
                 f"colorbalance=rs=-0.05:bs=0.05:rm=-0.04:bm=0.04:rh=-0.03:bh=0.02,curves=master='0/0 0.2/0.23 0.5/0.55 0.8/0.82 1/0.93',eq=contrast=1.05:saturation=1.04")
        fcg = (f"[0:v]{grade},split[a][b];[a]eq=brightness=0.06:gamma=1.1,unsharp=5:5:0.9:5:5:0.0[fg];[b]boxblur={max(2, S(14))}:2,eq=brightness=-0.12:saturation=0.85[bg];"
               f"[1:v]format=gray[m];[fg][m]alphamerge[fgm];[bg][fgm]overlay=0:0:shortest=1[c];[2:v]format=rgba[g];[c][g]overlay=0:0:shortest=1,format=yuv420p[v]")
        run([FF, "-v", "error", "-y", "-ss", f"{a:.3f}", "-t", f"{d + 0.4:.3f}", "-i", SRC, "-loop", "1", "-i", mask, "-loop", "1", "-i", topgrad,
             "-filter_complex", fcg, "-map", "[v]", "-an", "-frames:v", str(nf[k]), "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-r", str(FPS), vp])
        run([FF, "-v", "error", "-y", "-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", SRC, "-vn", "-ac", "1", "-ar", "48000",
             "-af", f"afade=t=in:d=0.02,afade=t=out:st={max(0, d - 0.05):.3f}:d=0.05", ap])
        vl.append(vp)
        al.append(ap)
    _concat(vl, FACE)
    pre = TMP / "voice_pre.wav"
    _concat(al, pre, ["-af", f"atempo={SPEED},highpass=f=80,afftdn=nf=-30,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120", "-ar", "48000"])
    r = subprocess.run([FF, "-hide_banner", "-i", str(pre), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    run([FF, "-v", "error", "-y", "-i", pre, "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
         f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000", VOICE])


def _concat(lst, out, extra=None):
    p = Path(str(out) + ".txt")
    p.write_text("".join(f"file '{x}'\n" for x in lst))
    run([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", p] + (extra or ["-c", "copy"]) + [out])


# ---------------- drawing primitives ----------------
def alpha_mul(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(ImageChops.multiply(im.getchannel("A"), Image.new("L", im.size, int(255 * clamp(a)))))
    return im


def text_img(text, f, fill, shadow=True):
    l, t, r, b = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f)
    pad = S(30)
    im = Image.new("RGBA", (r - l + 2 * pad, b - t + 2 * pad), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((pad - l, pad - t + S(4)), text, font=f, fill=(0, 0, 0, 190))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(S(9))))
    ImageDraw.Draw(im).text((pad - l, pad - t), text, font=f, fill=fill)
    return im, pad


_ti = {}


def tcache(text, f, fill):
    k = (text, f.size, f.getname(), fill)
    if k not in _ti:
        _ti[k] = text_img(text, f, fill)
    return _ti[k]


def reveal(canvas, text, cx, cy, f, t, fill=None, dur=11, left=False):
    """Mask reveal: the line rises out of a clip box."""
    if t <= 0:
        return
    fill = fill or C["white"]
    im, pad = tcache(text, f, fill)
    p = DEC(t / dur)
    hh = im.height - 2 * pad
    clip = Image.new("RGBA", im.size, (0, 0, 0, 0))
    clip.alpha_composite(im, (0, int((1 - p) * (hh + pad))))
    clip = alpha_mul(clip.crop((0, 0, im.width, pad + hh + S(14))), p * 1.6)
    x = int(cx - pad) if left else int(cx - im.width / 2)
    canvas.alpha_composite(clip, (x, int(cy - hh / 2 - pad)))


def title(canvas, text, y, t, px=60):
    """Accent bar draws on, then the title reveals 3 frames later."""
    d = ImageDraw.Draw(canvas)
    w = S(72) * DEC(t / 8)
    if w > 1:
        d.rounded_rectangle((W / 2 - w / 2, S(y) - S(68), W / 2 + w / 2, S(y) - S(58)), S(5), fill=C["accent"])
    reveal(canvas, text, W / 2, S(y), font("heavy", px), t - 3)


def credit(canvas, text, y, t):
    a = DEC((t - 8) / 10)
    if a > 0:
        ImageDraw.Draw(canvas, "RGBA").text((W / 2, S(y)), text, font=font("medium", 26), fill=(255, 255, 255, int(170 * a)), anchor="mm")


def pill(canvas, text, cx, cy, t, px=44, fg=None, bg=(20, 22, 28, 220)):
    p = spring(t)
    if p <= 0.01:
        return
    fg = fg or C["white"]
    f = font("bold", px)
    tw = ImageDraw.Draw(canvas).textlength(text, font=f)
    pw, ph = int(tw + S(56)), int(f.size + S(34))
    im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, pw - 1, ph - 1), ph // 2, fill=bg)
    d.text((pw / 2, ph / 2), text, font=f, fill=fg, anchor="mm")
    sc = 0.86 + 0.14 * p
    im = alpha_mul(im.resize((max(1, int(pw * sc)), max(1, int(ph * sc))), Image.BICUBIC), DEC(t / 6))
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2 + (1 - p) * S(24))))


def accent_pill(canvas, text, cx, cy, t, px=44):
    pill(canvas, text, cx, cy, t, px, fg=C["ink"], bg=C["accent"] + (240,))


def round_mask(size, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), r, fill=255)
    return m


_sh = {}


def shadow_for(size, r, spread=28):
    k = (size, r, spread)
    if k not in _sh:
        pad = S(70)
        im = Image.new("RGBA", (size[0] + 2 * pad, size[1] + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + size[0], pad + size[1]), r, fill=(0, 0, 0, 175))
        _sh[k] = (im.filter(ImageFilter.GaussianBlur(S(spread))), pad)
    return _sh[k]


def _solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [x - f * y for x, y in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] for i in range(n)]


def tilt(img, amt):
    if amt <= 0.003:
        return img
    w, h = img.size
    s = amt * 0.10 * h
    dst = [(0, s), (w, 0), (w, h), (0, h - s)]
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    A, bb = [], []
    for (x, y), (u, v) in zip(dst, src):
        A += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        bb += [u, v]
    return img.transform((w, h), Image.PERSPECTIVE, _solve(A, bb), Image.BICUBIC)


_bg = {}


def bg_frame(img, key, t, n, dark=0.5):
    """Blurred background that drifts at half the card's rate (parallax)."""
    if key not in _bg:
        r = max(W / img.width, H / img.height) * 1.08
        b = img.resize((int(img.width * r) + 2, int(img.height * r) + 2), Image.BILINEAR).filter(ImageFilter.GaussianBlur(S(42)))
        _bg[key] = Image.blend(b, Image.new("RGB", b.size, (8, 9, 12)), dark).convert("RGBA")
    b = _bg[key]
    p = t / max(1, n)
    ox = (b.width - W) / 2 + S(20) * (p - 0.5)
    oy = (b.height - H) / 2 - S(30) * p
    return b.crop((int(ox), int(oy), int(ox) + W, int(oy) + H))


def card(canvas, src, box, t, tile_h, n=60, drift=0.012):
    """Spring entrance: rises, scales 0.94 to 1 and untilts; shadow follows 2 frames late; then a 1% drift."""
    x, y, w, h = box
    p, ps = spring(t), spring(t - 2)
    z = 1 + drift * clamp((t - 14) / max(1, n - 14))
    cx, cy = x + w / 2, y + h / 2
    w2, h2 = w / z, h / z
    tw, th = S(TILE_W), S(tile_h)
    tile = src.resize((tw, th), Image.BICUBIC, box=(cx - w2 / 2, cy - h2 / 2, cx + w2 / 2, cy + h2 / 2)).convert("RGBA")
    tile.putalpha(round_mask((tw, th), S(28)))
    sc = 0.94 + 0.06 * p
    if p < 0.999:
        tile = tilt(tile, 0.45 * (1 - p))
        tile = tile.resize((max(1, int(tw * sc)), max(1, int(th * sc))), Image.BICUBIC)
    a = clamp(DEC(t / 6))
    tile = alpha_mul(tile, a)
    px = W // 2 - tile.width // 2
    py = S(TILE_CY) - tile.height // 2 + int((1 - p) * S(140))
    sh, pad = shadow_for((tile.width, tile.height), S(28))
    shy = S(TILE_CY) - tile.height // 2 + int((1 - ps) * S(140)) + S(26)
    if a > 0:
        canvas.alpha_composite(alpha_mul(sh, a), (px - pad, shy - pad))
    canvas.alpha_composite(tile, (px, py))
    return (px, py, tile.width, tile.height)


def callout(canvas, src, cy, width, t, outline="accent"):
    """Enlarged crop pops on a spring; its outline draws on 4 frames later."""
    if t <= 0:
        return
    if outline == "accent":
        outline = C["accent"]
    p = spring(t)
    tw = int(S(width) * (0.84 + 0.16 * p))
    th = int(tw * src.height / src.width)
    tile = src.resize((max(1, tw), max(1, th)), Image.LANCZOS).convert("RGBA")
    tile.putalpha(round_mask(tile.size, S(12)))
    a = clamp(DEC(t / 5))
    tile = alpha_mul(tile, a)
    sh, pad = shadow_for(tile.size, S(12), 22)
    x, y = W // 2 - tw // 2, S(cy) - th // 2 - int((1 - p) * S(30))
    canvas.alpha_composite(alpha_mul(sh, a), (x - pad, y - pad + S(18)))
    canvas.alpha_composite(tile, (x, y))
    q = DEC((t - 4) / 10)
    if q > 0 and outline:
        o = S(7)
        x0, y0, x1, y1 = x - o, y - o, x + tw + o, y + th + o
        L = 2 * (x1 - x0 + y1 - y0) * q
        d = ImageDraw.Draw(canvas)
        for (ax, ay, bx, by) in [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]:
            seg = math.hypot(bx - ax, by - ay)
            if L <= 0:
                break
            f = min(1, L / seg)
            d.line((ax, ay, ax + (bx - ax) * f, ay + (by - ay) * f), fill=outline, width=S(5))
            L -= seg


def kb(r0, r1, p):
    return tuple(a + (b - a) * p for a, b in zip(r0, r1))


def fit(img, cx, cy, w, aspect):
    """A crop box of the given aspect, centred on (cx, cy), clamped inside the image."""
    h = w / aspect
    x = min(max(cx - w / 2, 0), img.width - w)
    y = min(max(cy - h / 2, 0), img.height - h)
    return (x, y, w, h)


def pop_text(canvas, text, cx, cy, px, fill, t, big=1.35):
    """Stamp: starts large and transparent, slams down on a spring."""
    if t <= 0:
        return
    p = spring(t)
    ti, pad = tcache(text, font("heavy", px), fill)
    sc = big - (big - 1) * p
    t2 = alpha_mul(ti.resize((max(1, int(ti.width * sc)), max(1, int(ti.height * sc))), Image.BICUBIC), clamp(t / 3))
    canvas.alpha_composite(t2, (int(cx - t2.width / 2), int(cy - t2.height / 2)))


def solid(color_key="card"):
    return Image.new("RGBA", (W, H), C[color_key] + (255,))


# ---------------- piece rendering ----------------
def _encoder(path):
    return subprocess.Popen([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)


def _decoder(args, n):
    p = subprocess.Popen([FF, "-v", "error", *map(str, args), "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    last = None
    for _ in range(n):
        buf = p.stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            last = Image.frombytes("RGB", (W, H), buf)
        yield last
    p.stdout.close()
    p.wait()


def still(draw, blur_frames=8):
    """draw(t, n, g) -> RGBA image. Entrance frames get 180-degree-shutter motion blur."""
    def render(path, n, start):
        e = _encoder(path)
        for i in range(n):
            if i < blur_frames:
                s = [draw(i + o, n, start + i + o).convert("RGB") for o in (-0.25, 0.0, 0.25)]
                im = Image.blend(Image.blend(s[0], s[2], 0.5), s[1], 0.34)
            else:
                im = draw(i, n, start + i).convert("RGB")
            e.stdin.write(im.tobytes())
        e.stdin.close()
        e.wait()
    return render


def video_layer(args, overlay):
    def render(path, n, start):
        e = _encoder(path)
        for i, fr in enumerate(_decoder(args(start), n)):
            im = fr.convert("RGBA")
            overlay(im, i, n, start + i)
            e.stdin.write(im.convert("RGB").tobytes())
        e.stdin.close()
        e.wait()
    return render


def fill_args(src, ss, crop, zoom=0.03):
    x, y, w, h = crop
    return lambda start: ["-ss", f"{ss:.4f}", "-i", src, "-vf", f"fps={FPS},crop={w}:{h}:{x}:{y},scale={W}:{H}:flags=lanczos,"
                          f"zoompan=z='1+{zoom}*on/90':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},setsar=1"]


def card_args(src, ss, crop):
    x, y, w, h = crop
    fc = (f"[0:v]fps={FPS},crop={w}:{h}:{x}:{y},split[a][c];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur={S(30)}:2,eq=brightness=-0.2[bg];"
          f"[c]scale={S(TILE_W)}:-2:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:{S(TILE_CY)}-h/2,setsar=1[v]")
    return lambda start: ["-ss", f"{ss:.4f}", "-i", src, "-filter_complex", fc, "-map", "[v]"]


def face_args(zoom_expr):
    return lambda start: ["-ss", f"{start / FPS:.4f}", "-i", FACE, "-vf",
                          f"zoompan=z='{zoom_expr(start) if callable(zoom_expr) else zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih*0.4-(ih/zoom*0.4)':d=1:s={W}x{H}:fps={FPS}"]


# ---------------- beats ----------------
def mark(name, t):
    """Name a moment (source seconds). Beat helpers and reel-sound can key on marks."""
    _marks[name] = at(t)
    return _marks[name]


def quiet(label, t0, t1):
    """A window (source seconds) where reel-sound must not place effects, inside a beat."""
    _quiet.append({"label": label, "start": at(t0) / FPS, "end": at(t1) / FPS})


def beat(t, name, render, into=("cut", 2), blur_in=False, silent=False, captions=True):
    """Add a beat starting at source time t (None = reel start).
    into: transition into this beat, (kind, frames). Kinds: cut, fade, zoomin, slideup, slideleft, slideright.
    silent: reel-sound must not place effects inside this beat. captions: False hides burned captions."""
    _beats.append(dict(start=0 if t is None else at(t), name=name, render=render, into=into, blur_in=blur_in,
                       silent=silent, captions=captions))


def face(lines, pill_text=None, zoom="1.02+0.0010*on", punch_at=None, stamp=None, size=70, gap=90, y0=300):
    """Talking-head beat. lines: [(text, accent)] revealed with a 4-frame stagger.
    pill_text: a typed prompt pill under the lines. punch_at: frame to punch in.
    stamp: (text, frame) slammed down at that frame."""
    def ov(im, t, n, g):
        for k, (txt, acc) in enumerate(lines):
            reveal(im, txt, W / 2, S(y0 + k * gap), font("heavy", size), t - 1 - 4 * k, fill=C["accent"] if acc else None)
        if pill_text:
            p = spring(t - 12)
            if p > 0.01:
                f = font("demi", 40)
                tw = ImageDraw.Draw(im).textlength(pill_text, font=f)
                pw, ph = int(tw + S(76)), S(92)
                pl = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
                d = ImageDraw.Draw(pl)
                d.rounded_rectangle((0, 0, pw - 1, ph - 1), ph // 2, fill=C["ink"] + (230,), outline=C["accent"], width=S(3))
                k = int(len(pill_text) * clamp((t - 14) / 16))
                d.text((S(38), ph / 2), pill_text[:k], font=f, fill=C["white"], anchor="lm")
                if k < len(pill_text) and int(t) % 10 < 6:
                    cx = S(38) + d.textlength(pill_text[:k], font=f) + S(4)
                    d.rectangle((cx, ph * 0.28, cx + S(3), ph * 0.72), fill=C["accent"])
                sc = 0.9 + 0.1 * p
                pl = alpha_mul(pl.resize((int(pw * sc), int(ph * sc)), Image.BICUBIC), DEC((t - 12) / 6))
                yy = S(y0 + len(lines) * gap + 40)
                im.alpha_composite(pl, (int(W / 2 - pl.width / 2), int(yy - pl.height / 2 + (1 - p) * S(20))))
        if stamp:
            pop_text(im, stamp[0], W / 2, S(y0 + 30), 110, C["accent"], g - stamp[1] + 1)
    if punch_at is None:
        z = zoom
    else:
        z = lambda s: f"if(gte(on,{punch_at - s}),1.14+0.0005*(on-{punch_at - s}),1.0+0.0008*on)"
    return video_layer(face_args(z), ov)


def footage(src, ss, crop, title_text=None, credit_text=None, mode="fill", zoom=0.03):
    """B-roll beat. mode fill: crop fills the frame. mode card: rounded card over a blurred copy."""
    ty, cy = (270, 340) if mode == "fill" else (300, 370)
    def ov(im, t, n, g):
        if title_text:
            title(im, title_text, ty, t, 56 if len(title_text) > 22 else 60)
        if credit_text:
            credit(im, credit_text, cy, t)
    args = fill_args(src, ss, crop, zoom) if mode == "fill" else card_args(src, ss, crop)
    return video_layer(args, ov)


def doc_card(img, box, tile_h=760, title_text=None, highlights=(), hl_start=12, hl_frames=16, callout_img=None,
             callout_at=34, callout_w=1000, box_to=None, bg_dark=0.55, key=None, title_px=58):
    """Screenshot evidence: tweet, article, chart. highlights draw on in order; callout_img pops out at callout_at.
    box_to: if set, the card camera moves from box to box_to (no drift)."""
    key = key or f"doc{id(img)}"
    def draw(t, n, g):
        im = bg_frame(img, key, t, n, bg_dark).copy()
        base = img
        if highlights:
            base = img.copy()
            d = ImageDraw.Draw(base, "RGBA")
            done = DEC((t - hl_start) / hl_frames) * sum(b[2] - b[0] for b in highlights)
            for (x0, y0, x1, y1) in highlights:
                seg = min(done, x1 - x0)
                if seg > 0:
                    d.rectangle((x0, y0, x0 + seg, y1), fill=C["accent"] + (135,))
                done -= x1 - x0
        if box_to:
            card(im, base, kb(box, box_to, EXPR(clamp(t / n))), t, tile_h, n, 0.0)
        else:
            card(im, base, box, t, tile_h, n)
        if title_text:
            title(im, title_text, 300, t, title_px)
        if callout_img is not None:
            callout(im, callout_img, 1085, callout_w, t - callout_at)
        return im
    return still(draw)


def prompt_pair(bg_img, title_text, a_label, a_img, b_label, b_img):
    """Two prompts, enlarged and readable: plain label for a, accent label for b."""
    def draw(t, n, g):
        im = bg_frame(bg_img, f"pp{id(bg_img)}", t, n, 0.62).copy()
        title(im, title_text, 300, t, 60)
        pill(im, a_label, W / 2, S(560), t - 4, 38)
        callout(im, a_img, 700, 640, t - 7, outline=None)
        accent_pill(im, b_label, W / 2, S(900), t - 10, 38)
        callout(im, b_img, 1030, 980, t - 13, outline=None)
        return im
    return still(draw)


def scroll_card(col, label, para, accent=False, para_at=24):
    """A long answer scrolls to show its length, dims, then its opening paragraph pops out full width."""
    def draw(t, n, g):
        im = bg_frame(col, f"sc{id(col)}", t, n, 0.6).copy()
        wh = col.width * 740 / TILE_W
        y0 = (col.height - wh) * EXPR(clamp((t - 4) / (para_at - 2)))
        x, y, w, h = card(im, col, (0, y0, col.width, wh), t, 740, n, 0.0)
        dim = DEC((t - para_at) / 8)
        if dim > 0:
            ov = Image.new("RGBA", (w, h), (8, 9, 12, int(150 * dim)))
            ov.putalpha(ImageChops.multiply(ov.getchannel("A"), round_mask((w, h), S(28))))
            im.alpha_composite(ov, (x, y))
        callout(im, para, 790, 1040, t - para_at, outline=C["accent"] if accent else (170, 175, 182))
        if accent:
            accent_pill(im, label, W / 2, S(330), t - 3, 46)
        else:
            pill(im, label, W / 2, S(330), t - 3, 46)
        return im
    return still(draw)


def bars(rows, caption, bg_img=None, step=100):
    """rows: [(label, value, accent)]. Bars grow on soft springs 4 frames apart; numbers count up in `step`s."""
    top = max(v for _, v, _ in rows)
    def draw(t, n, g):
        im = bg_frame(bg_img, f"bars{id(bg_img)}", t, n, 0.72).copy() if bg_img is not None else solid()
        d = ImageDraw.Draw(im)
        for k, (lab, val, acc) in enumerate(rows):
            tt = t - 4 * k
            y = S(640 + k * 300)
            if tt <= 0:
                continue
            bw = (W - S(380)) * val / top * spring(tt, SPR_SOFT)
            reveal(im, lab, S(90), y - S(60), font("demi", 44), tt, fill=(225, 228, 233), left=True)
            d.rounded_rectangle((S(90), y, S(90) + max(S(20), bw), y + S(90)), S(22), fill=C["accent"] if acc else (120, 124, 132))
            num = int(round(val * DEC(clamp(tt / 15)) / step) * step)
            d.text((S(90) + max(S(20), bw) + S(24), y + S(45)), f"{num:,}", font=font("heavy", 72), fill=C["white"], anchor="lm")
        reveal(im, caption, W / 2, S(1120), font("demi", 40), t - 14, fill=(205, 210, 216))
        return im
    return still(draw)


def verdict(meter_label, heading, cards):
    """A meter fills to 100%, then verdict cards land at their frames. cards: [(text, ok, frame)]."""
    def draw(t, n, g):
        im = solid()
        d = ImageDraw.Draw(im)
        fill = DEC(clamp(t / 16))
        reveal(im, meter_label, S(90), S(450), font("demi", 42), t, fill=C["grey"], left=True)
        d.text((W - S(90), S(470)), f"{int(round(100 * fill))}%", font=font("heavy", 54), fill=C["red"], anchor="rs")
        d.rounded_rectangle((S(90), S(500), W - S(90), S(560)), S(30), fill=(40, 43, 50))
        d.rounded_rectangle((S(90), S(500), S(90) + max(S(60), (W - S(180)) * fill), S(560)), S(30), fill=C["red"])
        reveal(im, heading, W / 2, S(665), font("bold", 56), t - 4)
        for k, (txt, ok, f0) in enumerate(cards):
            tt = g - f0 + 1
            if tt <= 0:
                continue
            col = C["green"] if ok else C["red"]
            p = spring(tt)
            y, hgt, cw = S(760 + k * 220), S(180), W - S(180)
            ci = Image.new("RGBA", (cw, hgt), (0, 0, 0, 0))
            cd = ImageDraw.Draw(ci)
            cd.rounded_rectangle((0, 0, cw - 1, hgt - 1), S(28), fill=(30, 33, 40), outline=col, width=S(5))
            cx, cy = S(95), hgt // 2
            q = DEC((tt - 4) / 8)
            if ok:
                pts = [(cx - S(34), cy), (cx - S(8), cy + S(30)), (cx + S(40), cy - S(34))]
                L1 = q * 2
                if L1 > 0:
                    cd.line([pts[0], (pts[0][0] + (pts[1][0] - pts[0][0]) * min(1, L1), pts[0][1] + (pts[1][1] - pts[0][1]) * min(1, L1))], fill=col, width=S(16))
                if L1 > 1:
                    cd.line([pts[1], (pts[1][0] + (pts[2][0] - pts[1][0]) * (L1 - 1), pts[1][1] + (pts[2][1] - pts[1][1]) * (L1 - 1))], fill=col, width=S(16))
            else:
                r = S(32)
                a1, a2 = min(1, q * 2), clamp(q * 2 - 1)
                if a1 > 0:
                    cd.line([(cx - r, cy - r), (cx - r + 2 * r * a1, cy - r + 2 * r * a1)], fill=col, width=S(16))
                if a2 > 0:
                    cd.line([(cx + r, cy - r), (cx + r - 2 * r * a2, cy - r + 2 * r * a2)], fill=col, width=S(16))
            cd.text((S(190), cy), txt, font=font("heavy", 78), fill=C["white"], anchor="lm")
            x = S(90) - int((1 - p) * S(80))
            a = clamp(DEC(tt / 5))
            ci = alpha_mul(ci, a)
            sh, pad = shadow_for((cw, hgt), S(28))
            im.alpha_composite(alpha_mul(sh, a), (x - pad, y - pad + S(20)))
            im.alpha_composite(ci, (x, y))
        return im
    return still(draw)


def chat_test(title_text, prompt, reply_label, reply, reply_frame, stamp=None, stamp_frame=None):
    """Your own test: the prompt bubble, then the AI reply card at reply_frame, then an optional stamp."""
    def draw(t, n, g):
        im = solid()
        d = ImageDraw.Draw(im, "RGBA")
        title(im, title_text, 300, t, 60)
        f = font("medium", 38)
        bw = d.textlength(prompt, font=f) + S(64)
        p = spring(t - 4)
        if p > 0.01:
            x0 = W - S(60) - bw + (1 - p) * S(60)
            d.rounded_rectangle((x0, S(470), x0 + bw, S(560)), S(45), fill=(60, 64, 74, int(255 * clamp(p * 1.3))))
            d.text((x0 + bw / 2, S(515)), prompt, font=f, fill=C["white"], anchor="mm")
        tt = g - reply_frame + 1
        if tt > 0:
            reveal(im, reply_label, S(70), S(625), font("demi", 34), tt, fill=C["grey"], left=True)
            c = Image.new("RGBA", (W - S(120), S(150)), (0, 0, 0, 0))
            cd = ImageDraw.Draw(c)
            cd.rounded_rectangle((0, 0, c.width - 1, c.height - 1), S(26), fill=(244, 244, 246))
            cd.text((S(44), c.height // 2), reply, font=font("bold", 52), fill=C["ink"], anchor="lm")
            q = spring(tt)
            c2 = alpha_mul(c.resize((int(c.width * (0.9 + 0.1 * q)), int(c.height * (0.9 + 0.1 * q))), Image.BICUBIC), DEC(tt / 5))
            sh, pad = shadow_for(c2.size, S(26))
            px, py = W // 2 - c2.width // 2, S(735) - c2.height // 2 + int((1 - q) * S(40))
            im.alpha_composite(alpha_mul(sh, DEC(tt / 5)), (px - pad, py - pad + S(18)))
            im.alpha_composite(c2, (px, py))
        if stamp:
            pop_text(im, stamp, W / 2, S(1010), 170, C["accent"], g - stamp_frame + 1, big=1.6)
        return im
    return still(draw)


def quote_fix(bg_img, title_text, callout_img, label, quote):
    """The fix: your prompt pops out, then the source's exact words in an accent pill."""
    def draw(t, n, g):
        im = bg_frame(bg_img, f"qf{id(bg_img)}", t, n, 0.62).copy()
        title(im, title_text, 300, t, 60)
        callout(im, callout_img, 660, 1000, t - 3)
        reveal(im, label, W / 2, S(930), font("demi", 40), t - 12, fill=C["grey"])
        accent_pill(im, quote, W / 2, S(1030), t - 15, 50)
        return im
    return still(draw)


# ---------------- captions ----------------
def _ass_color(rgb):
    r, g, b = rgb
    return f"&H00{b:02X}{g:02X}{r:02X}&"


def _captions():
    toks = []
    for w in WORDS:
        t = w["word"].strip()
        if t == "%" and toks:
            toks[-1][0] += "%"
            toks[-1][2] = w["end"]
            continue
        toks.append([t, w["start"], w["end"]])
    no_caps = [(b["start"], b["end"]) for b in _beats if not b["captions"]]
    toks = [(t, at(s), at(e)) for t, s, e in toks]
    toks = [x for x in toks if not any(a <= x[1] < b for a, b in no_caps)]
    chunks, cur = [], []
    for w in toks:
        cur.append(w)
        if len(cur) >= 3 or w[0].endswith((".", "?", ",")):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    ats = lambda f: f"{int(f / FPS // 3600)}:{int(f / FPS % 3600 // 60):02d}:{f / FPS % 60:05.2f}"
    hi = _ass_color(C["accent"])
    ass = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 2", "", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           f"Style: Cap,{BRAND['caption_font']},{BRAND['caption_size']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,4,3,2,60,60,{BRAND['caption_margin_v']},1",
           "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for ci, c in enumerate(chunks):
        nxt = chunks[ci + 1][0][1] if ci + 1 < len(chunks) else 10 ** 9
        c_end = min(c[-1][2] + 4, nxt)
        for j, (t, s, e) in enumerate(c):
            e2 = c[j + 1][1] if j + 1 < len(c) else c_end
            txt = " ".join((f"{{\\c{hi}\\fscx106\\fscy106}}" + x + "{\\c&HFFFFFF&\\fscx100\\fscy100}") if k == j else x for k, (x, _, _) in enumerate(c))
            intro = "{\\alpha&HFF&\\t(0,90,\\alpha&H00&)}" if j == 0 else ""
            ass.append(f"Dialogue: 0,{ats(s)},{ats(max(e2, s + 1))},Cap,,0,0,0,,{intro}{txt}")
    path = TMP / "captions.ass"
    path.write_text("\n".join(ass) + "\n")
    return path


# ---------------- render ----------------
def render(name):
    """Render all beats, captions and the voice into <out>/<name>.mp4 and write <out>/<name>.timeline.json."""
    _beats.sort(key=lambda b: b["start"])
    for k, b in enumerate(_beats):
        end = _beats[k + 1]["start"] if k + 1 < len(_beats) else TOTAL
        nxt = _beats[k + 1]["into"][1] if k + 1 < len(_beats) else 0
        b["end"], b["n"], b["len"] = end, end - b["start"], end - b["start"] + nxt
        b["path"] = TMP / f"p{k:02d}_{b['name']}.mp4"
        b["render"](b["path"], b["len"], b["start"])
        print(f"{b['name']:14s} {b['start'] / FPS:6.2f}s {b['n'] / FPS:5.2f}s in:{b['into'][0]}", flush=True)
    ass = _captions()
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gp = ImageDraw.Draw(grad)
    for y in range(int(H * 0.56), H):
        gp.line((0, y, W, y), fill=(0, 0, 0, int(130 * max(0.0, (y - H * 0.56) / (H * 0.44)) ** 1.3)))
    gpath = TMP / "bottom_grad.png"
    grad.save(gpath)
    inp, fc, last, blur = [], [], "0:v", []
    for b in _beats:
        inp += ["-i", b["path"]]
    for k in range(1, len(_beats)):
        kind, d = _beats[k]["into"]
        off = _beats[k]["start"] / FPS
        fc.append(f"[{last}][{k}:v]xfade=transition={'fade' if kind == 'cut' else kind}:duration={(d - 0.5) / FPS:.4f}:offset={off:.4f}[x{k}]")
        last = f"x{k}"
        if _beats[k]["blur_in"]:
            blur.append((off + 1 / FPS, off + (d - 1) / FPS, 90 if kind in ("slideup", "slidedown") else 0))
    env = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b, ang in blur if ang == 90) or "0"
    enh = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b, ang in blur if ang == 0) or "0"
    nv = len(_beats)
    inp += ["-loop", "1", "-i", gpath, "-i", VOICE]
    fc.append(f"[{last}]dblur=angle=90:radius={S(36)}:enable='{env}',dblur=angle=0:radius={S(36)}:enable='{enh}'[mbv];"
              f"[{nv}:v]format=rgba[gr];[mbv][gr]overlay=0:0:shortest=1,ass='{ass}',format=yuv420p[v]")
    fc.append(f"[{nv + 1}:a]aformat=channel_layouts=mono,pan=stereo|c0=0.7071*c0|c1=0.7071*c0[a]")
    suffix = "_preview" if SC < 1 else ""
    final = OUT / f"{name}{suffix}.mp4"
    run([FF, "-v", "error", "-y", *inp, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
         "-crf", "17", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-t", f"{TOTAL / FPS:.3f}", "-movflags", "+faststart", final])
    timeline = {
        "fps": FPS, "speed": SPEED, "total_frames": TOTAL, "duration_seconds": TOTAL / FPS,
        "picture": str(final), "voice": str(VOICE), "scale": SC,
        "beats": {b["name"]: {"start": b["start"], "end": b["end"], "silent": b["silent"]} for b in _beats},
        "marks": _marks,
        "quiet_windows": [{"label": b["name"], "start": b["start"] / FPS, "end": b["end"] / FPS} for b in _beats if b["silent"]] + _quiet,
    }
    (OUT / f"{name}{suffix}.timeline.json").write_text(json.dumps(timeline, indent=2) + "\n")
    print(f"done {final} {TOTAL / FPS:.2f}s", flush=True)
    return final
