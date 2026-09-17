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


# --- the funnel seam: claims the landing page renders, which an ad may not echo ---
# The first version of the gate blocked "Saves 430 USD" and passed
# "430 USD saved per month" - the exact string the landing page shows. It was
# catching phrasings nobody writes and passing the two a buyer actually sees.


def test_money_saved_is_blocked_in_either_word_order():
    assert not check("430 USD saved per month, for each person").passed
    assert not check("Save 430 USD per person every month").passed
    assert not check("Saves you €430 a month").passed


def test_value_claim_without_a_save_word_is_blocked():
    assert not check("Worth 4,300 USD a month to a ten person firm").passed


def test_a_bare_price_is_not_a_claim():
    """A price is a fact about the offer. The gate must not block one."""
    assert check("89 USD per month for the whole firm, 500 USD setup.").passed


def test_return_multiples_are_blocked():
    assert not check("12x time saved, against what the firm pays").passed
    assert not check("Pays for itself twelve times over").passed


def test_pixel_dimensions_are_not_a_multiple():
    assert check("Static creative, 1200x628.").passed


def test_worded_time_claims_are_blocked():
    """These carry no digit at all, so no numeric pattern ever saw them."""
    assert not check("Cuts your email time in half").passed
    assert not check("Half the time on client mail").passed


def test_live_creative_still_ships():
    """The two real arms must survive every pattern added above."""
    import json
    from pathlib import Path

    from engine.gate import check_creative

    root = Path(__file__).resolve().parent.parent
    for path in sorted((root / "creative").glob("*.json")):
        assert check_creative(json.loads(path.read_text(encoding="utf-8"))).passed, path.name


def test_landing_scan_decodes_escapes_before_matching(tmp_path):
    """'430' and '\\u00a0USD' are separate fields. Left encoded, nothing spans them."""
    from engine.gate import check_landing

    (tmp_path / "en.ts").write_text(
        "export const en = { rows: [{ amount: '430', unit: '\\u00a0USD',"
        " label: 'saved per month' }] };",
        encoding="utf-8",
    )
    verdicts = check_landing(tmp_path)
    assert not verdicts["en.ts"].passed
    assert "money_saved" in verdicts["en.ts"].failures[0]


def test_landing_scan_keeps_non_ascii_intact(tmp_path):
    """unicode_escape would decode through latin-1 and mangle DK and LT copy."""
    from engine.gate import check_landing

    (tmp_path / "da.ts").write_text(
        "export const da = { a: 'Håndtér købsaftaler', b: 'Sąskaitų išrašymas' };",
        encoding="utf-8",
    )
    assert check_landing(tmp_path)["da.ts"].passed
