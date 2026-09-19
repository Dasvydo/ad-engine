"""engine/write.py: segment + selected concept -> one C3 ad job.

Every test is offline. The model is tests/stubs.py's StubClient, whose replies
lead with a thinking block; no test needs a key, and a fixture makes every
socket explode where the path could reach model.client().

What is pinned here, and why:

- ONE call, to model.MODEL_WRITE, with MAX_TOKENS_WRITE, one user message.
- The job carries every C3 key in gate.JOB_KEYS order, passes
  gate.structural(), and survives gate.run() written to disk - the writer and
  the gate are two halves of one contract, and the stub reply is built from
  the worked example the gate's own tests run over.
- da/lt are the placeholder; the model's English is copied verbatim.
- The prompt carries the segment, the limits, the cta enum, the full number
  word list with the write-arounds, every refused construction's advice, the
  verified claims' phrasings and the offer's - and NOT an unverified claim's
  note, NOT an offer's evidence line, NOT a line of the ICP brief.
- The hook is in the prompt when attestation-free and WITHHELD when it
  carries "10" or "ten"; an attested hook is carried through under the same
  field name and hashing the reel build uses.
- The feedback block lands after the concept block.
- A refusal, a truncation, an unreadable reply and a missing or mistyped
  authored key each raise a ValueError naming it.
- The placement decides creative_source; reel_selection() is a document the
  sibling's load_selection accepts, with its three checks replicated here.
"""
from __future__ import annotations

import ast
import builtins
import contextlib
import copy
import json
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine import gate, model, write
from engine.backlog import Segment
from tests.stubs import StubClient, json_reply, text_reply

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "engine" / "write.py"
EXAMPLE = ROOT / "creative" / "example-job.json"
BRIEF = ROOT / "docs" / "ICP-BRIEF.md"

SEGMENT = Segment(
    rank=2, id="payroll-bureaus", trade="Payroll bureaus",
    questions=("payslip query", "holiday pay", "tax card"), note="untested",
)

NOW = "2026-09-22T09:03:00Z"

CONCEPT = {
    "id": "a01",
    "segment": "payroll-bureaus",
    "angle": "a knowledge base answers the payslip mail nobody wants to retype",
    "hook": "The payslip request lands again, and the answer has not changed.",
    "pattern_ids": ["q03"],
    "placement": "reels-9x16",
    "offer": "guarantee",
    "needs_numbers": False,
}

PATTERN = {
    "id": "q03",
    "kind": "hook",
    "device": "negative-flip",
    "description": 'opening device "negative-flip"; median hook 9.0 words',
    "evidence": ["fb-1", "fb-2"],
    "median_days_running": 74,
    "median_reach": 12000,
    "n": 2,
}


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def payload(**overrides) -> dict:
    """A model reply shaped like the real thing: exactly AUTHORED, in English,
    taken from the worked example the gate's own tests run over - so a job
    built from it is one the gate is known to pass."""
    job = example()
    out = {}
    for key in write.AUTHORED:
        value = job[key]
        out[key] = value["en"] if isinstance(value, dict) else value
    out.update(overrides)
    return out


def reply(**overrides):
    return json_reply(payload(**overrides))


def generate(*, client=None, **kwargs) -> dict:
    """generate() over SEGMENT with a one-reply stub and a pinned clock."""
    kwargs.setdefault("now", NOW)
    client = client or StubClient([reply()])
    return write.generate(SEGMENT, client=client, **kwargs)


def sent(client) -> str:
    return client.sent(0)


def prose(text: str) -> str:
    """Whitespace folded and lower-cased, for asserting on hard-wrapped text."""
    return " ".join(text.split()).lower()


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    """No test here has a key, and none may need one."""
    for name in model.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def no_sockets(monkeypatch):
    def exploding(*args, **kwargs):
        raise AssertionError("the write path opened a socket")

    monkeypatch.setattr(socket, "socket", exploding)
    monkeypatch.setattr(socket, "create_connection", exploding)


# --- one call, the contract's model and budget ----------------------------


def test_the_writer_is_the_writing_model_not_the_judge():
    assert write.MODEL_WRITE == model.MODEL_WRITE
    assert write.MODEL_WRITE != model.MODEL_FLASH
    assert write.MAX_TOKENS_WRITE == 8000
    assert write.AUTHORED == ("primary_text", "headline", "description", "cta", "hypothesis")


def test_one_call_with_one_user_message(no_sockets):
    client = StubClient([reply()])
    generate(client=client, concept=CONCEPT, patterns=[PATTERN], feedback=["x"])
    assert len(client.calls) == 1
    assert client.remaining == 0
    call = client.calls[0]
    assert call["model"] == "gemini-3.6-flash"
    assert call["max_tokens"] == write.MAX_TOKENS_WRITE
    assert [m["role"] for m in call["messages"]] == ["user"]
    assert client.media(0) == []


def test_a_missing_key_is_a_config_error_before_any_socket(no_sockets):
    with pytest.raises(model.ConfigError, match="GEMINI_API_KEY"):
        write.generate(SEGMENT, now=NOW)


# --- the job ---------------------------------------------------------------


def test_the_job_carries_every_c3_key_in_the_gates_order():
    job = generate(concept=CONCEPT, patterns=[PATTERN])
    assert list(job) == list(gate.JOB_KEYS)


def test_the_job_passes_the_structural_gate():
    job = generate(concept=CONCEPT, patterns=[PATTERN])
    result = gate.structural(job)
    assert result.ok, result.failures


def test_the_job_written_to_disk_passes_the_whole_gate(tmp_path):
    """The round trip: the file propose writes, read by gate.run, both layers.
    The editorial verdict is stubbed; the structural layer is real."""
    job = generate(concept=CONCEPT, patterns=[PATTERN])
    path = tmp_path / "payroll-bureaus.json"
    path.write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    judge = StubClient([json_reply({"pass": True, "failures": []})])
    result = gate.run(path, client=judge)
    assert result.ok, result.failures
    assert result.layer == "editorial"
    assert judge.remaining == 0
    assert json.loads(path.read_text(encoding="utf-8")) == job
    assert list(json.loads(path.read_text(encoding="utf-8"))) == list(gate.JOB_KEYS)


def test_the_english_is_the_models_and_da_lt_are_the_placeholder():
    given = payload()
    job = generate(client=StubClient([json_reply(given)]))
    for name in gate.SPOKEN_FIELDS:
        assert job[name] == {
            "en": given[name],
            "da": gate.NATIVE_PLACEHOLDER,
            "lt": gate.NATIVE_PLACEHOLDER,
        }
    assert job["cta"] == given["cta"]
    assert job["hypothesis"] == given["hypothesis"]


def test_everything_else_is_stamped_from_the_concept_and_the_clock():
    job = generate(concept=CONCEPT, patterns=[PATTERN])
    assert job["id"] == "payroll-bureaus"
    assert job["segment"] == "payroll-bureaus"
    assert job["concept_id"] == "a01"
    assert job["pattern_ids"] == ["q03"]
    assert job["pattern_ids"] is not CONCEPT["pattern_ids"], "a fresh list, not the concept's"
    assert job["placement"] == "reels-9x16"
    assert job["offer"] == "guarantee"
    assert job["destination"] == "https://doviloop.dev"
    assert job["proposed_at"] == NOW
    assert job["ads"] == {}
    assert job["launched_at"] is None


def test_no_concept_writes_from_the_segment_alone():
    """generate(segment) is the whole entry point when nothing was selected:
    no concept id, no patterns, the default placement, no offer."""
    job = generate()
    assert job["concept_id"] is None
    assert job["pattern_ids"] == []
    assert job["placement"] == write.DEFAULT_PLACEMENT == "reels-9x16"
    assert job["offer"] == "none"
    assert gate.structural(job).ok


def test_the_concept_handed_in_is_not_mutated():
    concept = copy.deepcopy(CONCEPT)
    generate(concept=concept, patterns=[PATTERN])
    assert concept == CONCEPT


@pytest.mark.parametrize("placement, kind, template", [
    ("reels-9x16", "reel", "reel-c"),
    ("feed-4x5", "reel", "reel-b"),
    ("static-1x1", "still", "reel-c"),
])
def test_the_placement_decides_the_creative_source(placement, kind, template):
    job = generate(concept=dict(CONCEPT, placement=placement))
    assert job["placement"] == placement
    assert job["creative_source"] == {
        "kind": kind,
        "repo": "reel-engine",
        "template": template,
        "selection": "queue/proposed/payroll-bureaus.reel.json",
    }
    assert job["creative_source"]["kind"] in gate.CREATIVE_KINDS
    assert gate.structural(job).ok


def test_every_placement_the_gate_knows_has_a_creative_a_note_and_a_format():
    assert set(write.CREATIVE_BY_PLACEMENT) == set(gate.PLACEMENTS)
    assert set(write.PLACEMENT_NOTES) == set(gate.PLACEMENTS)
    assert set(write.FORMAT_BY_PLACEMENT) == set(gate.PLACEMENTS)
    for placement in gate.PLACEMENTS:
        assert write.creative_source(placement, "x")["kind"] in gate.CREATIVE_KINDS


def test_an_explicit_placement_wins_over_the_concepts():
    """An operator naming a placement is a decision, not a preference - the
    same rule the sibling's --template follows."""
    job = generate(concept=CONCEPT, placement="static-1x1")
    assert job["placement"] == "static-1x1"
    assert job["creative_source"]["kind"] == "still"


def test_placement_falls_back_to_the_concepts_then_the_default():
    assert generate(concept=dict(CONCEPT, placement="feed-4x5"))["placement"] == "feed-4x5"
    assert generate(concept=CONCEPT, placement="")["placement"] == "reels-9x16"
    assert generate()["placement"] == "reels-9x16"


def test_an_unknown_placement_is_refused_before_any_call():
    client = StubClient()
    with pytest.raises(ValueError, match="story-9x16"):
        generate(client=client, placement="story-9x16")
    with pytest.raises(ValueError, match="square"):
        generate(client=client, concept=dict(CONCEPT, placement="square"))
    assert client.calls == []


def test_the_prompt_names_the_placement_the_job_is_stamped_with():
    client = StubClient([reply()])
    generate(client=client, concept=CONCEPT, placement="feed-4x5")
    assert "THIS AD RUNS AS feed-4x5" in sent(client)
    assert write.PLACEMENT_NOTES["feed-4x5"] in sent(client)


# --- the prompt ------------------------------------------------------------


def test_the_prompt_carries_the_segment_and_asks_for_lookups():
    client = StubClient([reply()])
    generate(client=client)
    text = sent(client)
    assert "Payroll bureaus" in text
    assert "payslip query, holiday pay, tax card" in text
    assert "untested" in text
    assert "lookup" in text.lower()
    assert '{"refuse": "one sentence saying why"}' in text


def test_the_prompt_asks_for_exactly_the_authored_keys_in_english():
    client = StubClient([reply()])
    generate(client=client)
    text = sent(client)
    asked = text.split("Return ONLY a JSON object with exactly these keys:")[1].split("\n")[0]
    for key in write.AUTHORED:
        assert key in asked, key
    assert "English only" in text
    assert gate.NATIVE_PLACEHOLDER not in text, "the placeholder is stamped, never asked for"


def test_the_prompt_carries_the_limits_and_the_cta_enum():
    client = StubClient([reply()])
    generate(client=client)
    text = sent(client)
    for name, limit in gate.LIMITS.items():
        assert "%s at most %d" % (name, limit) in text, name
    assert ", ".join(gate.CTA_TYPES) in text


def test_the_prompt_names_every_banned_number_word():
    """gate.NUM_RE bans "one", "dozen", "twice" and "half" too, and an honest
    pronoun hard-fails the gate with no retry. The prompt lists what the
    regex matches, rendered from the same constants."""
    client = StubClient([reply()])
    generate(client=client)
    text = sent(client)
    for word in gate.CARDINALS.split("|") + gate.MULTIPLIERS.split("|"):
        assert '"%s"' % word in text, word
    assert "nobody" in text          # the offered rewrite of "no one"
    assert "a click" in text         # the offered rewrite of "one click"
    assert "Microsoft 365" in text   # the product's own trap: the digits count


def test_the_prompt_renders_every_refused_construction_from_the_gate():
    """Rendered from gate.REFUSED_CONSTRUCTIONS, not retyped: a construction
    added to the machine-checked list reaches the writer's brief with no
    second edit."""
    client = StubClient([reply()])
    generate(client=client)
    text = sent(client)
    for _, why in gate.REFUSED_CONSTRUCTIONS:
        assert why in text, why
    assert write.refused_block().count("\n") == len(gate.REFUSED_CONSTRUCTIONS) - 1


def test_the_prompt_carries_the_verified_claims_and_only_those():
    """The product facts are a table. Every verified claim's safe phrasings
    are the vocabulary; an unverified claim's note is advice to the operator
    and its figure must never be shown to the writer."""
    document = json.loads(gate.EVIDENCE.read_text(encoding="utf-8"))
    client = StubClient([reply()])
    generate(client=client)
    text = sent(client)
    verified = {k: v for k, v in document["claims"].items() if v["status"] == "verified"}
    assert len(verified) >= 3
    for entry in verified.values():
        for phrase in entry["safe_phrasings"]:
            assert phrase in text, phrase
    for key, entry in document["claims"].items():
        if entry["status"] != "verified":
            assert entry["evidence"] not in text, key
            assert entry.get("note", "never") not in text, key
    assert "10 hours" not in text


def test_verified_claims_reads_the_table_by_status_and_skips_documentation():
    document = {"claims": {
        "_note": "prose",
        "a": {"status": "verified", "safe_phrasings": ["Say this", " and this "]},
        "b": {"status": "UNVERIFIED", "safe_phrasings": ["never this"]},
        "c": {"status": "verified", "safe_phrasings": []},
        "d": "not an object",
    }}
    assert write.verified_claims(document) == {"a": ["Say this", "and this"]}
    assert write.verified_claims({}) == {}
    committed = write.verified_claims()
    assert set(committed) == {"never_auto_sends", "stays_in_outlook", "eu_hosted",
                              "own_knowledge_base", "per_person_voice"}


def test_the_prompt_carries_the_offers_phrasing_but_not_its_evidence_line():
    offers = gate.load_offers()
    client = StubClient([reply()])
    generate(client=client, concept=CONCEPT)
    text = sent(client)
    assert "THE OFFER is guarantee." in text
    for phrase in offers["guarantee"]["safe_phrasings"]:
        assert phrase in text
    assert offers["guarantee"]["evidence"] not in text
    assert "Make no other offer" in text
    for other in ("design_partner", "demo"):
        for phrase in offers[other]["safe_phrasings"]:
            assert phrase not in text, "another offer's phrasing reached the writer"


def test_no_offer_tells_the_writer_to_make_none():
    client = StubClient([reply()])
    generate(client=client)
    text = sent(client)
    assert "THE OFFER is none." in text
    assert "Make no offer at all" in text


def test_the_prompt_carries_the_worked_examples_english_fields_only():
    job = example()
    client = StubClient([reply()])
    generate(client=client)
    text = sent(client)
    assert "WORKED EXAMPLE" in text
    for key in write.AUTHORED:
        value = job[key]
        value = value["en"] if isinstance(value, dict) else value
        assert json.dumps(value) in text, key
    assert gate.NATIVE_PLACEHOLDER not in text
    assert '"creative_source"' not in text
    assert '"proposed_at"' not in text
    rendered = json.loads(write.example_block())
    assert list(rendered) == list(write.AUTHORED)


def test_the_worked_example_is_a_trade_off_the_backlog():
    """So it can never be mistaken for a live draft, and so its words are a
    shape to match rather than copy."""
    from engine import backlog
    assert example()["segment"] not in {s.id for s in backlog.load()}


def test_the_prompt_and_the_rubric_say_the_same_thing():
    """One string, both ends: the writer is told what the editorial gate will
    judge it by, in the gate's own words."""
    client = StubClient([reply()])
    generate(client=client)
    text = sent(client)
    prompt = prose(text)
    rubric = prose(gate.RUBRIC)
    for phrase in (
        "names a moment",
        "generic complaint about email, busyness or admin",
        "no customers, no logos, no testimonials and no measured outcome",
        "carry that one thing and nothing else",
    ):
        assert phrase in prompt, phrase
        assert phrase in rubric, phrase


# --- the concept block -----------------------------------------------------


def test_a_selected_concept_puts_its_angle_placement_offer_and_hook_in_the_prompt():
    """The point of the whole research chain: the ad that gets written is the
    one the run selected, not a fresh guess at the same segment."""
    client = StubClient([reply()])
    generate(client=client, concept=CONCEPT, patterns=[PATTERN])
    text = sent(client)
    assert write.CONCEPT_HEADER in text
    assert CONCEPT["angle"] in text
    assert CONCEPT["hook"] in text
    assert "placement: reels-9x16" in text
    assert "offer:     guarantee" in text
    assert "concept:   a01" in text
    assert "Open with that hook, in those words" in text


def test_the_pattern_evidence_behind_the_hook_reaches_the_prompt():
    """A hook with no measurements under it is indistinguishable from a hook
    somebody made up - and the figures are said to be not copy material."""
    client = StubClient([reply()])
    generate(client=client, concept=CONCEPT, patterns=[PATTERN])
    text = sent(client)
    for fragment in ("q03", "negative-flip", "fb-1", "fb-2", "74", "12000"):
        assert fragment in text, fragment
    assert write.PATTERN_HEADER in text
    assert "NOT material for the copy" in text
    assert "median_days_running" in text


def test_no_concept_leaves_the_prompt_exactly_as_it_was():
    """The concept block is appended, so the plain prompt is a prefix of it -
    for a concept that stamps the same offer and placement the plain path
    stamps; a concept's offer and placement legitimately reach the
    instruction above the block, and a test that ignored that would pass
    only by accident."""
    plain = StubClient([reply()])
    generate(client=plain)
    same_frame = dict(CONCEPT, offer="none", placement=write.DEFAULT_PLACEMENT)
    with_concept = StubClient([reply()])
    generate(client=with_concept, concept=same_frame, patterns=[PATTERN])
    assert write.CONCEPT_HEADER not in sent(plain)
    assert sent(with_concept).startswith(sent(plain))
    # And the offer block is the only thing a guarantee concept changes above
    # it: everything before "THE OFFER is" and everything from "HARD
    # FAILURES." to the concept header is byte-identical to the plain prompt.
    guarantee = StubClient([reply()])
    generate(client=guarantee, concept=CONCEPT, patterns=[PATTERN])
    head = sent(guarantee).split(write.CONCEPT_HEADER)[0]
    assert "THE OFFER is guarantee." in head and "THE OFFER is none." in sent(plain)
    assert head.split("THE OFFER is")[0] == sent(plain).split("THE OFFER is")[0]
    # rstrip: concept_block opens with a blank line, so the head carries one
    # more trailing newline than a prompt with no block at all.
    assert head.split("HARD FAILURES.")[1].rstrip() == sent(plain).split("HARD FAILURES.")[1].rstrip()


def test_a_concept_with_no_patterns_still_writes_its_ad():
    """Pattern evidence is the strong case, not a precondition."""
    client = StubClient([reply()])
    job = generate(client=client, concept=CONCEPT)
    assert job["headline"]["en"]
    assert CONCEPT["hook"] in sent(client)
    assert write.PATTERN_HEADER not in sent(client)


def test_concept_block_is_pure():
    """No client, no clock, no repo state beyond the attestations: the same
    inputs give the same lines, and the concept is untouched."""
    concept = copy.deepcopy(CONCEPT)
    first = write.concept_block(concept, [PATTERN])
    second = write.concept_block(concept, [PATTERN])
    assert first == second
    assert concept == CONCEPT
    assert first.startswith("\n" + write.CONCEPT_HEADER)
    assert first.endswith("\n")
    assert write.concept_block(concept, None) == write.concept_block(concept, [])


@pytest.mark.parametrize("hook", [
    "Payroll bureaus lose 10 hours a week retyping the same payslip answer.",
    "Payroll bureaus lose ten hours a week retyping the same payslip answer.",
])
def test_an_unattested_number_never_reaches_the_prompt_through_a_concept(monkeypatch, hook):
    """The concept path must not become the route an unattested figure takes
    into the copy. The hook is WITHHELD rather than softened: a model cannot
    copy a number it was never shown, and the gate downstream is then the
    second defence rather than the only one. Digits and number words both,
    because gate.NUM_RE matches both."""
    monkeypatch.setattr(gate, "load_attestations", dict)
    client = StubClient([reply()])
    generate(client=client, concept=dict(CONCEPT, hook=hook), patterns=[PATTERN])
    text = sent(client)
    assert hook not in text
    assert "lose 10 hours" not in text
    assert "lose ten hours" not in text
    assert "WITHHELD" in text
    assert "claims/evidence.json" in text
    # The rest of the decision still survives - only the figure is dropped.
    assert CONCEPT["angle"] in text
    assert "Open with that hook" not in text


def test_the_withheld_hook_names_the_figure_for_the_operator(monkeypatch):
    monkeypatch.setattr(gate, "load_attestations", dict)
    block = write.concept_block(dict(CONCEPT, hook="Half the payslip mail is the same question."))
    assert "WITHHELD" in block
    assert "'Half'" in block
    assert "Half the payslip mail" not in block


def test_an_attested_hook_number_is_carried_through(monkeypatch):
    """Same field name, same hashing, same file as the gate and the reel build:
    a hook attested for reel-engine's build passes here, so attesting a figure
    is not pointless."""
    hook = "Payroll bureaus lose 10 hours a week retyping the same answer."
    key = gate.evidence_key("hook", hook)
    monkeypatch.setattr(gate, "load_attestations", lambda: {key: {"kind": "measured"}})
    client = StubClient([reply()])
    generate(client=client, concept=dict(CONCEPT, hook=hook), patterns=[PATTERN])
    assert hook in sent(client)
    assert "WITHHELD" not in sent(client)


def test_an_attestation_under_another_field_does_not_attest_the_hook(monkeypatch):
    """The key is "hook", not "primary_text.en": the same figure in the written
    primary text needs its own attestation at the gate."""
    hook = "Payroll bureaus lose 10 hours a week retyping the same answer."
    wrong = gate.evidence_key("primary_text.en", hook)
    monkeypatch.setattr(gate, "load_attestations", lambda: {wrong: {"kind": "measured"}})
    assert "WITHHELD" in write.concept_block(dict(CONCEPT, hook=hook))


def test_needs_numbers_is_told_to_argue_without_counting():
    client = StubClient([reply()])
    generate(client=client, concept=dict(CONCEPT, needs_numbers=True), patterns=[PATTERN])
    text = sent(client)
    assert "needs_numbers" in text
    assert "without counting" in text
    plain = StubClient([reply()])
    generate(client=plain, concept=CONCEPT)
    assert "without counting" not in sent(plain)


# --- feedback --------------------------------------------------------------


def test_feedback_from_a_failed_gate_reaches_the_prompt():
    """A rewrite must not be a blind re-roll of a byte-identical prompt."""
    client = StubClient([reply()])
    generate(client=client, feedback=["hook is a generic complaint", "argues two things"])
    text = sent(client)
    assert write.FEEDBACK_HEADER in text
    assert "hook is a generic complaint" in text
    assert "argues two things" in text


def test_no_feedback_leaves_the_prompt_alone():
    client = StubClient([reply()])
    generate(client=client, feedback=[])
    assert write.FEEDBACK_HEADER not in sent(client)


def test_feedback_lands_after_the_concept_block():
    """The reasons a draft was rejected stay closest to the answer."""
    client = StubClient([reply()])
    generate(client=client, concept=CONCEPT, patterns=[PATTERN], feedback=["argues two things"])
    text = sent(client)
    assert text.index(write.CONCEPT_HEADER) < text.index(write.PATTERN_HEADER)
    assert text.index(write.PATTERN_HEADER) < text.index(write.FEEDBACK_HEADER)
    assert text.rstrip().endswith("argues two things")


def test_a_multi_line_failure_stays_one_bullet():
    client = StubClient([reply()])
    generate(client=client, feedback=["headline.en contains '40'.\n    text: forty\n    add: x"])
    text = sent(client)
    assert "  - headline.en contains '40'.\n        text: forty" in text


# --- the reply -------------------------------------------------------------


def test_a_refusal_raises_with_the_reason():
    """The honest-refusal path: the model's sentence must reach the operator."""
    client = StubClient([json_reply({"refuse": "these three questions are judgement calls"})])
    with pytest.raises(ValueError, match="these three questions are judgement calls"):
        generate(client=client)


def test_a_truncated_response_raises():
    client = StubClient([json_reply(payload(), stop_reason="max_tokens")])
    with pytest.raises(ValueError, match="truncated"):
        generate(client=client)


def test_unparseable_model_output_raises():
    with pytest.raises(ValueError, match="could not parse"):
        generate(client=StubClient([text_reply("I am not JSON.")]))
    with pytest.raises(ValueError, match="could not parse"):
        generate(client=StubClient([text_reply('["a", "list"]')]))


def test_the_authored_json_is_read_past_the_thinking_block():
    """The JSON is not content[0]; a thinking block is."""
    job = generate()
    assert job["headline"]["en"] == example()["headline"]["en"]


def test_json_in_a_code_fence_is_read():
    fenced = "```json\n%s\n```" % json.dumps(payload())
    job = generate(client=StubClient([text_reply(fenced)]))
    assert job["headline"]["en"] == example()["headline"]["en"]


def test_a_missing_authored_field_raises_naming_it():
    given = payload()
    del given["hypothesis"]
    with pytest.raises(ValueError, match="hypothesis"):
        generate(client=StubClient([json_reply(given)]))


def test_every_missing_field_is_named_at_once():
    given = payload()
    del given["headline"]
    del given["description"]
    with pytest.raises(ValueError, match="headline, description"):
        generate(client=StubClient([json_reply(given)]))


def test_a_language_map_where_a_string_was_asked_for_is_refused_by_name():
    """The model does not get to declare copy native: a {en, da, lt} map in
    the reply is a field it was told not to write."""
    given = payload(headline={"en": "x", "da": "y", "lt": "z"})
    with pytest.raises(ValueError, match="headline is dict, not a string"):
        generate(client=StubClient([json_reply(given)]))


def test_a_blank_authored_field_is_refused():
    with pytest.raises(ValueError, match="description is blank"):
        generate(client=StubClient([json_reply(payload(description="   "))]))


def test_edge_whitespace_is_trimmed_and_the_cta_is_folded():
    """A trailing newline is not copy, and "Learn more" is LEARN_MORE by case
    and separator only - whether it is a button the gate knows stays the
    gate's call."""
    job = generate(client=StubClient([json_reply(payload(headline="  Proof of cover \n", cta="learn more"))]))
    assert job["headline"]["en"] == "Proof of cover"
    assert job["cta"] == "LEARN_MORE"
    bad = generate(client=StubClient([json_reply(payload(cta="Buy Now"))]))
    assert bad["cta"] == "BUY_NOW"
    assert any(f.startswith("cta 'BUY_NOW' is not one of") for f in gate.structural(bad).failures)


def test_fields_the_model_volunteers_are_dropped():
    given = payload()
    given.update({"id": "hacked", "da": "Dansk", "offer": "free_trial", "placement": "static-1x1"})
    job = generate(client=StubClient([json_reply(given)]), concept=CONCEPT)
    assert job["id"] == "payroll-bureaus"
    assert job["offer"] == "guarantee"
    assert job["placement"] == "reels-9x16"
    assert job["primary_text"]["da"] == gate.NATIVE_PLACEHOLDER
    assert "da" not in job


# --- refusals before the call ----------------------------------------------


def test_an_unverified_offer_is_refused_before_any_call():
    """free_trial is UNVERIFIED in claims/evidence.json; the gate would refuse
    the finished job for it, after the call was paid for."""
    client = StubClient()
    with pytest.raises(ValueError, match="free_trial.*UNVERIFIED") as exc:
        generate(client=client, concept=dict(CONCEPT, offer="free_trial"))
    assert "guarantee" in str(exc.value)
    assert client.calls == []


def test_an_unknown_offer_is_refused_naming_the_verified_ones():
    client = StubClient()
    with pytest.raises(ValueError, match="'discount' is not in claims/evidence.json"):
        generate(client=client, concept=dict(CONCEPT, offer="discount"))
    with pytest.raises(ValueError, match="not in claims/evidence.json"):
        generate(client=client, concept=dict(CONCEPT, offer=""))
    assert client.calls == []


def test_a_concept_for_another_segment_is_refused():
    """A concept for accountants written for bookkeepers is somebody else's ad."""
    client = StubClient()
    with pytest.raises(ValueError, match="'accountants', not 'payroll-bureaus'"):
        generate(client=client, concept=dict(CONCEPT, segment="accountants"))
    assert client.calls == []
    unnamed = dict(CONCEPT)
    del unnamed["segment"]
    assert generate(concept=unnamed)["concept_id"] == "a01"


def test_a_concept_with_no_id_is_refused():
    client = StubClient()
    for bad in (dict(CONCEPT, id=""), {k: v for k, v in CONCEPT.items() if k != "id"}, "a01", ["a01"]):
        with pytest.raises(ValueError):
            generate(client=client, concept=bad)
    assert client.calls == []


def test_a_segment_without_a_backlog_row_is_refused():
    client = StubClient()
    with pytest.raises(ValueError, match="needs a queue/backlog.md row"):
        write.generate("payroll-bureaus", client=client)
    with pytest.raises(ValueError, match="names no id"):
        write.generate(Segment(rank=1, id="", trade="x", questions=("a", "b", "c"), note=""), client=client)
    assert client.calls == []


# --- the clock -------------------------------------------------------------


def test_proposed_at_is_pinned_by_now_in_every_accepted_form():
    aware = datetime(2026, 9, 22, 11, 3, tzinfo=timezone(timedelta(hours=2)))
    assert generate(now=aware)["proposed_at"] == NOW
    assert generate(now=datetime(2026, 9, 22, 9, 3))["proposed_at"] == NOW
    assert generate(now="2026-09-22T09:03:00+00:00")["proposed_at"] == NOW
    assert generate(now="2026-09-22T11:03:00+02:00")["proposed_at"] == NOW


def test_now_none_reads_the_clock_in_utc():
    before = datetime.now(timezone.utc).replace(microsecond=0)
    stamped = write.generate(SEGMENT, client=StubClient([reply()]))["proposed_at"]
    after = datetime.now(timezone.utc)
    parsed = datetime.strptime(stamped, write.TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    assert before <= parsed <= after


def test_a_now_that_is_not_a_time_is_refused():
    with pytest.raises(TypeError, match="now must be"):
        generate(now=1700000000)


# --- the reel selection ----------------------------------------------------


def load_selection_like_the_sibling(document) -> list[dict]:
    """reel-engine/engine/script.py's load_selection, minus the file: an
    object carrying a `selected` list and a `concepts` list, every selected id
    present among the records, and at least one selected. Replicated rather
    than imported so this suite never needs the sibling checkout."""
    assert isinstance(document, dict), "must be a JSON object"
    chosen = document.get("selected")
    records = document.get("concepts")
    assert isinstance(chosen, list) and isinstance(records, list), (
        "must carry a 'selected' list of concept ids and a 'concepts' list")
    by_id = {r.get("id"): r for r in records if isinstance(r, dict)}
    selected = []
    for concept_id in chosen:
        assert concept_id in by_id, "selects %r but carries no concept with that id" % concept_id
        selected.append(by_id[concept_id])
    assert selected, "selected no concepts, so there is nothing to write"
    return selected


def test_reel_selection_is_a_document_the_sibling_accepts():
    document = write.reel_selection(CONCEPT, SEGMENT, now=NOW)
    assert document["schema"] == 1
    assert document["generated_at"] == NOW
    assert document["source"] == "ad-engine"
    assert document["selected"] == ["a01"]
    records = load_selection_like_the_sibling(document)
    assert len(records) == 1
    record = records[0]
    assert list(record) == ["id", "segment", "angle", "hook", "pattern_ids",
                            "format", "needs_numbers"]
    assert record["id"] == "a01"
    assert record["segment"] == "payroll-bureaus"
    assert record["angle"] == CONCEPT["angle"]
    assert record["hook"] == CONCEPT["hook"]
    assert record["pattern_ids"] == []
    assert record["format"] == "vertical reel, 9:16"
    assert record["needs_numbers"] is False


def test_reel_selection_leaves_this_repositorys_pattern_ids_out():
    """q-ids are citations into research/patterns.json HERE; the sibling would
    look them up in its own file, where they do not exist."""
    document = write.reel_selection(dict(CONCEPT, pattern_ids=["q03", "q07"]), SEGMENT, now=NOW)
    assert document["concepts"][0]["pattern_ids"] == []
    assert "q03" not in json.dumps(document)


@pytest.mark.parametrize("placement, words", [
    ("reels-9x16", "vertical reel, 9:16"),
    ("feed-4x5", "feed video, 4:5"),
    ("static-1x1", "still frame, 1:1"),
])
def test_the_placement_words_become_the_format(placement, words):
    document = write.reel_selection(dict(CONCEPT, placement=placement), SEGMENT, now=NOW)
    assert document["concepts"][0]["format"] == words


def test_the_format_words_stage_nothing_in_the_sibling():
    """reel-engine's resolver reads `format` for staging keywords; the aspect
    words must not accidentally pick reel-s or reel-d. The keyword lists are
    the sibling's, quoted here so the suite stays offline."""
    staging = ("inbox", "crawl", "scroll", "sent folder", "mailbox", "objection",
               "sceptic", "conversation", "dialogue", "chat", "thread", "reply",
               "split", "side by side", "before and after", "contrast", "comparison")
    for words in write.FORMAT_BY_PLACEMENT.values():
        for keyword in staging:
            assert keyword not in words.lower(), (words, keyword)


def test_reel_selection_takes_a_segment_or_its_id_and_pins_the_clock():
    by_row = write.reel_selection(CONCEPT, SEGMENT, now=NOW)
    by_id = write.reel_selection(CONCEPT, "payroll-bureaus", now=NOW)
    assert by_row == by_id
    aware = datetime(2026, 9, 22, 11, 3, tzinfo=timezone(timedelta(hours=2)))
    assert write.reel_selection(CONCEPT, SEGMENT, now=aware)["generated_at"] == NOW


def test_reel_selection_refuses_what_the_sibling_could_not_read():
    with pytest.raises(ValueError, match="needs_numbers"):
        write.reel_selection(dict(CONCEPT, needs_numbers="false"), SEGMENT, now=NOW)
    with pytest.raises(ValueError, match="needs_numbers"):
        write.reel_selection({k: v for k, v in CONCEPT.items() if k != "needs_numbers"}, SEGMENT, now=NOW)
    with pytest.raises(ValueError, match="names no id"):
        write.reel_selection(dict(CONCEPT, id=" "), SEGMENT, now=NOW)
    with pytest.raises(ValueError, match="'accountants', not 'payroll-bureaus'"):
        write.reel_selection(dict(CONCEPT, segment="accountants"), SEGMENT, now=NOW)
    with pytest.raises(ValueError, match="placement"):
        write.reel_selection(dict(CONCEPT, placement="square"), SEGMENT, now=NOW)


def test_the_selection_path_stamped_on_the_job_is_where_propose_writes_the_sidecar():
    job = generate(concept=CONCEPT)
    assert job["creative_source"]["selection"] == "queue/proposed/%s.reel.json" % job["segment"]
    assert write.SELECTION_PATH % "x" == "queue/proposed/x.reel.json"


# --- the ICP brief is not model input --------------------------------------


@contextlib.contextmanager
def no_reads_under_docs():
    """Make any attempt to open a file under docs/ fail loudly, for the duration.
    Every binding that can open a file, not just the obvious two: Path.open
    routes through io.open, a different object from builtins.open."""
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
    with pytest.raises(AssertionError, match="docs"):
        with no_reads_under_docs():
            BRIEF.read_text(encoding="utf-8")


def test_a_whole_run_opens_no_file_under_docs():
    """With the real evidence table and the real worked example, so the files
    this path does read are proven to be the only ones."""
    with no_reads_under_docs():
        job = generate(concept=CONCEPT, patterns=[PATTERN], feedback=["x"])
        write.reel_selection(CONCEPT, SEGMENT, now=NOW)
    assert job["id"] == "payroll-bureaus"


def test_no_line_of_the_brief_reaches_the_prompt():
    """A distinctive phrase, and then every substantial line: the audience
    context a model may see is the segment's own trade, questions and note,
    and a claim's or an offer's safe phrasing - never the brief that cites
    them."""
    brief = BRIEF.read_text(encoding="utf-8")
    client = StubClient([reply()])
    generate(client=client, concept=CONCEPT, patterns=[PATTERN])
    text = sent(client)
    assert "ICP-BRIEF" not in text
    # Probes chosen to survive a price change. "$49" and "Design partner
    # (first 10)" were withdrawn from the brief when the 2026-09-06 price
    # decision landed, which turned this test's own guard message - "the brief
    # moved; pick another distinctive phrase" - into instructions. Deliberately
    # none of these is a price: the number is being reworked and a probe that
    # tracks it will break this test again for no reason.
    for phrase in ("what do I make per hour", "700\u2013800 firms",
                   "Design partners (first 10)", "Walk away from",
                   "the most defensible thing on the board"):
        assert phrase in brief, "the brief moved; pick another distinctive phrase"
        assert phrase not in text, phrase
    lines = [ln.strip() for ln in brief.splitlines()]
    distinctive = [ln for ln in lines if len(ln) >= 40]
    assert len(distinctive) > 5, "the brief should hold substantial prose"
    for line in distinctive:
        assert line not in text


def _non_docstring_strings(tree: ast.AST) -> list[str]:
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is not None:
                docstrings.add(id(node.body[0].value))
    return [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_the_module_holds_no_path_into_docs():
    """It may document that it does not read the brief - a docstring cannot
    reach a prompt - but no string that can be interpolated may name it."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    for value in _non_docstring_strings(tree):
        assert "ICP" not in value, value
        assert "docs" not in value, value


# --- what the module imports -----------------------------------------------


def _imported_modules(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names.add(base)
            names.update("%s.%s" % (base, alias.name) for alias in node.names)
    return names


def test_the_module_reaches_the_model_only_through_engine_model():
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = _imported_modules(tree)
    assert "engine.model" in imported
    assert "engine.gate" in imported
    for forbidden in ("google", "urllib", "http", "socket", "requests", "httpx",
                      "ssl", "subprocess", "anthropic", "engine.discover",
                      "engine.oauth", "engine.measure", "engine.approval"):
        for name in imported:
            assert not (name == forbidden or name.startswith(forbidden + ".")), name
    assert ".messages.create" not in source
    assert "content[0]" not in source
    assert "anthropic" not in source.lower()
    assert source.count("model.call_model(") == 1


def test_the_module_is_pure_ascii():
    MODULE.read_text(encoding="ascii")
