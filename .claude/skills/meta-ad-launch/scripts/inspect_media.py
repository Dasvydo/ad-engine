#!/usr/bin/env python3
"""Inspect ad media before it goes anywhere near Meta.

    python inspect_media.py <file> [<file> ...] --out <dir>

For every file: size, aspect ratio and the placement it suits. For video also
duration, codec, frame rate and audio level. It writes images for you to LOOK
at - a six-frame contact sheet per video, and a safe-zone overlay for anything
9:16 with Stories' top 14% and bottom 20% shaded red.

The script measures. It does not judge what is on screen: open every image it
prints and look.

Needs Pillow, plus ffmpeg for video. With no ffmpeg on PATH it falls back to the
static build shipped with `pip install imageio-ffmpeg`.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow is missing: pip install pillow")

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# ratio (w/h) -> (label, placement advice). Tolerance is generous on purpose:
# exports come out a few pixels off all the time.
RATIOS = [
    (9 / 16, "9:16", "Stories, Reels - keep text out of the top 14% and bottom 20%"),
    (4 / 5, "4:5", "Feed - the main placement at this budget; lead with it"),
    (1.0, "1:1", "Feed - works, loses height against 4:5"),
    (1.91, "1.91:1", "Link/landscape - right column, weak in mobile feed"),
    (16 / 9, "16:9", "In-stream video - weak in mobile feed"),
]
STORY_TOP, STORY_BOTTOM = 0.14, 0.20


def classify(w: int, h: int) -> tuple[str, str]:
    r = w / h
    best = min(RATIOS, key=lambda t: abs(t[0] - r))
    if abs(best[0] - r) / best[0] > 0.04:
        return f"{w}:{h} (non-standard)", "Unusual ratio - Meta will crop or letterbox it"
    return best[1], best[2]


def find_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def probe(ff: str, path: Path) -> dict:
    """Parse `ffmpeg -i` output. ffprobe is often missing; ffmpeg rarely is."""
    err = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    info: dict = {}
    if m := re.search(r"Duration: (\d+):(\d+):([\d.]+)", err):
        h, mi, s = m.groups()
        info["duration"] = int(h) * 3600 + int(mi) * 60 + float(s)
    if m := re.search(r"Video: (\w+).*?, (\d{2,5})x(\d{2,5})", err):
        info["vcodec"], info["w"], info["h"] = m.group(1), int(m.group(2)), int(m.group(3))
    if m := re.search(r"(\d+(?:\.\d+)?) fps", err):
        info["fps"] = float(m.group(1))
    if m := re.search(r"Audio: (\w+).*?(\d+) Hz, (\w+)", err):
        info["acodec"], info["arate"], info["alayout"] = m.group(1), int(m.group(2)), m.group(3)
    if "acodec" in info:
        vol = subprocess.run(
            [ff, "-hide_banner", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"],
            capture_output=True, text=True,
        ).stderr
        if m := re.search(r"mean_volume: (-?[\d.]+) dB", vol):
            info["mean_db"] = float(m.group(1))
        if m := re.search(r"max_volume: (-?[\d.]+) dB", vol):
            info["max_db"] = float(m.group(1))
    return info


def grab(ff: str, path: Path, t: float, dest: Path) -> Path | None:
    subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(path),
         "-frames:v", "1", "-y", str(dest)],
        capture_output=True,
    )
    return dest if dest.exists() else None


def safe_zone_overlay(img: Image.Image) -> Image.Image:
    """Shade the Stories/Reels UI bands so a collision is obvious at a glance."""
    base = img.convert("RGBA")
    shade = Image.new("RGBA", base.size, (0, 0, 0, 0))
    w, h = base.size
    band = Image.new("RGBA", (w, 1), (220, 0, 0, 110))
    for y in list(range(0, int(h * STORY_TOP))) + list(range(int(h * (1 - STORY_BOTTOM)), h)):
        shade.paste(band, (0, y))
    return Image.alpha_composite(base, shade).convert("RGB")


def contact_sheet(frames: list[Path], dest: Path, cols: int = 3, tile_w: int = 360) -> Path:
    ims = [Image.open(f).convert("RGB") for f in frames]
    ims = [im.resize((tile_w, int(im.height * tile_w / im.width))) for im in ims]
    rows = (len(ims) + cols - 1) // cols
    th, pad = ims[0].height, 8
    sheet = Image.new("RGB", (cols * tile_w + (cols - 1) * pad, rows * th + (rows - 1) * pad), "white")
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % cols) * (tile_w + pad), (i // cols) * (th + pad)))
    sheet.save(dest)
    return dest


def human(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="where to write the images to look at")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    ff = find_ffmpeg()
    rows, look, problems = [], [], []

    for f in a.files:
        if not f.exists():
            problems.append(f"{f}: not found")
            continue
        ext, size, stem = f.suffix.lower(), f.stat().st_size, f.stem

        if ext in IMAGE_EXT:
            im = Image.open(f)
            w, h = im.size
            label, advice = classify(w, h)
            rows.append(f"| {f.name} | image | {w}×{h} | {label} | - | {human(size)} | {advice} |")
            if w < 1080:
                problems.append(f"{f.name}: {w}px wide - export at 1080 or more, it will look soft in feed")
            if label == "9:16":
                p = a.out / f"{stem}-safezones.png"
                safe_zone_overlay(im.convert("RGB")).save(p)
                look.append(p)
            else:
                look.append(f)
            continue

        if ext in VIDEO_EXT:
            if not ff:
                problems.append(f"{f.name}: no ffmpeg - run `pip install imageio-ffmpeg` and re-run")
                continue
            info = probe(ff, f)
            if "w" not in info:
                problems.append(f"{f.name}: ffmpeg could not read a video stream")
                continue
            w, h, dur = info["w"], info["h"], info.get("duration", 0.0)
            label, advice = classify(w, h)
            audio = (
                f"{info['acodec']} {info['arate'] // 1000}kHz, mean {info.get('mean_db', '?')} dB"
                if "acodec" in info else "no audio"
            )
            spec = f"{info['vcodec']} {info.get('fps', '?')}fps · {audio}"
            rows.append(f"| {f.name} | video {dur:.1f}s | {w}×{h} | {label} | {spec} | {human(size)} | {advice} |")

            if info["vcodec"] not in {"h264", "hevc"}:
                problems.append(f"{f.name}: codec {info['vcodec']} - H.264 is the safe choice for Meta")
            if w < 1080:
                problems.append(f"{f.name}: {w}px wide - export at 1080 or more")
            if dur and dur < 6:
                problems.append(f"{f.name}: {dur:.1f}s - under 6s leaves no room for a CTA beat")
            if "acodec" not in info:
                problems.append(f"{f.name}: no audio track - fine for feed (autoplays muted), weak for Reels")

            # six frames spread across the clip, then the last frame on its own
            n = 6
            ts = [dur * (i + 0.5) / n for i in range(n)] if dur else [0.0]
            frames = [p for i, t in enumerate(ts) if (p := grab(ff, f, t, a.out / f"{stem}-f{i}.png"))]
            if frames:
                look.append(contact_sheet(frames, a.out / f"{stem}-sheet.png"))
            last = grab(ff, f, max(dur - 0.1, 0), a.out / f"{stem}-last.png")
            if last and label == "9:16":
                p = a.out / f"{stem}-safezones.png"
                safe_zone_overlay(Image.open(last).convert("RGB")).save(p)
                look.append(p)
            continue

        problems.append(f"{f.name}: unsupported type {ext}")

    print("| File | Kind | Size | Ratio | Spec | Bytes | Goes to |")
    print("|---|---|---|---|---|---|---|")
    print("\n".join(rows) if rows else "| - | | | | | | |")
    print("\nOPEN AND LOOK AT EACH OF THESE:")
    for p in look:
        print(f"  {p}")
    print("\nPROBLEMS:" if problems else "\nPROBLEMS: none found by measurement - still look at the images.")
    for p in problems:
        print(f"  ⚠️ {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
