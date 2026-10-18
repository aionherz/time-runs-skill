#!/usr/bin/env python3
"""
time-runs-fast: prepare overview sheets so the agent can SEE the media.

  * photos -> numbered contact sheets (12 per sheet) + a table with EXIF date / camera
  * videos -> one storyboard sheet per video with timestamps under every frame

Usage
  python scan_media.py <files or folders...> --out-dir sheets [--recursive]
  python scan_media.py clip.mp4 --out-dir sheets --from 40 --to 70 --step 1   # zoom into a video
Every tile carries a light 0.1 coordinate grid (0,0 = top-left) for reading
area=X0,Y0,X1,Y1 boxes. --no-grid turns it off.

Then open the printed sheet images with your image-viewing tool.
"""
import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_video import (IMG_EXT, VID_EXT, HEIC_OK, ffmpeg_or_exit, load_photo,  # noqa: E402
                        probe)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

THUMB = 440
COLS = 3
PER_SHEET = 9
GRID = True


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def exif_info(path):
    try:
        im = Image.open(path)
        ex = im.getexif()
        sub = ex.get_ifd(0x8769) if hasattr(ex, "get_ifd") else {}
        date = sub.get(36867) or ex.get(306)
        model = ex.get(272)
        return (str(date).strip() if date else ""), (str(model).strip() if model else "")
    except Exception:
        return "", ""


def add_grid(im):
    """Light coordinate grid every 0.1 of width/height, labelled every 0.2 (0,0 = top-left)."""
    im = im.convert("RGB")
    over = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    w, h = im.size
    f = font(max(12, w // 28))
    for i in range(1, 10):
        x, y = w * i / 10, h * i / 10
        a = 150 if i % 2 == 0 else 70
        d.line([(x, 0), (x, h)], fill=(255, 255, 255, a), width=1)
        d.line([(0, y), (w, y)], fill=(255, 255, 255, a), width=1)
        if i % 2 == 0:
            for txt, pos in ((f"{i / 10:.1f}", (x + 3, 2)), (f"{i / 10:.1f}", (3, y + 1))):
                d.text((pos[0] + 1, pos[1] + 1), txt, fill=(0, 0, 0, 200), font=f)
                d.text(pos, txt, fill=(255, 235, 120, 255), font=f)
    return Image.alpha_composite(im.convert("RGBA"), over).convert("RGB")


def sheet(tiles, title, path):
    """tiles: list of (PIL image, label)."""
    rows = math.ceil(len(tiles) / COLS)
    cell_h = THUMB + 44
    W, H = COLS * THUMB + (COLS + 1) * 10, rows * cell_h + 60
    S = Image.new("RGB", (W, H), (24, 24, 28))
    d = ImageDraw.Draw(S)
    d.text((12, 14), title, fill=(255, 255, 255), font=font(28))
    for n, (im, label) in enumerate(tiles):
        r, c = divmod(n, COLS)
        x, y = 10 + c * (THUMB + 10), 60 + r * cell_h
        im = im.copy()
        im.thumbnail((THUMB, THUMB))
        if GRID:
            im = add_grid(im)
        S.paste(im, (x + (THUMB - im.width) // 2, y + (THUMB - im.height) // 2))
        d.text((x + 4, y + THUMB + 6), label, fill=(255, 220, 120), font=font(24))
    S.save(path, quality=85)
    return path


def gather(inputs, recursive):
    files = []
    for inp in inputs:
        p = Path(inp).expanduser()
        if p.is_dir():
            it = p.rglob("*") if recursive else p.iterdir()
            files += sorted([q for q in it if q.is_file() and q.suffix.lower() in IMG_EXT | VID_EXT],
                            key=lambda q: str(q).lower())
        elif p.is_file():
            files.append(p)
        else:
            print(f"WARNING: not found: {p}", file=sys.stderr)
    return files


def video_frames(ffmpeg, path, times, tmp):
    out = []
    for i, t in enumerate(times):
        f = Path(tmp) / f"f{i:03d}.jpg"
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}",
                        "-i", str(path), "-frames:v", "1",
                        "-vf", f"scale=trunc(iw*sar/2)*2:ih,setsar=1,scale={THUMB}:{THUMB}:"
                               "force_original_aspect_ratio=decrease", str(f)],
                       stdin=subprocess.DEVNULL)
        if f.exists():
            out.append((Image.open(f).convert("RGB"), t))
    return out


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out-dir", default="sheets")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--from", dest="t_from", type=float, help="video detail: start second")
    ap.add_argument("--to", dest="t_to", type=float, help="video detail: end second")
    ap.add_argument("--step", type=float, help="video: seconds between frames")
    ap.add_argument("--max-frames", type=int, default=24)
    ap.add_argument("--no-grid", action="store_true", help="no coordinate grid on the tiles")
    args = ap.parse_args()
    global GRID
    GRID = not args.no_grid

    ffmpeg = ffmpeg_or_exit()
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    files = gather(args.inputs, args.recursive)
    photos = [f for f in files if f.suffix.lower() in IMG_EXT]
    videos = [f for f in files if f.suffix.lower() in VID_EXT]

    if photos:
        print("PHOTOS  (#  | exif date | camera | file)")
        tiles, sheets = [], []
        for n, p in enumerate(photos, 1):
            date, model = exif_info(p)
            print(f"  P{n:<3}| {date or '-':19} | {model or '-':18} | {p}")
            try:
                if p.suffix.lower() in {".heic", ".heif"} and not HEIC_OK:
                    raise RuntimeError("needs pillow-heif")
                im = load_photo(p)
                im.thumbnail((THUMB * 2, THUMB * 2))
            except Exception as e:
                print(f"     WARNING: cannot open ({e})", file=sys.stderr)
                im = Image.new("RGB", (THUMB, THUMB), (80, 0, 0))
            tiles.append((im, f"P{n}  {p.name[:22]}"))
        for s in range(0, len(tiles), PER_SHEET):
            path = out_dir / f"photos_{s // PER_SHEET + 1:02d}.jpg"
            sheets.append(sheet(tiles[s:s + PER_SHEET],
                                f"Photos P{s + 1}-P{min(s + PER_SHEET, len(tiles))}", path))
        print("PHOTO SHEETS:")
        for s in sheets:
            print(f"  {s}")

    if videos:
        print("VIDEOS")
        with tempfile.TemporaryDirectory() as tmp:
            for n, v in enumerate(videos, 1):
                info = probe(ffmpeg, v)
                dur = info["duration"] or 0
                a = max(0.0, args.t_from or 0.0)
                b = min(dur, args.t_to) if args.t_to else dur
                span = max(0.1, b - a)
                step = args.step or max(1.0, span / args.max_frames)
                count = min(args.max_frames, max(1, int(span / step)))
                times = [a + step * (i + 0.5) for i in range(count)]
                frames = video_frames(ffmpeg, v, times, tmp)
                for f in Path(tmp).glob("*.jpg"):
                    f.unlink()
                path = out_dir / f"video_V{n:02d}_{v.stem[:40]}.jpg"
                sheet([(im, mmss(t)) for im, t in frames],
                      f"V{n}  {v.name}  ({mmss(dur)}, {info['w']}x{info['h']}, every {step:.1f}s)",
                      path)
                print(f"  V{n:<3}| created {info['created'] or '-':27} | {dur:6.1f}s | "
                      f"{info['w']}x{info['h']} | {v}")
                print(f"       sheet: {path}")


if __name__ == "__main__":
    main()
