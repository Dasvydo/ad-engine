import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.audience import hash_field, normalise_email, from_outreach_csv
from engine.gate import check


def test_verified_claims_pass():
    assert check("Nothing sends until you read it. Runs on European servers.").passed


def test_time_saving_number_is_blocked():
    v = check("Save 10 hours a month.")
    assert not v.passed and "hours_saved" in v.failures[0]


def test_customer_count_is_blocked():
    assert not check("Trusted by 200 firms.").passed


def test_percentage_is_blocked():
    assert not check("Cut reply time by 40%.").passed


def test_email_normalisation_matches_meta_spec():
    assert normalise_email("  Lars@NordicRev.DK ") == "lars@nordicrev.dk"


def test_hash_is_sha256_hex():
    h = hash_field("lars@nordicrev.dk")
    assert len(h) == 64 and int(h, 16) >= 0


def test_empty_field_hashes_to_empty_not_a_hash():
    """Hashing '' would emit a valid-looking hash for missing data."""
    assert hash_field("") == ""


def test_small_audience_is_flagged_unusable(tmp_path):
    src = tmp_path / "s.csv"
    src.write_text("email,firstName,lastName,country\na@b.dk,A,B,DK\n")
    build = from_outreach_csv(src, tmp_path / "o.csv")
    assert build.rows == 1 and not build.usable and "1,000" in build.warning


# --- extended assertion patterns -------------------------------------------
# Each of these is a shape the gate missed before: an assertion that is just as
# public and just as unbacked as "save 10 hours", written differently.

import json
import pytest
from engine.gate import ROOT, check_creative, rules


@pytest.mark.parametrize(
    "copy",
    [
        "Save ten hours a month.",            # number written as a word
        "Get your hours back.",               # a saving with no figure at all
        "Save half a day every week.",
        "2x the output.",                     # the saving as a ratio
        "Twice as fast as before.",
        "Half the time, same quality.",
        "Trusted by Danish accounting firms.",  # social proof with no number
        "Our customers say it changed everything.",
        "Rated 4.8 out of 5.",
        "From $49 per seat.",                 # a price nobody has agreed to
        "Kun 349 kr. om maneden.",
        "Free trial, no card needed.",
        "The best AI assistant for accountants.",
        "Europe's first Outlook drafting tool.",
        "The only tool that keeps you in Outlook.",
        "Faster than any alternative.",
        "Unlike other tools, we stay in Outlook.",
        "Error-free drafts, every time.",
        "It never gets it wrong.",
        "Set up in 5 minutes.",
        "Replies drafted instantly.",
        "SOC 2 certified.",
        "Fully GDPR compliant.",              # EU hosting is not GDPR compliance
        "30-day money-back guarantee.",
        "Resultat garanteret.",               # da
        "Garantuotas rezultatas.",            # lt
        "Nemokamai 14 dienu.",                # lt
        "Reduce workload 30 procent.",        # da/lt percentage spelling
    ],
)
def test_unbacked_assertion_shapes_are_blocked(copy):
    assert not check(copy).passed, f"gate let through: {copy!r}"


@pytest.mark.parametrize(
    "copy",
    [
        "Nothing sends until you read it. Runs on European servers.",
        "It never leaves Outlook.",
        "Answers from your own fees, deadlines and policies.",
        "In each person's own words.",
        "More clients, same team.",
        "Stop re-typing the same reply.",
        "Three times before lunch, someone writes an email they have already written.",
        "Your team answers the same client questions every week.",
        "Built for accounting, admin and broker firms.",
        # The brief's own accounting hook. A gate that blocks the copy the brief
        # recommends is a gate someone will switch off.
        "The inbox triples at year-end and you cannot hire for eight weeks.",
    ],
)
def test_evidenced_and_non_assertive_copy_still_passes(copy):
    verdict = check(copy)
    assert verdict.passed, verdict.failures


def test_shipping_creative_passes_the_gate():
    """The two live variants must stay shippable as the ruleset grows."""
    for path in sorted((ROOT / "creative").glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        verdict = check_creative(spec)
        assert verdict.passed, f"{path.name}: {verdict.failures}"


def test_every_offending_span_is_reported_not_just_the_first():
    """A rewrite that fixes the first match and reships is how the second one lands."""
    verdict = check("Save 10 hours and cut costs by 40%.")
    assert len(verdict.failures) >= 2


def test_failure_names_the_field_an_editor_has_to_open():
    spec = {"headline": {"en": "Trusted by 200 firms"}}
    verdict = check_creative(spec)
    assert not verdict.passed
    assert "headline.en" in verdict.failures[0]


def test_hypothesis_and_underscore_fields_are_not_scanned():
    """Internal reasoning is allowed to discuss claims the copy may not make."""
    spec = {"hypothesis": "Save 10 hours", "_note": "Trusted by 200 firms", "headline": {"en": "More clients"}}
    assert check_creative(spec).passed


def test_every_pattern_resolves_to_a_real_evidence_entry():
    """A pattern pointing at a missing claim id blocks with a confusing message."""
    evidence = json.loads((ROOT / "claims" / "evidence.json").read_text(encoding="utf-8"))["claims"]
    missing = sorted({claim_id for _, claim_id in rules() if claim_id not in evidence})
    assert not missing, f"patterns assert claim ids absent from evidence.json: {missing}"
