"""The markdown -> PDF renderer, guarding the bugs found while building it.

Each test here corresponds to something that rendered wrongly on 2026-09-22 and
was only caught by looking at the output. None of them would fail the build.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

reportlab = pytest.importorskip("reportlab")

import md_to_pdf as m


@pytest.fixture(scope="module")
def st():
    m.register_fonts()
    return m.styles()


def _texts(flow):
    return [f.text for f in flow if hasattr(f, "text")]


def test_consecutive_lines_join_into_one_paragraph(st):
    """Markdown joins wrapped lines. Rendering each line as its own paragraph
    left orphaned half-sentences at full width with a gap between them."""
    flow = m.render("One sentence that\nwraps across two source lines.", st, 400)
    joined = [t for t in _texts(flow) if "wraps" in t]
    assert len(joined) == 1
    assert "One sentence that wraps across two source lines." in joined[0]


def test_a_blank_line_still_separates_paragraphs(st):
    flow = m.render("First para.\n\nSecond para.", st, 400)
    bodies = [t for t in _texts(flow) if "para" in t]
    assert len(bodies) == 2


def test_multiline_blockquote_is_one_callout(st):
    """A two-line quote became two stacked callouts, and split a `*...*` span
    so the asterisks leaked into the output."""
    flow = m.render("> half of a quote\n> and the other half", st, 400)
    tables = [f for f in flow if isinstance(f, m.Table)]
    assert len(tables) == 1


def test_checkbox_uses_bracket_not_the_missing_glyph(st):
    """DejaVu has no U+2610; it drew a filled black square instead."""
    flow = m.render("- [ ] do the thing", st, 400)
    text = _texts(flow)[0]
    assert "[ ]" in text
    assert "☐" not in text


def test_empty_header_row_makes_a_headless_table(st):
    """`| | |` is a layout table. Styling a header there drew a bare black bar."""
    rows = [["", ""], ["Ad account", "620456015062432"]]
    t = m.build_table(rows, st, 400)
    assert len(t._cellvalues) == 1, "the empty header row should be dropped"
    # ReportLab keeps BACKGROUND commands in _bkgrndcmds, not on a style object.
    assert not any(c[3] == m.INK for c in t._bkgrndcmds), \
        "a headless table must not draw the dark header band"


def test_real_header_row_keeps_its_band(st):
    rows = [["Word", "Means"], ["CPM", "Cost per 1,000 impressions"]]
    t = m.build_table(rows, st, 400)
    assert len(t._cellvalues) == 2
    assert any(c[3] == m.INK for c in t._bkgrndcmds)


def test_judgement_columns_are_coloured_on_the_paragraph(st):
    """A TableStyle TEXTCOLOR is overridden by the colour already on the
    Paragraph, and fails silently - the table renders, all in black."""
    rows = [["Number", "Bad", "Normal", "Good"],
            ["Link CTR", "under 0.5%", "0.6 - 1.0%", "over 1.5%"]]
    t = m.build_table(rows, st, 400)
    body = t._cellvalues[1]
    assert body[1].style.textColor == m.BAD
    assert body[3].style.textColor == m.GOOD
    assert body[2].style.textColor == m.INK


def test_inline_markup_escapes_before_it_adds_tags(st):
    """Escaping after adding tags would eat the tags themselves."""
    assert "&lt;script&gt;" in m.inline("<script>")
    assert "<b>bold</b>" in m.inline("**bold**")


def test_emoji_variation_selector_is_stripped(st):
    """U+FE0F has no glyph in DejaVu and renders as a box."""
    assert "️" not in m.inline("warning ⚠️ here")
