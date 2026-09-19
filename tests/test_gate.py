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


# ---------------------------------------------------------------------------
# The number policy ported from reel-engine/reel/build.py and the two gate
# layers. Appended below the original eight, which stay exactly as they were.
#
# Every test here is offline: the judge is tests/stubs.py's StubClient, the
# evidence file is the committed one or a temporary copy, and no test needs a
# key. A StubClient constructed with no replies raises on its first call, so
# "the gate spent no token" is an assertion the stub enforces on its own.
# ---------------------------------------------------------------------------
import hashlib
import json

import pytest

from engine import gate
from engine.gate import (
    LIMITS, MODEL_GATE, NATIVE_PLACEHOLDER, NUM_RE, REFUSED_CONSTRUCTIONS,
    GateResult, check_creative, editorial, evidence_key, load_attestations,
    load_offers, run, spoken, structural, unattested_numbers,
)
from tests.stubs import StubClient, json_reply, text_reply

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "creative" / "example-job.json"


def example_job() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def job(**overrides) -> dict:
    """The worked example, mutated per test.

    A spoken-field override given as a bare string replaces the English only,
    so a test can say `job(headline="...")` and keep the da/lt placeholders.
    """
    data = example_job()
    for key, value in overrides.items():
        if key in gate.SPOKEN_FIELDS and isinstance(value, str):
            data[key] = dict(data[key], en=value)
        else:
            data[key] = value
    return data


# --- NUM_RE, spoken, evidence_key ------------------------------------------


@pytest.mark.parametrize("text", [
    "We answer 40 emails before lunch.",
    "It costs 4,5 per seat.",
    "One click and it is drafted.",
    "It takes half the day.",
    "Twice a week the same question lands.",
    "A dozen renewals before lunch.",
])
def test_num_re_catches_digits_and_number_words(text):
    """The trap that kills most drafts: the policy matches words, not just
    digits, and it matches them as pronouns and articles too."""
    assert NUM_RE.search(text), text


@pytest.mark.parametrize("text", [
    "Someone on your team writes it again.",
    "None of them should retype this.",
    "Nobody should retype this.",
    "Often the answer is on file.",
])
def test_num_re_does_not_match_inside_other_words(text):
    """\\b keeps "someone" and "none" out; a policy that failed them would
    forbid ordinary English and be worked around within a week."""
    assert not NUM_RE.search(text), text


def test_spoken_strips_emphasis_and_collapses_whitespace():
    assert spoken("Three  times **before**\nlunch. ") == "Three times before lunch."


def test_evidence_key_is_sha256_of_field_and_spoken_text():
    """Same hashing as reel-engine, so a line attested there is attested here."""
    text = "Three  times **before** lunch."
    want = hashlib.sha256(b"headline.en|Three times before lunch.").hexdigest()
    assert evidence_key("headline.en", text) == want
    assert len(want) == 64


# --- attestations ------------------------------------------------------------

ATTESTED_HEADLINE = "Three renewals before lunch, drafted"


def _attest(monkeypatch, field: str, text: str) -> str:
    key = evidence_key(field, text)
    monkeypatch.setattr(gate, "load_attestations", lambda: {
        key: {"kind": "illustrative", "field": field, "text": text,
              "source": "test", "asOf": "2026-09-18"},
    })
    return key


def test_an_attested_headline_passes(monkeypatch):
    _attest(monkeypatch, "headline.en", ATTESTED_HEADLINE)
    result = structural(job(headline=ATTESTED_HEADLINE))
    assert result.ok is True, result.failures


def test_the_same_headline_unattested_fails_naming_the_key():
    """The failure prints the exact key to add, as reel/build.py does: the
    operator pastes it, they do not compute it."""
    result = structural(job(headline=ATTESTED_HEADLINE))
    assert result.ok is False
    assert result.layer == "structural"
    key = evidence_key("headline.en", ATTESTED_HEADLINE)
    line = next(f for f in result.failures if "no attestation" in f)
    assert line.startswith("headline.en contains 'Three'")
    assert key in line
    assert "claims/evidence.json" in line


def test_an_attestation_is_per_field_not_per_text(monkeypatch):
    """A headline attested as headline.en is not attested as description.en:
    the field is part of the key, exactly as in the sibling."""
    _attest(monkeypatch, "headline.en", ATTESTED_HEADLINE)
    result = structural(job(description=ATTESTED_HEADLINE))
    assert any("description.en contains" in f for f in result.failures)


def test_unattested_numbers_names_what_it_found():
    assert unattested_numbers("headline.en", "No number here.") == []
    found = unattested_numbers("headline.en", "Half the day, 40 times.",
                               attestations={})
    assert found == ["Half", "40"]
    key = evidence_key("headline.en", "Half the day, 40 times.")
    assert unattested_numbers("headline.en", "Half the day, 40 times.",
                              attestations={key: {"kind": "illustrative"}}) == []


def test_load_attestations_skips_the_note_on_the_committed_file():
    """The section ships empty on purpose; its _note is documentation."""
    assert load_attestations() == {}


def _write_evidence(path: Path, attestations: dict) -> None:
    path.write_text(json.dumps({
        "claims": {}, "attestations": attestations, "offers": {},
    }), encoding="utf-8")


@pytest.mark.parametrize("kind", ["measured", "architectural", "illustrative"])
def test_each_declared_evidence_kind_is_accepted(tmp_path, monkeypatch, kind):
    dest = tmp_path / "evidence.json"
    _write_evidence(dest, {"deadbeefcafe0123": {"kind": kind, "source": "s", "asOf": "2026-09-18"}})
    monkeypatch.setattr(gate, "EVIDENCE", dest)
    assert load_attestations()["deadbeefcafe0123"]["kind"] == kind


def test_an_invented_evidence_kind_is_refused_by_name(tmp_path, monkeypatch):
    """The three kinds are a closed set: an unrecognised one is a wildcard.
    Without this, "kind": "vibes" attests a number as convincingly as a
    measurement does, and the claims gate becomes decorative."""
    dest = tmp_path / "evidence.json"
    _write_evidence(dest, {"deadbeefcafe0123": {"kind": "vibes", "source": "s", "asOf": "2026-09-18"}})
    monkeypatch.setattr(gate, "EVIDENCE", dest)
    with pytest.raises(gate.EvidenceError) as caught:
        load_attestations()
    message = str(caught.value)
    assert "vibes" in message and "deadbeefcafe" in message
    for kind in ("measured", "architectural", "illustrative"):
        assert kind in message


def test_evidence_with_no_kind_at_all_is_refused(tmp_path, monkeypatch):
    """A bare {"source": ...} is the likeliest hand-edit mistake."""
    dest = tmp_path / "evidence.json"
    _write_evidence(dest, {"deadbeefcafe0123": {"source": "s", "asOf": "2026-09-18"}})
    monkeypatch.setattr(gate, "EVIDENCE", dest)
    with pytest.raises(gate.EvidenceError, match="None"):
        load_attestations()


def test_a_missing_attestations_section_is_not_an_error(tmp_path, monkeypatch):
    dest = tmp_path / "evidence.json"
    dest.write_text(json.dumps({"claims": {}}), encoding="utf-8")
    monkeypatch.setattr(gate, "EVIDENCE", dest)
    assert load_attestations() == {}
    assert load_offers() == {}


# --- offers ------------------------------------------------------------------


def test_load_offers_lists_the_contract_offers_and_nothing_else():
    offers = load_offers()
    assert set(offers) == {"guarantee", "design_partner", "demo", "free_trial"}
    assert offers["guarantee"]["status"] == "verified"
    assert offers["free_trial"]["status"] == "UNVERIFIED"
    assert offers["free_trial"]["safe_phrasings"] == []
    for entry in offers.values():
        assert set(entry) >= {"status", "evidence", "safe_phrasings"}


def test_unverified_offer_free_trial_fails_naming_it():
    result = structural(job(offer="free_trial"))
    assert result.ok is False
    line = next(f for f in result.failures if f.startswith("offer 'free_trial'"))
    assert "UNVERIFIED" in line
    assert "no self-serve trial exists" in line
    # It names the alternatives rather than merely refusing.
    assert "guarantee" in line and "design_partner" in line and "demo" in line


def test_unknown_offer_fails_naming_it():
    result = structural(job(offer="cashback"))
    assert any(f.startswith("offer 'cashback' is not in claims/evidence.json offers")
               for f in result.failures)


def test_offer_none_passes():
    assert structural(job(offer="none")).ok is True


# --- structural: shape, limits, enums ---------------------------------------


def test_a_missing_key_is_named():
    data = job()
    del data["ads"]
    result = structural(data)
    assert result.ok is False
    assert "missing key 'ads'" in result.failures[0]


def test_a_job_that_is_not_an_object_is_refused():
    result = structural(["not", "a", "job"])
    assert result.ok is False and result.layer == "structural"
    assert "list" in result.failures[0]


def test_a_spoken_field_that_is_not_a_map_is_named():
    """A bare string where the {en, da, lt} map should be: the old
    creative/*.json shape, refused by name rather than read as English."""
    result = structural(dict(job(), headline="Proof of cover"))
    assert any(f.startswith("headline must be a {en, da, lt} map, got str")
               for f in result.failures)


def test_a_missing_language_is_named():
    data = job()
    del data["headline"]["lt"]
    result = structural(data)
    assert any(f.startswith("headline is missing 'lt'") and NATIVE_PLACEHOLDER in f
               for f in result.failures)


def test_an_unknown_language_is_refused():
    """A language the gate does not read is silently unchecked copy."""
    data = job()
    data["headline"]["de"] = "Nachweis der Deckung"
    result = structural(data)
    assert any(f.startswith("headline has unknown language 'de'") for f in result.failures)


def test_an_empty_english_field_is_named():
    result = structural(job(description="  "))
    assert any(f.startswith("description.en is empty") for f in result.failures)


def test_a_placeholder_in_english_is_refused():
    """English is authored here; the placeholder means a native has not signed
    off a translation, and there is no translation of nothing."""
    result = structural(job(headline=NATIVE_PLACEHOLDER))
    assert any(f.startswith("headline.en is NEEDS_NATIVE_PROOFREAD") for f in result.failures)


def test_an_empty_danish_field_is_named_with_the_placeholder_as_the_fix():
    data = job()
    data["headline"]["da"] = ""
    result = structural(data)
    line = next(f for f in result.failures if f.startswith("headline.da is empty"))
    assert NATIVE_PLACEHOLDER in line


@pytest.mark.parametrize("name", sorted(LIMITS))
def test_each_limit_is_enforced_per_field(name):
    limit = LIMITS[name]
    too_long = "x" * (limit + 1)
    result = structural(job(**{name: too_long}))
    assert result.ok is False
    assert "%s.en is %d characters; the limit is %d" % (name, limit + 1, limit) in result.failures
    at_limit = "x" * limit
    assert structural(job(**{name: at_limit})).ok is True


def test_limits_apply_to_native_copy_too():
    data = job()
    data["headline"]["da"] = "y" * (LIMITS["headline"] + 1)
    result = structural(data)
    assert any(f.startswith("headline.da is 41 characters") for f in result.failures)


def test_cta_enum():
    result = structural(job(cta="BUY_NOW"))
    line = next(f for f in result.failures if f.startswith("cta 'BUY_NOW'"))
    for cta in gate.CTA_TYPES:
        assert cta in line


def test_placement_enum():
    result = structural(job(placement="story-9x16"))
    line = next(f for f in result.failures if f.startswith("placement 'story-9x16'"))
    for placement in gate.PLACEMENTS:
        assert placement in line


def test_creative_source_kind_enum():
    data = job()
    data["creative_source"]["kind"] = "video"
    result = structural(data)
    assert any(f.startswith("creative_source.kind 'video'") for f in result.failures)


def test_all_failures_are_reported_not_just_the_first():
    result = structural(job(cta="BUY_NOW", placement="story-9x16", offer="free_trial"))
    heads = {f.split(" ")[0] for f in result.failures}
    assert {"cta", "placement", "offer"} <= heads


# --- structural: the placeholder, check(), refused constructions ------------


def test_the_native_placeholder_is_skipped_not_failed():
    """NEEDS_NATIVE_PROOFREAD is the writer saying a native has not signed
    this off yet. The gate has nothing to read in it and must not read it as
    copy - not for limits, not for numbers, not for claims."""
    data = job()
    for name in gate.SPOKEN_FIELDS:
        assert data[name]["da"] == NATIVE_PLACEHOLDER
        assert data[name]["lt"] == NATIVE_PLACEHOLDER
    result = structural(data)
    assert result.ok is True
    assert not any(".da" in f or ".lt" in f for f in result.failures)


def test_a_danish_hours_claim_is_caught_by_check():
    """The five named regexes stay: "10 timer" is a time-saving claim the
    number policy alone would only report as an unattested "10"."""
    data = job()
    data["headline"]["da"] = "Spar 10 timer om måneden"
    result = structural(data)
    assert result.ok is False
    line = next(f for f in result.failures if f.startswith("headline.da: '10 timer'"))
    assert "hours_saved" in line and "UNVERIFIED" in line


def test_a_refused_construction_is_caught_with_its_advice():
    text = "Replies ready before you open your inbox. Nothing sends until you read it."
    result = structural(job(primary_text=text))
    assert result.ok is False
    line = next(f for f in result.failures if f.startswith("primary_text.en: 'before you open'"))
    assert "latency promise" in line
    assert '"The reply is waiting in your drafts"' in line


def test_never_sends_without_you_keeps_passing():
    """The patterns are narrow on purpose: this line is true by construction
    and the rubric names it as such."""
    result = structural(job(primary_text="It never sends without you. Nothing leaves Europe."))
    assert result.ok is True, result.failures


def test_every_refused_construction_carries_advice():
    for pattern, why in REFUSED_CONSTRUCTIONS:
        assert isinstance(pattern, str) and pattern
        assert isinstance(why, str) and "promise" in why


def test_the_refused_constructions_are_the_siblings():
    """Ported verbatim: the sibling's gate refused exactly these, and a list
    that drifted here would let its writer imitate what its gate refuses."""
    assert len(REFUSED_CONSTRUCTIONS) == 7
    patterns = [p for p, _ in REFUSED_CONSTRUCTIONS]
    assert r"never\s+(?:\*\*)?\s*(?:guess|invent)" in patterns
    assert r"finds\s+the\s+exact" in patterns


# --- GateResult --------------------------------------------------------------


def test_result_is_frozen():
    result = GateResult(ok=True, layer="structural", failures=[])
    with pytest.raises(Exception):
        result.ok = False


# --- editorial ---------------------------------------------------------------


def test_editorial_passes_on_a_clean_verdict():
    client = StubClient(json_reply({"pass": True, "failures": []}))
    result = editorial(job(), client=client)
    assert result.ok is True
    assert result.layer == "editorial"
    assert result.failures == []


def test_editorial_is_one_call_to_the_judge_model():
    client = StubClient(json_reply({"pass": True, "failures": []}))
    editorial(job(), client=client)
    assert len(client.calls) == 1 and client.remaining == 0
    assert client.calls[0]["model"] == MODEL_GATE == gate.model.MODEL_FLASH


def test_editorial_budgets_enough_tokens_for_thinking_plus_a_verdict():
    """Thinking is spent before the first visible token. 1024 was not enough."""
    client = StubClient(json_reply({"pass": True, "failures": []}))
    editorial(job(), client=client)
    assert client.calls[0]["max_tokens"] >= 4096


def test_editorial_prompt_carries_the_four_rules_and_the_trade():
    client = StubClient(json_reply({"pass": True, "failures": []}))
    editorial(job(), client=client)
    prompt = client.sent(0)
    for rule in ("1. NO UNSUPPORTABLE PROMISE", "2. THE HOOK NAMES A MOMENT",
                 "3. NOTHING THAT DOES NOT EXIST", "4. ONE ARGUMENT"):
        assert rule in prompt
    assert "insurance-brokers" in prompt
    assert "__SEGMENT__" not in prompt
    assert '{"pass": true|false' in prompt


def test_editorial_sends_the_english_copy_and_the_hypothesis_only():
    """The judge reads one argument once; placeholders and bookkeeping are
    noise it has no rule about."""
    client = StubClient(json_reply({"pass": True, "failures": []}))
    data = job()
    editorial(data, client=client)
    prompt = client.sent(0)
    assert data["headline"]["en"] in prompt
    assert data["hypothesis"] in prompt
    assert NATIVE_PLACEHOLDER not in prompt
    assert "proposed_at" not in prompt and "launched_at" not in prompt


def test_editorial_reports_the_models_failures():
    client = StubClient(json_reply({
        "pass": False, "failures": ["the hook is a generic complaint about email"],
    }))
    result = editorial(job(), client=client)
    assert result.ok is False
    assert result.layer == "editorial"
    assert result.failures == ["the hook is a generic complaint about email"]


def test_editorial_tolerates_prose_around_the_json():
    client = StubClient(text_reply('Here is my verdict:\n{"pass": true, "failures": []}\nDone.'))
    assert editorial(job(), client=client).ok is True


def test_editorial_fails_closed_on_prose():
    client = StubClient(text_reply("I could not decide."))
    result = editorial(job(), client=client)
    assert result.ok is False
    assert result.layer == "editorial"
    assert any("could not parse" in f for f in result.failures)


def test_editorial_fails_closed_on_a_verdict_without_pass():
    client = StubClient(json_reply({"failures": []}))
    result = editorial(job(), client=client)
    assert result.ok is False
    assert any("could not parse" in f for f in result.failures)


def test_editorial_fails_closed_on_max_tokens():
    """A verdict that says pass but was cut short is not an approval."""
    client = StubClient(json_reply({"pass": True, "failures": []}, stop_reason="max_tokens"))
    result = editorial(job(), client=client)
    assert result.ok is False
    assert result.layer == "editorial"
    assert any("truncated at max_tokens" in f for f in result.failures)


def test_a_bare_string_of_failures_stays_one_failure():
    """Iterating a string yields characters - one bullet per letter."""
    client = StubClient(json_reply({"pass": False, "failures": "these are judgement calls"}))
    result = editorial(job(), client=client)
    assert result.ok is False
    assert result.failures == ["these are judgement calls"]


def test_a_failing_verdict_with_no_failures_still_fails():
    client = StubClient(json_reply({"pass": False}))
    result = editorial(job(), client=client)
    assert result.ok is False
    assert result.failures == ["unspecified"]


# --- run ---------------------------------------------------------------------


def _write_job(tmp_path: Path, data: dict) -> Path:
    dest = tmp_path / "insurance-brokers.json"
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest


def test_run_short_circuits_before_calling_the_model(tmp_path):
    """A structural failure must not spend a token. The stub has no reply
    queued, so a call would raise inside the gate rather than pass here."""
    client = StubClient()
    result = run(_write_job(tmp_path, job(cta="BUY_NOW")), client=client)
    assert result.ok is False
    assert result.layer == "structural"
    assert client.calls == []


def test_run_reaches_editorial_when_structural_passes(tmp_path):
    client = StubClient(json_reply({"pass": True, "failures": []}))
    result = run(_write_job(tmp_path, job()), client=client)
    assert result.ok is True
    assert result.layer == "editorial"
    assert len(client.calls) == 1


def test_run_returns_the_editorial_failure(tmp_path):
    client = StubClient(json_reply({"pass": False, "failures": ["argues two things"]}))
    result = run(_write_job(tmp_path, job()), client=client)
    assert result.ok is False
    assert result.layer == "editorial"
    assert result.failures == ["argues two things"]


def test_run_on_a_file_that_is_not_json_fails_structurally(tmp_path):
    dest = tmp_path / "broken.json"
    dest.write_text("{not json", encoding="utf-8")
    client = StubClient()
    result = run(dest, client=client)
    assert result.ok is False and result.layer == "structural"
    assert "broken.json" in result.failures[0] and "not JSON" in result.failures[0]
    assert client.calls == []


def test_run_accepts_a_string_path(tmp_path):
    client = StubClient()
    result = run(str(_write_job(tmp_path, job(placement="story-9x16"))), client=client)
    assert result.layer == "structural" and not result.ok


# --- the worked example ------------------------------------------------------


def test_example_job_passes_structural():
    """The writer hands this file to the model as the thing to imitate, so it
    must pass the gate it is teaching - the sibling's example did not, for
    two runs' worth of refused drafts."""
    result = structural(example_job())
    assert result.ok is True, "\n".join(result.failures)
    assert result.failures == []


def test_example_job_passes_the_original_gate_too():
    assert check_creative(example_job()).passed


def test_example_job_is_the_contracts_worked_example():
    data = example_job()
    assert data["id"] == data["segment"] == "insurance-brokers"
    assert data["placement"] == "reels-9x16"
    assert data["offer"] == "guarantee"
    assert data["cta"] == "LEARN_MORE"
    assert data["creative_source"] == {
        "kind": "reel", "repo": "reel-engine", "template": "reel-c",
        "selection": "queue/proposed/insurance-brokers.reel.json",
    }
    assert data["proposed_at"] == "2026-09-18T00:00:00Z"
    assert data["ads"] == {} and data["launched_at"] is None
    assert data["hypothesis"].strip()
    assert list(data) == list(gate.JOB_KEYS)


def test_example_job_carries_no_number_in_any_spoken_field():
    """No digit or number word, so nothing in it needs attesting."""
    data = example_job()
    for name in gate.SPOKEN_FIELDS:
        for lang, text in data[name].items():
            assert not NUM_RE.search(text), "%s.%s: %r" % (name, lang, text)


def test_example_job_is_outside_the_backlog():
    """A trade not in the table, so the worked example can never be picked up
    as a live draft - the sibling's practice, kept."""
    table = (ROOT / "queue" / "backlog.md").read_text(encoding="utf-8")
    assert "| insurance-brokers |" not in table


def test_example_job_is_written_as_a_job_file():
    """indent=2, ensure_ascii=False, trailing newline, keys in authored order."""
    raw = EXAMPLE.read_text(encoding="utf-8")
    assert raw.endswith("}\n")
    assert raw == json.dumps(json.loads(raw), indent=2, ensure_ascii=False) + "\n"
