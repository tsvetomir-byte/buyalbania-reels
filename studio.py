#!/usr/bin/env python3
"""BuyAlbania Luxury Reels Studio - one finished luxury Reel from one property.

Runs in GitHub Actions (studio.yml). It never publishes anything: it only creates files for approval.
Inputs (env): PROPERTY (id or URL, empty = newest not posted), LENGTH (15-35 s), STYLE, LANG (cs/en/sk),
VARIANT (all/viral/luxury/sales). Output folder: out/<id>-<time>/ with reel_*.mp4, cover_*.jpg, captions.json, meta.json.
"""
import json
import os
import random
import re
import subprocess
import sys
import html as htmlmod
from datetime import datetime
from zoneinfo import ZoneInfo

import librosa
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import reels as R

W, H, FPS = 1080, 1920, 30
GOLD = (222, 188, 124)
WHITE = (255, 255, 255)
SITE = R.SITE
WORK = "work"
SERIF = os.environ.get("FONT_SERIF", "fonts/PlayfairDisplay.ttf")
SANS = os.environ.get("FONT_SANS", "fonts/Poppins-Medium.ttf")
MIXKIT = "Mixkit Stock Music Free License (https://mixkit.co/license/)"

# (id, title, artist) - free for social media posts and online ads, no attribution needed
MUSIC = {
    "deep_house": [(744, "House 02", "Lily J"), (745, "House Vibez", "Lily J"),
                   (129, "House Vibes", "Alejandro Magana"), (836, "Let's Move", "Michael Ramir C.")],
    "melodic_house": [(628, "Summer Dream", "Eugenio Mininni"), (1001, "I Do!", "Michael Ramir C."), (744, "House 02", "Lily J")],
    "lounge": [(695, "Pop 05", "Grigoriy Nuzhny"), (234, "Thinking About You", "Arulo"),
               (105, "See Line Funk", "Alejandro Magana"), (752, "Romantic 01", "Lily J")],
    "cinematic": [(471, "Rising Forest", "Diego Nava"), (770, "Autofahren", "Mauro Urbina")],
    "med_chill": [(475, "Majestic", "Diego Nava"), (427, "New York", "Arulo"), (234, "Thinking About You", "Arulo")],
}

T = {
    "cs": {
        "layout": "DISPOZICE", "area": "PLOCHA", "sea": "K MOŘI", "price": "CENA", "stock": "ilustrační záběr",
        "emotion": "Vlastní apartmán u moře může být blíž, než si myslíte.", "brand": "Váš nový život u moře.",
        "cta": "Napište nám MOŘE do zprávy.", "albania": "Albánie",
        "perks": ["Počasí jako v Itálii", "Albánie na cestě do EU", "Citrusy, moře a skvělé jídlo", "Skvělí lidé a výborná kuchyně"],
        "viral": ["Tipnete si cenu?", "Tenhle detail vás překvapí."],
        "luxury": ["Tohle není dovolená. Tohle může být váš domov.", "Představte si, že takhle začíná vaše ráno."],
        "sales": ["Takto vypadá {p} v Albánii.", "Co koupíte u moře za {p}?"],
        "ig": "Představte si ráno, kdy místo dopravní zácpy posloucháte moře. ☀️🌊",
        "fb": "Objevte Albánii, kde se středomořský životní styl potkává se zajímavými cenami nemovitostí. Česká společnost, právní servis a možnost splátek.",
        "more": "🏡 Tuto nabídku najdete na webu BuyAlbania.eu – ID {id}",
        "dm": "📩 Napište nám MOŘE a pošleme vám dostupné nemovitosti.",
        "lp": "Cena", "la": "Plocha", "ls": "K moři", "ll": "Dispozice",
    },
    "en": {
        "layout": "LAYOUT", "area": "AREA", "sea": "TO THE SEA", "price": "PRICE", "stock": "illustrative footage",
        "emotion": "Your own place by the sea may be closer than you think.", "brand": "Your new life by the sea.",
        "cta": "Message us SEA.", "albania": "Albania",
        "perks": ["Italian-like weather", "Albania on its way to the EU", "Citrus, sea and great food", "Warm people, amazing cuisine"],
        "viral": ["Can you guess the price?", "This detail will surprise you."],
        "luxury": ["This is not a holiday. This could be your home.", "Imagine your morning starting like this."],
        "sales": ["This is what {p} buys in Albania.", "What can {p} buy by the sea?"],
        "ig": "Imagine a morning when you hear the sea instead of traffic. ☀️🌊",
        "fb": "Discover Albania, where Mediterranean living meets attractive property prices. Czech company, legal help and instalments.",
        "more": "🏡 Find this offer on BuyAlbania.eu – ID {id}",
        "dm": "📩 Message us SEA and we will send you available properties.",
        "lp": "Price", "la": "Area", "ls": "To the sea", "ll": "Layout",
    },
    "sk": {
        "layout": "DISPOZÍCIA", "area": "PLOCHA", "sea": "K MORU", "price": "CENA", "stock": "ilustračný záber",
        "emotion": "Vlastný apartmán pri mori môže byť bližšie, než si myslíte.", "brand": "Váš nový život pri mori.",
        "cta": "Napíšte nám MORE do správy.", "albania": "Albánsko",
        "perks": ["Počasie ako v Taliansku", "Albánsko na ceste do EÚ", "Citrusy, more a skvelé jedlo", "Skvelí ľudia a výborná kuchyňa"],
        "viral": ["Tipnete si cenu?", "Tento detail vás prekvapí."],
        "luxury": ["Toto nie je dovolenka. Toto môže byť váš domov.", "Predstavte si, že takto začína vaše ráno."],
        "sales": ["Takto vyzerá {p} v Albánsku.", "Čo kúpite pri mori za {p}?"],
        "ig": "Predstavte si ráno, keď namiesto dopravnej zápchy počúvate more. ☀️🌊",
        "fb": "Objavte Albánsko, kde sa stredomorský životný štýl stretáva so zaujímavými cenami nehnuteľností. Česká spoločnosť, právny servis a možnosť splátok.",
        "more": "🏡 Túto ponuku nájdete na webe BuyAlbania.eu – ID {id}",
        "dm": "📩 Napíšte nám MORE a pošleme vám dostupné nehnuteľnosti.",
        "lp": "Cena", "la": "Plocha", "ls": "K moru", "ll": "Dispozícia",
    },
}


def log(*a):
    print(*a, flush=True)


def ff(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, check=True)


def probe(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).strip())


def fmt_price(p):
    digits = re.sub(r"\D", "", p or "")
    return re.sub(r"(?<=\d)(?=(\d{3})+$)", " ", digits) + " €" if digits else ""


# ---------------------------------------------------------------- property
def load_property(ref, lang):
    """only verified data from buyalbania.eu; stops when the offer is gone, reserved or sold."""
    url = ref if ref.startswith("http") else None
    pid = re.search(r"(\d+)/?(?:\?.*)?$", ref).group(1) if ref else None
    if not url:
        ids = R.collect_ids()
        if not pid:
            posted = json.load(open("posted.json")) if os.path.exists("posted.json") else {}
            pid = sorted([i for i in ids if i not in posted], key=int, reverse=True)[0]
        if pid not in ids:
            sys.exit("Property %s is not on buyalbania.eu (sold, reserved or removed)" % pid)
        url = ids[pid]
    page = R.get(url).text
    en = re.search(r'(/en/properties/detail/[^"\s]+/%s)\b' % pid, page)
    cs = re.search(r'(/cs/nemovitosti/detail/[^"\s]+/%s)\b' % pid, page)
    en_page = R.get(SITE + en.group(1)).text if en else page
    cs_page = R.get(SITE + cs.group(1)).text if cs else page
    f = R.facts(en_page, pid)
    txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", cs_page, flags=re.S | re.I)
    txt = re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", txt)))
    head = txt.split("O nemovitosti")[0]
    if re.search(r"\b(Rezervováno|Prodáno|Reserved|Sold)\b", head):
        sys.exit("Property %s is reserved or sold - no Reel" % pid)
    title = re.search(r'property="og:title"[^>]+content="([^"]+)"', cs_page)
    title = re.sub(r"\s*\|\s*BuyAlbania.*$", "", htmlmod.unescape(title.group(1)) if title else f["title"])
    layout = re.search(r"Dispozice\s*(\d\+\w+|studio|Studio)", head)
    town = re.search(r"Albánie\s+([^,·]{2,40}),\s*Albánie\s*·\s*ID", head)
    price = fmt_price(f["price"])
    if not price:
        sys.exit("Property %s has no price on the web" % pid)
    title_area = re.search(r"(\d+)\s*m²", title)
    warn = []
    area = f["area"]
    if title_area and area and title_area.group(1) != re.sub(r"[.,].*$", "", area):
        warn.append("Plocha v titulku (%s m²) a v parametrech (%s m²) nesouhlasí - plocha se ve videu nezobrazí." % (title_area.group(1), area))
        area = ""
    imgs = []
    for mm in re.finditer(r"https://buyalbania\.fra1\.cdn\.digitaloceanspaces\.com/%s/([A-Za-z0-9_\-]+?)(?:_w\d+)?\.(?:webp|jpe?g|png)" % pid, en_page):
        if mm.group(1) not in imgs:
            imgs.append(mm.group(1))
    base = "https://buyalbania.fra1.cdn.digitaloceanspaces.com/%s/%%s_w%%d.webp" % pid
    return {"id": pid, "title": title, "price": price, "area": area, "sea": f["sea"], "layout": layout.group(1) if layout else "",
            "town": town.group(1).strip() if town else f["town"], "url": SITE + (cs.group(1) if cs else en.group(1) if en else ""),
            "images": [base % (i, 0) for i in imgs[:12]], "image_base": [(base, i) for i in imgs[:12]], "warnings": warn}


def fetch_photos(f):
    out = []
    for n, (base, name) in enumerate(f["image_base"]):
        for size in (1920, 1440, 960):
            try:
                data = R.get(base % (name, size)).content
                break
            except Exception:
                data = None
        if not data:
            continue
        p = "%s/photo%d.webp" % (WORK, n)
        open(p, "wb").write(data)
        im = Image.open(p).convert("RGB")
        if min(im.size) < 400:
            continue
        j = "%s/photo%d.jpg" % (WORK, n)
        im.save(j, quality=95)
        out.append(j)
    return out


# ---------------------------------------------------------------- graphics
def tfont(path, size):
    return ImageFont.truetype(path, size)


def lines_of(d, text, f, max_w):
    words, ls, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=f) <= max_w:
            cur = t
        else:
            ls.append(cur)
            cur = w_
    return ls + [cur]


def text_soft(img, xy, text, f, fill=WHITE, anchor="la"):
    """text with a soft shadow, readable on any photo."""
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((xy[0], xy[1] + 4), text, font=f, fill=(0, 0, 0, 190), anchor=anchor)
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    ImageDraw.Draw(img).text(xy, text, font=f, fill=fill + (255,), anchor=anchor)


def shade(img, top, bottom, alpha):
    g = Image.new("L", (1, H), 0)
    for y in range(top, bottom):
        g.putpixel((0, y), int(alpha * (y - top) / max(1, bottom - top)))
    for y in range(bottom, H):
        g.putpixel((0, y), alpha)
    black = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    black.putalpha(g.resize((W, H)))
    img.alpha_composite(black)


def ovl_hook(out, text, stock_note=None):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 70))
    d = ImageDraw.Draw(img)
    size = 112
    while size > 64:
        f = tfont(SERIF, size)
        ls = lines_of(d, text, f, W - 180)
        if len(ls) <= 4:
            break
        size -= 6
    y = 860 - (len(ls) * int(size * 1.22)) // 2
    for ln in ls:
        text_soft(img, (W // 2, y), ln, f, anchor="ma")
        y += int(size * 1.22)
    d.line([(W // 2 - 70, y + 34), (W // 2 + 70, y + 34)], fill=GOLD + (255,), width=4)
    note(img, stock_note)
    img.save(out)


def note(img, text):
    if text:
        ImageDraw.Draw(img).text((W - 150, H - 330), text, font=tfont(SANS, 24), fill=(255, 255, 255, 170), anchor="ra")


def ovl_place(out, big, small):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade(img, 900, 1500, 170)
    d = ImageDraw.Draw(img)
    f = tfont(SERIF, 92)
    y = 1190
    for ln in lines_of(d, big, f, W - 200):
        text_soft(img, (80, y), ln, f)
        y += 112
    if small:
        d.text((84, y + 14), small.upper(), font=tfont(SANS, 34), fill=GOLD + (255,))
    img.save(out)


def ovl_fact(out, value, label):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade(img, 900, 1500, 180)
    d = ImageDraw.Draw(img)
    d.text((84, 1160), label, font=tfont(SANS, 36), fill=GOLD + (255,))
    size = 138
    while d.textlength(value, font=tfont(SERIF, size)) > W - 200:
        size -= 6
    text_soft(img, (80, 1220), value, tfont(SERIF, size))
    img.save(out)


def ovl_line(out, text, stock_note=None):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 55))
    d = ImageDraw.Draw(img)
    f = tfont(SERIF, 84)
    ls = lines_of(d, text, f, W - 200)
    y = 860 - len(ls) * 52
    for ln in ls:
        text_soft(img, (W // 2, y), ln, f, anchor="ma")
        y += 106
    note(img, stock_note)
    img.save(out)


def end_card(out, photo, tx, pid):
    im = Image.open(photo).convert("RGB")
    r = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1)).crop((0, 0, W, H)).filter(ImageFilter.GaussianBlur(26))
    im = ImageEnhance.Brightness(im).enhance(0.33).convert("RGBA")
    d = ImageDraw.Draw(im)
    text_soft(im, (W // 2, 660), "BUYALBANIA.EU", tfont(SERIF, 98), anchor="ma")
    d.line([(W // 2 - 90, 810), (W // 2 + 90, 810)], fill=GOLD + (255,), width=4)
    d.text((W // 2, 850), tx["brand"], font=tfont(SERIF, 56), fill=WHITE + (255,), anchor="ma")
    f = tfont(SANS, 46)
    y = 1040
    for ln in lines_of(d, tx["cta"], f, W - 240):
        d.text((W // 2, y), ln, font=f, fill=GOLD + (255,), anchor="ma")
        y += 64
    d.text((W // 2, y + 26), "ID " + pid, font=tfont(SANS, 32), fill=(255, 255, 255, 200), anchor="ma")
    im.convert("RGB").save(out, quality=95)


# ---------------------------------------------------------------- shots
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]
GRADE = "eq=contrast=1.06:saturation=1.14:brightness=0.012,vignette=PI/7"


def text_in(st=0.12):
    return ("[1:v]format=rgba,fade=t=in:st=%.2f:d=0.3:alpha=1[ov];" % st,
            "overlay=x=0:y='if(lt(t,%.2f),(%.2f-t)*120,0)':shortest=1,format=yuv420p" % (st + 0.3, st + 0.3))


def shot_photo(photo, ovl, dur, out, n):
    """smooth camera move on a full-screen photo (rendered at double size, so it does not shake)."""
    im = Image.open(photo).convert("RGB")
    wide = im.width / im.height > (W / H) * 1.18
    a, b = text_in()
    frames = int(round(dur * FPS))
    if wide:  # slow pan through the room
        r = H * 2 / im.height
        tmp = "%s/s%d.jpg" % (WORK, n)
        sw = int(im.width * r) // 2 * 2
        im.resize((sw, H * 2), Image.LANCZOS).save(tmp, quality=92)
        spare = sw - W * 2
        x0, x1 = (spare * 0.25, spare * 0.75) if n % 2 else (spare * 0.75, spare * 0.25)
        vf = "[0:v]format=rgb24,crop=%d:%d:x='%.1f+(%.1f)*t/%.3f':y=0:exact=1,scale=%d:%d,%s,format=yuv420p[bg];" % (
            W * 2, H * 2, x0, x1 - x0, dur, W, H, GRADE)
    else:  # slow zoom
        r = max(W * 2 / im.width, H * 2 / im.height)
        tmp = "%s/s%d.jpg" % (WORK, n)
        c = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
        c = c.crop(((c.width - W * 2) // 2, (c.height - H * 2) // 2, (c.width + W * 2) // 2, (c.height + H * 2) // 2))
        c.save(tmp, quality=92)
        z = "1+0.09*on/%d" % frames if n % 2 else "1.09-0.09*on/%d" % frames
        vf = "[0:v]zoompan=z='%s':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=%d:s=%dx%d:fps=%d,scale=%d:%d,%s,format=yuv420p[bg];" % (
            z, frames, W * 2, H * 2, FPS, W, H, GRADE)
    ff(["-loop", "1", "-framerate", str(FPS), "-i", tmp, "-loop", "1", "-framerate", str(FPS), "-i", ovl,
        "-filter_complex", vf + a + "[bg][ov]" + b, "-t", "%.3f" % dur] + ENC + [out])


def shot_video(src, ovl, dur, out):
    a, b = text_in(0.05)
    vf = "[0:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d,%s,format=yuv420p[bg];" % (W, H, W, H, FPS, GRADE)
    length = probe(src)
    ss = "%.2f" % max(0, random.uniform(0, max(0, length - dur - 0.5)))
    ff(["-ss", ss, "-i", src, "-loop", "1", "-framerate", str(FPS), "-i", ovl, "-filter_complex", vf + a + "[bg][ov]" + b,
        "-t", "%.3f" % dur] + ENC + [out])


def shot_still(img, dur, out):
    ff(["-loop", "1", "-framerate", str(FPS), "-i", img, "-vf", "fade=t=in:st=0:d=0.3,format=yuv420p", "-t", "%.3f" % dur] + ENC + [out])


_USED = set()


def beach_clip(path, queries):
    """free beach video from Pixabay (or Pexels), upright footage first."""
    key, pex = os.environ.get("PIXABAY_KEY"), os.environ.get("PEXELS_KEY")
    q = random.choice(queries)
    try:
        if pex:
            r = requests.get("https://api.pexels.com/videos/search", params={"query": q, "orientation": "portrait", "per_page": 30},
                             headers={"Authorization": pex}, timeout=30).json()
            vids = [v for v in r.get("videos", []) if v.get("duration", 0) >= 5 and v["id"] not in _USED]
            random.shuffle(vids)
            for v in vids:
                fs = sorted([x for x in v["video_files"] if x.get("width") and x.get("height", 0) > x["width"] >= 1000], key=lambda x: x["width"])
                if fs:
                    open(path, "wb").write(R.get(fs[0]["link"]).content)
                    _USED.add(v["id"])
                    return {"path": path, "source": v.get("url"), "license": "Pexels License"}
        if key:
            r = requests.get("https://pixabay.com/api/videos/", params={"key": key, "q": q, "per_page": 60, "safesearch": "true"}, timeout=30).json()
            hits = [h for h in r.get("hits", []) if h.get("duration", 0) >= 5 and h["id"] not in _USED]
            random.shuffle(hits)
            hits.sort(key=lambda h: h["videos"].get("large", {}).get("height", 0) > h["videos"].get("large", {}).get("width", 1), reverse=True)
            for h in hits:
                v = h["videos"].get("large") or h["videos"].get("medium")
                if v and v.get("url"):
                    open(path, "wb").write(R.get(v["url"]).content)
                    _USED.add(h["id"])
                    return {"path": path, "source": h.get("pageURL"), "license": "Pixabay Content License"}
    except Exception as e:
        log("beach clip failed:", e)
    return None


# ---------------------------------------------------------------- music + timing
def choose_style(f, wanted):
    if wanted in MUSIC:
        return wanted
    digits = int(re.sub(r"\D", "", f["price"]) or 0)
    if digits >= 180000:
        return "deep_house"
    if re.search(r"terasa|terrace|balk|výhled|sea view", f["title"], re.I):
        return "melodic_house"
    return random.choice(["med_chill", "deep_house", "lounge"])


def load_music(style, length):
    tracks = MUSIC[style][:]
    random.shuffle(tracks)
    for tid, name, artist in tracks:
        url = "https://assets.mixkit.co/music/%d/%d.mp3" % (tid, tid)
        try:
            data = R.get(url).content
            p = WORK + "/music.mp3"
            open(p, "wb").write(data)
            y, sr = librosa.load(p, sr=22050, mono=True)
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
            tempo = float(np.atleast_1d(tempo)[0])
            if len(beats) < 40 or len(y) / sr < length + 6:
                log("track too short", name)
                continue
            rms = librosa.feature.rms(y=y, hop_length=512)[0]
            times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=512)
            best, best_e = 0, -1  # strongest part of the song that still fits
            for k in range(0, len(beats), 4):
                if beats[k] + length + 3 > len(y) / sr:
                    break
                e = rms[(times >= beats[k]) & (times < beats[k] + length)].mean()
                if e > best_e:
                    best, best_e = k, e
            log("music:", name, "bpm %.0f" % tempo, "start %.1f" % beats[best])
            return {"id": tid, "title": name, "artist": artist, "url": url, "license": MIXKIT, "source": "Mixkit (mixkit.co)",
                    "bpm": round(tempo), "beats": [float(b) for b in beats[best:]], "style": style}
        except Exception as e:
            log("music failed", name, e)
    sys.exit("No music track could be loaded")


def on_beats(beats, wanted):
    """shot lengths that begin and end exactly on the beat of the music."""
    out, k, goal = [], 0, 0.0
    for w_ in wanted:
        goal += w_  # keeps the total length right even after rounding to beats
        n = 2
        while k + n + 2 < len(beats) and abs(beats[k + n + 2] - beats[0] - goal) <= abs(beats[k + n] - beats[0] - goal):
            n += 2
        out.append(beats[k + n] - beats[k])
        k += n
    return out


def join(clips, durs, td, out):
    args, fc = [], []
    for c in clips:
        args += ["-i", c]
    prev, pos = "[0:v]", 0.0
    kinds = ["fade", "smoothleft", "fade", "smoothup", "fade", "fadeblack"]
    for i in range(1, len(clips)):
        pos += durs[i - 1]
        lab = "[v%d]" % i
        fc.append("%s[%d:v]xfade=transition=%s:duration=%.3f:offset=%.3f%s" % (prev, i, kinds[(i - 1) % len(kinds)], td, pos, lab))
        prev = lab
    ff(args + ["-filter_complex", ";".join(fc), "-map", prev] + ENC + [out])


def with_music(video, music, out):
    dur = probe(video)
    ff(["-i", video, "-ss", "%.3f" % music["beats"][0], "-i", WORK + "/music.mp3", "-filter_complex",
        "[1:a]atrim=0:%.3f,asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st=%.3f:d=1.6,aresample=48000[a]" % (dur, dur - 1.6),
        "-map", "0:v", "-map", "[a]"] + R.IG_ENC + ["-t", "%.3f" % dur, out])


# ---------------------------------------------------------------- texts
def hooks(f, lang):
    t = T[lang]
    return {"viral": random.choice(t["viral"]), "luxury": random.choice(t["luxury"]),
            "sales": random.choice(t["sales"]).replace("{p}", f["price"])}


def recommended(f):
    digits = int(re.sub(r"\D", "", f["price"]) or 0)
    return "sales" if digits and digits <= 120000 else "luxury" if f["sea"] else "viral"


def captions(f, lang):
    def one(lg, long_=False):
        t = T[lg]
        tag = "#" + re.sub(r"[^a-z0-9]", "", f["town"].lower())
        tags = [tag, "#albanie" if lg != "en" else "#albania", "#buyalbania", "#albanianriviera", "#nemovitostiumore" if lg != "en" else "#seasideproperty",
                "#apartmanumore" if lg != "en" else "#apartmentbythesea", "#realestate", "#luxuryrealestate", "#investice" if lg != "en" else "#investment"]
        ls = [t["ig"], "", f["title"], "💶 %s: %s" % (t["lp"], f["price"])]
        if f["layout"]:
            ls.append("🛏 %s: %s" % (t["ll"], f["layout"]))
        if f["area"]:
            ls.append("📐 %s: %s m²" % (t["la"], f["area"]))
        if f["sea"]:
            ls.append("🌊 %s: %s" % (t["ls"], f["sea"]))
        if long_:
            ls += ["", t["fb"]]
        ls += ["", t["more"].replace("{id}", f["id"]), t["dm"], "", " ".join(tags)]
        return "\n".join(ls)
    return {"instagram": one(lang), "facebook": one(lang, True), "english": one("en"), "cta": T[lang]["cta"], "language": lang}


# ---------------------------------------------------------------- main
def plan(f, tx):
    facts_ = [(tx["price"], f["price"])]
    if f["sea"]:
        facts_.insert(0, (tx["sea"], f["sea"]))
    if f["area"]:
        facts_.insert(0, (tx["area"], f["area"] + " m²"))
    if f["layout"]:
        facts_.insert(0, (tx["layout"], f["layout"]))
    return facts_[:4]


def build(f, opts):
    os.makedirs(WORK, exist_ok=True)
    lang, length = opts["lang"], opts["length"]
    tx = T[lang]
    stamp = datetime.now(ZoneInfo("Europe/Prague")).strftime("%Y%m%d-%H%M")
    out_dir = "out/%s-%s" % (f["id"], stamp)
    os.makedirs(out_dir, exist_ok=True)
    photos = fetch_photos(f)
    if len(photos) < 4:
        sys.exit("Property %s has only %d usable photos" % (f["id"], len(photos)))
    style = choose_style(f, opts["style"])
    music = load_music(style, length + 2)
    facts_ = plan(f, tx)
    base = [1.6, 1.6] + [2.2] * 4 + [2.4] * len(facts_) + [2.4, 3.0, 3.6]
    k = length / sum(base)
    durs = on_beats(music["beats"], [b * k for b in base])
    td = 0.16
    log("shots:", [round(d, 2) for d in durs], "total %.1f" % sum(durs))

    sources = []
    def beach(name, q):
        c = beach_clip("%s/%s.mp4" % (WORK, name), q)
        if c:
            sources.append({"source": c["source"], "license": c["license"]})
        return c
    b_hook = beach("b_hook", ["mediterranean beach aerial", "turquoise sea beach drone", "sea waves beach aerial"])
    b_mid = beach("b_mid", ["beach walk sunset", "beach waves slow motion", "turquoise sea beach"])
    b_end = beach("b_end", ["sunset beach sea", "sea sunset drone", "beach sunset waves"])

    body, i = [], 2
    for n in range(4):  # the property
        o = "%s/o_p%d.png" % (WORK, n)
        if n == 0:
            ovl_place(o, f["town"], tx["albania"])
        else:
            Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(o)
        c = "%s/c%d.mp4" % (WORK, i)
        shot_photo(photos[(n + 1) % len(photos)], o, durs[i] + td, c, n + 1)
        body.append(c)
        i += 1
    for n, (label, value) in enumerate(facts_):  # main facts
        o = "%s/o_f%d.png" % (WORK, n)
        ovl_fact(o, value, label)
        c = "%s/c%d.mp4" % (WORK, i)
        shot_photo(photos[(n + 5) % len(photos)], o, durs[i] + td, c, n + 5)
        body.append(c)
        i += 1
    perk = random.choice(tx["perks"])
    for name, clip, text in (("mid", b_mid, perk), ("end", b_end, tx["emotion"])):  # emotion
        o = "%s/o_%s.png" % (WORK, name)
        ovl_line(o, text, tx["stock"] if clip else None)
        c = "%s/c%d.mp4" % (WORK, i)
        if clip:
            shot_video(clip["path"], o, durs[i] + td, c)
        else:
            shot_photo(photos[0], o, durs[i] + td, c, i)
        body.append(c)
        i += 1
    end_card(WORK + "/end.jpg", photos[0], tx, f["id"])
    shot_still(WORK + "/end.jpg", durs[i] + 0.6, WORK + "/cend.mp4")
    body.append(WORK + "/cend.mp4")

    all_hooks = hooks(f, lang)
    best = recommended(f)
    wanted = list(all_hooks) if opts["variant"] == "all" else [opts["variant"]]
    results = {}
    for v in wanted:
        o = "%s/o_h_%s.png" % (WORK, v)
        ovl_hook(o, all_hooks[v], tx["stock"] if b_hook else None)
        c0, c1 = "%s/h0_%s.mp4" % (WORK, v), "%s/h1_%s.mp4" % (WORK, v)
        if b_hook:
            shot_video(b_hook["path"], o, durs[0] + td, c0)
        else:
            shot_photo(photos[0], o, durs[0] + td, c0, 0)
        o2 = "%s/o_h2_%s.png" % (WORK, v)
        ovl_hook(o2, all_hooks[v])
        shot_photo(photos[0], o2, durs[1] + td, c1, 2)
        raw = "%s/raw_%s.mp4" % (WORK, v)
        join([c0, c1] + body, durs, td, raw)
        final = "%s/reel_%s.mp4" % (out_dir, v)
        with_music(raw, music, final)
        cover = "%s/cover_%s.jpg" % (out_dir, v)
        make_cover(photos[0], o2, cover)
        results[v] = {"hook": all_hooks[v], "video": os.path.basename(final), "cover": os.path.basename(cover), "seconds": round(probe(final), 1)}
        log("done", final, results[v])

    qc = quality(f, results, durs, photos, b_hook, opts)
    json.dump(captions(f, lang), open(out_dir + "/captions.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    meta = {"property": {k_: f[k_] for k_ in ("id", "title", "price", "area", "layout", "sea", "town", "url")}, "language": lang,
            "length": length, "variants": results, "recommended_hook": best, "all_hooks": all_hooks,
            "music": {k_: music[k_] for k_ in ("id", "title", "artist", "source", "url", "license", "bpm", "style")},
            "stock_video": sources, "quality": qc, "cost_czk": 0, "created": stamp, "published": False}
    json.dump(meta, open(out_dir + "/meta.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    sheet(out_dir, wanted[0])
    log(json.dumps(meta["quality"], ensure_ascii=False))
    return out_dir


def make_cover(photo, ovl, out):
    im = Image.open(photo).convert("RGB")
    r = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    c = ImageEnhance.Color(im.crop((x, y, x + W, y + H))).enhance(1.12).convert("RGBA")
    c.alpha_composite(Image.open(ovl).convert("RGBA"))
    c.convert("RGB").save(out, quality=93)


def quality(f, results, durs, photos, stock, opts):
    checks, warn = [], list(f["warnings"])
    for v, r in results.items():
        checks.append({"check": "délka %s" % v, "ok": 15 <= r["seconds"] <= 35, "value": r["seconds"]})
        checks.append({"check": "hook %s nejvýše 10 slov" % v, "ok": len(r["hook"].split()) <= 10, "value": r["hook"]})
    if not stock:
        warn.append("Úvod bez videa z pláže (nedostupné video z banky).")
    if len(photos) < 8:
        warn.append("Jen %d fotek, některé se opakují." % len(photos))
    return {"passed": all(c["ok"] for c in checks), "checks": checks, "warnings": warn}


def sheet(out_dir, v):
    """contact sheet for a quick visual check."""
    p = "%s/reel_%s.mp4" % (out_dir, v)
    ff(["-i", p, "-vf", "fps=1/2.5,scale=216:-1,tile=8x2", "-frames:v", "1", out_dir + "/preview.jpg"])


def main():
    length = max(15, min(35, int(os.environ.get("LENGTH") or 28)))
    lang = os.environ.get("LANG_REEL") or "cs"
    opts = {"length": length, "lang": lang if lang in T else "cs", "style": os.environ.get("STYLE") or "auto",
            "variant": os.environ.get("VARIANT") or "all"}
    f = load_property((os.environ.get("PROPERTY") or "").strip(), opts["lang"])
    log(json.dumps({k: v for k, v in f.items() if k not in ("images", "image_base")}, ensure_ascii=False))
    print(build(f, opts))


if __name__ == "__main__":
    main()
