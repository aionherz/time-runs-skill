#!/usr/bin/env python3
"""
time-runs-fast: build an emotional, cinematic family film from photos and
short video moments, set to music.

Works on macOS, Windows and Linux. Needs Python 3.8+, numpy, Pillow and ffmpeg
(ffmpeg from PATH, or the pip package `imageio-ffmpeg` as a fallback).

Order file (one item per line, in display order; '#' lines are comments):
    /photos/2014_birth.jpg
    /photos/2014_family.jpg [area=0.30,0.20,0.72,0.95]       # the child(ren) + the moment
    /photos/2014_portrait.jpg [area=0.35,0.15,0.60,0.70 fill] # fill the frame, cropped around it
    /videos/first_steps.mp4 [start=12.5 dur=5 area=0.2,0.3,0.6,1.0]
Relative paths are resolved against the order file's folder.

Examples
  python make_video.py --check
  python make_video.py --order-file order.txt --lang ru --format 9:16 --out film.mp4
  python make_video.py --order-file order.txt --lang de --preview --out preview.mp4
"""
import argparse
import math
import multiprocessing
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
except ImportError:
    sys.exit("ERROR: missing Python packages. Install them with:\n"
             "  python -m pip install numpy pillow")

try:  # optional: iPhone HEIC photos
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_OK = True
except Exception:
    HEIC_OK = False

SKILL_DIR = Path(__file__).resolve().parent.parent
MUSIC_DIR = SKILL_DIR / "assets" / "music"
FONT_DIR = SKILL_DIR / "assets" / "fonts"

END_LEN = 10.0             # closing card on white: this long after the music has ended
WHITE_FADE = 1.5           # the last picture melts into white during the last seconds of the music
END_BG = (251, 249, 245)   # warm white
END_INK = (58, 50, 44)     # warm dark grey text
END_TEXT = {
    "en": ("Made with {engine}", "and the free skill", "Time runs fast",
           "Music: Time runs fast — Aion Herz", "aionherz.de"),
    "de": ("Erstellt mit {engine}", "und dem kostenlosen Skill", "Time runs fast",
           "Musik: Time runs fast — Aion Herz", "aionherz.de"),
    "ru": ("Сделано в {engine}", "с бесплатным скиллом", "Time runs fast",
           "Музыка: Time runs fast — Aion Herz", "aionherz.de"),
}

FORMATS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}
LANGS = ("en", "de", "ru")
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif"}
VID_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mts", ".m2ts", ".3gp", ".mpg", ".mpeg",
           ".wmv", ".webm", ".dv"}
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus"}

OVERSAMPLE = 1.22          # base canvas is larger than the frame, so zooms stay sharp
TARGET_SLOT = 4.0          # seconds a photo is ideally on screen
MAX_SLOT = 5.5             # longer than this -> photos are repeated in another cycle
MIN_COMFORT_SLOT = 1.8     # shorter than this -> warn: too many photos for the track
MIN_REPEAT_SLOT = 3.2      # repeating photos must not make them shorter than this
CONTAIN_EXTRA = 1.3        # whole-photo layouts get a sharper canvas: their camera may go closer
AREA_MARGIN = 1.3          # the camera stops when the important area fills ~1/1.3 of the frame
MAX_ZOOM_COVER = 1.3       # never closer than this on photos that fill the frame
MAX_ZOOM_CONTAINED = 1.6   # ...or on photos shown whole (smaller) in the frame
DEFAULT_AREA = (0.2, 0.12, 0.8, 0.82)  # no area given: the middle, a bit high
CLIP_OVERLAP = 1.0         # transitions next to a video moment are at most this long
CLIP_LEN = 5.0             # a video moment lasts this long (a photo is on screen ~TARGET_SLOT)


# ----------------------------------------------------------------------------- tools

def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ffmpeg_or_exit():
    exe = find_ffmpeg()
    if not exe:
        sys.exit("ERROR: ffmpeg not found. Install one of:\n"
                 "  macOS:   brew install ffmpeg\n"
                 "  Windows: winget install Gyan.FFmpeg   (then open a new terminal)\n"
                 "  Linux:   sudo apt install ffmpeg\n"
                 "  any OS:  python -m pip install imageio-ffmpeg")
    return exe


def probe(ffmpeg, path):
    """Duration, display size (after rotation / pixel aspect) and creation time."""
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)],
                       capture_output=True, text=True, errors="replace")
    err = r.stderr
    info = {"duration": None, "w": None, "h": None, "created": None}
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        h, mi, s = m.groups()
        info["duration"] = int(h) * 3600 + int(mi) * 60 + float(s)
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        d = re.search(r"Video:.*?DAR (\d+):(\d+)", err)
        if d and int(d.group(2)) > 0:
            w = int(round(h * int(d.group(1)) / int(d.group(2))))
        rot = re.search(r"rotation of (-?\d+(?:\.\d+)?) degrees", err) or \
            re.search(r"rotate\s*:\s*(-?\d+)", err)
        if rot and abs(round(float(rot.group(1)))) % 180 == 90:
            w, h = h, w
        info["w"], info["h"] = w, h
    m = re.search(r"creation_time\s*:\s*(\S+)", err)
    if m:
        info["created"] = m.group(1)
    return info


def find_music(lang):
    if not MUSIC_DIR.is_dir():
        return None
    for p in sorted(MUSIC_DIR.iterdir()):
        if p.is_file() and p.stem.lower() == lang and p.suffix.lower() in AUDIO_EXT:
            return p
    return None


def run_check():
    ok = True
    print(f"python   : {sys.version.split()[0]}  OK")
    print(f"numpy    : {np.__version__}  OK")
    import PIL
    print(f"pillow   : {PIL.__version__}  OK")
    print(f"heic     : {'OK' if HEIC_OK else 'not installed (optional: python -m pip install pillow-heif)'}")
    ff = find_ffmpeg()
    print(f"ffmpeg   : {ff or 'MISSING'}")
    ok &= bool(ff)
    for lang in LANGS:
        m = find_music(lang)
        print(f"music {lang} : {m.name if m else 'not added yet (assets/music/' + lang + '.mp3)'}")
    print("READY" if ok else "NOT READY")
    return 0 if ok else 1


# ----------------------------------------------------------------------------- items

OPTS_RE = re.compile(r"\s*\[([^\[\]]*)\]\s*$")


def parse_item(text, base_dir=None):
    """'path [area=X0,Y0,X1,Y1 fill]' for photos, 'path [start=S dur=D area=...]' for videos.
    Coordinates are fractions of the picture's width and height (0,0 = top-left)."""
    text = text.strip()
    opts = {}
    m = OPTS_RE.search(text)
    if m:
        body = re.sub(r"\s*,\s*", ",", m.group(1).strip())
        body = re.sub(r"\s*=\s*", "=", body)
        for tok in body.split():
            if "=" not in tok:
                opts[tok.lower()] = True
                continue
            key, val = tok.split("=", 1)
            try:
                opts[key.lower()] = (tuple(float(v) for v in val.split(","))
                                     if "," in val else float(val))
            except ValueError:
                sys.exit(f"ERROR: cannot read option '{tok}' in: {text}")
        text = text[:m.start()].strip()
    text = text.strip('"').strip("'")
    p = Path(text).expanduser()
    if base_dir is not None and not p.is_absolute():
        p = base_dir / p
    return p, opts


def read_area(opts, name):
    """area=X0,Y0,X1,Y1 - the important part of the picture, fractions of width/height."""
    area = opts.get("area")
    if area is None:
        return None
    if not (isinstance(area, tuple) and len(area) == 4):
        sys.exit(f"ERROR: area must be written area=X0,Y0,X1,Y1 (fractions 0..1) for {name}")
    x0, y0, x1, y1 = (min(max(v, 0.0), 1.0) for v in area)
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    if x1 - x0 < 0.02 or y1 - y0 < 0.02:
        sys.exit(f"ERROR: area is too small for {name}: {area}")
    return (x0, y0, x1, y1)


def collect_items(inputs, order_file, ffmpeg):
    raw = []
    if order_file:
        of = Path(order_file).expanduser()
        for line in of.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.strip().startswith("#"):
                raw.append(parse_item(line, of.parent))
    for inp in inputs:
        p = Path(inp).expanduser()
        if p.is_dir():
            for q in sorted(p.iterdir(), key=lambda q: q.name.lower()):
                if q.suffix.lower() in IMG_EXT | VID_EXT:
                    raw.append((q, {}))
        else:
            raw.append(parse_item(inp))

    items = []
    for p, opts in raw:
        start, dur = opts.get("start"), opts.get("dur")
        if not p.is_file():
            sys.exit(f"ERROR: file not found: {p}")
        ext = p.suffix.lower()
        if ext in VID_EXT:
            info = probe(ffmpeg, p)
            if not info["w"]:
                sys.exit(f"ERROR: cannot read video {p}")
            length = info["duration"] or 0
            if start is None:
                start, dur = min(1.0, length * 0.2), min(CLIP_LEN, max(1.0, length - 1.0))
                print(f"WARNING: no moment chosen for {p.name}; using {start:.1f}s +{dur:.1f}s",
                      file=sys.stderr)
            if length and start >= length:
                sys.exit(f"ERROR: start={start} is beyond the end of {p.name} ({length:.1f}s)")
            if length:
                dur = min(dur, length - start)
            dur = max(dur, 1.5)
            items.append(dict(kind="video", path=p, start=start, dur=dur,
                              w=info["w"], h=info["h"], area=read_area(opts, p.name)))
        else:
            if ext in {".heic", ".heif"} and not HEIC_OK:
                sys.exit(f"ERROR: {p.name} is HEIC. Run: python -m pip install pillow-heif")
            area = read_area(opts, p.name)
            fill = bool(opts.get("fill"))
            if fill and area is None:
                sys.exit(f"ERROR: 'fill' needs an area too: [area=X0,Y0,X1,Y1 fill] for {p.name}")
            items.append(dict(kind="photo", path=p, area=area, fill=fill))
    if not items:
        sys.exit("ERROR: no photos or videos given")
    return items


# ----------------------------------------------------------------------------- look

def grade_array(a, look):
    """Gentle cinematic grade on a float [0,1] HxWx3 array."""
    if look == "natural":
        return a
    s = a * a * (3 - 2 * a)
    a = a * 0.72 + s * 0.28                      # soft S-curve
    lum = (a @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
    if look == "warm":
        sat, lift, top = 1.04, 0.035, 0.975
        tint = np.array([1.035, 1.0, 0.93], np.float32)
        shadow_tint = np.array([0.02, 0.008, -0.004], np.float32)
    else:  # film
        sat, lift, top = 0.86, 0.06, 0.95
        tint = np.array([1.03, 1.0, 0.95], np.float32)
        shadow_tint = np.array([-0.01, 0.012, 0.022], np.float32)
    a = lum + (a - lum) * sat
    a = a * tint + shadow_tint * (1 - lum)
    return np.clip(lift + a * (top - lift), 0, 1)  # faded blacks, soft highlights


def load_photo(path, need=None):
    """Open with EXIF rotation. `need`=(w, h): decode/shrink early to about that size."""
    im = Image.open(path)
    if need and im.format == "JPEG":
        m = max(need)
        im.draft("RGB", (m, m))  # fast DCT downscale while decoding
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (0, 0, 0))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    im = im.convert("RGB")
    if need:
        scale = max(need[0] / im.width, need[1] / im.height)
        if scale < 1:
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))),
                           Image.LANCZOS)
    return im


def fast_blur(im, radius):
    """Strong blur cheaply: downscale, blur, upscale."""
    w, h = im.size
    f = 8
    small = im.resize((max(1, w // f), max(1, h // f)), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(radius / f))
    return small.resize((w, h), Image.BILINEAR)


def fills_frame(w, h, BW, BH):
    ratio = max(BW / BH, w / h) / min(BW / BH, w / h)
    return ratio <= 1.2


def clamp_area(a):
    x0, y0, x1, y1 = a
    return (max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1))


def build_photo_base(path, W, H, look, area=None, fill=False):
    """Photo on an oversampled canvas, plus where its important area lands on that canvas.
    Cover-crop when the aspect is close (or `fill` is asked) - centred on the area; otherwise
    the whole photo over a blurred, darkened copy of itself."""
    BW, BH = int(round(W * OVERSAMPLE)), int(round(H * OVERSAMPLE))
    with Image.open(path) as probe_im:
        pw, ph = ImageOps.exif_transpose(probe_im).size if probe_im.getexif().get(274, 1) in (
            5, 6, 7, 8) else probe_im.size
    cover = fills_frame(pw, ph, BW, BH)
    if fill and not cover:  # only crop if the whole area fits into the crop
        sc = max(BW / pw, BH / ph)
        ax0, ay0, ax1, ay1 = area
        if (ax1 - ax0) * pw * sc <= BW * 0.98 and (ay1 - ay0) * ph * sc <= BH * 0.98:
            cover = True
        else:
            print(f"WARNING: {Path(path).name}: the area does not fit a full-frame crop - "
                  "showing the whole photo instead of 'fill'.", file=sys.stderr)
    if not cover:
        BW, BH = int(round(BW * CONTAIN_EXTRA)), int(round(BH * CONTAIN_EXTRA))
    if cover:
        s = max(BW / pw, BH / ph)
    else:
        s = min(BW * 0.94 / pw, BH * 0.94 / ph)
    im = load_photo(path, (math.ceil(pw * s), math.ceil(ph * s)))
    if look != "natural":  # grade the small image only: fast
        a = grade_array(np.asarray(im).astype(np.float32) / 255.0, look)
        im = Image.fromarray((a * 255 + 0.5).astype(np.uint8))
    pw, ph = im.size
    ax0, ay0, ax1, ay1 = area if area is not None else DEFAULT_AREA
    fx, fy = (ax0 + ax1) / 2, (ay0 + ay1) / 2

    if cover:
        scale = max(BW / pw, BH / ph)
        nw, nh = math.ceil(pw * scale), math.ceil(ph * scale)
        if (nw, nh) != (pw, ph):
            im = im.resize((nw, nh), Image.LANCZOS)
        if area is not None:  # keep the important area as central as the crop allows
            x = int(min(max(fx * nw - BW / 2, 0), nw - BW))
            y = int(min(max(fy * nh - BH / 2, 0), nh - BH))
        else:
            x = (nw - BW) // 2
            y = int((nh - BH) * 0.4)  # bias up: faces are usually in the upper part
        mapped = ((ax0 * nw - x) / BW, (ay0 * nh - y) / BH, (ax1 * nw - x) / BW, (ay1 * nh - y) / BH)
        return im.crop((x, y, x + BW, y + BH)), clamp_area(mapped), False

    scale = min(BW * 0.94 / pw, BH * 0.94 / ph)
    nw, nh = int(pw * scale), int(ph * scale)
    fg = im if (nw, nh) == (pw, ph) else im.resize((nw, nh), Image.LANCZOS)
    # background: the photo itself, cover-scaled, heavily blurred and darkened
    small = im.resize((max(1, pw // 8), max(1, ph // 8)), Image.BILINEAR)
    s2 = max(BW / small.width, BH / small.height)
    bg = small.resize((math.ceil(small.width * s2), math.ceil(small.height * s2)), Image.BILINEAR)
    bx, by = (bg.width - BW) // 2, (bg.height - BH) // 2
    bg = fast_blur(bg.crop((bx, by, bx + BW, by + BH)), 60)
    canvas = Image.fromarray((np.asarray(bg).astype(np.float32) * 0.5).astype(np.uint8))
    x, y = (BW - nw) // 2, (BH - nh) // 2
    shadow = Image.new("L", (BW, BH), 0)
    off = int(min(BW, BH) * 0.012)
    shadow.paste(150, (x + off // 2, y + off, x + nw + off // 2, y + nh + off))
    shadow = shadow.filter(ImageFilter.GaussianBlur(min(BW, BH) * 0.02))
    canvas.paste((0, 0, 0), (0, 0), shadow)
    canvas.paste(fg, (x, y))
    mapped = ((x + ax0 * nw) / BW, (y + ay0 * nh) / BH, (x + ax1 * nw) / BW, (y + ay1 * nh) / BH)
    return canvas, clamp_area(mapped), True


FFMPEG_GRADE = {
    "warm": "curves=all='0/0.035 0.25/0.22 0.5/0.505 0.75/0.79 1/0.975',"
            "colorchannelmixer=rr=1.035:bb=0.93,eq=saturation=1.04",
    "film": "curves=all='0/0.06 0.25/0.23 0.5/0.5 0.75/0.76 1/0.95',"
            "colorchannelmixer=rr=1.03:bb=0.95,eq=saturation=0.86",
    "natural": "null",
}


class VideoSource:
    """Streams one video moment from ffmpeg, graded and composed on the oversampled canvas.
    Restarts with a fresh seek if asked for a frame far from the current position."""

    def __init__(self, ffmpeg, item, length, W, H, fps, look):
        BW, BH = int(round(W * OVERSAMPLE)) // 2 * 2, int(round(H * OVERSAMPLE)) // 2 * 2
        self.size, self.ffmpeg, self.item, self.length, self.fps = (BW, BH), ffmpeg, item, length, fps
        pre = (f"bwdif=deint=interlaced,scale=trunc(iw*sar/2)*2:ih,setsar=1,"
               f"{FFMPEG_GRADE[look]},fps={fps}")
        w, h = item["w"], item["h"]
        ax0, ay0, ax1, ay1 = item.get("area") or DEFAULT_AREA
        fx, fy = (ax0 + ax1) / 2, (ay0 + ay1) / 2
        if fills_frame(w, h, BW, BH):
            sc = max(BW / w, BH / h)
            nw, nh = w * sc, h * sc
            if item.get("area"):
                x = min(max(fx * nw - BW / 2, 0), nw - BW)
                y = min(max(fy * nh - BH / 2, 0), nh - BH)
            else:
                x, y = (nw - BW) / 2, (nh - BH) * 0.4
            self.vf = (f"{pre},scale={BW}:{BH}:force_original_aspect_ratio=increase,"
                       f"crop={BW}:{BH}:{int(x)}:{int(y)}")
            self.area = clamp_area(((ax0 * nw - x) / BW, (ay0 * nh - y) / BH,
                                    (ax1 * nw - x) / BW, (ay1 * nh - y) / BH))
            self.contained = False
        else:
            self.contained = True
            fw, fh = int(BW * 0.94) // 2 * 2, int(BH * 0.94) // 2 * 2
            sc = min(fw / w, fh / h)
            nw, nh = w * sc, h * sc
            ox, oy = (BW - nw) / 2, (BH - nh) / 2
            self.area = ((ox + ax0 * nw) / BW, (oy + ay0 * nh) / BH,
                         (ox + ax1 * nw) / BW, (oy + ay1 * nh) / BH)
            self.vf = (f"{pre},split[a][b];"
                       f"[a]scale={BW}:{BH}:force_original_aspect_ratio=increase,crop={BW}:{BH},"
                       f"scale={BW // 8}:{BH // 8},gblur=sigma=7,scale={BW}:{BH},"
                       f"colorchannelmixer=rr=0.5:gg=0.5:bb=0.5[bg];"
                       f"[b]scale={fw}:{fh}:force_original_aspect_ratio=decrease[fg];"
                       f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
        self.nbytes = BW * BH * 3
        self.proc, self.idx, self.cur = None, -1, None

    def _open(self, idx0):
        self.close()
        off = idx0 / self.fps
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error",
               "-ss", f"{max(0.0, self.item['start'] + off):.3f}", "-i", str(self.item["path"]),
               "-t", f"{max(0.2, self.length - off + 0.5):.3f}", "-an",
               "-filter_complex", self.vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        self.idx = idx0 - 1

    def get(self, idx):
        if self.proc is None or idx < self.idx or idx > self.idx + 2 * self.fps:
            self._open(idx)
        while self.idx < idx:
            data = self.proc.stdout.read(self.nbytes)
            if len(data) < self.nbytes:
                self.idx = idx  # end of stream: hold the last frame
                break
            self.cur, self.idx = data, self.idx + 1
        if self.cur is None:
            return Image.new("RGB", self.size, (0, 0, 0))
        return Image.frombytes("RGB", self.size, self.cur)

    def close(self):
        if self.proc is not None:
            try:
                self.proc.stdout.close()
                self.proc.kill()
                self.proc.wait()
            except Exception:
                pass
            self.proc = None


# ----------------------------------------------------------------------------- plan

# The camera works with the important AREA (the child, with what makes the moment), given
# in canvas fractions. The close framing shows the whole area with a margin and never goes
# closer than that or than MAX_ZOOM; every move starts or ends on that framing.
def motion_path(name, area, contained=False):
    x0, y0, x1, y1 = area
    c = ((x0 + x1) / 2, (y0 + y1) / 2)
    size = max(x1 - x0, y1 - y0) * AREA_MARGIN          # view size needed, canvas fraction
    zmax = MAX_ZOOM_CONTAINED if contained else MAX_ZOOM_COVER
    zc = min(max(1.0 / max(size, 1e-6), 1.0), zmax)       # close framing zoom
    mid = (0.5, 0.5)

    def slack(z):  # how far the view can slide and still show the whole area
        return max(0.0, (1.0 / z - max(x1 - x0, y1 - y0)) / 2)

    if name == "zoom_in":      # whole picture -> the moment
        return 1.0, zc, mid, c
    if name == "zoom_out":     # the moment -> whole picture
        return zc, 1.0, c, mid
    zp = max(zc, 1.05)         # moving shots need a little room
    d = min(0.07, slack(zp) + 0.02)
    if name == "pan_right":    # glide in from the left, settle on the moment
        return zp, zp, (c[0] - d, c[1]), c
    if name == "pan_left":
        return zp, zp, (c[0] + d, c[1]), c
    if name == "rise":         # rise from below
        return zp, zp, (c[0], c[1] + d), c
    if name == "drift":        # slow diagonal approach
        z0 = max(1.0, 1 + (zc - 1) * 0.45)
        return z0, max(zc, 1.03), (c[0] + (0.5 - c[0]) * 0.8 + 0.03, c[1] + (0.5 - c[1]) * 0.8), c
    if name == "video_push":   # gentle push towards the moment on video
        return 1.0, 1 + (zc - 1) * 0.6, mid, (0.5 + (c[0] - 0.5) * 0.7, 0.5 + (c[1] - 0.5) * 0.7)
    raise ValueError(name)


MOTION_NAMES = ["zoom_in", "zoom_out", "pan_right", "pan_left", "rise", "drift", "video_push"]
PHOTO_MOTIONS = [m for m in MOTION_NAMES if m != "video_push"]

TRANSITIONS = {  # name: weight
    "crossfade": 3,
    "light_leak": 2,
    "blur_dissolve": 2,
    "zoom_dissolve": 2,
    "dip_black": 1,
}


def plan(items, total, rng):
    photos = [i for i, it in enumerate(items) if it["kind"] == "photo"]
    clip_slot = {i: max(1.2, it["dur"])
                 for i, it in enumerate(items) if it["kind"] == "video"}
    clip_time = sum(clip_slot.values())

    seq = list(range(len(items)))
    if photos:
        per = (total - clip_time) / len(photos)
        if per <= 0:
            sys.exit(f"ERROR: video moments ({clip_time:.0f}s) are longer than the music "
                     f"({total:.0f}s). Choose fewer or shorter moments.")
        cycles = 1
        if per > MAX_SLOT:
            rem = total - clip_time
            cycles = max(1, round(rem / (len(photos) * TARGET_SLOT)))
            while cycles > 1 and rem / (len(photos) * cycles) < MIN_REPEAT_SLOT:
                cycles -= 1
            seq += photos * (cycles - 1)  # later cycles: photos only, same order
        per = (total - clip_time) / (len(photos) * cycles)
    else:
        per = clip_time / len(items)
        cycles = max(1, math.ceil(total / max(clip_time, 1e-6)))
        seq = seq * cycles

    n = len(seq)
    is_photo = [items[i]["kind"] == "photo" for i in seq]
    weights = [1.0] * n
    if n >= 3:  # linger on the first and the last moment
        for k in (0, n - 1):
            if is_photo[k]:
                weights[k] = 1.5
    photo_w = sum(w for w, ph in zip(weights, is_photo) if ph)
    fixed = sum(clip_slot[i] for i, ph in zip(seq, is_photo) if not ph)
    unit = (total - fixed) / photo_w if photo_w else 0
    durs = [w * unit if ph else clip_slot[i] for i, w, ph in zip(seq, weights, is_photo)]
    if not photos:  # only videos: stretch evenly onto the music
        f = total / sum(durs)
        durs = [d * f for d in durs]
    starts = [0.0]
    for d in durs[:-1]:
        starts.append(starts[-1] + d)

    motions, used = [], {}
    for k, i in enumerate(seq):
        if not is_photo[k]:
            m = "video_push"
        elif k == 0:
            m = "zoom_in"
        elif k == n - 1 and n > 1:
            m = "zoom_out"
        else:
            u = used.setdefault(i, set())
            opts = [x for x in PHOTO_MOTIONS if x not in u and (not motions or x != motions[-1])]
            if not opts:
                opts = [x for x in PHOTO_MOTIONS if not motions or x != motions[-1]]
            m = rng.choice(opts)
        motions.append(m)
        u = used.setdefault(i, set())
        u.add(m)
        if len(u) >= len(PHOTO_MOTIONS):
            used[i] = {m}

    trans = []
    tnames, tweights = list(TRANSITIONS), list(TRANSITIONS.values())
    cycle_len = len(items)
    for k in range(n - 1):
        while True:
            t = rng.choices(tnames, tweights)[0]
            if trans and t == trans[-1]:
                continue
            if t == "dip_black" and (k < 2 or "dip_black" in trans[-4:]):
                continue
            break
        if cycles > 1 and photos and k + 1 >= cycle_len and (k + 1 - cycle_len) % len(photos) == 0:
            t = "dip_black"  # a new cycle starts: a gentle breath
        trans.append(t)

    tlens = []
    for k in range(n - 1):
        cap = CLIP_OVERLAP if (not is_photo[k] or not is_photo[k + 1]) else 1.3
        tl = min(cap, 0.42 * min(durs[k], durs[k + 1]))
        if trans[k] == "dip_black":
            tl = min(max(cap, 1.6) if is_photo[k] and is_photo[k + 1] else cap,
                     0.5 * min(durs[k], durs[k + 1]))
        tlens.append(tl)
    return dict(seq=seq, starts=starts, durs=durs, motions=motions, trans=trans,
                tlens=tlens, cycles=cycles, per=per, clip_time=clip_time)


# ----------------------------------------------------------------------------- end card

def _font(name, size):
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except Exception:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


def build_end_card(W, H, lang, engine):
    """Text lines as alpha masks: list of (x, y, mask float HxW, appear_time)."""
    made, with_skill, title, music, site = END_TEXT[lang]
    u = min(W, H) / 1080.0
    spec = [  # text, font, size, gap above, appear (s after the white is complete)
        (made.format(engine=engine), "CormorantGaramond_300Light_Italic.ttf", 58, 0, 0.5),
        (with_skill, "CormorantGaramond_300Light_Italic.ttf", 58, 4, 0.5),
        (title, "CormorantGaramond_600SemiBold.ttf", 124, 22, 0.85),
        ("—", "CormorantGaramond_500Medium.ttf", 50, 30, 1.25),
        (music, "CormorantGaramond_500Medium.ttf", 50, 26, 1.25),
        (site, "CormorantGaramond_600SemiBold.ttf", 66, 16, 1.6),
    ]
    lines, y = [], 0.0
    for text, font_name, size, gap, appear in spec:
        size = max(10, int(size * u))
        f = _font(font_name, size)
        while f.getlength(text) > W * 0.88 and size > 10:  # never wider than the frame
            size = int(size * 0.94)
            f = _font(font_name, size)
        l, t, r, b = f.getbbox(text)
        mask = Image.new("L", (r - l + 4, int(size * 1.35)), 0)
        ImageDraw.Draw(mask).text((2 - l, int(size * 0.12)), text, font=f, fill=255)
        y += gap * u
        lines.append([text, mask, y, appear + WHITE_FADE])  # timed from the start of the white fade
        y += mask.height
    top = (H - y) / 2 - H * 0.02
    out = []
    for text, mask, ly, appear in lines:
        x = int((W - mask.width) / 2)
        out.append((x, int(top + ly), np.asarray(mask).astype(np.float32) / 255.0, appear))
    return out


# ----------------------------------------------------------------------------- render

def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def soft_linear(x):
    """Mostly linear (motion keeps flowing through transitions), softened ends."""
    x = min(max(x, 0.0), 1.0)
    return 0.75 * x + 0.25 * (0.5 - 0.5 * math.cos(math.pi * x))


class Renderer:
    """Renders frame t. All pixel math is float32 in the 0..255 range."""

    def __init__(self, items, W, H, look, pl, ffmpeg, fps, end=None):
        self.items, self.W, self.H, self.look, self.pl = items, W, H, look, pl
        self.ffmpeg, self.fps = ffmpeg, fps
        self.end = end  # None or dict(lang, engine, start)
        if end:
            self.end_lines = build_end_card(W, H, end["lang"], end["engine"])
            self.end_bg = np.array(END_BG, np.float32)
            self.end_ink = np.array(END_INK, np.float32)
        self.photo_cache, self.photo_order = {}, []
        self.videos = {}  # slot index -> VideoSource
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
        strength = {"natural": 0.18, "warm": 0.32, "film": 0.42}[look]
        self.vignette = (1 - strength * np.clip(d, 0, 1) ** 2.2)[..., None].astype(np.float32)
        grain_amt = {"natural": 0.0, "warm": 0.0, "film": 3.0}[look]
        g = np.random.default_rng(7)
        self.grain = [(g.standard_normal((H, W, 1)).astype(np.float32) * grain_amt)
                      for _ in range(6)] if grain_amt else None
        lw, lh = max(2, W // 8), max(2, H // 8)
        ly, lx = np.mgrid[0:lh, 0:lw].astype(np.float32)
        self.leak_grid = (lx / lw, ly / lh)

    def clip_span(self, k):
        pl = self.pl
        a = pl["starts"][k] - (pl["tlens"][k - 1] / 2 if k > 0 else 0)
        b = pl["starts"][k] + pl["durs"][k] + (pl["tlens"][k] / 2 if k < len(pl["seq"]) - 1 else 0)
        return a, b

    def photo_base(self, i):
        if i not in self.photo_cache:
            it = self.items[i]
            self.photo_cache[i] = build_photo_base(it["path"], self.W, self.H, self.look,
                                                   it.get("area"), it.get("fill", False))
            self.photo_order.append(i)
            while len(self.photo_order) > 4:
                self.photo_cache.pop(self.photo_order.pop(0), None)
        return self.photo_cache[i]

    def video_frame(self, k, t, a, b):
        if k not in self.videos:
            it = self.items[self.pl["seq"][k]]
            self.videos[k] = VideoSource(self.ffmpeg, it, b - a, self.W, self.H, self.fps, self.look)
        return self.videos[k].get(max(0, int((t - a) * self.fps)))

    def release(self, k_min):
        for k in [k for k in self.videos if k < k_min]:
            self.videos.pop(k).close()

    def clip(self, k, t, extra_zoom=1.0):
        a, b = self.clip_span(k)
        u = soft_linear((t - a) / max(1e-6, b - a))
        if self.items[self.pl["seq"][k]]["kind"] == "video":
            base = self.video_frame(k, t, a, b)
            area, contained = self.videos[k].area, self.videos[k].contained
        else:
            base, area, contained = self.photo_base(self.pl["seq"][k])
        z0, z1, (cx0, cy0), (cx1, cy1) = motion_path(self.pl["motions"][k], area, contained)
        z = (z0 + (z1 - z0) * u) * extra_zoom
        cx, cy = cx0 + (cx1 - cx0) * u, cy0 + (cy1 - cy0) * u
        BW, BH = base.size
        # z=1 shows the whole composition; the base is oversampled, so even at the
        # strongest zoom we are still downscaling (stays sharp)
        vw, vh = min(BW / z, BW), min(BH / z, BH)
        x0 = min(max(cx * BW - vw / 2, 0), BW - vw)
        y0 = min(max(cy * BH - vh / 2, 0), BH - vh)
        img = base.resize((self.W, self.H), Image.BILINEAR, box=(x0, y0, x0 + vw, y0 + vh))
        return np.asarray(img).astype(np.float32)

    def blurred(self, arr, amount):
        if amount < 0.02:
            return arr
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        b = np.asarray(fast_blur(im, 70 * amount)).astype(np.float32)
        return arr + (b - arr) * min(1.0, amount * 1.6)

    def leak(self, p, k):
        lx, ly = self.leak_grid
        side = 1 if k % 2 == 0 else -1
        cx, cy = 0.5 + side * (0.9 - 1.4 * p), 0.25 + 0.3 * p
        r = np.sqrt(((lx - cx) / 0.75) ** 2 + ((ly - cy) / 0.9) ** 2)
        m = np.clip(1 - r, 0, 1) ** 1.6 * math.sin(math.pi * p) * 0.9
        col = np.array([1.0, 0.6, 0.28], np.float32)
        small = (m[..., None] * col * 255).astype(np.uint8)
        big = Image.fromarray(small).resize((self.W, self.H), Image.BILINEAR)
        return np.asarray(big).astype(np.float32) * (1 / 255.0)

    def frame(self, t, fi, total):
        if not self.end:
            return self.content_frame(t, fi, total, fade_out=True)
        c0 = self.end["start"]               # white fade starts; content (and music) end at c0 + WHITE_FADE
        if t < c0:
            return self.content_frame(t, fi, total, fade_out=False)
        w = ease((t - c0) / WHITE_FADE)
        if t < c0 + WHITE_FADE:
            out = self.content_frame(t, fi, total, fade_out=False, as_float=True)
            out += (self.end_bg - out) * w
        else:
            out = np.empty((self.H, self.W, 3), np.float32)
            out[:] = self.end_bg
        u = min(self.W, self.H) / 1080.0
        for x, y, mask, appear in self.end_lines:
            a = ease((t - c0 - appear) / 0.9)
            if a <= 0:
                continue
            yy = y + int(round((1 - a) * 16 * u))  # drifts up gently while appearing
            h, wd = mask.shape
            y0, y1 = max(0, yy), min(self.H, yy + h)
            x0, x1 = max(0, x), min(self.W, x + wd)
            if y1 <= y0 or x1 <= x0:
                continue
            m = mask[y0 - yy:y1 - yy, x0 - x:x1 - x, None] * a
            reg = out[y0:y1, x0:x1]
            reg += (self.end_ink - reg) * m
        np.clip(out, 0, 255, out=out)
        return out.astype(np.uint8)

    def content_frame(self, t, fi, total, fade_out=True, as_float=False):
        pl = self.pl
        n = len(pl["seq"])
        k = 0
        while k + 1 < n and t >= pl["starts"][k + 1]:
            k += 1
        tk = None
        if k + 1 < n and t > pl["starts"][k + 1] - pl["tlens"][k] / 2:
            tk = k
        elif k > 0 and t < pl["starts"][k] + pl["tlens"][k - 1] / 2:
            tk = k - 1
        self.release(k - 1)

        if tk is None:
            out = self.clip(k, t)
        else:
            tl = pl["tlens"][tk]
            p = (t - (pl["starts"][tk + 1] - tl / 2)) / tl
            pe = ease(p)
            kind = pl["trans"][tk]
            if kind == "zoom_dissolve":
                a = self.clip(tk, t, 1.0 + 0.05 * pe)
                b = self.clip(tk + 1, t, 1.07 - 0.07 * pe)
                out = a + (b - a) * pe
            else:
                a, b = self.clip(tk, t), self.clip(tk + 1, t)
                if kind == "dip_black":
                    out = a * max(0.0, 1 - 2 * pe) ** 1.3 if pe < 0.5 else b * (2 * pe - 1) ** 0.8
                elif kind == "blur_dissolve":
                    out = self.blurred(a, pe)
                    out = out + (self.blurred(b, 1 - pe) - out) * pe
                else:
                    out = a + (b - a) * pe
                    if kind == "light_leak":
                        L = self.leak(p, tk)
                        out = 255.0 - (255.0 - out) * (1 - L)

        np.multiply(out, self.vignette, out=out)
        fade_in, fade_len = 1.4, 2.4
        if t < fade_in:
            out *= ease(t / fade_in)
        elif fade_out and t > total - fade_len:
            out *= ease((total - t) / fade_len)
        if self.grain is not None:
            np.add(out, self.grain[fi % len(self.grain)], out=out)
        np.clip(out, 0, 255, out=out)
        return out if as_float else out.astype(np.uint8)

    def close(self):
        self.release(10 ** 9)


# ------------------------------------------------------------------- parallel workers

_RENDERER = None


def _init_worker(rargs):
    global _RENDERER
    _RENDERER = Renderer(*rargs)


def _render_chunk(job):
    f0, f1, fps, total = job
    try:
        return b"".join(_RENDERER.frame((fi + 0.5) / fps, fi, total).tobytes()
                        for fi in range(f0, f1))
    finally:
        _RENDERER.release(10 ** 9)  # chunks are not contiguous per worker


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Emotional family film from photos and video moments.")
    ap.add_argument("media", nargs="*", help="photos/videos/folders in display order "
                    "(a video may be followed by [start=S dur=D])")
    ap.add_argument("--order-file", help="text file, one item per line, in display order")
    ap.add_argument("--lang", choices=LANGS, help="selects assets/music/<lang>.* as soundtrack")
    ap.add_argument("--music", help="explicit audio file (overrides --lang)")
    ap.add_argument("--format", default="9:16", choices=list(FORMATS))
    ap.add_argument("--look", default="warm", choices=["warm", "film", "natural"])
    ap.add_argument("--duration", type=float, help="length in seconds of the photo/video series "
                    "when there is no music (the closing card comes on top)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seed", type=int, default=None, help="fix the effect variety")
    ap.add_argument("--preview", action="store_true", help="half resolution, fast encode")
    ap.add_argument("--workers", type=int, default=0, help="parallel processes (default: all cores)")
    ap.add_argument("--engine", default="AI",
                    help="AI tool named on the closing card, e.g. Claude or Codex")
    ap.add_argument("--no-end-card", action="store_true", help="skip the closing card")
    ap.add_argument("--out", default="time-runs-fast.mp4")
    ap.add_argument("--check", action="store_true", help="check dependencies and exit")
    args = ap.parse_args()

    if args.check:
        sys.exit(run_check())

    ffmpeg = ffmpeg_or_exit()
    items = collect_items(args.media, args.order_file, ffmpeg)

    music = None
    if args.music:
        music = Path(args.music).expanduser()
        if not music.is_file():
            sys.exit(f"ERROR: music file not found: {music}")
    elif args.lang:
        music = find_music(args.lang)
        if music is None:
            print(f"WARNING: no track for '{args.lang}' in {MUSIC_DIR} - rendering without music.",
                  file=sys.stderr)

    n_photos = sum(1 for it in items if it["kind"] == "photo")
    clip_guess = sum(max(1.2, it["dur"]) for it in items if it["kind"] == "video")
    if music:  # the photo/video series is exactly as long as the music
        content_total = probe(ffmpeg, music)["duration"]
        if not content_total:
            sys.exit(f"ERROR: cannot read duration of {music}")
    elif args.duration:
        content_total = args.duration
    else:
        content_total = TARGET_SLOT * (n_photos + 1) + clip_guess

    end = None
    total = content_total
    if not args.no_end_card:  # the closing card on white follows after the music has ended
        if content_total < 6:
            sys.exit("ERROR: the photo/video series is too short for the closing card; "
                     "use --no-end-card")
        end = dict(lang=args.lang or "en", engine=args.engine.strip() or "AI",
                   start=content_total - WHITE_FADE)  # last picture melts into white
        total = content_total + END_LEN

    W, H = FORMATS[args.format]
    if args.preview:
        W, H = (W // 2) // 2 * 2, (H // 2) // 2 * 2

    pl = plan(items, content_total, random.Random(args.seed))
    if n_photos and pl["per"] < MIN_COMFORT_SLOT:
        print(f"WARNING: {n_photos} photos get only {pl['per']:.1f}s each; it will feel rushed. "
              "Use fewer photos or fewer video moments.", file=sys.stderr)

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    n_frames = int(round(total * args.fps))

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(args.fps), "-i", "-"]
    if music:
        cmd += ["-i", str(music)]
    cmd += ["-map", "0:v"]
    if music:
        cmd += ["-map", "1:a", "-c:a", "aac", "-b:a", "192k",  # faded out at the end of the music
                "-af", f"afade=t=out:st={max(0.0, content_total - 3.0):.3f}:d=3,apad"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast" if args.preview else "medium",
            "-crf", "23" if args.preview else "19", "-maxrate", "6M" if args.preview else "14M",
            "-bufsize", "28M", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)]

    workers = args.workers or max(1, os.cpu_count() or 1)
    n_vid = len(items) - n_photos
    print(f"photos={n_photos} video_moments={n_vid} cycles={pl['cycles']} "
          f"slots={len(pl['seq'])} photo_time={pl['per']:.1f}s series={content_total:.1f}s "
          f"duration={total:.1f}s "
          f"size={W}x{H} workers={workers} music={music.name if music else 'none'}")

    rargs = (items, W, H, args.look, pl, ffmpeg, args.fps, end)
    chunk = args.fps  # one second of frames per job
    jobs = [(f0, min(f0 + chunk, n_frames), args.fps, total) for f0 in range(0, n_frames, chunk)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0, last, done = time.time(), -1, 0

    def progress(nf):
        nonlocal last
        pct = int(100 * nf / n_frames)
        if pct // 10 != last // 10:
            last = pct
            print(f"  {pct:3d}%  ({time.time() - t0:.0f}s)", flush=True)

    try:
        if workers == 1:
            _init_worker(rargs)
            for job in jobs:
                proc.stdin.write(_render_chunk(job))
                done += job[1] - job[0]
                progress(done)
        else:
            with multiprocessing.Pool(workers, initializer=_init_worker, initargs=(rargs,)) as pool:
                pending, it = deque(), iter(jobs)
                for job in it:  # keep a bounded window of jobs in flight (memory)
                    pending.append((job, pool.apply_async(_render_chunk, (job,))))
                    if len(pending) >= workers * 2:
                        break
                while pending:
                    job, res = pending.popleft()
                    proc.stdin.write(res.get())
                    done += job[1] - job[0]
                    progress(done)
                    nxt = next(it, None)
                    if nxt is not None:
                        pending.append((nxt, pool.apply_async(_render_chunk, (nxt,))))
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait() != 0:
        sys.exit("ERROR: ffmpeg failed")
    print(f"DONE {out.resolve()}  ({total:.1f}s, rendered in {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
