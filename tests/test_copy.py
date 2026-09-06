"""The copy rules are a deliverable, so they are a test.

Voice rules that a reviewer would have to remember (no em dashes, the exact UTM,
one destination) are cheaper to enforce here than to catch in Ads Manager.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.gate import check, check_creative

COPY = sorted((ROOT / "creative" / "copy").glob("*.json"))
STATIC_SPECS = sorted((ROOT / "creative" / "static" / "specs").glob("*.json"))

UTM = "utm_source=meta&utm_medium=paid&utm_campaign=teams_q4&utm_content="


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _rendered_strings(spec):
    """Every string a human will read, ignoring internal notes."""
    out = []

    def walk(node, key=""):
        if isinstance(node, str):
            if not key.startswith("_") and key not in {"maps_to", "job", "note", "hypothesis"}:
                out.append(node)
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)

    walk(spec)
    return out


def test_there_are_six_copy_variants():
    assert len(COPY) == 6


def test_there_are_eight_statics():
    assert len(STATIC_SPECS) == 8


@pytest.mark.parametrize("path", COPY + STATIC_SPECS, ids=lambda p: p.stem)
def test_no_em_or_en_dash_anywhere(path):
    blob = "\n".join(_rendered_strings(_load(path)))
    assert "—" not in blob, "em dash"
    assert "–" not in blob, "en dash"


@pytest.mark.parametrize("path", COPY + STATIC_SPECS, ids=lambda p: p.stem)
def test_claims_gate_passes(path):
    """No time saving figure, no percentage, no customer count. The repo's gate
    blocks all three because nothing has been measured yet."""
    verdict = check_creative(_load(path))
    assert verdict.passed, verdict.failures


@pytest.mark.parametrize("path", COPY, ids=lambda p: p.stem)
def test_destination_is_teams_with_the_exact_utm(path):
    spec = _load(path)
    assert spec["destination"].startswith("https://teams.doviloop.dev/")
    assert UTM + spec["id"] in spec["destination"]


@pytest.mark.parametrize("path", COPY, ids=lambda p: p.stem)
def test_variant_has_all_three_meta_fields(path):
    spec = _load(path)
    for field in ("primary_text", "headline", "description"):
        assert spec[field].strip(), field


@pytest.mark.parametrize("path", COPY, ids=lambda p: p.stem)
def test_headline_and_description_fit_the_placement(path):
    """Meta truncates headlines past roughly 40 characters and descriptions past
    roughly 30 in most feed placements. A truncated headline is a wasted one."""
    spec = _load(path)
    assert len(spec["headline"]) <= 40, spec["headline"]
    assert len(spec["description"]) <= 32, spec["description"]


@pytest.mark.parametrize("path", COPY, ids=lambda p: p.stem)
def test_english_only(path):
    """Ads run in English in all three markets to keep spend down. A stray
    NEEDS_NATIVE_PROOFREAD placeholder means a variant was copied from the
    pre-campaign arms without being rewritten."""
    spec = _load(path)
    assert spec["language"] == "en"
    assert "NEEDS_NATIVE" not in json.dumps(spec)


def test_every_objection_has_a_copy_variant():
    mapped = " ".join(_load(p)["maps_to"] for p in COPY)
    for n in range(1, 6):
        assert f"objection-{n}" in mapped, f"objection {n} has no copy variant"


def test_every_objection_has_a_static():
    mapped = " ".join(_load(p)["maps_to"] for p in STATIC_SPECS)
    for n in range(1, 6):
        assert f"objection-{n}" in mapped, f"objection {n} has no static"


def test_both_ratios_rendered_for_every_static():
    out = ROOT / "creative" / "static" / "out"
    for spec in STATIC_SPECS:
        sid = _load(spec)["id"]
        for ratio in ("1x1", "4x5"):
            assert (out / f"{sid}-{ratio}.png").exists(), f"{sid}-{ratio} not rendered"


# --- The ROI rule, decided 2026-09-06 ----------------------------------------
# Dovy confirmed the 9x / 400 EUR a month / 40-day figures are a model, not a
# measurement. They may appear in an ad only if that ad says so. The gate
# encodes exactly that and nothing looser.


@pytest.mark.parametrize(
    "text",
    [
        "About 9x ROI for a ten seat firm.",
        "Payback in about 40 days.",
        "It saves EUR 400 a month per seat.",
        "EUR 400 a month saved, per seat.",
        "It pays for itself.",
    ],
    ids=["multiple", "payback", "saves-eur", "eur-saved", "pays-for-itself"],
)
def test_roi_figures_are_blocked_when_presented_as_an_outcome(text):
    verdict = check(text)
    assert not verdict.passed
    assert any("roi_model" in f for f in verdict.failures), verdict.failures


@pytest.mark.parametrize(
    "text",
    [
        "About 9x ROI for a ten seat firm. That is a worked example, not a measurement.",
        "Payback in about 40 days, in our model. Run it on your own numbers.",
    ],
    ids=["worked-example", "our-model"],
)
def test_roi_figures_pass_only_when_the_ad_itself_says_they_are_a_model(text):
    assert check(text).passed, check(text).failures


def test_framing_does_not_unlock_hours_saved():
    """The allowance is per claim. hours_saved has no allowed_if_framed_as, so
    a time-saving number stays blocked even next to 'worked example'."""
    verdict = check("Saves 10 hours a month. A worked example, not a measurement.")
    assert not verdict.passed
    assert any("hours_saved" in f for f in verdict.failures), verdict.failures


def test_ratio_strings_are_not_roi_multiples():
    assert check("Renders at 1x1, 4x5 and 9x16.").passed


def test_price_is_verified_and_passes():
    assert check("89 USD a seat a month plus 500 USD one-off setup.").passed


def test_evidence_records_the_dated_decisions():
    ev = json.loads((ROOT / "claims" / "evidence.json").read_text(encoding="utf-8"))
    topics = {d["topic"] for d in ev["_decisions"]}
    assert "ROI figures" in topics and "Price and destination" in topics
    assert all(d["date"] == "2026-09-06" for d in ev["_decisions"])
    assert ev["claims"]["roi_model"]["status"] == "UNVERIFIED"
    assert ev["claims"]["price"]["status"] == "verified"
