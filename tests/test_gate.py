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


def test_our_own_price_passes():
    """A price we set is a fact we control, so the offer's core line ships."""
    v = check("One price for the whole firm. 199 USD a month, up to twenty people.")
    assert v.passed, v.failures


def test_naming_a_rival_is_blocked():
    """The strongest line the offer has is the one we are least entitled to
    write: rival rates came off a round-up, not a vendor page."""
    v = check("Fyxer charges 30 USD a seat. DoviLoop is 199 for the firm.")
    assert not v.passed and any("competitor_price" in f for f in v.failures)


def test_characterising_rival_billing_is_blocked():
    """Even without naming anyone, 'they charge per seat' is the same claim
    from the same unverified source."""
    v = check("Most email tools charge per seat. This one does not.")
    assert not v.passed and any("rivals_charge_per_seat" in f for f in v.failures)


def test_our_coverage_claim_passes():
    v = check("Drafts are pooled across the firm, not rationed per person.")
    assert v.passed, v.failures
