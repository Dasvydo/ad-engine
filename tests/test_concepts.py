"""Concepts: one model call for all N, and every citation, placement and offer
has to point at something.

Five properties carry this module; the rest is bookkeeping.

**One call, whatever N is.** The free tier is the budget, and a call per
concept would spend N times the quota to buy nothing. The tests below count
the calls for several values of N rather than trusting the docstring.

**A citation is checked, not trusted.** A concept exists to carry a hook back
to an ad that measurably ran, so a pattern id nobody counted is rejected by
name. The tests pin both the rejection and the message that makes it fixable.

**A placement and an offer are checked from tables, not judged.** The gate's
placement list and claims/evidence.json's offers are the tables; a concept
naming a placement nobody renders or an offer nobody makes is refused by
name, and the unverified free trial is the case that matters.

**The patterns it reads are the ones engine.learn writes.** A document
learn.build() produces from two corpus records validates here unchanged, so
the two halves of C5 cannot drift apart without a test going red.

**The ICP brief is not model input.** Three tests guard it from three
directions: the module names no path into docs/, an open of one during a run
is made to explode, and no substantial line of the real brief appears in the
prompt. A fourth test proves the explosive guard is not vacuous.

Every test here is offline. The client is tests/stubs.StubClient, injected;
no test needs a key, and a fixture makes every socket explode where the path
under test could reach one.
"""
import ast
import builtins
import contextlib
import copy
import json
import os
import socket
from pathlib import Path

import pytest

from engine import concepts, gate, learn, model
from engine.backlog import Segment
from engine.model import ConfigError
from tests.stubs import StubClient, json_reply, text_reply

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "engine" / "concepts.py"
BRIEF = ROOT / "docs" / "ICP-BRIEF.md"

# A C5 document, written here rather than imported: the learn step that
# produces the real one is a separate module, and a test that waits for it
# cannot pin this module's half of the contract. One test further down does
# build a real one and checks it validates here.
PATTERNS = {
    "schema": 1,
    "generated_at": "2026-09-14T00:00:00Z",
    "corpus_size": 41,
    "patterns": [
        {
            "id": "q01",
            "kind": "hook",
            "device": "negative-flip",
            "description": 'opening device "negative-flip"; median hook 9.0 words; '
                           'example: "Your bureau is not answering questions."',
            "evidence": ["fb-961046237012883", "fb-961046237012884"],
            "median_days_running": 74,
            "median_reach": 12000,
            "n": 7,
        },
        {
            "id": "q03",
            "kind": "longevity",
            "device": "days:60-119",
            "description": "60-119 days running; median 74.0",
            "evidence": ["fb-961046237012885"],
            "median_days_running": 74,
            "median_reach": 9800,
            "n": 3,
        },
        {
            "id": "q07",
            "kind": "offer",
            "device": "guarantee",
            "description": 'offer "guarantee"; example: "If it does not fit, you do not pay"',
            "evidence": ["fb-961046237012886"],
            "median_days_running": 41,
            "median_reach": 3300,
            "n": 4,
        },
    ],
}

SEGMENTS = [
    Segment(
        rank=2,
        id="payroll-bureaus",
        trade="Payroll bureaus",
        questions=("payslip", "holiday", "tax-code"),
        note="strongest lookup profile of the set",
    ),
    Segment(
        rank=3,
        id="bookkeepers",
        trade="Bookkeeping firms",
        questions=("invoice", "vat", "receipt"),
        note="bogholder vs revisor, a distinct audience from accountants",
    ),
]

# The offers table as gate.load_offers() returns it, mirroring the committed
# claims/evidence.json so the tests read the same shape without reading the
# file. free_trial is UNVERIFIED there on purpose: no self-serve trial exists.
OFFERS = {
    "guarantee": {
        "status": "verified",
        "evidence": "the brief: knowledge base first; not good enough, do not pay",
        "safe_phrasings": ["If the drafts are not good enough to send, you do not "
                           "pay and you keep the knowledge base"],
    },
    "design_partner": {
        "status": "verified",
        "evidence": "the brief: first ten firms, onboarding waived",
        "safe_phrasings": ["Design-partner terms for the first firms in"],
    },
    "demo": {
        "status": "verified",
        "evidence": "a call can be booked",
        "safe_phrasings": ["See it on your own inbox"],
    },
    "free_trial": {
        "status": "UNVERIFIED",
        "evidence": "no self-serve trial exists; revenue is switched off in the product",
        "safe_phrasings": [],
    },
}
VERIFIED = ("demo", "design_partner", "guarantee")


def concept(**overrides) -> dict:
    """One raw concept as the model writes it: no id, that is stamped later."""
    written = {
        "segment": "payroll-bureaus",
        "angle": "The same payslip question arrives every week from a new address.",
        "hook": "Your bureau is not answering questions. It is retyping answers.",
        "pattern_ids": ["q01"],
        "placement": "reels-9x16",
        "offer": "guarantee",
        "needs_numbers": False,
    }
    written.update(overrides)
    return written


def reply(n: int, *, concepts_written=None, stop_reason="end_turn"):
    """A stubbed reply holding exactly n concepts, each with its own hook."""
    if concepts_written is None:
        concepts_written = [concept(hook="Hook number %d." % i) for i in range(1, n + 1)]
    return json_reply({"concepts": concepts_written}, stop_reason=stop_reason)


def generate(*args, client, **kwargs):
    """concepts.generate with the fixture offers unless a test says otherwise,
    so no test here depends on the committed evidence file by accident."""
    kwargs.setdefault("offers", OFFERS)
    return concepts.generate(*args, client=client, **kwargs)


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    """No test here has a key, and none may need one."""
    for name in model.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def no_sockets(monkeypatch):
    def exploding(*args, **kwargs):
        raise AssertionError("the concepts path opened a socket")

    monkeypatch.setattr(socket, "socket", exploding)
    monkeypatch.setattr(socket, "create_connection", exploding)


# --- one call, whatever N is ---------------------------------------------


@pytest.mark.parametrize("n", [1, 3, 12, 40])
def test_one_model_call_produces_every_concept(n):
    """N times the calls would be N times the quota for no gain."""
    client = StubClient([reply(n)])
    result = generate(PATTERNS, SEGMENTS, n=n, client=client)
    assert len(client.calls) == 1
    assert client.remaining == 0
    assert len(result) == n


def test_n_defaults_to_twelve():
    client = StubClient([reply(12)])
    assert concepts.DEFAULT_N == 12
    assert len(generate(PATTERNS, SEGMENTS, client=client)) == 12
    assert "12 ad concepts" in client.sent(0)


def test_asking_for_no_concepts_is_refused_before_a_call_is_spent():
    client = StubClient([reply(1)])
    with pytest.raises(concepts.ConceptsError):
        generate(PATTERNS, SEGMENTS, n=0, client=client)
    assert client.calls == []


def test_the_writing_model_writes_the_concepts():
    """concepts.MODEL_CONCEPTS is the writer, not the judge: the free tier
    counts its 20-a-day PER MODEL, so writing and gating split the ids."""
    assert concepts.MODEL_CONCEPTS == model.MODEL_WRITE
    assert concepts.MODEL_CONCEPTS != model.MODEL_FLASH
    client = StubClient([reply(2)])
    generate(PATTERNS, SEGMENTS, n=2, client=client)
    assert client.calls[0]["model"] == concepts.MODEL_CONCEPTS


def test_the_call_goes_through_call_model_with_one_user_message():
    client = StubClient([reply(1)])
    generate(PATTERNS, SEGMENTS, n=1, client=client)
    call = client.calls[0]
    assert set(call) == {"model", "max_tokens", "messages"}
    assert [m["role"] for m in call["messages"]] == ["user"]
    assert client.media(0) == []


def test_the_token_ceiling_grows_with_n():
    """One truncated reply costs the whole run, and N is a parameter."""
    assert concepts.max_tokens_for(concepts.DEFAULT_N) == concepts.MAX_TOKENS_BASE
    assert concepts.max_tokens_for(40) > concepts.max_tokens_for(12)
    client = StubClient([reply(40)])
    generate(PATTERNS, SEGMENTS, n=40, client=client)
    assert client.calls[0]["max_tokens"] == concepts.max_tokens_for(40)


def test_a_provider_fault_propagates_as_itself():
    """A selection loop catches CapacityError by class to try the next
    concept; wrapping it here would take that away."""
    client = StubClient([model.CapacityError("Gemini is out of capacity right now")])
    with pytest.raises(model.CapacityError):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


# --- the C4 record --------------------------------------------------------


def test_the_concept_record_is_exactly_contract_c4():
    """Pinned literally. The scorer and the writer read these keys and
    nothing else."""
    assert concepts.KEYS == (
        "id", "segment", "angle", "hook", "pattern_ids", "placement", "offer",
        "needs_numbers",
    )
    assert concepts.AUTHORED == tuple(k for k in concepts.KEYS if k != "id")
    assert concepts.SCHEMA == 1


def test_every_returned_concept_has_exactly_the_contract_keys():
    client = StubClient([reply(4)])
    for record in generate(PATTERNS, SEGMENTS, n=4, client=client):
        assert tuple(record) == concepts.KEYS


def test_the_c4_example_from_the_contract_is_accepted_as_written():
    written = [{
        "segment": "payroll-bureaus", "angle": "...", "hook": "...",
        "pattern_ids": ["q03"], "placement": "reels-9x16", "offer": "guarantee",
        "needs_numbers": False,
    }]
    client = StubClient([reply(1, concepts_written=written)])
    record = generate(PATTERNS, SEGMENTS, n=1, client=client)[0]
    assert record == {"id": "a01", **written[0]}


def test_ids_are_stamped_stable_and_sortable():
    client = StubClient([reply(12)])
    ids = [r["id"] for r in generate(PATTERNS, SEGMENTS, n=12, client=client)]
    assert ids[:3] == ["a01", "a02", "a03"]
    assert ids[-1] == "a12"
    assert ids == sorted(ids)


def test_ids_stay_sortable_past_ninety_nine():
    """a100 sorts before a99 as a string, so the width follows N."""
    client = StubClient([reply(100)])
    ids = [r["id"] for r in generate(PATTERNS, SEGMENTS, n=100, client=client)]
    assert ids[0] == "a001" and ids[-1] == "a100"
    assert ids == sorted(ids)


def test_ids_are_ad_ids_not_reel_ids():
    """An `a` prefix, so a scorer or a queue can never confuse an ad concept
    with one of the sibling's c-ids, the way q-patterns cannot be p-patterns."""
    client = StubClient([reply(2)])
    for record in generate(PATTERNS, SEGMENTS, n=2, client=client):
        assert record["id"].startswith("a")
        assert not record["id"].startswith("c")


def test_an_id_the_model_invents_does_not_survive():
    """Ids are bookkeeping, and a model-written one is neither stable nor unique."""
    written = [concept(id="concept-seven"), concept(id="concept-seven")]
    client = StubClient([reply(2, concepts_written=written)])
    ids = [r["id"] for r in generate(PATTERNS, SEGMENTS, n=2, client=client)]
    assert ids == ["a01", "a02"]


def test_a_stray_field_never_reaches_the_scorer():
    written = [concept(confidence=0.9, format="inbox scroll")]
    client = StubClient([reply(1, concepts_written=written)])
    record = generate(PATTERNS, SEGMENTS, n=1, client=client)[0]
    assert "confidence" not in record
    assert "format" not in record


def test_the_json_is_read_past_the_thinking_block():
    """tests/stubs.py leads every reply with a thinking block that has no
    .text; a call site reading content[0].text dies here, not live."""
    client = StubClient([reply(1)])
    assert generate(PATTERNS, SEGMENTS, n=1, client=client)[0]["hook"]


# --- a citation has to point at something ---------------------------------


def test_a_concept_citing_a_real_pattern_is_kept():
    """The positive control for the rejection below."""
    written = [concept(pattern_ids=["q03", "q07"])]
    client = StubClient([reply(1, concepts_written=written)])
    record = generate(PATTERNS, SEGMENTS, n=1, client=client)[0]
    assert record["pattern_ids"] == ["q03", "q07"]


def test_every_cited_pattern_exists_in_the_patterns_it_was_given():
    known = {p["id"] for p in PATTERNS["patterns"]}
    client = StubClient([reply(6)])
    for record in generate(PATTERNS, SEGMENTS, n=6, client=client):
        assert record["pattern_ids"]
        assert set(record["pattern_ids"]) <= known


def test_an_unknown_pattern_id_is_rejected_by_name():
    written = [concept(), concept(pattern_ids=["q99"])]
    client = StubClient([reply(2, concepts_written=written)])
    with pytest.raises(concepts.UnknownPatternError) as caught:
        generate(PATTERNS, SEGMENTS, n=2, client=client)
    message = str(caught.value)
    assert "q99" in message
    assert "a02" in message           # which concept, of the twelve
    assert "q01" in message           # and what it could have cited instead


def test_a_reel_pattern_id_is_unknown_here():
    """p07 is a reel-engine id. The patterns file here never holds one, so a
    concept citing it is citing nothing, by name."""
    written = [concept(pattern_ids=["p07"])]
    client = StubClient([reply(1, concepts_written=written)])
    with pytest.raises(concepts.UnknownPatternError, match="p07"):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


def test_the_error_hierarchy_lets_a_caller_retry_a_bad_citation_alone():
    """The subclasses exist so a caller can retry a bad citation without
    catching a missing key as well, but every one stays a ValueError."""
    assert issubclass(concepts.UnknownPatternError, concepts.ConceptInvalid)
    assert issubclass(concepts.UnknownSegmentError, concepts.ConceptInvalid)
    assert issubclass(concepts.ConceptInvalid, concepts.ConceptsError)
    assert issubclass(concepts.PatternsInvalid, concepts.ConceptsError)
    assert issubclass(concepts.ConceptsError, ValueError)


def test_patterns_invalid_is_also_the_learn_modules_class():
    """A caller that catches engine.learn.PatternsInvalid around the file
    catches this module's refusal of the same file too: one fix, one class."""
    assert issubclass(concepts.PatternsInvalid, learn.PatternsInvalid)
    assert concepts.DEFAULT_PATTERNS == learn.DEFAULT_PATH


def test_a_concept_citing_nothing_is_rejected():
    written = [concept(pattern_ids=[])]
    client = StubClient([reply(1, concepts_written=written)])
    with pytest.raises(concepts.ConceptInvalid, match="pattern_ids"):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


def test_a_pattern_id_that_is_not_a_string_is_rejected():
    written = [concept(pattern_ids=[3])]
    client = StubClient([reply(1, concepts_written=written)])
    with pytest.raises(concepts.ConceptInvalid, match="expected a string"):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


def test_pattern_ids_given_as_a_bare_string_is_rejected():
    """"q01" iterates into characters, so it would validate a letter at a time."""
    written = [concept(pattern_ids="q01")]
    client = StubClient([reply(1, concepts_written=written)])
    with pytest.raises(concepts.ConceptInvalid, match="pattern_ids"):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


def test_a_concept_for_a_segment_nobody_ranked_is_rejected():
    written = [concept(segment="letting-agents")]
    client = StubClient([reply(1, concepts_written=written)])
    with pytest.raises(concepts.UnknownSegmentError) as caught:
        generate(PATTERNS, SEGMENTS, n=1, client=client)
    assert "letting-agents" in str(caught.value)
    assert "payroll-bureaus" in str(caught.value)


# --- placement: checked against the gate's table --------------------------


def test_placements_are_the_gates_and_are_the_contracts():
    """Pinned literally against the contract AND against gate.PLACEMENTS: the
    writer copies a concept's placement into the job unchanged, and the gate
    is what refuses the job, so the two lists cannot be allowed to differ."""
    assert concepts.PLACEMENTS == ("reels-9x16", "feed-4x5", "static-1x1")
    assert concepts.PLACEMENTS == gate.PLACEMENTS


@pytest.mark.parametrize("placement", concepts.PLACEMENTS)
def test_every_known_placement_is_accepted(placement):
    written = [concept(placement=placement)]
    client = StubClient([reply(1, concepts_written=written)])
    record = generate(PATTERNS, SEGMENTS, n=1, client=client)[0]
    assert record["placement"] == placement


def test_an_unknown_placement_is_rejected_by_name():
    written = [concept(), concept(placement="story-9x16")]
    client = StubClient([reply(2, concepts_written=written)])
    with pytest.raises(concepts.ConceptInvalid) as caught:
        generate(PATTERNS, SEGMENTS, n=2, client=client)
    message = str(caught.value)
    assert "story-9x16" in message
    assert "a02" in message
    for known in concepts.PLACEMENTS:
        assert known in message


def test_every_placement_is_described_to_the_model():
    """A placement is a request for a video or for a picture, and the prompt
    says which for every id the gate accepts, or a widened tuple would list
    a bare id the model cannot read."""
    for placement in concepts.PLACEMENTS:
        assert placement in concepts.PLACEMENT_NOTES
    client = StubClient([reply(1)])
    generate(PATTERNS, SEGMENTS, n=1, client=client)
    sent = client.sent(0)
    for placement, note in concepts.PLACEMENT_NOTES.items():
        assert placement in sent and note in sent


# --- offer: checked against claims/evidence.json, not judged ---------------


def test_no_offer_is_always_allowed():
    written = [concept(offer="none")]
    client = StubClient([reply(1, concepts_written=written)])
    record = generate(PATTERNS, SEGMENTS, n=1, client=client, offers={})
    assert record[0]["offer"] == "none"
    assert concepts.NO_OFFER == "none"


@pytest.mark.parametrize("offer", VERIFIED)
def test_every_verified_offer_is_accepted(offer):
    written = [concept(offer=offer)]
    client = StubClient([reply(1, concepts_written=written)])
    assert generate(PATTERNS, SEGMENTS, n=1, client=client)[0]["offer"] == offer


def test_an_unverified_offer_is_rejected_by_name():
    """free_trial is in the table and is UNVERIFIED: no self-serve trial
    exists, and the message says so and says what could be offered instead."""
    written = [concept(), concept(offer="free_trial")]
    client = StubClient([reply(2, concepts_written=written)])
    with pytest.raises(concepts.ConceptInvalid) as caught:
        generate(PATTERNS, SEGMENTS, n=2, client=client)
    message = str(caught.value)
    assert "free_trial" in message
    assert "UNVERIFIED" in message
    assert "a02" in message
    assert "no self-serve trial exists" in message
    for known in VERIFIED:
        assert known in message


def test_an_offer_not_in_the_table_is_rejected_by_name():
    written = [concept(offer="discount")]
    client = StubClient([reply(1, concepts_written=written)])
    with pytest.raises(concepts.ConceptInvalid) as caught:
        generate(PATTERNS, SEGMENTS, n=1, client=client)
    message = str(caught.value)
    assert "discount" in message
    assert "claims/evidence.json" in message
    assert "guarantee" in message


def test_a_verified_offer_is_rejected_when_the_table_does_not_verify_it():
    """The table is the authority, not the id: the same `guarantee` with its
    status changed is no longer an offer an ad may make."""
    table = copy.deepcopy(OFFERS)
    table["guarantee"]["status"] = "UNVERIFIED"
    written = [concept(offer="guarantee")]
    client = StubClient([reply(1, concepts_written=written)])
    with pytest.raises(concepts.ConceptInvalid, match="guarantee"):
        generate(PATTERNS, SEGMENTS, n=1, client=client, offers=table)


def test_the_offers_default_to_the_committed_evidence_file():
    """Without offers=, gate.load_offers() is the table: guarantee passes and
    free_trial is refused against the file as committed."""
    assert set(gate.load_offers()) == {"guarantee", "design_partner", "demo", "free_trial"}
    assert concepts.verified_offers(gate.load_offers()) == list(VERIFIED)

    client = StubClient([reply(1, concepts_written=[concept(offer="guarantee")])])
    assert concepts.generate(PATTERNS, SEGMENTS, n=1, client=client)[0]["offer"] == "guarantee"

    client = StubClient([reply(1, concepts_written=[concept(offer="free_trial")])])
    with pytest.raises(concepts.ConceptInvalid, match="free_trial"):
        concepts.generate(PATTERNS, SEGMENTS, n=1, client=client)


def test_verified_offers_reads_status_only():
    """An entry that is not an object, or has any status but `verified`, is
    not an offer; a `_note` key never reaches here because gate strips it."""
    table = {
        "b": {"status": "verified"},
        "a": {"status": "verified", "safe_phrasings": []},
        "c": {"status": "Verified"},
        "d": "verified",
        "e": {"status": "UNVERIFIED"},
    }
    assert concepts.verified_offers(table) == ["a", "b"]


def test_an_offers_table_that_is_not_a_table_is_refused_before_a_call():
    client = StubClient([reply(1)])
    with pytest.raises(concepts.ConceptsError, match="gate.load_offers"):
        concepts.generate(PATTERNS, SEGMENTS, n=1, client=client, offers=["guarantee"])
    assert client.calls == []


# --- the fields the scorer branches on ------------------------------------


def test_needs_numbers_must_be_a_real_boolean():
    """The string "false" is truthy, so a coerced one flips the flag."""
    written = [concept(needs_numbers="false")]
    client = StubClient([reply(1, concepts_written=written)])
    with pytest.raises(concepts.ConceptInvalid, match="needs_numbers"):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


@pytest.mark.parametrize("value", [0, 1, None, "true"])
def test_needs_numbers_that_is_not_a_boolean_is_refused(value):
    written = [concept(needs_numbers=value)]
    client = StubClient([reply(1, concepts_written=written)])
    with pytest.raises(concepts.ConceptInvalid, match="needs_numbers"):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


def test_needs_numbers_survives_as_written():
    written = [concept(needs_numbers=True), concept(needs_numbers=False)]
    client = StubClient([reply(2, concepts_written=written)])
    flags = [r["needs_numbers"] for r in
             generate(PATTERNS, SEGMENTS, n=2, client=client)]
    assert flags == [True, False]


@pytest.mark.parametrize("field", concepts.AUTHORED)
def test_a_missing_field_raises_and_names_it(field):
    written = concept()
    del written[field]
    client = StubClient([reply(1, concepts_written=[written])])
    with pytest.raises(concepts.ConceptInvalid, match=field):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


@pytest.mark.parametrize("field", ["angle", "hook", "segment", "placement", "offer"])
def test_an_empty_text_field_raises(field):
    written = [concept(**{field: "   "})]
    client = StubClient([reply(1, concepts_written=written)])
    with pytest.raises(concepts.ConceptInvalid, match=field):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


def test_a_concept_that_is_not_an_object_raises():
    client = StubClient([reply(1, concepts_written=["a string"])])
    with pytest.raises(concepts.ConceptInvalid, match="not a JSON object"):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


# --- a reply that cannot be trusted ---------------------------------------


def test_a_truncated_reply_raises_rather_than_returning_a_short_list():
    """An incomplete answer is not an answer, even when it parses."""
    client = StubClient([reply(4, stop_reason="max_tokens")])
    with pytest.raises(ValueError, match="truncated"):
        generate(PATTERNS, SEGMENTS, n=12, client=client)


def test_a_truncated_reply_that_happens_to_be_complete_still_raises():
    """A max_tokens stop with exactly N concepts is a coincidence the reader
    cannot tell from a list cut at the right place."""
    client = StubClient([reply(2, stop_reason="max_tokens")])
    with pytest.raises(concepts.ConceptsError, match="truncated"):
        generate(PATTERNS, SEGMENTS, n=2, client=client)


def test_a_short_batch_raises_and_says_how_short():
    client = StubClient([reply(9)])
    with pytest.raises(concepts.ConceptsError) as caught:
        generate(PATTERNS, SEGMENTS, n=12, client=client)
    assert "9" in str(caught.value) and "12" in str(caught.value)


def test_a_long_batch_raises_too():
    """Thirteen for twelve is not generosity: the extra one was not asked for
    and the ids would no longer say which twelve were."""
    client = StubClient([reply(13)])
    with pytest.raises(concepts.ConceptsError, match="13"):
        generate(PATTERNS, SEGMENTS, n=12, client=client)


def test_an_unparseable_reply_raises():
    client = StubClient([text_reply("Here are some ideas, in prose.")])
    with pytest.raises(concepts.ConceptsError, match="could not parse"):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


def test_an_empty_reply_raises():
    client = StubClient([text_reply("")])
    with pytest.raises(concepts.ConceptsError, match="could not parse"):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


def test_a_reply_without_a_concepts_list_raises():
    client = StubClient([json_reply({"ideas": []})])
    with pytest.raises(concepts.ConceptsError, match="ideas"):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


def test_a_refusal_raises_with_the_reason():
    client = StubClient([json_reply({"refuse": "every question is a judgement call"})])
    with pytest.raises(concepts.ConceptsError, match="judgement call"):
        generate(PATTERNS, SEGMENTS, n=1, client=client)


def test_the_object_is_found_after_leading_prose():
    text = "Sure - here you go:\n" + json.dumps({"concepts": [concept()]})
    client = StubClient([text_reply(text)])
    assert len(generate(PATTERNS, SEGMENTS, n=1, client=client)) == 1


def test_the_object_is_found_inside_a_code_fence():
    text = "```json\n" + json.dumps({"concepts": [concept()]}) + "\n```\n"
    client = StubClient([text_reply(text)])
    assert len(generate(PATTERNS, SEGMENTS, n=1, client=client)) == 1


# --- what reaches the prompt ----------------------------------------------


def test_the_prompt_carries_the_segment_context():
    client = StubClient([reply(2)])
    generate(PATTERNS, SEGMENTS, n=2, client=client)
    sent = client.sent(0)
    for expected in ("payroll-bureaus", "Payroll bureaus", "payslip", "tax-code",
                     "strongest lookup profile", "bookkeepers", "vat"):
        assert expected in sent, expected


def test_the_prompt_carries_the_patterns_with_their_evidence():
    """A concept should draw on a pattern because it worked, so the model has
    to see how long those ads ran and which ads they were."""
    client = StubClient([reply(2)])
    generate(PATTERNS, SEGMENTS, n=2, client=client)
    sent = client.sent(0)
    for expected in ("q01", "negative-flip", "fb-961046237012883", "q07",
                     "median_days_running", '"median_reach": 12000', "days:60-119"):
        assert expected in sent, expected


def test_the_prompt_explains_the_ad_and_what_the_patterns_measured():
    client = StubClient([reply(2)])
    generate(PATTERNS, SEGMENTS, n=2, client=client)
    sent = client.sent(0)
    for expected in ("primary text", "headline", "placement", "offer",
                     "See more", "kept paying to run for a long time",
                     "%d characters" % gate.LIMITS["headline"]):
        assert expected in sent, expected


def test_the_prompt_names_the_traps_that_kill_a_concept_downstream():
    """needs_numbers, the accuracy promise, the latency promise and an
    invented customer are all unrecoverable later."""
    client = StubClient([reply(2)])
    generate(PATTERNS, SEGMENTS, n=2, client=client)
    sent = client.sent(0)
    lowered = sent.lower()
    assert "needs_numbers" in sent
    assert "never promise accuracy" in lowered
    assert "never promise latency" in lowered
    assert "lookups, not judgement calls" in lowered
    assert "testimonial" in lowered
    assert '"refuse"' in sent


def test_the_prompt_asks_for_spread_across_segments_and_placements():
    client = StubClient([reply(2)])
    generate(PATTERNS, SEGMENTS, n=2, client=client)
    lowered = client.sent(0).lower()
    assert "across the segments" in lowered
    assert "across the placements" in lowered


def test_the_prompt_lists_the_gates_number_words_for_the_hook():
    """The list is the gate's own, not a remembered sample: "one", "half" and
    "twice" are what catch honest writing, and "dozen" is what a model tries."""
    client = StubClient([reply(2)])
    generate(PATTERNS, SEGMENTS, n=2, client=client)
    sent = client.sent(0)
    assert "out of the hook unless needs_numbers" in sent
    for word in gate.CARDINALS.split("|") + gate.MULTIPLIERS.split("|"):
        assert '"%s"' % word in sent, word


def test_the_prompt_lists_verified_offers_by_phrasing_and_names_the_rest_unavailable():
    client = StubClient([reply(2)])
    generate(PATTERNS, SEGMENTS, n=2, client=client)
    sent = client.sent(0)
    for offer in VERIFIED:
        assert offer in sent
    assert "See it on your own inbox" in sent
    assert "you keep the knowledge base" in sent
    assert "free_trial" in sent
    assert "NOT AVAILABLE" in sent
    # The evidence line is not model input: it cites the brief.
    assert "the brief:" not in sent


def test_the_prompt_is_pure_ascii():
    client = StubClient([reply(2)])
    generate(PATTERNS, SEGMENTS, n=2, client=client)
    assert client.sent(0).isascii()


def test_non_ascii_in_a_pattern_is_escaped_not_dropped():
    """A Danish example in a description reaches the model escaped, so the
    wire stays ASCII and the words still arrive."""
    rows = [dict(PATTERNS["patterns"][0], description='example: "Bruger du stadig timer på bogføring?"')]
    client = StubClient([reply(1)])
    generate({**PATTERNS, "patterns": rows}, SEGMENTS, n=1, client=client)
    sent = client.sent(0)
    assert sent.isascii()
    assert "\\u00e5 bogf\\u00f8ring" in sent


# --- the ICP brief is not model input -------------------------------------


@contextlib.contextmanager
def no_reads_under_docs():
    """Make any attempt to open a file under docs/ fail loudly, for the duration."""
    # Every binding that can open a file, not just the obvious two. Path.open
    # routes through io.open, which is a DIFFERENT object from builtins.open -
    # so a leak written as Path(brief).open().read() walks past a guard that
    # patches only builtins.open, and this guard exists to catch exactly the
    # leak nobody thought to write.
    import io

    real_builtins_open = builtins.open
    real_io_open = io.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_path_open = Path.open
    marker = os.sep + "docs" + os.sep

    def guard(target):
        text = str(target)
        if "ICP-BRIEF" in text or marker in text:
            raise AssertionError("a file under docs/ was opened: %s" % text)

    def opened(file, *args, **kwargs):
        guard(file)
        return real_io_open(file, *args, **kwargs)

    def read_text(self, *args, **kwargs):
        guard(self)
        return real_read_text(self, *args, **kwargs)

    def read_bytes(self, *args, **kwargs):
        guard(self)
        return real_read_bytes(self, *args, **kwargs)

    def path_open(self, *args, **kwargs):
        guard(self)
        return real_path_open(self, *args, **kwargs)

    builtins.open = opened
    io.open = opened
    Path.read_text = read_text
    Path.read_bytes = read_bytes
    Path.open = path_open
    try:
        yield
    finally:
        builtins.open = real_builtins_open
        io.open = real_io_open
        Path.read_text = real_read_text
        Path.read_bytes = real_read_bytes
        Path.open = real_path_open


def test_the_guard_below_is_not_vacuous():
    """Proves the next test would actually catch a read of the brief."""
    with pytest.raises(AssertionError, match="docs"):
        with no_reads_under_docs():
            BRIEF.read_text(encoding="utf-8")


def test_a_whole_run_opens_no_file_under_docs(tmp_path):
    """With the DEFAULT offers, so the one file this path does read -
    claims/evidence.json - is proven to be the only one."""
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps(PATTERNS), encoding="utf-8")
    client = StubClient([reply(3)])
    with no_reads_under_docs():
        result = concepts.generate(path, SEGMENTS, n=3, client=client)
    assert len(result) == 3


def test_no_substantial_line_of_the_brief_reaches_the_prompt():
    """The brief is a strategy document about a real market. The audience
    context a model may see is the segment's own trade, questions and note,
    and an offer's safe phrasing - never the evidence line that cites it."""
    lines = [ln.strip() for ln in BRIEF.read_text(encoding="utf-8").splitlines()]
    distinctive = [ln for ln in lines if len(ln) >= 40]
    assert len(distinctive) > 5, "the brief should hold substantial prose"

    client = StubClient([reply(3)])
    concepts.generate(PATTERNS, SEGMENTS, n=3, client=client)
    sent = client.sent(0)
    assert "ICP-BRIEF" not in sent
    for line in distinctive:
        assert line not in sent


def _non_docstring_strings(tree: ast.AST) -> list[str]:
    """Every string literal the module could hand to open(), which is every one
    that is not a docstring. Comments are not in the tree at all, so a comment
    mentioning the brief - as the module's own do - is correctly ignored."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is not None:
                docstrings.add(id(node.body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_the_module_holds_no_path_into_docs():
    """It may document that it does not read the brief - a docstring cannot be
    opened - but no literal it could pass to open() may name it, or its
    directory. Naming queue/backlog.md or claims/evidence.json in an error
    message is not the same thing: the segments arrive as objects and the
    offers arrive as a table, and neither file is opened here."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    for value in _non_docstring_strings(tree):
        assert "ICP" not in value, value
        assert "docs" not in value, value


# --- the transport ---------------------------------------------------------


def _imported_modules(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def test_the_model_is_reached_only_through_engine_model():
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = _imported_modules(tree)
    assert not any(m.split(".")[0] == "google" for m in modules), modules
    for forbidden in ("urllib", "http", "socket", "requests", "httpx", "ssl",
                      "subprocess"):
        assert not any(m.split(".")[0] == forbidden for m in modules), modules
    assert "anthropic" not in source.lower()
    assert "engine.model" in modules
    assert ".messages.create" not in source
    assert "content[0]" not in source


def test_a_missing_key_is_a_config_error_before_any_socket(no_sockets):
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        concepts.generate(PATTERNS, SEGMENTS, n=1, offers=OFFERS)


def test_a_stubbed_run_opens_no_socket(no_sockets, tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps(PATTERNS), encoding="utf-8")
    client = StubClient([reply(2)])
    assert len(concepts.generate(path, SEGMENTS, n=2, client=client)) == 2


# --- the patterns file -----------------------------------------------------


def test_the_pattern_keys_are_the_c5_contracts():
    assert concepts.PATTERN_KEYS == (
        "id", "kind", "device", "description", "evidence",
        "median_days_running", "median_reach", "n",
    )


def test_a_patterns_file_round_trips(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps(PATTERNS), encoding="utf-8")
    assert concepts.load_patterns(path) == PATTERNS


def test_a_missing_patterns_file_says_what_writes_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="learn step") as caught:
        concepts.load_patterns(tmp_path / "nothing.json")
    assert "python -m engine.learn" in str(caught.value)


def test_a_patterns_file_that_is_not_json_is_reported_apart(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text("<<<<<<< HEAD\n", encoding="utf-8")
    with pytest.raises(concepts.PatternsInvalid, match="not valid JSON"):
        concepts.load_patterns(path)


def test_an_unknown_patterns_schema_is_refused(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps({**PATTERNS, "schema": 2}), encoding="utf-8")
    with pytest.raises(concepts.PatternsInvalid, match="schema"):
        concepts.load_patterns(path)


def test_a_patterns_document_that_is_not_an_object_is_refused():
    with pytest.raises(concepts.PatternsInvalid, match="JSON object"):
        concepts.validate_patterns([PATTERNS])


def test_a_patterns_list_that_is_not_a_list_is_refused():
    with pytest.raises(concepts.PatternsInvalid, match="'patterns' must be a list"):
        concepts.validate_patterns({**PATTERNS, "patterns": {"q01": {}}})


@pytest.mark.parametrize("key", concepts.PATTERN_KEYS)
def test_a_pattern_missing_a_contract_key_is_refused(key):
    row = {k: v for k, v in PATTERNS["patterns"][0].items() if k != key}
    with pytest.raises(concepts.PatternsInvalid, match=key):
        concepts.validate_patterns({**PATTERNS, "patterns": [row]})


def test_a_reel_engine_patterns_file_is_refused_by_its_keys():
    """The sibling's file carries median_views; the ads file carries
    median_days_running and median_reach. The wrong file is named, not read."""
    row = {**PATTERNS["patterns"][0]}
    del row["median_days_running"], row["median_reach"]
    row["median_views"] = 412000
    with pytest.raises(concepts.PatternsInvalid, match="median_days_running"):
        concepts.validate_patterns({**PATTERNS, "patterns": [row]})


def test_a_pattern_with_a_blank_id_is_refused():
    rows = [{**PATTERNS["patterns"][0], "id": "  "}]
    with pytest.raises(concepts.PatternsInvalid, match="expected a name"):
        concepts.validate_patterns({**PATTERNS, "patterns": rows})


def test_a_pattern_whose_evidence_is_not_a_list_is_refused():
    rows = [{**PATTERNS["patterns"][0], "evidence": "fb-1"}]
    with pytest.raises(concepts.PatternsInvalid, match="evidence"):
        concepts.validate_patterns({**PATTERNS, "patterns": rows})


def test_duplicate_pattern_ids_are_refused():
    """A concept citing that id would trace to two things, which is neither."""
    rows = PATTERNS["patterns"] + [dict(PATTERNS["patterns"][0])]
    with pytest.raises(concepts.PatternsInvalid, match="q01"):
        concepts.validate_patterns({**PATTERNS, "patterns": rows})


def test_an_unlisted_pattern_kind_is_allowed():
    """A tenth kind the learn step finds must not be rejected by the module
    that consumes it: a concept cites an id, not a kind."""
    rows = [{**PATTERNS["patterns"][0], "kind": "onscreen-text"}]
    assert concepts.validate_patterns({**PATTERNS, "patterns": rows}) == rows


def test_a_patterns_document_with_no_patterns_cannot_produce_concepts():
    client = StubClient([reply(1)])
    with pytest.raises(concepts.PatternsInvalid, match="learn step"):
        generate({**PATTERNS, "patterns": []}, SEGMENTS, n=1, client=client)
    assert client.calls == []


def test_generate_accepts_a_path_to_the_patterns_file(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps(PATTERNS), encoding="utf-8")
    client = StubClient([reply(2)])
    assert len(generate(path, SEGMENTS, n=2, client=client)) == 2


def _corpus_record(rid, *, days_running, reach):
    """A C1 record, the C1 example of tests/test_corpus.py with two knobs.
    Copied rather than imported: each suite pins its own contract."""
    hook = "Bruger du stadig timer på bogføring hver uge?"
    return {
        "schema": 1,
        "id": rid,
        "platform": "meta-ad",
        "url": f"https://www.facebook.com/ads/library/?id={rid}",
        "channel": "Balance - Your AI Powered Accountants",
        "origin": "icp-adjacent",
        "fetched_at": "2026-09-14T00:00:00Z",
        "metrics": {
            "eu_total_reach": reach, "days_running": days_running, "active": True,
            "variants": 3, "page_id": "1007614045762121",
            "publisher_platforms": ["facebook", "instagram"],
            "languages": ["da"], "countries": ["DK"],
        },
        "analysis": {
            "copy": {
                "primary_text": hook + " Vi gør dit regnskab bedre og billigere.",
                "headline": "Se om vi kan gøre dit regnskab bedre",
                "description": "AI-drevet bogholderi til små virksomheder",
                "link_caption": "balance.dk",
                "words": 48,
            },
            "hook": {"words": 9, "text": hook, "device": "question"},
            "structure": ["hook", "problem", "offer", "cta"],
            "offer": {"type": "guarantee", "text": "Ingen betaling hvis ikke tilfreds"},
            "proof": {"type": "none", "text": ""},
            "cta": {"type": "learn-more", "text": "Se om vi kan gøre dit regnskab bedre"},
            "objections": ["we already have an accountant"],
            "creative": {"kind": "text-only"},
            "outlier_ratio": 2.4,
        },
        "model": "gemini-3.6-flash",
    }


def test_a_document_the_learn_step_writes_validates_here_and_is_cited(tmp_path):
    """The two halves of C5 in one test: engine.learn builds a real document
    from two corpus records, this module reads it from disk, its ids are
    q-ids, and a concept can cite one of them."""
    records = [
        _corpus_record("fb-1", days_running=90, reach=12000),
        _corpus_record("fb-2", days_running=60, reach=9000),
    ]
    document = learn.build(records)
    path = learn.write(document, tmp_path / "patterns.json")

    rows = concepts.load_patterns(path)["patterns"]
    assert rows, "two identical ads should support at least one pattern"
    assert rows == concepts.validate_patterns(document)
    for row in rows:
        assert row["id"].startswith("q")
        assert tuple(row) == tuple(sorted(concepts.PATTERN_KEYS))

    cited = rows[0]["id"]
    client = StubClient([reply(1, concepts_written=[concept(pattern_ids=[cited])])])
    record = generate(path, SEGMENTS, n=1, client=client)[0]
    assert record["pattern_ids"] == [cited]
    assert cited in client.sent(0)


def test_an_empty_backlog_is_refused_before_a_call_is_spent():
    client = StubClient([reply(1)])
    with pytest.raises(concepts.ConceptsError, match="backlog"):
        generate(PATTERNS, [], n=1, client=client)
    assert client.calls == []


def test_swapped_arguments_say_so():
    """Both arguments are collections, so the default error would send the
    reader to the wrong file."""
    client = StubClient([reply(1)])
    with pytest.raises(concepts.ConceptsError, match="generate\\(patterns, segments\\)"):
        generate(SEGMENTS, PATTERNS, n=1, client=client)
    assert client.calls == []


def test_a_patterns_document_in_the_segments_slot_is_caught_on_its_own():
    """Even when the first argument is not obviously a backlog."""
    client = StubClient([reply(1)])
    with pytest.raises(concepts.ConceptsError, match="generate\\(patterns, segments\\)"):
        generate({**PATTERNS, "patterns": []}, PATTERNS, n=1, client=client)
    assert client.calls == []


def test_the_shipped_backlog_is_an_audience_this_module_can_write_for():
    """queue/backlog.md loads, and every one of its ids is quoted back
    verbatim in the prompt - the model has to spell them exactly."""
    from engine import backlog

    segments = backlog.load()
    assert segments
    client = StubClient([reply(1, concepts_written=[concept(segment=segments[0].id)])])
    record = generate(PATTERNS, segments, n=1, client=client)[0]
    assert record["segment"] == segments[0].id
    sent = client.sent(0)
    for segment in segments:
        assert "[%s] %s" % (segment.id, segment.trade) in sent
