"""Static ad renderer. The typeset half of the hm-static-ad-generator pipeline.

The skill (`hm-static-ad-generator`) defaults to hybrid mode: an image model
makes the bed, and the brand-critical layer (Playfair headline, exact background
hex, the single amber accent, the logo) is typeset in HTML/CSS and screenshotted
with Playwright, because an LLM-image model gives you near-Playfair and
near-amber, never exact. The skill describes that pipeline but ships no code for
it. This is that code.

    python -m creative.static.render all           # every spec, both ratios
    python -m creative.static.render s01-glance    # one spec

Fonts are vendored under `fonts/` and base64-inlined into the page, so a render
needs no network and always uses real Playfair Display and real DM Sans. A
render that silently fell back to a system serif would be off-brand in a way
nobody notices until it is live, so `vet.py` checks for exactly that.

If `assets/logo.png` (transparent monogram) is present it is placed to the left
of the wordmark. It is absent today, so the wordmark ships alone, which the
brand lock allows.

If `beds/<id>.png` is present it is drawn behind the type as the generated bed.
None are present today. The layouts already account for one.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPECS = HERE / "specs"
FONTS = HERE / "fonts"
BEDS = HERE / "beds"
ASSETS = HERE / "assets"
OUT = HERE / "out"

# Straight from references/brand-lock.md. Nothing here is a guess.
PALETTE = {
    "light": {
        "bg": "#FFF0E5",       # Cream. The cardinal rule. Never anything near it.
        "ink": "#251D18",      # Espresso Ink
        "muted": "#70635C",
        "card": "#FDF9F7",
        "border": "#E4D7CD",
        "sand": "#F2E3D9",
        "amber": "#F59B0A",    # Light amber. Once per creative, small.
    },
    "dark": {
        "bg": "#1D1816",       # Charcoal
        "ink": "#FAF1EB",      # Warm White
        "muted": "#B8A394",
        "card": "#28221F",
        "border": "#463E39",
        "sand": "#38312E",
        "amber": "#FBBD23",    # Dark amber
    },
}

WORDMARK_TEAL = "#2A6C7C"
WORDMARK_ORANGE = "#E96C32"

RATIOS = {
    "1x1": (1080, 1080),
    "4x5": (1080, 1350),
}


@dataclass(frozen=True)
class Render:
    spec_id: str
    ratio: str
    path: Path


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _font_css() -> str:
    playfair = _b64(FONTS / "PlayfairDisplay-Variable.woff2")
    dmsans = _b64(FONTS / "DMSans-Variable.woff2")
    return f"""
@font-face {{
  font-family: 'Playfair Display';
  src: url(data:font/woff2;base64,{playfair}) format('woff2');
  font-weight: 400 700; font-style: normal; font-display: block;
}}
@font-face {{
  font-family: 'DM Sans';
  src: url(data:font/woff2;base64,{dmsans}) format('woff2');
  font-weight: 300 700; font-style: normal; font-display: block;
}}"""


def _headline_html(lines: list[str], amber_word: str | None, amber: str) -> str:
    """Lines are broken deliberately, per the brand lock. Exactly one word amber."""
    out = []
    used = False
    for line in lines:
        words = []
        for word in line.split(" "):
            if not used and amber_word and word == amber_word:
                words.append(f'<span style="color:{amber}">{word}</span>')
                used = True
            else:
                words.append(word)
        out.append(" ".join(words))
    if amber_word and not used:
        raise ValueError(f"amber_word {amber_word!r} not found in headline lines")
    return "<br>".join(out)


def _card_html(card: dict, c: dict, amber_row: bool) -> str:
    """A concrete Outlook draft card. The brand lock prefers real content over
    abstract 'AI' graphics, so these are believable client subject lines."""
    rows = []
    amber_spent = False
    for row in card["rows"]:
        marked = row.get("draft", False)
        # Amber is the single signal element on the whole creative. One row gets it.
        # Every other marked row gets a muted dot, or the ad reads as a yellow list.
        signal = marked and amber_row and not amber_spent
        if signal:
            amber_spent = True
        colour = c["amber"] if signal else c["border"]
        dot = f'<span class="dot" style="background:{colour}"></span>'
        label = (
            f'<span class="tag" style="color:{c["muted"]}">Draft ready</span>'
            if signal
            else ""
        )
        rows.append(
            f"""<div class="row">
                  {dot}
                  <div class="rowtext">
                    <div class="from">{row['from']}</div>
                    <div class="subject">{row['subject']}</div>
                  </div>
                  {label}
                </div>"""
        )
    return f"""
    <div class="card">
      <div class="cardhead">{card['title']}</div>
      {''.join(rows)}
    </div>"""


def build_html(spec: dict, ratio: str) -> str:
    w, h = RATIOS[ratio]
    c = PALETTE[spec["theme"]]
    tall = ratio == "4x5"

    amber_row = bool(spec.get("card") and spec.get("amber") == "card_row")
    amber_word = spec.get("amber_word") if spec.get("amber") == "headline_word" else None

    head_px = spec.get("headline_px", {}).get(ratio, 92 if tall else 82)
    sub_px = 34 if tall else 31
    pad = 92 if tall else 84

    bed = BEDS / f"{spec['id']}.png"
    bed_css = (
        f"background-image:url(data:image/png;base64,{_b64(bed)});"
        "background-size:cover;background-position:center;"
        if bed.exists()
        else ""
    )

    logo = ASSETS / "logo.png"
    logo_html = (
        f'<img class="mark" src="data:image/png;base64,{_b64(logo)}" alt="">'
        if logo.exists()
        else ""
    )

    card = spec.get("card")
    # s08 puts the draft body in the subject slot, so it must wrap rather than
    # ellipsis away the half of the sentence the ad exists to show.
    subject_wrap = "normal" if (card and card.get("wrap")) else "nowrap"
    card_html = _card_html(card, c, amber_row) if card else ""

    eyebrow_html = (
        f'<div class="eyebrow">{spec["eyebrow"]}</div>' if spec.get("eyebrow") else ""
    )

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{_font_css()}
* {{ box-sizing: border-box; }}
html, body {{ margin:0; padding:0; }}
body {{
  width:{w}px; height:{h}px; background:{c['bg']}; {bed_css}
  font-family:'DM Sans', sans-serif; color:{c['ink']};
  display:flex; flex-direction:column; justify-content:space-between;
  padding:{pad}px;
}}
.eyebrow {{
  font-size:24px; font-weight:500; letter-spacing:.14em; text-transform:uppercase;
  color:{c['muted']};
}}
h1 {{
  font-family:'Playfair Display', serif; font-weight:600;
  font-size:{head_px}px; line-height:1.06; letter-spacing:-.01em;
  margin:26px 0 0; color:{c['ink']};
}}
.sub {{
  font-size:{sub_px}px; line-height:1.45; color:{c['muted']};
  margin:30px 0 0; max-width:{'820' if tall else '860'}px; font-weight:400;
}}
.card {{
  background:{c['card']}; border:1px solid {c['border']}; border-radius:16px;
  padding:30px 34px; margin-top:38px;
  box-shadow:0 18px 40px rgba(37,29,24,.07);
}}
.cardhead {{
  font-size:22px; font-weight:500; letter-spacing:.1em; text-transform:uppercase;
  color:{c['muted']}; margin-bottom:20px;
}}
.row {{ display:flex; align-items:center; gap:18px; padding:15px 0;
        border-top:1px solid {c['border']}; }}
.row:first-of-type {{ border-top:none; }}
.dot {{ width:12px; height:12px; border-radius:50%; flex:none; }}
.rowtext {{ flex:1; min-width:0; }}
.from {{ font-size:23px; font-weight:500; color:{c['ink']}; }}
.subject {{ font-size:23px; color:{c['muted']}; margin-top:4px;
            white-space:{subject_wrap};
            overflow:hidden; text-overflow:ellipsis; line-height:1.35; }}
.tag {{ font-size:19px; letter-spacing:.08em; text-transform:uppercase;
        white-space:nowrap; }}
.foot {{ display:flex; align-items:center; gap:16px; }}
.mark {{ height:44px; width:auto; }}
.wordmark {{ font-size:34px; font-weight:400; letter-spacing:-.01em; }}
/* Centre the block. A headline stranded at the top of 1350px with 500px of
   empty cream under it reads unfinished rather than editorial. */
.top {{ flex:1 1 auto; display:flex; flex-direction:column; justify-content:center; }}
.bottom {{ flex:0 0 auto; padding-top:36px; }}
</style></head><body>
<div class="top">
  <div class="stack">
    {eyebrow_html}
    <h1>{_headline_html(spec['headline'], amber_word, c['amber'])}</h1>
    <div class="sub">{spec['subline']}</div>
    {card_html}
  </div>
</div>
<div class="bottom">
  <div class="foot">
    {logo_html}
    <div class="wordmark"><span style="color:{WORDMARK_TEAL}">Dovi</span><span
      style="color:{WORDMARK_ORANGE}">Loop</span></div>
  </div>
</div>
</body></html>"""


def render(spec: dict, ratio: str, out_dir: Path = OUT) -> Render:
    from playwright.sync_api import sync_playwright

    w, h = RATIOS[ratio]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{spec['id']}-{ratio}.png"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        page.set_content(build_html(spec, ratio), wait_until="load")
        page.wait_for_timeout(250)
        # Deliberate line breaks are in the spec, but a long line at a large size
        # still overflows. Shrink until it fits rather than letting it crowd the edge.
        page.evaluate(
            """() => {
              const h = document.querySelector('h1');
              const pad = parseFloat(getComputedStyle(document.body).paddingLeft);
              const max = document.body.clientWidth - pad * 2;
              let size = parseFloat(getComputedStyle(h).fontSize);
              const widest = () => {
                const r = document.createRange();
                let w = 0;
                h.childNodes.forEach(n => {
                  if (n.nodeType === 3 || n.nodeName !== 'BR') {
                    r.selectNodeContents(n.nodeType === 3 ? n : n);
                    w = Math.max(w, r.getBoundingClientRect().width);
                  }
                });
                return Math.max(w, h.scrollWidth);
              };
              while (widest() > max && size > 40) {
                size -= 2;
                h.style.fontSize = size + 'px';
              }
            }"""
        )
        # Vertical fit. A square frame is 270px shorter than a 4:5 one, and a
        # card-led creative overflows it silently, clipping the wordmark off the
        # bottom edge. Shrink the block until the whole thing sits inside.
        page.evaluate(
            """() => {
              // .top is flex:1, so it always reports as full height and an
              // overflow inside it never grows body.scrollHeight. Measure the
              // real content stack against the space it actually has.
              const stack = document.querySelector('.stack');
              const foot = document.querySelector('.bottom');
              const body = document.body;
              const pad = parseFloat(getComputedStyle(body).paddingTop);
              const room = () => body.clientHeight - pad * 2 - foot.offsetHeight;
              let z = 1;
              while (stack.getBoundingClientRect().height > room() && z > 0.65) {
                z -= 0.02;
                stack.style.zoom = z;
              }
            }"""
        )
        page.wait_for_timeout(150)
        page.screenshot(path=str(path))
        browser.close()

    return Render(spec["id"], ratio, path)


def load_specs(only: str | None = None) -> list[dict]:
    specs = []
    for path in sorted(SPECS.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        if only in (None, "all") or spec["id"].startswith(only):
            specs.append(spec)
    if not specs:
        raise SystemExit(f"no spec matched {only!r}")
    return specs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="creative.static.render")
    ap.add_argument("target", nargs="?", default="all")
    ap.add_argument("--ratio", choices=[*RATIOS, "both"], default="both")
    args = ap.parse_args(argv)

    ratios = list(RATIOS) if args.ratio == "both" else [args.ratio]
    for spec in load_specs(args.target):
        for ratio in ratios:
            r = render(spec, ratio)
            print(f"{r.spec_id:26s} {r.ratio}  {r.path.stat().st_size:>7,} B  {r.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
