"""Render a reel.json into a 1080x1920 cinematic MP4: b-roll, word-timed captions, calm voice, music.

reel.json: {"handle": "@you", "slides": [{"say": "spoken words", "broll": "pexels search", "highlight": ["word"]}, ...]}
Usage: python render.py reel.json out.mp4
Needs: ffmpeg on PATH, pip install pillow edge-tts
Optional: PEXELS_API_KEY env (free) for b-roll, music.mp3 next to this file for a music bed.
"""
import asyncio
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
WHITE, GOLD = (250, 250, 245), (245, 197, 66)
VOICE, RATE = "en-US-ChristopherNeural", "-4%"
WORDS_PER_CAPTION = 3
HERE = Path(__file__).parent
FONTS = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
GRADE = "eq=brightness=-0.10:saturation=0.55:contrast=1.08,vignette=PI/4"


def font(size):
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


async def _speak(text, mp3):
    words = []
    with open(mp3, "wb") as f:
        async for chunk in edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary").stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append((chunk["text"], chunk["offset"] / 1e7))  # 100ns ticks -> seconds
    return words


def speak(text, mp3):
    """Write mp3, return [(word, start_seconds)]."""
    return asyncio.run(_speak(text, mp3))


def captions(words, total):
    """Group words into short captions: [(text_words, start, end)]."""
    groups = [words[i:i + WORDS_PER_CAPTION] for i in range(0, len(words), WORDS_PER_CAPTION)]
    out = []
    for i, g in enumerate(groups):
        end = groups[i + 1][0][1] if i + 1 < len(groups) else total
        out.append(([w for w, _ in g], g[0][1], end))
    return out


def draw_caption(words, highlight, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 96
    while True:  # shrink until the line fits inside the safe margins
        f = font(size)
        space = d.textlength(" ", font=f)
        widths = [d.textlength(w.upper(), font=f) for w in words]
        if sum(widths) + space * (len(words) - 1) <= W - 120 or size <= 48:
            break
        size -= 6
    x = (W - sum(widths) - space * (len(words) - 1)) / 2
    y = H * 0.58
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for w, wd in zip(words, widths):
        key = re.sub(r"\W", "", w).lower()
        hot = key in highlight or any(c.isdigit() for c in w)
        sd.text((x + 4, y + 6), w.upper(), font=f, fill=(0, 0, 0, 200))
        d.text((x, y), w.upper(), font=f, fill=GOLD if hot else WHITE)
        x += wd + space
    out = Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(8)), img)
    out.save(path)


def handle_overlay(handle, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text(((W - d.textlength(handle, font=font(40))) / 2, H - 230), handle, font=font(40),
           fill=(255, 255, 255, 170))
    img.save(path)


def broll(query, dest):
    """Download a portrait Pexels clip for query. Returns path or None."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key or not query:
        return None
    try:
        url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(
            {"query": query, "orientation": "portrait", "per_page": 8})
        req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "ig-content-bot/1.0"})
        videos = json.load(urllib.request.urlopen(req, timeout=20))["videos"]
        files = [f for v in videos for f in v["video_files"]
                 if f.get("file_type") == "video/mp4" and (f.get("height") or 0) >= 1280]
        if not files:
            return None
        pick = random.choice(sorted(files, key=lambda f: f["height"])[:4])  # smallest HD = fast download
        urllib.request.urlretrieve(pick["link"], dest)
        return dest
    except Exception as e:  # no b-roll is fine, a crashed run is not
        print(f"warn: b-roll '{query}': {e}", file=sys.stderr)
        return None


def render_slide(slide, handle_png, tmp, i):
    mp3 = tmp / f"{i}.mp3"
    words = speak(slide["say"], mp3)
    total = duration(mp3) + 0.35
    highlight = {h.lower() for h in slide.get("highlight", [])}
    caps = captions(words, total)
    pngs = []
    for j, (ws, _, _) in enumerate(caps):
        p = tmp / f"{i}_{j}.png"
        draw_caption(ws, highlight, p)
        pngs.append(p)

    bg = broll(slide.get("broll"), tmp / f"{i}_bg.mp4")
    if bg:
        bg_in = ["-stream_loop", "-1", "-i", str(bg)]
        bg_f = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,{GRADE}[bg]"
    else:  # shortcut: dark gradient + slow zoom when there is no Pexels key; b-roll looks far better.
        bg_in = ["-f", "lavfi", "-i", f"color=c=0x0b0b0e:s={W}x{H}:r=30"]
        bg_f = f"[0:v]{GRADE}[bg]"

    inputs = bg_in + ["-i", str(mp3), "-i", str(handle_png)]
    chain = [bg_f, "[bg][2:v]overlay=0:0[v0]"]
    for j, (p, (_, start, end)) in enumerate(zip(pngs, caps)):
        inputs += ["-i", str(p)]
        chain.append(f"[v{j}][{j + 3}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[v{j + 1}]")
    out = tmp / f"{i}.mp4"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", f"[v{len(pngs)}]",
         "-map", "1:a", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out)])
    return out


def render(reel, out):
    slides = reel["slides"]
    assert 3 <= len(slides) <= 10, "need 3-10 slides"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        handle_png = tmp / "handle.png"
        handle_overlay(reel.get("handle", ""), handle_png)
        clips = [render_slide(s, handle_png, tmp, i) for i, s in enumerate(slides)]
        lst = tmp / "list.txt"
        lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), "utf-8")
        joined = tmp / "joined.mp4"
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
        music = HERE / "music.mp3"
        if music.exists():
            run(["ffmpeg", "-y", "-i", str(joined), "-stream_loop", "-1", "-i", str(music), "-filter_complex",
                 "[1:a]volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                 "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(out)])
        else:
            run(["ffmpeg", "-y", "-i", str(joined), "-c", "copy", "-movflags", "+faststart", str(out)])
    total = duration(out)
    assert 3 <= total <= 90, f"reel is {total:.1f}s, Instagram wants 3-90s"
    return total


if __name__ == "__main__":
    assert [c[0] for c in captions([("a", 0), ("b", 1), ("c", 2), ("d", 3)], 5)] == [["a", "b", "c"], ["d"]]
    reel = json.loads(Path(sys.argv[1]).read_text("utf-8"))
    print(f"{sys.argv[2]}: {render(reel, sys.argv[2]):.1f}s")
