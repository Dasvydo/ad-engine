#!/usr/bin/env python3
"""Render a repo markdown doc to a typeset PDF.

The markdown stays canonical. This derives the PDF from it, so the two cannot
drift: regenerate rather than hand-editing a PDF.

Handles the subset this repo's docs actually use - headings, pipe tables,
bullets, `- [ ]` checkboxes, fenced code, blockquotes, horizontal rules, bold
and inline code. Anything else passes through as body text.

    python tools/md_to_pdf.py docs/META-ADS-CHEATSHEET.md -o build/cheatsheet.pdf

Fonts: DejaVu, registered explicitly. ReportLab's built-in Type 1 faces have no
arrows, box-drawing or warning glyphs and render them as black boxes.
"""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, KeepTogether,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
INK      = colors.HexColor("#1b1f24")
MUTED    = colors.HexColor("#5b6670")
ACCENT   = colors.HexColor("#0b5fff")
RULE     = colors.HexColor("#d7dde3")
BAND     = colors.HexColor("#f4f6f8")
WARN_BG  = colors.HexColor("#fff6e5")
WARN_ED  = colors.HexColor("#e8a33d")
GOOD     = colors.HexColor("#0f7a3d")
BAD      = colors.HexColor("#c0392b")


def register_fonts() -> None:
    # This DejaVu build ships no Oblique face. Map the italic slot to the
    # regular one rather than letting ReportLab fail on a missing file; emphasis
    # in these docs is carried by weight and colour, not slant.
    for name, file in (("DJ", "DejaVuSans.ttf"), ("DJ-B", "DejaVuSans-Bold.ttf"),
                       ("DJM", "DejaVuSansMono.ttf"),
                       ("DJM-B", "DejaVuSansMono-Bold.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
    pdfmetrics.registerFontFamily("DJ", normal="DJ", bold="DJ-B",
                                  italic="DJ", boldItalic="DJ-B")


def styles() -> dict:
    """One explicit style per role.

    Written out rather than spread from a shared base dict: a style that
    overrides a base key raises "multiple values for keyword argument", and the
    resulting patch-and-retry is worse than the repetition.
    """
    def mk(name, **kw):
        kw.setdefault("fontName", "DJ")
        kw.setdefault("textColor", INK)
        kw.setdefault("alignment", TA_LEFT)
        return ParagraphStyle(name, **kw)

    return {
        "title":  mk("title", fontName="DJ-B", fontSize=23, leading=27, spaceAfter=2),
        "sub":    mk("sub", fontSize=9.5, leading=13.5, textColor=MUTED, spaceAfter=14),
        "h2":     mk("h2", fontName="DJ-B", fontSize=13.5, leading=17,
                     spaceBefore=15, spaceAfter=5),
        "h3":     mk("h3", fontName="DJ-B", fontSize=10.5, leading=14,
                     spaceBefore=9, spaceAfter=3),
        "body":   mk("body", fontSize=9.2, leading=13.4, spaceAfter=5),
        "bullet": mk("bullet", fontSize=9.2, leading=13.4, leftIndent=11,
                     bulletIndent=2, spaceAfter=2.5),
        "cell":   mk("cell", fontSize=8.6, leading=11.8),
        "cellbad":  mk("cellbad", fontSize=8.6, leading=11.8, textColor=BAD,
                       fontName="DJ-B"),
        "cellgood": mk("cellgood", fontSize=8.6, leading=11.8, textColor=GOOD,
                       fontName="DJ-B"),
        "cellh":  mk("cellh", fontName="DJ-B", fontSize=8.6, leading=11.8,
                     textColor=colors.white),
        "code":   mk("code", fontName="DJM", fontSize=8.4, leading=12),
        "quote":  mk("quote", fontSize=9.2, leading=13.4, leftIndent=10,
                     textColor=MUTED),
        "warn":   mk("warn", fontSize=9.0, leading=13),
    }


def inline(md: str) -> str:
    """Markdown inline -> ReportLab markup. Escape first, then re-introduce tags."""
    s = html.escape(md, quote=False)
    s = re.sub(r"`([^`]+)`", r'<font face="DJM" size="8.4">\1</font>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)          # links -> their text
    # Emoji variation selectors have no glyph in DejaVu and render as a box.
    return s.replace("️", "")


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def build_table(rows: list[list[str]], st: dict, width: float) -> Table:
    head = rows[0]
    ncol = len(head)
    # A table written with an empty header row (| | |) is a layout table, not a
    # headed one. Drawing the header band there leaves a bare black bar.
    headless = not any(c.strip() for c in head)
    body = rows[1:]

    # Which columns are judgement bands, so their cells can be coloured. This
    # has to happen in the Paragraph's own style: a TableStyle TEXTCOLOR command
    # is overridden by the colour already set on the Paragraph, and fails
    # silently - the table renders, just all in black.
    lowered = [h.lower().strip() for h in head]
    col_style = {}
    if "bad" in lowered and "good" in lowered:
        col_style[lowered.index("bad")] = "cellbad"
        col_style[lowered.index("good")] = "cellgood"

    data = [] if headless else [[Paragraph(inline(c), st["cellh"]) for c in head]]
    for r in body:
        r = (r + [""] * ncol)[:ncol]
        data.append([Paragraph(inline(c), st[col_style.get(j, "cell")])
                     for j, c in enumerate(r)])
    if not data:
        data = [[Paragraph("", st["cell"])] * ncol]

    # First column carries the label and wants the room; the rest share evenly.
    if ncol == 1:
        widths = [width]
    else:
        first = width * (0.34 if ncol <= 3 else 0.28)
        widths = [first] + [(width - first) / (ncol - 1)] * (ncol - 1)

    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]
    if not headless:
        style.append(("BACKGROUND", (0, 0), (-1, 0), INK))

    zebra_from = 0 if headless else 1
    for i in range(zebra_from, len(data)):
        if (i - zebra_from) % 2 == 1:
            style.append(("BACKGROUND", (0, i), (-1, i), BAND))

    t = Table(data, colWidths=widths, repeatRows=0 if headless else 1, hAlign="LEFT")
    t.setStyle(TableStyle(style))
    return t


def callout(text: str, st: dict, width: float) -> Table:
    p = Paragraph(inline(text.lstrip("⚠ ").strip()), st["warn"])
    t = Table([[Paragraph('<font color="#a86a12"><b>!</b></font>', st["warn"]), p]],
              colWidths=[9 * mm, width - 9 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WARN_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2, WARN_ED),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, -1), 7), ("RIGHTPADDING", (1, 0), (1, -1), 8),
    ]))
    return t


BLOCK_START = re.compile(r"^(#{1,6} |[-*] |\d+\. |> |\||```|---\s*$)")


def _is_block_start(line: str) -> bool:
    return bool(BLOCK_START.match(line)) or line.strip().startswith("\u26a0")


def render(md: str, st: dict, width: float) -> list:
    """Markdown -> flowables.

    Markdown joins consecutive non-blank lines into one block; rendering each
    source line separately produced orphaned half-sentences at full width, split
    a two-line blockquote into two callouts, and cut a `*...*` span in half so
    the asterisks leaked into the output. So every branch below consumes its
    whole block, not one line.
    """
    flow, lines, i = [], md.split("\n"), 0
    first_h1 = True
    while i < len(lines):
        ln = lines[i]

        if ln.startswith("```"):                                    # fenced code
            i += 1; buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            body = "<br/>".join(html.escape(b, quote=False).replace(" ", "&nbsp;")
                                for b in buf)
            t = Table([[Paragraph(body, st["code"])]], colWidths=[width], hAlign="LEFT")
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BAND),
                                   ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                                   ("TOPPADDING", (0, 0), (-1, -1), 7),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 9)]))
            flow += [t, Spacer(1, 7)]; continue

        if ln.startswith("|") and i + 1 < len(lines) and set(lines[i+1].replace("|", "").strip()) <= set("-: "):
            rows = [split_row(ln)]; i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(split_row(lines[i])); i += 1
            flow += [build_table(rows, st, width), Spacer(1, 8)]; continue

        if ln.startswith("# "):
            if first_h1:
                flow.append(Paragraph(inline(ln[2:]), st["title"])); first_h1 = False
            else:
                flow.append(Paragraph(inline(ln[2:]), st["h2"]))
            i += 1
            # The lines under the title are its standfirst, not body copy.
            if first_h1 is False and len(flow) == 1:
                buf = []
                while i < len(lines) and lines[i].strip() and not _is_block_start(lines[i]):
                    buf.append(lines[i].strip()); i += 1
                if buf:
                    flow.append(Paragraph(inline(" ".join(buf)), st["sub"]))
            continue

        if ln.startswith("## "):
            flow += [Spacer(1, 3), Paragraph(inline(ln[3:]), st["h2"]),
                     HRFlowable(width="100%", thickness=0.8, color=ACCENT,
                                spaceBefore=1, spaceAfter=7)]
            i += 1; continue

        if ln.startswith("### "):
            flow.append(Paragraph(inline(ln[4:]), st["h3"])); i += 1; continue

        if ln.startswith("> ") or ln.strip().startswith("\u26a0"):   # callout
            buf = []
            while i < len(lines) and (lines[i].startswith("> ")
                                      or lines[i].strip().startswith("\u26a0")
                                      or (buf and lines[i].strip() and not _is_block_start(lines[i]))):
                buf.append(lines[i].lstrip("> ").strip().lstrip("\u26a0").strip()); i += 1
            flow += [callout(" ".join(buf), st, width), Spacer(1, 7)]; continue

        m = re.match(r"^(- \[[ x]\] |[-*] |\d+\. )(.*)$", ln)
        if m:
            marker, rest = m.group(1), m.group(2)
            buf = [rest]; i += 1
            while i < len(lines) and lines[i].strip() and not _is_block_start(lines[i]):
                buf.append(lines[i].strip()); i += 1
            text = " ".join(buf)
            if marker.startswith("- ["):
                # DejaVu has no U+2610 glyph and draws a filled box instead.
                bullet = '<font face="DJM">[ ]</font>'
            elif marker[0].isdigit():
                bullet = marker.strip()
            else:
                bullet = "\u2022"
            flow.append(Paragraph(f"<bullet>{bullet}</bullet>" + inline(text), st["bullet"]))
            continue

        if ln.strip() == "---":
            flow += [Spacer(1, 2), HRFlowable(width="100%", thickness=0.5, color=RULE,
                                              spaceBefore=4, spaceAfter=8)]
            i += 1; continue

        if ln.strip():                                              # paragraph
            buf = [ln.strip()]; i += 1
            while i < len(lines) and lines[i].strip() and not _is_block_start(lines[i]):
                buf.append(lines[i].strip()); i += 1
            flow.append(Paragraph(inline(" ".join(buf)), st["body"]))
            continue
        i += 1
    return flow


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source"); ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--footer", default="")
    a = ap.parse_args()

    register_fonts(); st = styles()
    src = Path(a.source); out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)

    M = 16 * mm
    page_w, page_h = A4
    width = page_w - 2 * M
    doc = BaseDocTemplate(str(out), pagesize=A4, leftMargin=M, rightMargin=M,
                          topMargin=14 * mm, bottomMargin=16 * mm,
                          title=src.stem.replace("-", " ").title(), author="DoviLoop")

    footer = a.footer or src.name

    def decorate(canvas, _doc):
        canvas.saveState()
        canvas.setFont("DJ", 7.4); canvas.setFillColor(MUTED)
        canvas.drawString(M, 9.5 * mm, footer)
        canvas.drawRightString(page_w - M, 9.5 * mm, f"{canvas.getPageNumber()}")
        canvas.setStrokeColor(RULE); canvas.setLineWidth(0.4)
        canvas.line(M, 12.5 * mm, page_w - M, 12.5 * mm)
        canvas.restoreState()

    frame = Frame(M, 16 * mm, width, page_h - 30 * mm, id="body",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=decorate)])
    doc.build(render(src.read_text(), st, width))
    print(f"{out}  ({out.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
