"""Concept scoring: four measured dimensions, one model call, three ads.

Every fixture here is built in tmp_path against the C4/C5 contracts rather than
imported from the module that will produce them - the concept writer and the
learn step are separate tasks, and a test that imports them would fail for
their reasons instead of this module's.

Every test is offline: the model client is tests/stubs.StubClient, the
attestation table is handed to load_context as a set of keys, and no test
needs a key. The one test that reads the committed creative/ directory reads
files, not sockets.
"""
from __future__ import annotations

import ast
import json
import re
import socket
from pathlib import Path

import pytest

from engine import approval, gate, learn, model, score
from tests.stubs import StubClient, json_reply, text_reply

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# fixtures: the files the four measured dimensions read
# --------------------------------------------------------------------------

BACKLOG = """# Segment backlog

| rank | id | trade | questions | note |
|---|---|---|---|---|
| 1 | payroll-bureaus | Payroll bureaus | payslip, holiday, tax-code | all lookups |
| 2 | bookkeepers | Bookkeeping firms | invoice, vat, receipt | all lookups |
| 3 | admin-firms | Outsourced back-office | invoice, scope, document | all lookups |
| 4 | audit-firms | Audit firms | deadline, allowance, fee | allowance is a judgement call |
"""


def _patterns(*entries) -> dict:
    return {
        "schema": 1,
        "generated_at": "2026-09-14T00:00:00Z",
        "corpus_size": len(entries),
        "patterns": list(entries),
    }


def _pattern(pid, *, n, days, reach=12000, **overrides) -> dict:
    entry = {
        "id": pid,
        "kind": "hook",
        "device": "question",
        "description": 'opening device "question"; median hook 9.0 words',
        "evidence": ["fb-%d" % i for i in range(n if isinstance(n, int) else 1)],
        "median_days_running": days,
        "median_reach": reach,
        "n": n,
    }
    entry.update(overrides)
    return entry


STRONG = _pattern("q01", n=4, days=150, reach=40000, device="negative-flip")
WEAK = _pattern("q02", n=1, days=5, reach=900, device="direct-offer")
JUNK = _pattern("q03", n=None, days="quite a lot", device="how-to")


@pytest.fixture
def repo(tmp_path) -> Path:
    """A minimal stand-in repo: a backlog, a patterns file, an empty queue, an
    empty creative/ directory."""
    for stage in ("proposed", "built", "launched", "rejected"):
        (tmp_path / "queue" / stage).mkdir(parents=True)
    (tmp_path / "creative").mkdir()
    (tmp_path / "backlog.md").write_text(BACKLOG, encoding="utf-8")
    (tmp_path / "patterns.json").write_text(
        json.dumps(_patterns(STRONG, WEAK, JUNK)), encoding="utf-8"
    )
    return tmp_path


def context_for(repo: Path, *, evidence=None) -> score.Context:
    return score.load_context(
        patterns_path=repo / "patterns.json",
        backlog_path=repo / "backlog.md",
        queue_root=repo / "queue",
        creative_root=repo / "creative",
        evidence=evidence if evidence is not None else set(),
    )


@pytest.fixture
def context(repo) -> score.Context:
    return context_for(repo)


def _copy_map(text: str) -> dict:
    return {"en": text, "da": gate.NATIVE_PLACEHOLDER, "lt": gate.NATIVE_PLACEHOLDER}


def job(repo: Path, stage: str, segment: str, *, headline="", primary_text="",
        description="Built for accounting, admin and broker firms") -> Path:
    """Write a job file the way engine/propose.py files one: <segment>.json,
    the three copy fields as {en, da, lt} maps."""
    content = {
        "id": segment,
        "segment": segment,
        "headline": _copy_map(headline),
        "primary_text": _copy_map(primary_text),
        "description": _copy_map(description),
    }
    path = repo / "queue" / stage / ("%s.json" % segment)
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def creative(repo: Path, name: str, *, headline="", primary_text="") -> Path:
    """Write a hand-written arm the way creative/capacity.json is written."""
    content = {
        "id": name,
        "framing": name,
        "headline": _copy_map(headline),
        "primary_text": _copy_map(primary_text),
        "description": _copy_map("Built for accounting, admin and broker firms"),
    }
    path = repo / "creative" / ("%s.json" % name)
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def concept(concept_id="a01", **overrides) -> dict:
    """A C4 concept record."""
    record = {
        "id": concept_id,
        "segment": "payroll-bureaus",
        "angle": "the payslip request that arrives again every single month",
        "hook": "You spend your morning pulling records you have already filed.",
        "pattern_ids": ["q01"],
        "placement": "reels-9x16",
        "offer": "guarantee",
        "needs_numbers": False,
    }
    record.update(overrides)
    return record


# --------------------------------------------------------------------------
# the stub client: one call, counted, from tests/stubs.py
# --------------------------------------------------------------------------


def prose(text: str) -> str:
    """A hard-wrapped prompt read as prose: whitespace runs folded to one space."""
    return " ".join(text.split())


def ids_in(prompt: str) -> list:
    """The concept ids the one prompt actually carried.

    Read from after the CONCEPTS: marker, because the rubric's own worked
    example of the answer shape carries an id too.
    """
    payload = prompt.split("CONCEPTS:", 1)[-1]
    return re.findall(r'"id": "([^"]+)"', payload)


def flat(concepts, value: float, **kw):
    """A reply giving every concept the same editorial score."""
    return json_reply({
        "scores": [
            {"id": c["id"], "score": value, "reason": "stubbed"} for c in concepts
        ]
    }, **kw)


def by_id(**scores):
    """A reply giving named concepts named scores."""
    return json_reply({
        "scores": [
            {"id": i, "score": v, "reason": "stubbed"} for i, v in scores.items()
        ]
    })


# --------------------------------------------------------------------------
# 1. four dimensions, zero model calls
# --------------------------------------------------------------------------


def test_the_four_measured_dimensions_need_no_client_at_all(context, monkeypatch):
    """No client argument, and nothing that could reach a model behind its back."""

    def explode(*args, **kwargs):
        raise AssertionError("the measured dimensions must not call a model")

    monkeypatch.setattr(model, "call_model", explode)
    monkeypatch.setattr(model, "client", explode)
    monkeypatch.setattr(socket, "socket", explode)

    card = score.measured(concept(), context)

    for dimension in score.MEASURED:
        assert isinstance(card.scores[dimension], float), dimension
        assert 0.0 <= card.scores[dimension] <= 1.0, dimension
    assert set(card.scores) == set(score.DIMENSIONS)
    assert card.scores["editorial"] == 0.0, "editorial is unscored until it is scored"
    assert len(card.reasons) == len(score.MEASURED)


def test_pattern_evidence_weighs_n_and_median_days_running(context):
    strong = score.measured(concept(pattern_ids=["q01"]), context)
    weak = score.measured(concept(pattern_ids=["q02"]), context)
    both = score.measured(concept(pattern_ids=["q01", "q02"]), context)

    assert strong.scores["pattern_evidence"] > both.scores["pattern_evidence"]
    assert both.scores["pattern_evidence"] > weak.scores["pattern_evidence"]
    assert "q01 n=4 median_days_running=150" in " ".join(strong.reasons)


def _evidence_for(repo: Path, *, n, days) -> float:
    (repo / "patterns.json").write_text(
        json.dumps(_patterns(_pattern("q10", n=n, days=days))), encoding="utf-8"
    )
    card = score.measured(concept(pattern_ids=["q10"]), context_for(repo))
    return card.scores["pattern_evidence"]


def test_days_running_is_weighed_on_a_log_scale_to_days_full(repo):
    """Half the score is n (full at 3), half is longevity: 0 at no days, full
    at DAYS_FULL, and a week-to-month step worth about as much as a
    month-to-four-months step - the shape a linear scale would not have."""
    assert score.DAYS_FULL == 120
    assert score.EVIDENCE_FULL_N == 3

    assert _evidence_for(repo, n=3, days=0) == pytest.approx(0.5)
    assert _evidence_for(repo, n=3, days=score.DAYS_FULL) == pytest.approx(1.0)
    assert _evidence_for(repo, n=3, days=score.DAYS_FULL * 10) == pytest.approx(1.0), (
        "past the ceiling a pattern is not more true, only older"
    )
    assert _evidence_for(repo, n=0, days=score.DAYS_FULL) == pytest.approx(0.5)

    ten = _evidence_for(repo, n=3, days=10) - 0.5
    hundred = _evidence_for(repo, n=3, days=100) - 0.5
    assert ten > 0.5 * hundred, "ten days already earns half of what a hundred does"
    assert hundred > ten


def test_a_learn_sentinel_of_zero_days_is_a_zero_not_a_crash(repo):
    """engine/learn.py writes 0 when no supporting ad carried a usable value;
    a log scale over it must read as zero longevity, not raise."""
    assert 0.0 <= _evidence_for(repo, n=2, days=0) <= 1.0


def test_a_concept_citing_no_pattern_has_no_evidence(context):
    card = score.measured(concept(pattern_ids=[]), context)
    assert card.scores["pattern_evidence"] == 0.0
    assert any("cites no pattern" in r for r in card.reasons)


def test_an_unknown_pattern_id_is_named_not_assumed(context):
    card = score.measured(concept(pattern_ids=["q99"]), context)
    assert card.scores["pattern_evidence"] == 0.0
    assert any("q99 is not in the patterns file" in r for r in card.reasons)


def test_a_non_numeric_median_is_counted_as_zero_with_a_note_not_a_crash(context):
    """Nothing type-checks median_days_running on the way back in, so scoring
    must survive junk in it - and say so."""
    card = score.measured(concept(pattern_ids=["q03"]), context)

    assert 0.0 <= card.scores["pattern_evidence"] <= 1.0
    assert card.scores["pattern_evidence"] == 0.0, "n None and days junk both count as 0"
    reasons = " ".join(card.reasons)
    assert "q03 median_days_running is 'quite a lot', not a number; counted as 0" in reasons
    assert "q03 n is None, not a number; counted as 0" in reasons
    assert card.eligible is True, "junk evidence is a low score, not a refusal"


def test_a_boolean_or_infinite_leaf_is_junk_too(repo):
    (repo / "patterns.json").write_text(
        json.dumps(_patterns(_pattern("q11", n=True, days=float("inf")))),
        encoding="utf-8",
    )
    card = score.measured(concept(pattern_ids=["q11"]), context_for(repo))
    reasons = " ".join(card.reasons)
    assert "q11 n is True, not a number" in reasons
    assert "q11 median_days_running is inf, which is not a usable number" in reasons


def test_a_pattern_id_arriving_as_a_bare_string_is_not_iterated(context):
    card = score.measured(concept(pattern_ids="q01"), context)
    assert card.scores["pattern_evidence"] > 0.0


# --------------------------------------------------------------------------
# 2. claims survivability: a gate, not a gradient
# --------------------------------------------------------------------------


def test_needs_numbers_scores_zero_on_claims_survivability(context):
    card = score.measured(concept(needs_numbers=True), context)
    assert card.scores["claims_survivability"] == 0.0
    assert card.eligible is False
    assert any("needs_numbers" in r for r in card.reasons)


def test_an_unattested_number_in_the_hook_scores_zero(context):
    card = score.measured(
        concept(hook="We answer 40 emails before lunch."), context
    )
    assert card.scores["claims_survivability"] == 0.0
    assert card.eligible is False
    reason = next(r for r in card.reasons if "claims survivability" in r)
    assert "claims/evidence.json" in reason
    assert "'40'" in reason
    assert gate.evidence_key("hook", "We answer 40 emails before lunch.") in reason, (
        "the reason prints the exact key to add, as the gate does"
    )
    assert '"field": "hook"' in reason


def test_a_number_word_counts_as_a_number(context):
    """The gate's policy matches 'three' and 'half', not only digits."""
    card = score.measured(concept(hook="Three times before lunch, you retype it."), context)
    assert card.scores["claims_survivability"] == 0.0
    card = score.measured(concept(hook="Half your morning goes on the same reply."), context)
    assert card.scores["claims_survivability"] == 0.0


def test_an_attested_hook_number_survives(repo):
    hook = "Three times before lunch, you write an email you've already written."
    ctx = context_for(
        repo, evidence={gate.evidence_key("hook", hook): {"kind": "illustrative"}}
    )
    card = score.measured(concept(hook=hook), ctx)
    assert card.scores["claims_survivability"] == 1.0
    assert card.eligible is True
    assert any("attested in claims/evidence.json" in r for r in card.reasons)


def test_evidence_is_injectable_as_a_bare_set_of_keys(repo):
    """load_context takes the attestation table or just its keys; the context
    keeps the key set either way."""
    hook = "You lose 20 minutes to the same reply."
    key = gate.evidence_key("hook", hook)
    ctx = context_for(repo, evidence={key})
    assert ctx.evidence == frozenset({key})
    assert score.measured(concept(hook=hook), ctx).scores["claims_survivability"] == 1.0


def test_the_attestation_key_is_the_gates_own_key(repo):
    """Same field name, same hash, same file - not a second standard."""
    hook = "You lose 20 minutes to the same reply."
    ctx = context_for(repo, evidence={gate.evidence_key("hook", hook): {"kind": "measured"}})
    assert score.measured(concept(hook=hook), ctx).scores["claims_survivability"] == 1.0
    assert score.measured(concept(hook=hook), context_for(repo)).eligible is False
    # A key under another field name attests nothing here: the hook is gated
    # under "hook", exactly as reel-engine's build gates it.
    other = context_for(
        repo, evidence={gate.evidence_key("headline.en", hook): {"kind": "measured"}}
    )
    assert score.measured(concept(hook=hook), other).eligible is False


def test_load_context_reads_the_gates_attestations_when_none_are_given(repo, monkeypatch):
    hook = "You lose 20 minutes to the same reply."
    key = gate.evidence_key("hook", hook)
    monkeypatch.setattr(gate, "load_attestations", lambda: {key: {"kind": "measured"}})
    ctx = score.load_context(
        patterns_path=repo / "patterns.json",
        backlog_path=repo / "backlog.md",
        queue_root=repo / "queue",
        creative_root=repo / "creative",
    )
    assert key in ctx.evidence
    assert score.measured(concept(hook=hook), ctx).eligible is True


def test_the_committed_evidence_file_loads_as_a_context(repo):
    """evidence=None against the real claims/evidence.json: no attestation
    yet, so the set is empty and a number still fails."""
    ctx = score.load_context(
        patterns_path=repo / "patterns.json",
        backlog_path=repo / "backlog.md",
        queue_root=repo / "queue",
        creative_root=repo / "creative",
    )
    assert ctx.evidence == frozenset(gate.load_attestations())


# --------------------------------------------------------------------------
# 3. ICP fit
# --------------------------------------------------------------------------


def test_a_segment_outside_the_backlog_scores_zero_on_icp_fit(context):
    card = score.measured(concept(segment="letting-agents"), context)
    assert card.scores["icp_fit"] == 0.0
    assert any("queue/backlog.md" in r for r in card.reasons)


def test_a_missing_segment_scores_zero_on_icp_fit(context):
    card = score.measured(concept(segment=None), context)
    assert card.scores["icp_fit"] == 0.0
    assert card.segment == ""


def test_a_backlog_segment_of_pure_lookups_scores_full_icp_fit(context):
    card = score.measured(concept(segment="bookkeepers"), context)
    assert card.scores["icp_fit"] == 1.0
    assert any("all three tags read as lookups" in r for r in card.reasons)


def test_a_judgement_call_question_costs_icp_fit(context):
    """`allowance` is the tag queue/backlog.md records the gate rejecting twice."""
    card = score.measured(concept(segment="audit-firms"), context)
    assert card.scores["icp_fit"] == pytest.approx(2.0 / 3.0)
    assert any("judgement calls" in r for r in card.reasons)


def test_is_lookup_reads_a_tag_not_a_question():
    assert score._is_lookup("payslip")
    assert score._is_lookup("tax-code")
    assert not score._is_lookup("allowance")
    assert not score._is_lookup("can I claim the laptop")
    assert not score._is_lookup("")


# --------------------------------------------------------------------------
# 4. novelty: the live queue and the creative/ arms
# --------------------------------------------------------------------------


def test_novelty_is_full_when_nothing_is_live(context):
    card = score.measured(concept(), context)
    assert card.scores["novelty"] == 1.0


def test_a_live_job_on_the_same_segment_costs_novelty(repo):
    job(repo, "proposed", "payroll-bureaus", headline="A completely different line.")
    card = score.measured(concept(segment="payroll-bureaus"), context_for(repo))
    assert card.scores["novelty"] <= 1.0 - score.SAME_SEGMENT_SIMILARITY
    assert any("queue/proposed/payroll-bureaus.json already holds this segment" in r
               for r in card.reasons)


def test_reused_wording_costs_novelty_even_on_another_segment(repo):
    record = concept(segment="bookkeepers")
    job(repo, "built", "admin-firms", headline=record["hook"], primary_text=record["angle"])
    card = score.measured(record, context_for(repo))
    assert card.scores["novelty"] == 0.0
    assert any("queue/built/admin-firms.json" in r for r in card.reasons)


def test_novelty_reads_headline_en_and_primary_text_en_only(repo):
    """The description is the trade line on every ad; da/lt are the placeholder
    or a proofread of the same argument. Neither carries an angle."""
    record = concept(segment="bookkeepers")
    path = job(repo, "built", "admin-firms", headline="Nothing in common.",
               description=record["hook"])
    assert score.measured(record, context_for(repo)).scores["novelty"] == 1.0

    content = json.loads(path.read_text(encoding="utf-8"))
    content["headline"]["da"] = record["hook"]
    path.write_text(json.dumps(content), encoding="utf-8")
    assert score.measured(record, context_for(repo)).scores["novelty"] == 1.0


def test_a_bare_string_copy_field_is_read_too(repo):
    """An older hand-written arm may carry headline as a plain string."""
    record = concept(segment="bookkeepers")
    path = repo / "queue" / "launched" / "admin-firms.json"
    path.write_text(json.dumps({"headline": record["hook"]}), encoding="utf-8")
    assert score.measured(record, context_for(repo)).scores["novelty"] == 0.0


def test_all_three_live_directories_count(repo):
    """proposed, built and launched are all live work; a stage is not a filter."""
    assert score.LIVE_STAGES == ("proposed", "built", "launched")
    assert score.LIVE_STAGES == approval.LIVE_STAGES
    record = concept(segment="bookkeepers")
    for stage in score.LIVE_STAGES:
        path = job(repo, stage, "admin-firms", headline=record["hook"],
                   primary_text=record["angle"])
        card = score.measured(record, context_for(repo))
        assert card.scores["novelty"] == 0.0, stage
        path.unlink()


def test_a_rejected_draft_does_not_take_an_angle(repo):
    """queue/backlog.md: a parked draft never passed the gate, so it holds nothing."""
    record = concept(segment="bookkeepers")
    job(repo, "rejected", "bookkeepers", headline=record["hook"], primary_text=record["angle"])
    job(repo, "built", "admin-firms", headline="Nothing in common with the above.")
    card = score.measured(record, context_for(repo))
    assert card.scores["novelty"] == 1.0


def test_an_unreadable_job_file_does_not_stop_a_run(repo):
    (repo / "queue" / "proposed" / "broken.json").write_text("{not json", encoding="utf-8")
    (repo / "queue" / "built" / "list.json").write_text("[1, 2]", encoding="utf-8")
    card = score.measured(concept(), context_for(repo))
    assert card.scores["novelty"] == 1.0


def test_a_reel_selection_sidecar_is_not_a_job(repo):
    """queue/proposed/<segment>.reel.json travels with the job and carries the
    concept, not copy; its stem is not a segment either."""
    assert score.REEL_SELECTION_SUFFIX == approval.REEL_SELECTION_SUFFIX
    record = concept(segment="bookkeepers")
    sidecar = repo / "queue" / "proposed" / "bookkeepers.reel.json"
    sidecar.write_text(json.dumps({
        "schema": 1, "selected": ["a01"],
        "concepts": [{"id": "a01", "hook": record["hook"], "angle": record["angle"]}],
        "headline": {"en": record["hook"]},
    }), encoding="utf-8")
    ctx = context_for(repo)
    assert ctx.jobs == ()
    assert score.measured(record, ctx).scores["novelty"] == 1.0


def test_a_creative_arm_sharing_the_wording_costs_novelty(repo):
    record = concept(segment="bookkeepers")
    creative(repo, "capacity", headline=record["hook"], primary_text=record["angle"])
    card = score.measured(record, context_for(repo))
    assert card.scores["novelty"] == 0.0
    assert any("creative/capacity.json shares 100% of this angle's wording" in r
               for r in card.reasons)


def test_a_creative_arm_holds_no_segment(repo):
    """A creative file is a framing, not a segment: even one named after the
    concept's segment floors nothing when its wording is unrelated."""
    creative(repo, "payroll-bureaus", headline="Nothing in common with the concept.")
    ctx = context_for(repo)
    assert len(ctx.jobs) == 1
    assert ctx.jobs[0].segment is None
    assert ctx.jobs[0].stage == "creative"
    card = score.measured(concept(segment="payroll-bureaus"), ctx)
    assert card.scores["novelty"] == 1.0
    assert not any("already holds this segment" in r for r in card.reasons)


def test_the_worked_example_is_excluded_by_name(repo):
    record = concept(segment="bookkeepers")
    assert score.EXAMPLE_JOB == "example-job.json"
    creative(repo, "example-job", headline=record["hook"], primary_text=record["angle"])
    ctx = context_for(repo)
    assert ctx.jobs == ()
    assert score.measured(record, ctx).scores["novelty"] == 1.0


def test_a_missing_creative_directory_is_no_creative_arms(repo):
    (repo / "creative").rmdir()
    assert context_for(repo).jobs == ()


def test_jobs_are_ordered_queue_first_then_creative(repo):
    job(repo, "launched", "bookkeepers", headline="b")
    job(repo, "proposed", "admin-firms", headline="a")
    creative(repo, "hours", headline="h")
    creative(repo, "capacity", headline="c")
    paths = [j.path for j in score.load_jobs(repo / "queue", repo / "creative")]
    assert paths == [
        "queue/proposed/admin-firms.json",
        "queue/launched/bookkeepers.json",
        "creative/capacity.json",
        "creative/hours.json",
    ]


def test_the_committed_creative_directory_is_read_by_default(repo):
    """creative_root=None is ROOT/creative: the two hand-written arms count,
    the writer's worked example does not."""
    jobs = score.load_jobs(repo / "queue", None)
    paths = [j.path for j in jobs]
    assert "creative/capacity.json" in paths
    assert "creative/hours.json" in paths
    assert "creative/example-job.json" not in paths
    assert all(j.segment is None for j in jobs)

    capacity = next(j for j in jobs if j.path == "creative/capacity.json")
    assert score._words("More clients, same team") <= capacity.words

    ctx = score.load_context(
        patterns_path=repo / "patterns.json",
        backlog_path=repo / "backlog.md",
        queue_root=repo / "queue",
        evidence=set(),
    )
    card = score.measured(
        concept(hook="More clients, same team.", angle="more clients with the same team"),
        ctx,
    )
    assert card.scores["novelty"] < 1.0
    assert any("creative/capacity.json" in r for r in card.reasons)


def test_overlap_is_containment_not_jaccard():
    hook = score._words("You spend your morning pulling records you have already filed.")
    body = hook | score._words(
        "DoviLoop turns your own fee schedule, deadlines and policies into a reply "
        "already waiting in each person's Outlook drafts, in their own words. "
        "Nothing sends until they read it. Nothing leaves Europe."
    )
    assert score._overlap(hook, body) == 1.0, "a hook quoted inside a long body is not novel"
    assert score._overlap(frozenset(), body) == 0.0


# --------------------------------------------------------------------------
# 5. exactly one model call, for every concept
# --------------------------------------------------------------------------


def test_exactly_one_model_call_scores_every_concept(context):
    concepts = [concept("a%02d" % i) for i in range(1, 9)]
    client = StubClient([flat(concepts, 0.7)])

    selection = score.select(concepts, context=context, client=client)

    assert len(client.calls) == 1, "one call per concept would be 8x the quota"
    assert client.remaining == 0
    assert selection.model_calls == 1
    carried = ids_in(client.sent(0))
    assert carried == [c["id"] for c in concepts], "all 8 went into the one call"
    for card in selection.scorecards:
        assert card.scores["editorial"] == pytest.approx(0.7)


def test_the_one_call_is_budgeted_for_thinking_plus_the_answer(context):
    client = StubClient([flat([concept()], 0.5)])
    score.select([concept()], context=context, client=client)
    assert client.calls[0]["max_tokens"] >= 4096
    assert client.calls[0]["max_tokens"] == score.MAX_TOKENS_SCORE
    assert client.calls[0]["model"] == score.MODEL_SCORE
    assert score.MODEL_SCORE == model.MODEL_WRITE
    assert set(client.calls[0]) == {"model", "max_tokens", "messages"}


def test_the_prompt_carries_the_words_and_not_the_measured_fields(context):
    """The model is not asked to re-judge anything already read off a file."""
    client = StubClient([flat([concept()], 0.5)])
    score.select([concept()], context=context, client=client)
    prompt = client.sent(0)
    assert "pulling records you have already filed" in prompt
    assert "payslip request that arrives again" in prompt
    assert "needs_numbers" not in prompt
    assert "pattern_ids" not in prompt
    assert '"guarantee"' not in prompt, "the offer is checked from a table, not judged"
    assert "first line of an ad" in prose(prompt)
    assert "reel-generation" not in prompt
    assert client.media(0) == []


def test_the_rubric_judges_an_ads_opening_line_for_that_trade():
    assert "first line of an ad" in prose(score.RUBRIC)
    assert "do NOT score evidence, novelty" in prose(score.RUBRIC)
    assert '{"scores": [{"id": "a01"' in score.RUBRIC
    assert score.RUBRIC.rstrip().endswith("CONCEPTS:")


def test_nothing_to_score_spends_no_call(context):
    client = StubClient()
    selection = score.select([], context=context, client=client)
    assert client.calls == []
    assert selection.model_calls == 0
    assert selection.selected == []
    assert selection.scorecards == []
    assert score.editorial([], client=client) == {}


def test_no_client_and_no_key_is_a_config_error_before_any_socket(context, monkeypatch):
    for name in model.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)

    def explode(*args, **kwargs):
        raise AssertionError("no socket may open")

    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(socket, "create_connection", explode)
    with pytest.raises(model.ConfigError, match="GEMINI_API_KEY"):
        score.select([concept()], context=context)


def test_a_truncated_reply_raises(context):
    client = StubClient([flat([concept()], 0.9, stop_reason="max_tokens")])
    with pytest.raises(ValueError, match="truncated at max_tokens"):
        score.select([concept()], context=context, client=client)


def test_an_unreadable_reply_raises(context):
    client = StubClient([text_reply("I could not decide.")])
    with pytest.raises(ValueError, match="could not read editorial scores"):
        score.select([concept()], context=context, client=client)


def test_a_reply_whose_scores_are_not_a_list_raises(context):
    client = StubClient([json_reply({"scores": {"a01": 0.4}})])
    with pytest.raises(ValueError, match="could not read editorial scores"):
        score.select([concept()], context=context, client=client)


def test_prose_around_the_json_is_tolerated(context):
    client = StubClient([text_reply(
        'Here you go:\n```json\n{"scores": [{"id": "a01", "score": 0.4, "reason": "flat"}]}\n```\n'
    )])
    selection = score.select([concept()], context=context, client=client)
    assert selection.scorecards[0].scores["editorial"] == pytest.approx(0.4)
    assert any("editorial 0.40: flat" in r for r in selection.scorecards[0].reasons)


def test_a_concept_the_model_skipped_scores_zero_and_says_so(context):
    concepts = [concept("a01"), concept("a02")]
    client = StubClient([by_id(a01=0.9)])
    selection = score.select(concepts, context=context, client=client)
    missed = next(c for c in selection.scorecards if c.id == "a02")
    assert missed.scores["editorial"] == 0.0
    assert any("the model returned no score for this concept" in r for r in missed.reasons)
    assert len(missed.reasons) == len(score.DIMENSIONS)


def test_a_junk_editorial_score_is_coerced_not_crashed_on(context):
    client = StubClient([json_reply(
        {"scores": [{"id": "a01", "score": "high", "reason": "x"}, "not an entry", {"score": 1}]}
    )])
    selection = score.select([concept()], context=context, client=client)
    card = selection.scorecards[0]
    assert card.scores["editorial"] == 0.0
    assert any("not a number; counted as 0" in r for r in card.reasons)


def test_an_out_of_range_editorial_score_is_clipped(context):
    client = StubClient([json_reply({"scores": [{"id": "a01", "score": 7, "reason": None}]})])
    selection = score.select([concept()], context=context, client=client)
    card = selection.scorecards[0]
    assert card.scores["editorial"] == 1.0
    assert any("no reason given" in r for r in card.reasons)


def test_a_provider_fault_propagates_as_itself(context):
    client = StubClient([model.CapacityError("Gemini is out of capacity right now")])
    with pytest.raises(model.CapacityError):
        score.select([concept()], context=context, client=client)


# --------------------------------------------------------------------------
# 6. a claims failure cannot be selected, whatever else it scores
# --------------------------------------------------------------------------


def test_a_claims_failure_cannot_reach_the_top_three(context):
    """Perfect on every other dimension, and still excluded - it would die at the gate."""
    doomed = concept(
        "a00",
        needs_numbers=True,
        segment="bookkeepers",
        pattern_ids=["q01"],
        angle="an angle nothing in the queue has ever argued",
        hook="A hook nothing in the queue has ever used.",
    )
    # Four survivors, deliberately weaker: weak evidence and a poor editorial
    # score, so the doomed concept outscores every one of them.
    others = [
        concept("a%02d" % i, segment="bookkeepers", pattern_ids=["q02"])
        for i in range(1, 5)
    ]
    client = StubClient([by_id(a00=1.0, a01=0.1, a02=0.1, a03=0.1, a04=0.1)])

    selection = score.select([doomed] + others, context=context, client=client)

    cards = {c.id: c for c in selection.scorecards}
    assert cards["a00"].total > max(c.total for c in selection.scorecards if c.selected)
    assert cards["a00"].selected is False
    assert cards["a00"].eligible is False
    assert "a00" not in [c["id"] for c in selection.selected]
    assert len(selection.selected) == 3
    assert "excluded" in cards["a00"].verdict


def test_the_excluded_verdict_says_why(context):
    client = StubClient([flat([concept("a01")], 1.0)])
    selection = score.select(
        [concept("a01", needs_numbers=True)], context=context, client=client
    )
    card = selection.scorecards[0]
    assert card.verdict.startswith("excluded: claims survivability is 0.00")
    assert "engine/gate.py" in card.verdict
    assert selection.selected == []


# --------------------------------------------------------------------------
# 7. a scorecard for every concept, not just the winners
# --------------------------------------------------------------------------


def test_every_concept_gets_a_full_scorecard(context):
    concepts = [concept("a%02d" % i) for i in range(1, 7)]
    concepts[3]["needs_numbers"] = True
    client = StubClient([by_id(a01=0.9, a02=0.8, a03=0.7, a04=1.0, a05=0.2, a06=0.1)])

    selection = score.select(concepts, context=context, client=client)

    assert len(selection.scorecards) == len(concepts)
    assert {c.id for c in selection.scorecards} == {c["id"] for c in concepts}
    for card in selection.scorecards:
        assert set(card.scores) == set(score.DIMENSIONS)
        assert all(isinstance(v, float) for v in card.scores.values())
        assert 0.0 <= card.total <= 1.0
        assert card.verdict, "every concept says why it was or was not selected"
        assert len(card.reasons) == len(score.DIMENSIONS)

    assert [c.id for c in selection.scorecards if c.selected] == ["a01", "a02", "a03"]
    missed = next(c for c in selection.scorecards if c.id == "a05")
    assert "not selected" in missed.verdict and "below the cut" in missed.verdict
    assert selection.scorecards[-1].id == "a04", "the excluded one sorts last"


def test_the_scorecard_serialises_for_an_audit_trail(context):
    client = StubClient([flat([concept("a01"), concept("a02")], 0.6)])
    selection = score.select(
        [concept("a01"), concept("a02", needs_numbers=True)],
        context=context,
        client=client,
    )
    payload = json.loads(json.dumps(selection.as_dict(), sort_keys=True, ensure_ascii=False))
    assert set(payload) == {"selected", "model_calls", "scorecards"}
    assert payload["selected"] == ["a01"]
    assert payload["model_calls"] == 1
    assert len(payload["scorecards"]) == 2
    first = payload["scorecards"][0]
    assert set(first["scores"]) == set(score.DIMENSIONS)
    assert first["total"] == selection.scorecards[0].total
    assert first["segment"] == "payroll-bureaus"
    assert first["placement"] == "reels-9x16"
    assert set(first) == {
        "id", "segment", "placement", "scores", "total", "eligible", "selected",
        "verdict", "reasons",
    }


def test_selected_carries_the_concept_records_themselves(context):
    concepts = [concept("a%02d" % i) for i in range(1, 5)]
    client = StubClient([by_id(a01=0.9, a02=0.8, a03=0.7, a04=0.1)])
    selection = score.select(concepts, context=context, client=client)
    assert selection.selected == [concepts[0], concepts[1], concepts[2]]


def test_selection_is_deterministic_and_ties_break_by_id(context):
    concepts = [concept(i) for i in ("a09", "a02", "a07", "a04")]

    first = score.select(concepts, context=context, client=StubClient([flat(concepts, 0.5)]))
    second = score.select(concepts, context=context, client=StubClient([flat(concepts, 0.5)]))
    reversed_in = score.select(
        list(reversed(concepts)), context=context, client=StubClient([flat(concepts, 0.5)])
    )

    assert [c.id for c in first.scorecards] == [c.id for c in second.scorecards]
    assert [c.id for c in first.scorecards] == [c.id for c in reversed_in.scorecards]
    assert [c["id"] for c in second.selected] == ["a02", "a04", "a07"]
    assert [c.id for c in first.scorecards] == ["a02", "a04", "a07", "a09"]


def test_selecting_none_still_scores_and_explains_everything(context):
    """top=0 is a dry run, not a crash: every concept still gets its verdict."""
    concepts = [concept("a01"), concept("a02")]
    client = StubClient([flat(concepts, 0.5)])
    selection = score.select(concepts, context=context, client=client, top=0)
    assert selection.selected == []
    assert len(selection.scorecards) == 2
    assert all("not selected" in c.verdict for c in selection.scorecards)
    assert all("top was 0" in c.verdict for c in selection.scorecards)


def test_a_negative_top_is_refused(context):
    with pytest.raises(ValueError, match="top must not be negative"):
        score.select([concept()], context=context, client=StubClient(), top=-1)


def test_fewer_eligible_than_wanted_selects_what_there_is(context):
    concepts = [concept("a01"), concept("a02", needs_numbers=True)]
    client = StubClient([flat(concepts, 0.5)])
    selection = score.select(concepts, context=context, client=client)
    assert [c["id"] for c in selection.selected] == ["a01"]


def test_top_is_three_by_default(context):
    concepts = [concept("a%02d" % i) for i in range(1, 13)]
    client = StubClient([flat(concepts, 0.5)])
    selection = score.select(concepts, context=context, client=client)
    assert score.TOP_N == 3
    assert len(selection.selected) == 3
    assert sum(1 for c in selection.scorecards if c.selected) == 3


# --------------------------------------------------------------------------
# 8. inputs the producers can get wrong
# --------------------------------------------------------------------------


def test_a_concept_with_no_id_is_refused(context):
    with pytest.raises(ValueError, match="cannot be scored"):
        score.measured({"segment": "bookkeepers"}, context)
    with pytest.raises(ValueError, match="cannot be scored"):
        score.measured({"id": "  ", "segment": "bookkeepers"}, context)


def test_duplicate_concept_ids_are_refused_before_the_call(context):
    client = StubClient()
    with pytest.raises(ValueError, match="duplicate concept id"):
        score.select([concept("a01"), concept("a01")], context=context, client=client)
    assert client.calls == []


def test_a_missing_patterns_file_is_actionable(tmp_path):
    with pytest.raises(FileNotFoundError, match="engine.learn"):
        score.load_patterns(tmp_path / "nope.json")


def test_an_unknown_patterns_schema_is_refused(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps({"schema": 2, "patterns": []}), encoding="utf-8")
    with pytest.raises(learn.PatternsInvalid, match="schema 2"):
        score.load_patterns(path)


def test_a_patterns_file_that_is_not_json_is_refused(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(learn.PatternsInvalid, match="not valid JSON"):
        score.load_patterns(path)


def test_a_pattern_with_no_id_is_refused(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps(_patterns({"device": "x"})), encoding="utf-8")
    with pytest.raises(score.PatternsInvalid, match="no string id"):
        score.load_patterns(path)


def test_a_repeated_pattern_id_is_refused(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps(_patterns(STRONG, STRONG)), encoding="utf-8")
    with pytest.raises(score.PatternsInvalid, match="repeats pattern id 'q01'"):
        score.load_patterns(path)


def test_patterns_that_are_not_a_list_are_refused(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps({"schema": 1, "patterns": {"q01": STRONG}}), encoding="utf-8")
    with pytest.raises(score.PatternsInvalid, match="must be a list"):
        score.load_patterns(path)


def test_score_patterns_invalid_is_learns_patterns_invalid():
    """One exception family: a caller catching learn's catches the scorer's."""
    assert issubclass(score.PatternsInvalid, learn.PatternsInvalid)
    assert issubclass(score.PatternsInvalid, ValueError)
    assert score.PATTERNS_SCHEMA == learn.SCHEMA == 1


def test_a_real_learn_document_loads(tmp_path, repo):
    """The file engine/learn.py writes is the file this reads: same schema,
    ids, median_days_running and n, no median_views anywhere."""
    document = _patterns(STRONG, WEAK)
    path = tmp_path / "patterns.json"
    path.write_text(learn.dumps(document), encoding="utf-8")
    patterns = score.load_patterns(path)
    assert set(patterns) == {"q01", "q02"}
    assert "median_views" not in json.dumps(patterns)


def test_measurement_outweighs_judgement(context):
    """0.80 of the total is read off files; the model's taste cannot outvote it."""
    assert sum(score.WEIGHTS.values()) == pytest.approx(1.0)
    measured_weight = sum(score.WEIGHTS[d] for d in score.MEASURED)
    assert measured_weight == pytest.approx(0.80)
    assert score.WEIGHTS[score.JUDGED] < measured_weight
    assert score.WEIGHTS == {
        "pattern_evidence": 0.30,
        "claims_survivability": 0.10,
        "icp_fit": 0.25,
        "novelty": 0.15,
        "editorial": 0.20,
    }


# --------------------------------------------------------------------------
# 9. three winners: three segments first, then three placements
# --------------------------------------------------------------------------


def spread(*triples) -> list:
    """Concepts as (id, segment[, placement]) tuples, each with its own angle
    and hook.

    The wording carries no DIGIT, deliberately: gate.NUM_RE matches the "01"
    in a concept id, so putting the id in the hook would make every fixture
    here fail claims survivability and prove nothing about the spread.
    """
    made = []
    for index, triple in enumerate(triples):
        concept_id, segment = triple[0], triple[1]
        placement = triple[2] if len(triple) > 2 else "reels-9x16"
        tag = chr(ord("a") + index % 26) * 3
        made.append(concept(
            concept_id,
            segment=segment,
            placement=placement,
            angle="the %s request that reaches a %s desk every month" % (tag, segment),
            hook="A %s morning at a %s firm reopens the same record." % (tag, segment),
        ))
    return made


def test_three_winners_never_land_on_one_segment_while_others_are_free(context):
    """icp_fit is a pure function of the segment, so the top three by raw score
    cluster on whichever segment scores best - and three concepts on one segment
    are one job file (queue/proposed/<segment>.json), not three."""
    concepts = spread(
        ("a01", "payroll-bureaus"),
        ("a02", "payroll-bureaus"),
        ("a03", "payroll-bureaus"),
        ("a04", "bookkeepers"),
        ("a05", "admin-firms"),
    )
    # The top three on raw score are the three that share a segment.
    client = StubClient([by_id(a01=0.9, a02=0.85, a03=0.8, a04=0.2, a05=0.1)])

    selection = score.select(concepts, context=context, client=client, top=3)

    cards = {c.id: c for c in selection.scorecards}
    assert [cards[i].total for i in ("a01", "a02", "a03")] > [
        cards[i].total for i in ("a02", "a03", "a04")
    ], "the fixture must rank the same-segment three on top, or it proves nothing"

    segments = [c["segment"] for c in selection.selected]
    assert len(selection.selected) == 3
    assert len(set(segments)) == 3, segments
    assert [c["id"] for c in selection.selected] == ["a01", "a04", "a05"]


def test_a_concept_passed_over_for_its_segment_is_told_so_not_dropped(context):
    """The scorecard is the audit trail: a higher-scoring concept that lost to
    the spread must say that is what happened, and to whom."""
    concepts = spread(
        ("a01", "payroll-bureaus"),
        ("a02", "payroll-bureaus"),
        ("a03", "payroll-bureaus"),
        ("a04", "bookkeepers"),
        ("a05", "admin-firms"),
    )
    client = StubClient([by_id(a01=0.9, a02=0.85, a03=0.8, a04=0.2, a05=0.1)])

    selection = score.select(concepts, context=context, client=client, top=3)

    assert len(selection.scorecards) == 5, "nothing is dropped from the report"
    cards = {c.id: c for c in selection.scorecards}
    lowest = min(c.total for c in selection.scorecards if c.selected)

    for passed_over in ("a02", "a03"):
        card = cards[passed_over]
        assert card.selected is False
        assert card.eligible is True, "it could have shipped; it lost on diversity"
        assert card.total > lowest, (
            "the fixture must pass over a concept that outscored a winner"
        )
        assert "segment diversity" in card.verdict
        assert "a01 already won segment 'payroll-bureaus'" in card.verdict
        assert "queue/proposed/payroll-bureaus.json" in card.verdict
        # Not the other verdicts: it was NOT below the cut, and no placement
        # pass ran, so saying either would send the operator looking for a
        # scoring problem that is not there.
        assert "below the cut" not in card.verdict
        assert "placement" not in card.verdict

    assert "below the cut" not in cards["a01"].verdict
    assert cards["a04"].verdict.startswith("selected:")


def test_each_segment_is_won_by_its_own_best_concept(context):
    """The spread picks the best concept per segment, not the first one seen."""
    concepts = spread(
        ("a01", "payroll-bureaus"),
        ("a02", "bookkeepers"),
        ("a03", "admin-firms"),
        ("a04", "payroll-bureaus"),
        ("a05", "bookkeepers"),
        ("a06", "admin-firms"),
    )
    client = StubClient([
        by_id(a01=0.2, a02=0.3, a03=0.1, a04=0.9, a05=0.8, a06=0.7)
    ])

    selection = score.select(concepts, context=context, client=client, top=3)

    assert [c["id"] for c in selection.selected] == ["a04", "a05", "a06"]
    assert sorted(c["segment"] for c in selection.selected) == [
        "admin-firms", "bookkeepers", "payroll-bureaus",
    ]


def test_when_segments_run_out_the_next_slot_prefers_a_different_placement(context):
    """Two segments, three slots: the third winner is the best concept on a
    placement no winner holds, so a trade carrying two ads carries a Reel and
    a static rather than two Reels - and the Reel it outscored is told why."""
    concepts = spread(
        ("a01", "payroll-bureaus", "reels-9x16"),
        ("a02", "payroll-bureaus", "reels-9x16"),
        ("a03", "payroll-bureaus", "static-1x1"),
        ("a04", "bookkeepers", "reels-9x16"),
    )
    client = StubClient([by_id(a01=0.9, a02=0.85, a03=0.8, a04=0.2)])

    selection = score.select(concepts, context=context, client=client, top=3)

    assert [c["id"] for c in selection.selected] == ["a01", "a03", "a04"]
    assert sorted(c["placement"] for c in selection.selected) == [
        "reels-9x16", "reels-9x16", "static-1x1",
    ]
    cards = {c.id: c for c in selection.scorecards}
    passed = cards["a02"]
    assert passed.selected is False and passed.eligible is True
    assert passed.total > min(c.total for c in selection.scorecards if c.selected)
    assert "segment and placement diversity" in passed.verdict
    assert "a01 already won segment 'payroll-bureaus'" in passed.verdict
    assert "a01 already won placement 'reels-9x16'" in passed.verdict
    assert "below the cut" not in passed.verdict

    third = cards["a03"]
    assert third.selected is True
    assert "a01 already holds segment 'payroll-bureaus'" in third.verdict
    assert "queue/proposed/payroll-bureaus.json" in third.verdict


def test_with_one_placement_everywhere_score_order_fills_the_rest_and_says_so(context):
    """A rule meant to protect an ad must not cost one: when the eligible
    concepts name fewer segments than there are slots and every placement is
    already held, the spread is spent and score order finishes the job - out
    loud, because the two winners sharing a segment cannot both be filed. The
    concept that lost the last slot lost it to the SEGMENT rule (a lower
    scorer on a free segment), and its verdict must not blame the placement."""
    concepts = spread(
        ("a01", "payroll-bureaus"),
        ("a02", "payroll-bureaus"),
        ("a03", "payroll-bureaus"),
        ("a04", "bookkeepers"),
    )
    client = StubClient([by_id(a01=0.9, a02=0.8, a03=0.7, a04=0.1)])

    selection = score.select(concepts, context=context, client=client, top=3)

    assert [c["id"] for c in selection.selected] == ["a01", "a02", "a04"]
    cards = {c.id: c for c in selection.scorecards}
    second = cards["a02"]
    assert second.selected is True
    assert "a01 already holds segment 'payroll-bureaus'" in second.verdict
    assert "queue/proposed/payroll-bureaus.json" in second.verdict
    assert "named fewer than 3 segments" in second.verdict

    third = cards["a03"]
    assert third.selected is False
    assert "segment diversity" in third.verdict
    assert "placement" not in third.verdict


def test_an_ineligible_concept_does_not_hold_a_segment_or_a_placement(context):
    """A concept that cannot ship cannot spend a segment: gate.structural()
    would refuse it, so the segment is still free for one that can."""
    concepts = spread(
        ("a01", "payroll-bureaus"),
        ("a02", "bookkeepers"),
        ("a03", "admin-firms"),
    )
    concepts[0]["needs_numbers"] = True
    client = StubClient([by_id(a01=1.0, a02=0.5, a03=0.4, a04=0.3)])
    doomed_segment = concepts[0]["segment"]
    concepts.append(spread(("a04", doomed_segment))[0])

    selection = score.select(concepts, context=context, client=client, top=3)

    assert [c["id"] for c in selection.selected] == ["a02", "a03", "a04"]
    excluded = next(c for c in selection.scorecards if c.id == "a01")
    assert excluded.verdict.startswith("excluded:")


def test_spread_alone_on_hand_built_cards():
    """The three passes, on cards with nothing but a segment, a placement and
    a total: segments first, then placements, then score order."""
    def card(cid, segment, placement, total):
        return score.Scorecard(
            id=cid, segment=segment, placement=placement,
            scores={"pattern_evidence": total, "claims_survivability": total,
                    "icp_fit": total, "novelty": total, "editorial": total},
        )

    ranked = [
        card("a01", "s1", "reels-9x16", 0.9),
        card("a02", "s1", "reels-9x16", 0.8),
        card("a03", "s1", "feed-4x5", 0.7),
        card("a04", "s2", "reels-9x16", 0.6),
        card("a05", "s1", "static-1x1", 0.5),
    ]
    result = score._spread(ranked, 4)
    assert [c.id for c in result.winners] == ["a01", "a04", "a03", "a05"]
    assert result.by_segment["s1"].id == "a01"
    assert result.by_segment["s2"].id == "a04"
    assert result.by_placement["reels-9x16"].id == "a01"
    assert result.by_placement["feed-4x5"].id == "a03"
    assert result.by_placement["static-1x1"].id == "a05"
    assert result.placement_passed == frozenset({"a02"})

    everything = score._spread(ranked, 5)
    assert [c.id for c in everything.winners] == ["a01", "a04", "a03", "a05", "a02"]
    assert everything.placement_passed == frozenset(), "a02 was taken after all"

    nothing = score._spread(ranked, 0)
    assert nothing.winners == [] and nothing.by_segment == {}


# --------------------------------------------------------------------------
# 10. hygiene: what the module is made of
# --------------------------------------------------------------------------

FORBIDDEN_IMPORTS = (
    "google", "urllib", "http", "socket", "requests", "httpx", "aiohttp",
    "ssl", "subprocess", "engine.discover", "engine.oauth", "engine.approval",
)


def test_score_imports_no_network_no_sdk_and_no_transport():
    tree = ast.parse(Path(score.__file__).read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    for name in names:
        for bad in FORBIDDEN_IMPORTS:
            assert not (name == bad or name.startswith(bad + ".")), name


def test_the_constants_are_the_contracts():
    assert score.DIMENSIONS == (
        "pattern_evidence", "claims_survivability", "icp_fit", "novelty", "editorial",
    )
    assert score.MEASURED == score.DIMENSIONS[:4]
    assert score.JUDGED == "editorial"
    assert score.DAYS_FULL == learn.LONGEVITY_EDGES[-1]
    assert not hasattr(score, "VIEWS_FULL")
    assert score.MAX_TOKENS_SCORE == 16000
    assert score.DEFAULT_PATTERNS == learn.DEFAULT_PATH
    assert score.DEFAULT_QUEUE == ROOT / "queue"
    assert score.DEFAULT_CREATIVE == ROOT / "creative"
    assert score.JOB_ANGLE_KEYS == ("headline", "primary_text")
