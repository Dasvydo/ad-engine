"""Brand QA for the rendered statics. `references/vetting-checklist.md` as code.

    python -m creative.static.vet

The checklist in the skill is written for a human eye. Most of it is machine
checkable, and the items that matter most are exactly the ones a tired human
misses: a background that has drifted off cream, amber that has quietly become
the second biggest thing on the page, a headline that fell back to a system
serif because the font failed to load.

Exit code is non-zero if any creative fails, so this can gate a commit.

What this does NOT check, and a human still must: whether the ad makes one point,
whether the copy reads human, whether the line breaks land well.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

from creative.static.render import OUT, PALETTE, RATIOS, SPECS, build_html

# Tolerance for "is this pixel that colour". PNG screenshots are exact, but
# antialiased type edges blend, so nearby pixels are allowed.
NEAR = 6
AMBER_MAX_SHARE = 0.030   # amber may be a signal, never a surface
EDGE_PAD = 36             # nothing may be clipped at the edge


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _close(px, target, tol=NEAR) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(px, target))


def check_image(path: Path, spec: dict, ratio: str) -> list[str]:
    fails: list[str] = []
    c = PALETTE[spec["theme"]]
    bg = _hex(c["bg"])
    amber = _hex(c["amber"])
    im = Image.open(path).convert("RGB")

    if im.size != RATIOS[ratio]:
        fails.append(f"size {im.size} is not {RATIOS[ratio]}")

    w, h = im.size

    # 1. The yellow test, done properly: the ground must be the exact hex.
    corners = [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3), (w // 2, 4)]
    for x, y in corners:
        px = im.getpixel((x, y))
        if not _close(px, bg, 2):
            fails.append(f"background at ({x},{y}) is {px}, not {c['bg']} {bg}")
            break

    getter = getattr(im, "get_flattened_data", None)  # Pillow 12+ name
    pixels = list(getter()) if getter else list(im.getdata())
    if pixels and isinstance(pixels[0], int):   # flattened returns a flat band list
        pixels = list(zip(pixels[0::3], pixels[1::3], pixels[2::3]))
    total = len(pixels)

    # 2. Amber discipline: present, and small.
    amber_px = sum(1 for p in pixels if _close(p, amber, 26))
    share = amber_px / total
    if amber_px == 0:
        fails.append("no amber accent found; every creative gets exactly one signal")
    if share > AMBER_MAX_SHARE:
        fails.append(
            f"amber covers {share:.1%} of the frame (limit {AMBER_MAX_SHARE:.1%}); "
            "amber is an accent, never a fill or wash"
        )

    # 3. Colour family: warm only. No blue, no neon, no cool grey.
    blue = sum(1 for r, g, b in pixels if b > r + 12 and b > g + 12)
    if blue / total > 0.02:
        # The teal in the wordmark is deliberate and tiny, hence the 2% allowance.
        fails.append(f"{blue/total:.1%} of pixels read cool/blue; palette is warm only")

    # 4. Nothing clipped: the outer band is background only, apart from nothing.
    band = []
    for x in range(0, w, 7):
        band.append(im.getpixel((x, EDGE_PAD // 2)))
        band.append(im.getpixel((x, h - 1 - EDGE_PAD // 2)))
    for y in range(0, h, 7):
        band.append(im.getpixel((EDGE_PAD // 2, y)))
        band.append(im.getpixel((w - 1 - EDGE_PAD // 2, y)))
    if any(not _close(p, bg, 4) for p in band):
        fails.append(f"content within {EDGE_PAD//2}px of the edge; needs comfortable padding")

    return fails


def check_text(spec: dict) -> list[str]:
    fails = []
    blob = " ".join(
        [spec.get("eyebrow", ""), " ".join(spec["headline"]), spec["subline"]]
        + [r["from"] + " " + r["subject"] for r in (spec.get("card") or {}).get("rows", [])]
    )
    if "—" in blob or "–" in blob:
        fails.append("em or en dash in rendered copy; the brand lock forbids it")
    if "jetbrains" in blob.lower():
        fails.append("JetBrains Mono is product-only, never marketing")
    if spec.get("amber") == "headline_word" and not spec.get("amber_word"):
        fails.append("amber mode is headline_word but no amber_word is set")
    return fails


def check_fonts(spec: dict) -> list[str]:
    """The failure nobody notices: the woff2 does not load and Chromium quietly
    substitutes a system serif. Measure it rather than trusting it."""
    from playwright.sync_api import sync_playwright

    fails = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350})
        page.set_content(build_html(spec, "4x5"), wait_until="load")
        page.wait_for_timeout(250)
        ok = page.evaluate(
            """() => ({
                playfair: document.fonts.check("600 96px 'Playfair Display'"),
                dmsans: document.fonts.check("400 34px 'DM Sans'"),
                families: [...new Set([...document.querySelectorAll('h1,.sub,.eyebrow,.wordmark')]
                    .map(e => getComputedStyle(e).fontFamily.split(',')[0].replace(/['"]/g,'').trim()))]
            })"""
        )
        browser.close()
    if not ok["playfair"]:
        fails.append("Playfair Display did not load; headline would ship as a fallback serif")
    if not ok["dmsans"]:
        fails.append("DM Sans did not load")
    extra = set(ok["families"]) - {"Playfair Display", "DM Sans"}
    if extra:
        fails.append(f"third typeface in use: {sorted(extra)}")
    return fails


def main() -> int:
    specs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SPECS.glob("*.json"))]
    bad = 0
    print(f"{'creative':26s} {'ratio':6s} verdict")
    print("-" * 68)
    for spec in specs:
        text_fails = check_text(spec) + check_fonts(spec)
        for ratio in RATIOS:
            path = OUT / f"{spec['id']}-{ratio}.png"
            if not path.exists():
                print(f"{spec['id']:26s} {ratio:6s} MISSING, run render first")
                bad += 1
                continue
            fails = text_fails + check_image(path, spec, ratio)
            print(f"{spec['id']:26s} {ratio:6s} {'PASS' if not fails else 'FAIL'}")
            for f in fails:
                print(f"{'':33s}   {f}")
            bad += bool(fails)
    print("-" * 68)
    print(f"{len(specs) * len(RATIOS)} renders checked, {bad} failing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
