#!/usr/bin/env python3
"""BuyAlbania Instagram Reels autopilot (runs in GitHub Actions).

Every run (9:00 and 18:00 Europe/Prague):
  1. picks the newest property on buyalbania.eu that was never posted (posted.json)
  2. builds a 9:16 video: stock hook clip (Pexels) -> property photos with zoom + texts -> CTA end card
  3. adds free music (Kevin MacLeod, incompetech.com, CC BY 4.0)
  4. publishes it as an Instagram Reel and records the property in posted.json

Secrets (GitHub -> Settings -> Secrets and variables -> Actions):
  IG_TOKEN    - Facebook page access token (never expires)
  IG_USER_ID  - Instagram business account id
  PIXABAY_KEY - free API key from pixabay.com/api/docs (stock sea/drone/food clips; optional)
  PEXELS_KEY  - alternative free key from pexels.com/api (optional)
"""
import html as htmlmod
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SITE = "https://www.buyalbania.eu"
GRAPH = "https://graph.facebook.com/v26.0"
W, H, FPS = 1080, 1920, 30
RED = (155, 27, 48)
WHITE = (255, 255, 255)
UA = {"User-Agent": "Mozilla/5.0 BuyAlbaniaReels"}
WORK = "work"
FONT_BOLD = "fonts/Poppins-Bold.ttf"
FONT_REG = "fonts/Poppins-Medium.ttf"

PERKS = [
    "Only minutes from the sea",
    "Albania is on its way to the EU",
    "Citrus trees & Mediterranean gardens",
    "Italian-like weather, 300 sunny days",
    "Warm, welcoming people",
    "Amazing fresh food & seafood",
]
HOOKS_MORNING = ["Wake up to THIS view", "Your sea-view home in Albania", "Coffee with a sea view?", "Seaside living in Albania"]
HOOKS_EVENING = ["Sunsets like this, every day", "Your own place by the sea", "Tonight's seaside pick", "Still renting your holidays?"]
# Kevin MacLeod (incompetech.com) - Licensed under Creative Commons: By Attribution 4.0
MUSIC = ["Pamgaea", "Funkorama", "Life of Riley", "Happy Alley", "Carefree", "Pixel Peeker Polka - faster",
         "Monkeys Spinning Monkeys", "Fluffing a Duck", "Wallpaper", "Sneaky Snitch"]
STOCK_QUERIES = ["mediterranean sea drone", "albania beach", "sea waves beach aerial", "sunset sea", "turquoise sea coast"]
STOCK_MID = ["mediterranean food", "lemon tree", "beach walk sunset", "seafood restaurant", "old town mediterranean", "drone coastline"]
STOCK_END = ["sunset beach", "sea drone", "couple beach sunset", "beach waves slow motion"]


def log(*a):
    print(*a, flush=True)


def get(url, **kw):
    r = requests.get(url, headers=UA, timeout=60, **kw)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------- property
def collect_ids():
    urls = [SITE + "/en/properties"] + [SITE + "/en/properties?advertList-page=%d" % p for p in range(2, 31)]
    ids = {}
    for u in urls:
        try:
            h = get(u).text
        except Exception:
            continue
        for m in re.finditer(r'href="(/en/properties/detail/[^"/]+/(\d+))(?:\?[^"]*)?"', h):
            ids.setdefault(m.group(2), SITE + m.group(1))
    if not ids:
        sys.exit("No properties found on buyalbania.eu")
    return ids


def pick_town(title):
    parts = [p.strip() for p in title.split(",")]
    for t in reversed(parts):
        t = re.sub(r"\s+(by|near) the sea$", "", t, flags=re.I).strip()
        if not t or re.search(r"albania", t, re.I) or re.search(r"\d|apartment|studio|floor|house|villa|bedroom|residence|m²|kk", t, re.I) or len(t) > 22:
            continue
        return t
    return "Albanian Riviera"


def facts(page, pid):
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', page, re.I) or re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    title = re.sub(r"<[^>]+>", "", htmlmod.unescape(m.group(1) if m else "")).strip()
    title = re.sub(r"\s*[|–-]\s*BuyAlbania.*$", "", title, flags=re.I)
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S | re.I)
    text = htmlmod.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text)
    price = re.search(r"(\d{1,3}(?:[ ,.]\d{3})+|\d{4,})\s*EUR(?!\s*/)", text)
    area = re.search(r"\bArea\s*:?\s*([\d.,]+)\s*m", text)
    sea = re.search(r"To the sea\s*:?\s*([\d.,]+\s*k?m)\b", text, re.I)
    imgs, seen = [], set()
    for mm in re.finditer(r"https://buyalbania\.fra1\.cdn\.digitaloceanspaces\.com/%s/([A-Za-z0-9_\-]+?)(?:_w\d+)?\.(?:webp|jpe?g|png)" % pid, page):
        if mm.group(1) in seen:
            continue
        seen.add(mm.group(1))
        imgs.append("https://buyalbania.fra1.cdn.digitaloceanspaces.com/%s/%s_w960.webp" % (pid, mm.group(1)))
    return {
        "id": pid,
        "title": title,
        "price": re.sub(r"[ .]", ",", price.group(1)) if price else "",
        "area": area.group(1) if area else "",
        "sea": sea.group(1) if sea else "",
        "town": pick_town(title),
        "images": imgs[:7],
    }


# ---------------------------------------------------------------- graphics
def font(path, size):
    return ImageFont.truetype(path, size)


def fit_text(draw, text, path, size, max_w):
    while size > 20:
        f = font(path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return font(path, size)


def wrap(draw, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if draw.textlength(test, font=f) <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = w_
    lines.append(cur)
    return lines


def pill(draw, xy, text, f, fill=RED, color=WHITE, pad=(36, 18)):
    x, y = xy
    tw = draw.textlength(text, font=f)
    asc, desc = f.getmetrics()
    box = [x, y, x + tw + pad[0] * 2, y + asc + desc + pad[1] * 2]
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=fill)
    draw.text((x + pad[0], y + pad[1]), text, font=f, fill=color)
    return box


def shadow_text(draw, xy, text, f, fill=WHITE, anchor="la"):
    x, y = xy
    for dx, dy in ((3, 3), (2, 2)):
        draw.text((x + dx, y + dy), text, font=f, fill=(0, 0, 0, 160), anchor=anchor)
    draw.text((x, y), text, font=f, fill=fill, anchor=anchor)


def photo_frame(src, out):
    """photo -> 9:16 frame: blurred cover background + full photo in the middle."""
    im = Image.open(src).convert("RGB")
    bg = im.copy()
    r = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * r) + 1, int(bg.height * r) + 1)).crop((0, 0, W, H)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.35)
    r = W / im.width
    fg = im.resize((W, int(im.height * r)))
    if fg.height > H * 0.75:
        fg = fg.crop((0, (fg.height - int(H * 0.75)) // 2, W, (fg.height + int(H * 0.75)) // 2))
    bg.paste(fg, (0, (H - fg.height) // 2 - 80))
    bg.save(out, quality=95)


def overlay_png(out, lines_big=None, line_small=None, tag=True, bottom=True):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if tag:
        pill(d, (60, 140), "FOR SALE · ALBANIA", font(FONT_BOLD, 40))
    if bottom and (lines_big or line_small):
        grad = Image.new("RGBA", (W, 700), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        for i in range(700):
            gd.line([(0, i), (W, i)], fill=(0, 0, 0, int(200 * i / 700)))
        img.alpha_composite(grad, (0, H - 700))
        y = H - 520
        if lines_big:
            f = fit_text(d, lines_big, FONT_BOLD, 110, W - 120)
            shadow_text(d, (60, y), lines_big, f)
            y += f.getmetrics()[0] + f.getmetrics()[1] + 10
        if line_small:
            f = font(FONT_REG, 50)
            for ln in wrap(d, line_small, f, W - 120):
                shadow_text(d, (60, y), ln, f)
                y += 66
    img.save(out)


def hook_png(out, hook, price):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pill(d, (60, 140), "FOR SALE · ALBANIA", font(FONT_BOLD, 40))
    f = font(FONT_BOLD, 96)
    lines = wrap(d, hook, f, W - 140)
    y = 640
    for ln in lines:
        shadow_text(d, (W // 2, y), ln, f, anchor="ma")
        y += 120
    if price:
        pf = font(FONT_BOLD, 80)
        tw = d.textlength("€ " + price, font=pf)
        pill(d, (int((W - tw) / 2) - 40, y + 30), "€ " + price, pf, pad=(40, 20))
    img.save(out)


def end_png(out, f_):
    img = Image.new("RGB", (W, H), RED)
    d = ImageDraw.Draw(img)
    shadow_text(d, (W // 2, 560), "BuyAlbania.eu", font(FONT_BOLD, 110), anchor="ma")
    d.text((W // 2, 720), "Seaside property in Albania", font=font(FONT_REG, 52), fill=WHITE, anchor="ma")
    pill(d, (150, 900), "DM us for details", font(FONT_BOLD, 72), fill=WHITE, color=RED, pad=(60, 30))
    d.text((W // 2, 1150), "Find it on BuyAlbania.eu – ID " + f_["id"], font=font(FONT_REG, 50), fill=WHITE, anchor="ma")
    d.text((W // 2, 1260), "Czech company · legal help · instalments", font=font(FONT_REG, 42), fill=WHITE, anchor="ma")
    img.save(out, quality=95)


# ---------------------------------------------------------------- video
def ff(args):
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + args
    subprocess.run(cmd, check=True)


ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]
# camera moves: (zoom expr, x expr, y expr) - stronger, alternating, "lively"
MOVES = [
    ("1+0.30*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),                 # punch zoom in
    ("1.22", "(iw-iw/zoom)*on/{n}", "ih/2-(ih/zoom/2)"),                       # pan left -> right
    ("1.30-0.30*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),              # zoom out
    ("1.22", "(iw-iw/zoom)*(1-on/{n})", "ih/2-(ih/zoom/2)"),                   # pan right -> left
    ("1+0.25*on/{n}", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/{n}"),              # zoom + tilt down
]
# final encode exactly to Instagram Reels specs (H.264 High 4.1, CFR 30 fps, closed 2 s GOP, AAC 48 kHz)
IG_ENC = ["-c:v", "libx264", "-preset", "medium", "-profile:v", "high", "-level:v", "4.1", "-pix_fmt", "yuv420p",
          "-r", "30", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0", "-b:v", "6M", "-maxrate", "8M", "-bufsize", "12M",
          "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k", "-movflags", "+faststart"]
XFADES = ["slideleft", "zoomin", "slideup", "circleopen", "smoothleft", "fadewhite", "slideright", "radial"]


def clip_from_image(img, ovl, dur, out, move=0, st=0.15):
    """Ken-Burns move + text overlay that slides up and fades in."""
    n = int(dur * FPS)
    z, x, y = [e.format(n=n) for e in MOVES[move % len(MOVES)]]
    vf = ("[0:v]scale=%d:%d,zoompan=z='%s':x='%s':y='%s':d=%d:s=%dx%d:fps=%d[bg];"
          "[1:v]format=rgba,fade=t=in:st=%.2f:d=0.25:alpha=1[ov];"
          "[bg][ov]overlay=x=0:y='if(lt(t,%.2f),(%.2f-t)*500,0)':shortest=1,format=yuv420p"
          % (W * 2, H * 2, z, x, y, n, W, H, FPS, st, st + 0.3, st + 0.3))
    ff(["-loop", "1", "-i", img, "-loop", "1", "-i", ovl, "-filter_complex", vf, "-t", str(dur)] + ENC + [out])


def clip_from_video(src, ovl, dur, out):
    vf = ("[0:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d,"
          "zoompan=z='1.15-0.15*on/%d':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=%dx%d:fps=%d[bg];"
          "[1:v]format=rgba,fade=t=in:st=0:d=0.2:alpha=1[ov];"
          "[bg][ov]overlay=x=0:y='if(lt(t,0.25),(0.25-t)*500,0)':shortest=1,format=yuv420p"
          % (W, H, W, H, FPS, int(dur * FPS), W, H, FPS))
    ff(["-i", src, "-loop", "1", "-i", ovl, "-filter_complex", vf, "-t", str(dur)] + ENC + [out])


def join_with_transitions(clips, durs, out, td=0.35):
    """chain clips with varied xfade transitions."""
    args, fc = [], []
    for c in clips:
        args += ["-i", c]
    prev, offset = "[0:v]", 0.0
    for i in range(1, len(clips)):
        offset += durs[i - 1] - td
        tr = XFADES[(i - 1) % len(XFADES)]
        lab = "[v%d]" % i
        fc.append("%s[%d:v]xfade=transition=%s:duration=%.2f:offset=%.2f%s" % (prev, i, tr, td, offset, lab))
        prev = lab
    ff(args + ["-filter_complex", ";".join(fc), "-map", prev] + ENC + [out])


_USED_STOCK = set()


def stock_clip(path, query=None):
    """free stock video (Pixabay, or Pexels if a key exists): sea, drone, beach, food..."""
    q = query or random.choice(STOCK_QUERIES)
    pix, pex = os.environ.get("PIXABAY_KEY"), os.environ.get("PEXELS_KEY")
    try:
        if pix:
            r = requests.get("https://pixabay.com/api/videos/", params={"key": pix, "q": q, "per_page": 50, "safesearch": "true"},
                             timeout=30).json()
            hits = [h for h in r.get("hits", []) if h.get("duration", 0) >= 4 and h["id"] not in _USED_STOCK]
            random.shuffle(hits)
            for h in hits:
                v = h.get("videos", {})
                f = v.get("medium") or v.get("large") or v.get("small")
                if f and f.get("url"):
                    open(path, "wb").write(get(f["url"]).content)
                    _USED_STOCK.add(h["id"])
                    log("stock clip (pixabay):", q, h.get("pageURL"))
                    return path
        if pex:
            r = requests.get("https://api.pexels.com/videos/search",
                             params={"query": q, "orientation": "portrait", "per_page": 30, "page": random.randint(1, 3)},
                             headers={"Authorization": pex}, timeout=30).json()
            vids = [v for v in r.get("videos", []) if v.get("duration", 0) >= 4 and v["id"] not in _USED_STOCK]
            random.shuffle(vids)
            for v in vids:
                files = sorted([f for f in v["video_files"] if f.get("width") and 700 <= f["width"] <= 1440 and f["height"] > f["width"]],
                               key=lambda f: f["width"])
                if files:
                    open(path, "wb").write(get(files[-1]["link"]).content)
                    _USED_STOCK.add(v["id"])
                    log("stock clip (pexels):", q, v.get("url"))
                    return path
    except Exception as e:
        log("stock video failed:", e)
    return None


def music(path):
    tracks = MUSIC[:]
    random.shuffle(tracks)
    for t in tracks:
        try:
            url = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/%s.mp3" % requests.utils.quote(t)
            r = get(url)
            if len(r.content) > 100000:
                open(path, "wb").write(r.content)
                return t
        except Exception as e:
            log("music failed", t, e)
    return None


def build_video(f_, hour):
    os.makedirs(WORK, exist_ok=True)
    clips = []
    hook = random.choice(HOOKS_MORNING if hour < 12 else HOOKS_EVENING)
    photos = []
    for i, u in enumerate(f_["images"]):
        p = "%s/p%d.webp" % (WORK, i)
        open(p, "wb").write(get(u).content)
        fr = "%s/f%d.jpg" % (WORK, i)
        photo_frame(p, fr)
        photos.append(fr)
    if not photos:
        raise RuntimeError("no photos")

    # 1) hook 3 s: stock video (or first photo)
    hook_png(WORK + "/hook.png", hook, f_["price"])
    sv = stock_clip(WORK + "/stock.mp4")
    if sv:
        clip_from_video(sv, WORK + "/hook.png", 2.5, WORK + "/c0.mp4")
    else:
        clip_from_image(photos[0], WORK + "/hook.png", 2.5, WORK + "/c0.mp4", move=0, st=0)
    clips.append(WORK + "/c0.mp4")
    durs = [2.5]

    # 2) photos with info
    perks = random.sample(PERKS, 3)
    infos = [
        ("€ " + f_["price"] if f_["price"] else "Seaside home", f_["town"] + ", Albania"),
        ((f_["sea"] + " to the sea") if f_["sea"] else "Close to the beach", (f_["area"] + " m²") if f_["area"] else ""),
        (perks[0], ""),
        (perks[1], ""),
        (perks[2], ""),
        ("Legal help & instalments", "Czech company you can trust"),
        ("DM us today", "BuyAlbania.eu – ID " + f_["id"]),
    ]
    for i, fr in enumerate(photos[:7]):
        big, small = infos[i % len(infos)]
        ov = "%s/o%d.png" % (WORK, i)
        overlay_png(ov, big, small or None)
        out = "%s/c%d.mp4" % (WORK, i + 1)
        clip_from_image(fr, ov, 1.9, out, move=i + 1)
        clips.append(out)
        durs.append(1.9)
        if i == min(2, len(photos[:7]) - 1):  # free stock B-roll in the middle (food, citrus, beach life)
            ovm = "%s/om.png" % WORK
            overlay_png(ovm, perks[1], "Life in Albania")
            sm = stock_clip(WORK + "/stock_mid.mp4", random.choice(STOCK_MID)) or stock_clip(WORK + "/stock_mid.mp4")
            if sm:
                clip_from_video(sm, ovm, 2.2, WORK + "/cmid.mp4")
                clips.append(WORK + "/cmid.mp4")
                durs.append(2.2)

    # 3) stock B-roll with CTA before the end card
    ove = WORK + "/oe.png"
    overlay_png(ove, "DM us today", "Find it on BuyAlbania.eu – ID " + f_["id"])
    se = stock_clip(WORK + "/stock_end.mp4", random.choice(STOCK_END))
    if se:
        clip_from_video(se, ove, 2.2, WORK + "/cse.mp4")
        clips.append(WORK + "/cse.mp4")
        durs.append(2.2)

    # 4) end card
    end_png(WORK + "/end.jpg", f_)
    empty = WORK + "/empty.png"
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(empty)
    clip_from_image(WORK + "/end.jpg", empty, 2.8, WORK + "/cend.mp4", move=0)
    clips.append(WORK + "/cend.mp4")
    durs.append(2.8)

    join_with_transitions(clips, durs, WORK + "/video.mp4")

    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", WORK + "/video.mp4"]).strip())
    track = music(WORK + "/music.mp3")
    if track:
        ff(["-i", WORK + "/video.mp4", "-ss", "1.5", "-stream_loop", "-1", "-i", WORK + "/music.mp3",
            "-filter_complex", "[1:a]volume=0.9,afade=t=in:d=0.2,afade=t=out:st=%.2f:d=1.5[a]" % (dur - 1.5),
            "-map", "0:v", "-map", "[a]"] + IG_ENC + ["-t", "%.2f" % dur,
            "-movflags", "+faststart", "final.mp4"])
    else:
        ff(["-i", WORK + "/video.mp4", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"] + IG_ENC + [
            "-shortest", "-movflags", "+faststart", "final.mp4"])
    return "final.mp4", track, hook


def caption(f_, hook, track):
    perks = random.sample(PERKS, 3)
    tags = ["#albania", "#albanianriviera", "#propertyinalbania", "#albaniarealestate", "#seaview", "#apartmentforsale",
            "#investinalbania", "#holidayhome", "#mediterranean", "#durres", "#golem", "#buyalbania", "#realestate", "#reels"]
    t = "#" + re.sub(r"[^a-z0-9]", "", f_["town"].lower())
    if t not in tags:
        tags.insert(0, t)
    lines = ["🌊 " + hook + ("" if hook[-1] in "?!" else "!"), "", "🏡 " + f_["title"]]
    if f_["price"]:
        lines.append("💶 Price: " + f_["price"] + " EUR")
    if f_["area"]:
        lines.append("📐 Area: " + f_["area"] + " m²")
    if f_["sea"]:
        lines.append("🌊 To the sea: " + f_["sea"])
    lines += ["📍 " + f_["town"] + ", Albania", "", "✨ Why Albania?"] + ["• " + p for p in perks]
    lines += ["", "🇨🇿 Czech company · legal help · instalments possible",
              "📩 DM us for details or find it on BuyAlbania.eu – ID " + f_["id"], "", " ".join(tags[:15])]
    if track:
        lines += ["", '🎵 Music: "%s" by Kevin MacLeod (incompetech.com), CC BY 4.0' % track]
    return "\n".join(lines)


# ---------------------------------------------------------------- instagram
def publish_reel(path, cap):
    """upload + publish with up to 3 attempts (a fresh container each time)."""
    tok, ig = os.environ["IG_TOKEN"], os.environ["IG_USER_ID"]
    data = open(path, "rb").read()
    last = None
    for attempt in range(1, 4):
        try:
            return _publish_once(tok, ig, data, cap)
        except Exception as e:
            last = e
            log("attempt %d failed: %s" % (attempt, e))
            time.sleep(30 * attempt)
    raise RuntimeError("all upload attempts failed: %s" % last)

def _publish_once(tok, ig, data, cap):
    r = requests.post("%s/%s/media" % (GRAPH, ig), data={
        "media_type": "REELS", "upload_type": "resumable", "caption": cap,
        "share_to_feed": "true", "thumb_offset": "3500", "access_token": tok}, timeout=60).json()
    if "id" not in r:
        raise RuntimeError("container error: %s" % r)
    cid = r["id"]
    up = requests.post("https://rupload.facebook.com/ig-api-upload/v26.0/%s" % cid,
                       headers={"Authorization": "OAuth " + tok, "offset": "0", "file_size": str(len(data)),
                                "Content-Type": "application/octet-stream"},
                       data=data, timeout=300)
    log("upload:", up.status_code, up.text[:200])
    if up.status_code != 200:
        raise RuntimeError("upload failed: %s %s" % (up.status_code, up.text[:300]))
    for _ in range(60):
        s = requests.get("%s/%s" % (GRAPH, cid), params={"fields": "status_code,status", "access_token": tok}, timeout=30).json()
        log("status:", s.get("status_code"), s.get("status", ""))
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError("processing failed: %s" % s)
        time.sleep(10)
    for _ in range(5):
        p = requests.post("%s/%s/media_publish" % (GRAPH, ig), data={"creation_id": cid, "access_token": tok}, timeout=60).json()
        if "id" in p:
            return p["id"]
        log("publish not ready:", p)
        time.sleep(15)
    raise RuntimeError("publish error: %s" % p)

# ---------------------------------------------------------------- main
def main():
    now = datetime.now(ZoneInfo("Europe/Prague"))
    force = os.environ.get("FORCE") == "1"
    if not force and now.hour not in (9, 18):
        log("Not posting time in Prague (%s) - skip" % now.strftime("%H:%M"))
        return
    posted = json.load(open("posted.json")) if os.path.exists("posted.json") else {}
    slot = now.strftime("%Y-%m-%d-") + ("am" if now.hour < 12 else "pm")
    if not force and any(v.get("slot") == slot for v in posted.values()):
        log("Already posted in slot", slot)
        return
    ids = collect_ids()
    fresh = sorted([i for i in ids if i not in posted], key=int, reverse=True)
    log("properties:", len(ids), "not posted yet:", len(fresh))
    for pid in fresh[:5]:
        f_ = facts(get(ids[pid]).text, pid)
        if len(f_["images"]) < 2:
            log("skip", pid, "- not enough photos")
            continue
        video, track, hook = build_video(f_, now.hour)
        cap = caption(f_, hook, track)
        log(cap)
        if os.environ.get("DRY_RUN") == "1":
            log("DRY RUN - not publishing")
            return
        mid = publish_reel(video, cap)
        posted[pid] = {"media": mid, "at": now.isoformat(), "slot": slot, "type": "reel"}
        json.dump(posted, open("posted.json", "w"), indent=1)
        log("Published reel", mid, "for property", pid)
        return
    sys.exit("No suitable property found")


if __name__ == "__main__":
    main()
