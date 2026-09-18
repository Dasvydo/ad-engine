"""engine/propose.py: the step that turns a selected concept into a queue job.

Every test is offline. The model is tests/stubs.py's StubClient and every
socket in the process explodes, so a call that reached the network would fail
loudly rather than cost anything. The queue is a tmp_path tree - engine.approval
reads its QUEUE global through queue_dir() on every call, which is the sanctioned
way to redirect it - and the backlog and the selection report are tmp files too,
so no test can propose a job into the real queue/.

ONE CALL PER ATTEMPT IS TWO REPLIES. engine.write makes the writing call and
engine.gate's editorial layer makes the judging one, so a stub covering a single
attempt queues write-then-gate. A structural failure never reaches the second,
and several tests assert exactly that by leaving the queue empty.
"""
from __future__ import annotations

import ast
import json
import socket
from pathlib import Path

import pytest

from engine import approval, backlog, gate, learn, model, propose, write
from engine.backlog import Segment
from tests.stubs import StubClient, json_reply

ROOT = Path(__file__).resolve().parents[1]

NOW = "2026-09-22T09:03:00Z"

BACKLOG = """# A test backlog

<!-- backlog:begin -->
| rank | id | trade | questions | note |
|---|---|---|---|---|
| 1 | payroll-bureaus | Payroll bureaus | payslip, holiday, tax-code | all three are a record fetch |
| 2 | bookkeepers | Bookkeeping firms | invoice, vat, receipt | bogholder, not revisor |
| 3 | audit-firms | Audit firms | deadline, document, fee | the inbox reads differently |
<!-- backlog:end -->
"""

TOO_LONG = "A headline that is far too long for any Meta placement"

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


def concept(concept_id: str = "a01", segment: str = "payroll-bureaus",
            **overrides) -> dict:
    """One C4 concept, the shape engine.concepts writes and score selects."""
    record = {
        "id": concept_id,
        "segment": segment,
        "angle": "a knowledge base answers the mail nobody wants to retype",
        "hook": "The request lands again, and the answer has not changed.",
        "pattern_ids": ["q03"],
        "placement": "reels-9x16",
        "offer": "none",
        "needs_numbers": False,
    }
    record.update(overrides)
    return record


def example() -> dict:
    """The worked C3 job the gate's own tests run over."""
    return json.loads((ROOT / "creative" / "example-job.json").read_text(encoding="utf-8"))


def payload(**overrides) -> dict:
    """A model reply shaped like the real thing: exactly write.AUTHORED, in
    English, taken from the worked example - so a job built from it is one the
    gate is known to pass."""
    job = example()
    out = {}
    for key in write.AUTHORED:
        value = job[key]
        out[key] = value["en"] if isinstance(value, dict) else value
    out.update(overrides)
    return out


def written(**overrides):
    """The writing call's reply."""
    return json_reply(payload(**overrides))


def passed():
    """The editorial call's reply, approving."""
    return json_reply({"pass": True})


def refused(*failures):
    """The editorial call's reply, refusing with reasons."""
    return json_reply({"pass": False, "failures": list(failures) or ["unspecified"]})


def selection(*records, path: Path | None = None) -> dict:
    """A research/selection.json holding these concepts, all selected."""
    document = {
        "schema": 1,
        "generated_at": NOW,
        "ok": True,
        "selected": [r["id"] for r in records],
        "concepts": list(records),
    }
    if path is not None:
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    return document


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    """No test may fall back to a real client."""
    for name in model.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_sockets(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a test tried to open a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A whole repository's worth of state, all of it under tmp_path."""
    queue = tmp_path / "queue"
    for stage in approval.ALL_STAGES:
        (queue / stage).mkdir(parents=True)
    monkeypatch.setattr(approval, "QUEUE", queue)

    backlog_path = tmp_path / "backlog.md"
    backlog_path.write_text(BACKLOG, encoding="utf-8")
    monkeypatch.setattr(backlog, "DEFAULT_PATH", backlog_path)

    monkeypatch.setattr(propose, "DEFAULT_SELECTION", tmp_path / "selection.json")

    patterns = tmp_path / "patterns.json"
    patterns.write_text(
        json.dumps({"schema": 1, "generated_at": NOW, "patterns": [PATTERN]},
                   sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(learn, "DEFAULT_PATH", patterns)
    return tmp_path


def job_path(repo, segment_id, stage="proposed") -> Path:
    return repo / "queue" / stage / ("%s.json" % segment_id)


def sidecar_path(repo, segment_id, stage="proposed") -> Path:
    return repo / "queue" / stage / ("%s.reel.json" % segment_id)


def park(repo, segment_id, stage="rejected", **overrides) -> Path:
    """A job file on disk at a stage, restamped for this segment."""
    job = example()
    job["id"] = job["segment"] = segment_id
    job["creative_source"]["selection"] = "queue/proposed/%s.reel.json" % segment_id
    job.update(overrides)
    path = job_path(repo, segment_id, stage)
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# the happy path
# --------------------------------------------------------------------------

def test_a_passing_draft_lands_in_proposed_with_its_reel_selection(repo):
    client = StubClient([written(), passed()])

    assert propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW) == 0

    path = job_path(repo, "payroll-bureaus")
    job = json.loads(path.read_text(encoding="utf-8"))
    assert job["id"] == job["segment"] == "payroll-bureaus"
    assert job["proposed_at"] == NOW
    assert client.remaining == 0


def test_the_job_file_keeps_authored_key_order_and_the_queue_shape(repo):
    client = StubClient([written(), passed()])
    propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW)

    text = job_path(repo, "payroll-bureaus").read_text(encoding="utf-8")
    job = json.loads(text)
    assert list(job) == list(gate.JOB_KEYS)
    assert text == json.dumps(job, ensure_ascii=False, indent=2) + "\n"


def test_the_reel_selection_is_written_beside_the_job_as_a_sorted_document(repo):
    client = StubClient([written(), passed()])
    propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW)

    text = sidecar_path(repo, "payroll-bureaus").read_text(encoding="utf-8")
    document = json.loads(text)
    assert text == json.dumps(document, sort_keys=True, indent=2,
                              ensure_ascii=False) + "\n"
    assert document["source"] == "ad-engine"
    assert document["generated_at"] == NOW


def test_the_selection_sidecar_is_one_reel_engine_would_accept(repo):
    """The three checks reel-engine/engine/script.py's load_selection makes."""
    client = StubClient([written(), passed()])
    propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW)

    document = json.loads(sidecar_path(repo, "payroll-bureaus").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    assert isinstance(document["selected"], list)
    assert isinstance(document["concepts"], list)
    by_id = {r["id"]: r for r in document["concepts"]}
    assert document["selected"]
    for concept_id in document["selected"]:
        assert concept_id in by_id


def test_a_job_written_without_a_concept_gets_a_synthetic_one(repo):
    client = StubClient([written(), passed()])
    propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW)

    document = json.loads(sidecar_path(repo, "payroll-bureaus").read_text(encoding="utf-8"))
    record = document["concepts"][0]
    job = json.loads(job_path(repo, "payroll-bureaus").read_text(encoding="utf-8"))
    # A job written from the segment alone stamps concept_id null, so the
    # sidecar names the segment; the hook is the headline and the angle is the
    # hypothesis.
    assert job["concept_id"] is None
    assert record["id"] == "payroll-bureaus"
    assert record["hook"] == job["headline"]["en"]
    assert record["angle"] == job["hypothesis"]
    assert record["segment"] == "payroll-bureaus"
    assert record["pattern_ids"] == []
    assert record["needs_numbers"] is False


def test_a_concept_without_a_concept_id_falls_back_to_the_segment(repo):
    record = propose.synthetic_concept({"segment": "audit-firms",
                                        "concept_id": None,
                                        "headline": {"en": "A hook"},
                                        "hypothesis": "an angle",
                                        "placement": "feed-4x5"})
    assert record["id"] == "audit-firms"
    assert record["placement"] == "feed-4x5"
    assert record["hook"] == "A hook"


def test_the_id_file_holds_the_bare_segment_id_on_a_single_run(repo, tmp_path):
    ids = tmp_path / "proposed.txt"
    client = StubClient([written(), passed()])

    propose.main(["--segment", "payroll-bureaus", "--id-file", str(ids)],
                 client=client, now=NOW)

    assert ids.read_text(encoding="utf-8") == "payroll-bureaus"


def test_with_no_segment_it_takes_the_next_unused_row(repo):
    park(repo, "payroll-bureaus", stage="proposed")
    client = StubClient([written(), passed()])

    assert propose.main([], client=client, now=NOW) == 0
    assert job_path(repo, "bookkeepers").exists()


def test_a_rejected_draft_does_not_mark_its_segment_used(repo):
    park(repo, "payroll-bureaus", stage="rejected")
    client = StubClient([written(), passed()])

    propose.main([], client=client, now=NOW)

    assert job_path(repo, "payroll-bureaus").exists()


def test_every_segment_spoken_for_is_a_quiet_zero(repo, capsys):
    for segment_id in ("payroll-bureaus", "bookkeepers", "audit-firms"):
        park(repo, segment_id, stage="proposed")

    assert propose.main([], client=StubClient([]), now=NOW) == 0
    assert "nothing to propose" in capsys.readouterr().out


# --------------------------------------------------------------------------
# the placement
# --------------------------------------------------------------------------

def test_placement_overrides_the_concept_and_a_still_gets_no_sidecar(repo, tmp_path):
    selection(concept(), path=tmp_path / "selection.json")
    client = StubClient([written(), passed()])

    assert propose.main(["--concept", "a01", "--placement", "static-1x1"],
                        client=client, now=NOW) == 0

    job = json.loads(job_path(repo, "payroll-bureaus").read_text(encoding="utf-8"))
    assert job["placement"] == "static-1x1"
    assert job["creative_source"]["kind"] == "still"
    assert not sidecar_path(repo, "payroll-bureaus").exists()


def test_an_unknown_placement_is_argparse_not_a_call(repo):
    with pytest.raises(SystemExit) as caught:
        propose.main(["--segment", "payroll-bureaus", "--placement", "billboard"],
                     client=StubClient([]))
    assert caught.value.code == 2


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------

def test_a_structural_failure_parks_the_exact_text_and_returns_one(repo, capsys):
    client = StubClient([written(headline=TOO_LONG)])

    assert propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW) == 1

    parked = job_path(repo, "payroll-bureaus", "rejected")
    assert json.loads(parked.read_text(encoding="utf-8"))["headline"]["en"] == TOO_LONG
    assert not job_path(repo, "payroll-bureaus").exists()
    # The editorial call was never made: a structural failure is free.
    assert client.remaining == 0
    out = capsys.readouterr().out
    assert "--regate %s" % parked in out


def test_a_parked_draft_leaves_its_segment_in_the_backlog(repo):
    client = StubClient([written(headline=TOO_LONG)])
    propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW)

    assert "payroll-bureaus" not in approval.used_ids()


def test_a_structural_failure_writes_no_sidecar(repo):
    client = StubClient([written(headline=TOO_LONG)])
    propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW)

    assert not sidecar_path(repo, "payroll-bureaus").exists()
    assert not sidecar_path(repo, "payroll-bureaus", "rejected").exists()


def test_a_second_structural_failure_never_overwrites_the_parked_draft(repo, capsys):
    first = TOO_LONG
    propose.main(["--segment", "payroll-bureaus"],
                 client=StubClient([written(headline=first)]), now=NOW)

    second = "Another headline that is also far too long to be a Meta headline"
    assert propose.main(["--segment", "payroll-bureaus"],
                        client=StubClient([written(headline=second)]), now=NOW) == 1

    parked = job_path(repo, "payroll-bureaus", "rejected")
    assert json.loads(parked.read_text(encoding="utf-8"))["headline"]["en"] == first
    assert not job_path(repo, "payroll-bureaus").exists()
    assert "already exists" in capsys.readouterr().out


def test_an_editorial_failure_retries_once_with_the_failures_in_the_prompt(repo):
    reason = "rule 3: the hook names no moment in the payroll week"
    client = StubClient([written(), refused(reason),
                         written(headline="Payslips, already drafted"), passed()])

    assert propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW) == 0

    assert reason in client.sent(2)
    assert reason not in client.sent(0)
    assert client.remaining == 0
    job = json.loads(job_path(repo, "payroll-bureaus").read_text(encoding="utf-8"))
    assert job["headline"]["en"] == "Payslips, already drafted"


def test_an_editorial_failure_twice_stops_and_leaves_nothing_behind(repo, capsys):
    client = StubClient([written(), refused("rule 1"), written(), refused("rule 1")])

    assert propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW) == 1

    assert not job_path(repo, "payroll-bureaus").exists()
    assert not job_path(repo, "payroll-bureaus", "rejected").exists()
    assert "Segment stays in the backlog" in capsys.readouterr().out


def test_retries_zero_means_one_attempt(repo):
    client = StubClient([written(), refused("rule 1")])

    assert propose.main(["--segment", "payroll-bureaus", "--retries", "0"],
                        client=client, now=NOW) == 1
    assert client.remaining == 0


def test_a_negative_retries_is_refused_before_any_call(repo):
    assert propose.main(["--retries", "-1"], client=StubClient([])) == 1


def test_a_writing_failure_leaves_nothing_behind(repo, capsys):
    client = StubClient([json_reply({"refuse": "this segment asks for a number"})])

    assert propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW) == 1
    assert not job_path(repo, "payroll-bureaus").exists()
    assert "writing FAILED" in capsys.readouterr().out


# --------------------------------------------------------------------------
# never overwriting a live job
# --------------------------------------------------------------------------

def test_a_live_proposed_job_is_refused_without_force(repo, capsys):
    park(repo, "payroll-bureaus", stage="proposed", hypothesis="the original")

    assert propose.main(["--segment", "payroll-bureaus"],
                        client=StubClient([]), now=NOW) == 1

    job = json.loads(job_path(repo, "payroll-bureaus").read_text(encoding="utf-8"))
    assert job["hypothesis"] == "the original"
    assert "--force" in capsys.readouterr().out


def test_force_overwrites_a_proposed_job(repo):
    park(repo, "payroll-bureaus", stage="proposed", hypothesis="the original")
    client = StubClient([written(), passed()])

    assert propose.main(["--segment", "payroll-bureaus", "--force"],
                        client=client, now=NOW) == 0

    job = json.loads(job_path(repo, "payroll-bureaus").read_text(encoding="utf-8"))
    assert job["hypothesis"] != "the original"


@pytest.mark.parametrize("stage", ["built", "launched"])
def test_force_refuses_past_proposed(repo, capsys, stage):
    park(repo, "payroll-bureaus", stage=stage)

    assert propose.main(["--segment", "payroll-bureaus", "--force"],
                        client=StubClient([]), now=NOW) == 1
    out = capsys.readouterr().out
    assert stage in out
    assert "Move that job by hand" in out


def test_force_over_a_structural_failure_parks_nothing_and_says_so(repo, capsys):
    park(repo, "payroll-bureaus", stage="proposed")

    assert propose.main(["--segment", "payroll-bureaus", "--force"],
                        client=StubClient([written(headline=TOO_LONG)]),
                        now=NOW) == 1

    # The overwritten file stays where it is: moving it would drop the segment
    # back into the backlog behind the operator's back.
    assert job_path(repo, "payroll-bureaus").exists()
    assert not job_path(repo, "payroll-bureaus", "rejected").exists()
    out = capsys.readouterr().out
    assert "Nothing was parked" in out
    assert "--force overwrote it" in out


def test_two_live_jobs_for_one_segment_are_refused_not_picked_between(repo, capsys):
    park(repo, "payroll-bureaus", stage="proposed")
    park(repo, "payroll-bureaus", stage="built")

    assert propose.main(["--segment", "payroll-bureaus", "--force"],
                        client=StubClient([]), now=NOW) == 1
    assert "two live jobs" in capsys.readouterr().out


# --------------------------------------------------------------------------
# --regate
# --------------------------------------------------------------------------

def test_regate_promotes_a_fixed_draft_and_writes_its_sidecar(repo, capsys):
    parked = park(repo, "payroll-bureaus", stage="rejected")
    client = StubClient([passed()])

    assert propose.main(["--regate", str(parked)], client=client, now=NOW) == 0

    assert not parked.exists()
    assert job_path(repo, "payroll-bureaus").exists()
    document = json.loads(sidecar_path(repo, "payroll-bureaus").read_text(encoding="utf-8"))
    assert document["selected"] == ["a01"]
    assert "approval open --segment payroll-bureaus" in capsys.readouterr().out


def test_regate_leaves_a_still_failing_draft_where_it_is(repo, capsys):
    parked = park(repo, "payroll-bureaus", stage="rejected")
    client = StubClient([refused("rule 4: it claims a customer exists")])

    assert propose.main(["--regate", str(parked)], client=client, now=NOW) == 1

    assert parked.exists()
    assert not job_path(repo, "payroll-bureaus").exists()
    assert "left in place" in capsys.readouterr().out


def test_regate_refuses_to_give_one_segment_two_jobs(repo, capsys):
    park(repo, "payroll-bureaus", stage="built")
    parked = park(repo, "payroll-bureaus", stage="rejected")

    assert propose.main(["--regate", str(parked)],
                        client=StubClient([passed()]), now=NOW) == 1
    assert parked.exists()
    assert "already has a job" in capsys.readouterr().out


def test_regate_refuses_a_draft_whose_fields_disagree_with_its_filename(repo, capsys):
    parked = park(repo, "payroll-bureaus", stage="rejected")
    job = json.loads(parked.read_text(encoding="utf-8"))
    job["segment"] = "bookkeepers"
    parked.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    assert propose.main(["--regate", str(parked)],
                        client=StubClient([passed()]), now=NOW) == 1

    assert parked.exists()
    assert not job_path(repo, "payroll-bureaus").exists()
    assert "filename says" in capsys.readouterr().out


def test_regate_of_a_missing_file_is_one_line(repo):
    with pytest.raises(SystemExit) as caught:
        propose.main(["--regate", str(repo / "nope.json")], client=StubClient([]))
    assert "no such file" in str(caught.value)


def test_regate_spends_no_call_on_a_structural_failure(repo):
    parked = park(repo, "payroll-bureaus", stage="rejected",
                  cta="BUY_IT_NOW_IMMEDIATELY")

    # StubClient with no replies: any model call is an AssertionError.
    assert propose.main(["--regate", str(parked)], client=StubClient([]), now=NOW) == 1
    assert parked.exists()


# --------------------------------------------------------------------------
# --concept and the selection report
# --------------------------------------------------------------------------

def test_a_concept_picks_its_own_backlog_row_and_is_cited_by_the_job(repo, tmp_path):
    selection(concept("a02", "bookkeepers"), path=tmp_path / "selection.json")
    client = StubClient([written(), passed()])

    assert propose.main(["--concept", "a02"], client=client, now=NOW) == 0

    job = json.loads(job_path(repo, "bookkeepers").read_text(encoding="utf-8"))
    assert job["segment"] == "bookkeepers"
    assert job["concept_id"] == "a02"
    assert job["pattern_ids"] == ["q03"]
    document = json.loads(sidecar_path(repo, "bookkeepers").read_text(encoding="utf-8"))
    assert document["selected"] == ["a02"]
    assert document["concepts"][0]["hook"] == concept()["hook"]


def test_cited_patterns_travel_with_the_concept(repo, tmp_path):
    patterns = tmp_path / "patterns.json"
    patterns.write_text(json.dumps({"schema": 1, "generated_at": NOW,
                                    "patterns": [PATTERN]}, indent=2) + "\n",
                        encoding="utf-8")
    selection(concept(), path=tmp_path / "selection.json")

    record, cited = propose.load_concept("a01", patterns_path=patterns)

    assert record["id"] == "a01"
    assert cited == [PATTERN]


def test_an_id_the_patterns_file_no_longer_holds_is_dropped(repo, tmp_path):
    patterns = tmp_path / "patterns.json"
    patterns.write_text(json.dumps({"schema": 1, "patterns": []}) + "\n",
                        encoding="utf-8")
    selection(concept(), path=tmp_path / "selection.json")

    _, cited = propose.load_concept("a01", patterns_path=patterns)
    assert cited == []


def test_a_missing_patterns_file_names_the_concept_that_cited_it(repo, tmp_path):
    selection(concept(), path=tmp_path / "selection.json")
    with pytest.raises(propose.SelectionInvalid) as caught:
        propose.load_concept("a01", patterns_path=tmp_path / "nothing.json")
    assert "a01 cites q03" in str(caught.value)


def test_a_missing_selection_report_names_the_fanout_step(repo, tmp_path):
    with pytest.raises(propose.SelectionInvalid) as caught:
        propose.load_selection()
    assert "engine.fanout" in str(caught.value)


def test_a_selection_that_selects_a_concept_it_does_not_carry_is_refused(repo, tmp_path):
    path = tmp_path / "selection.json"
    path.write_text(json.dumps({"selected": ["a09"], "concepts": [concept()]}),
                    encoding="utf-8")
    with pytest.raises(propose.SelectionInvalid) as caught:
        propose.load_selection(path)
    assert "a09" in str(caught.value)


def test_a_selection_that_is_not_json_is_refused_by_name(repo, tmp_path):
    path = tmp_path / "selection.json"
    path.write_text("{oh dear", encoding="utf-8")
    with pytest.raises(propose.SelectionInvalid) as caught:
        propose.load_selection(path)
    assert str(path) in str(caught.value)


def test_a_selection_that_selected_nothing_is_refused(repo, tmp_path):
    path = tmp_path / "selection.json"
    path.write_text(json.dumps({"selected": [], "concepts": []}), encoding="utf-8")
    with pytest.raises(propose.SelectionInvalid) as caught:
        propose.load_selection(path)
    assert "selected no concepts" in str(caught.value)


def test_a_concept_naming_no_segment_is_refused(repo, tmp_path):
    selection(concept(segment=""), path=tmp_path / "selection.json")
    with pytest.raises(propose.SelectionInvalid) as caught:
        propose.load_concept("a01")
    assert "names no segment" in str(caught.value)


def test_a_selection_fault_is_one_line_not_a_traceback(repo, capsys):
    assert propose.main(["--from-selection"], client=StubClient([])) == 1
    assert "stopped:" in capsys.readouterr().err


# --------------------------------------------------------------------------
# --from-selection
# --------------------------------------------------------------------------

def test_from_selection_proposes_every_selected_concept(repo, tmp_path):
    selection(concept("a01", "payroll-bureaus"),
              concept("a02", "bookkeepers"),
              path=tmp_path / "selection.json")
    client = StubClient([written(), passed(), written(), passed()])

    assert propose.main(["--from-selection"], client=client, now=NOW) == 0

    assert job_path(repo, "payroll-bureaus").exists()
    assert job_path(repo, "bookkeepers").exists()
    assert client.remaining == 0


def test_from_selection_writes_the_id_file_once_with_every_segment(repo, tmp_path):
    ids = tmp_path / "proposed.txt"
    selection(concept("a01", "payroll-bureaus"),
              concept("a02", "bookkeepers"),
              path=tmp_path / "selection.json")
    client = StubClient([written(), passed(), written(), passed()])

    propose.main(["--from-selection", "--id-file", str(ids)], client=client, now=NOW)

    assert ids.read_text(encoding="utf-8") == "payroll-bureaus\nbookkeepers"


def test_the_id_file_survives_a_config_error_on_the_last_concept(repo, tmp_path, capsys):
    ids = tmp_path / "proposed.txt"
    selection(concept("a01", "payroll-bureaus"),
              concept("a02", "bookkeepers"),
              concept("a03", "audit-firms"),
              path=tmp_path / "selection.json")
    client = StubClient([
        written(), passed(),
        written(), passed(),
        model.ConfigError("Gemini rejected the key: set GEMINI_API_KEY"),
    ])

    assert propose.main(["--from-selection", "--id-file", str(ids)],
                        client=client, now=NOW) == 1

    assert ids.read_text(encoding="utf-8") == "payroll-bureaus\nbookkeepers"
    assert job_path(repo, "payroll-bureaus").exists()
    assert job_path(repo, "bookkeepers").exists()
    assert not job_path(repo, "audit-firms").exists()
    assert "stopped:" in capsys.readouterr().err


def test_a_capacity_spike_moves_on_to_the_next_concept(repo, tmp_path, capsys):
    selection(concept("a01", "payroll-bureaus"),
              concept("a02", "bookkeepers"),
              path=tmp_path / "selection.json")
    client = StubClient([
        model.CapacityError("Gemini is out of capacity right now (503: busy)"),
        written(), passed(),
    ])

    assert propose.main(["--from-selection"], client=client, now=NOW) == 1

    assert not job_path(repo, "payroll-bureaus").exists()
    assert job_path(repo, "bookkeepers").exists()
    assert "moving on to the next concept" in capsys.readouterr().out


def test_a_spoken_for_segment_is_skipped_with_exit_zero(repo, tmp_path, capsys):
    park(repo, "payroll-bureaus", stage="proposed")
    selection(concept("a01", "payroll-bureaus"), path=tmp_path / "selection.json")

    # No replies at all: a skipped concept must cost nothing.
    assert propose.main(["--from-selection"], client=StubClient([]), now=NOW) == 0
    out = capsys.readouterr().out
    assert "already has a live job" in out
    assert "Nothing to do" in out


def test_a_spoken_for_segment_writes_no_id_file(repo, tmp_path):
    ids = tmp_path / "proposed.txt"
    park(repo, "payroll-bureaus", stage="proposed")
    selection(concept("a01", "payroll-bureaus"), path=tmp_path / "selection.json")

    propose.main(["--from-selection", "--id-file", str(ids)],
                 client=StubClient([]), now=NOW)

    assert not ids.exists()


def test_from_selection_carries_the_operators_other_flags_to_every_concept(repo, tmp_path):
    selection(concept("a01", "payroll-bureaus"),
              concept("a02", "bookkeepers"),
              path=tmp_path / "selection.json")
    client = StubClient([written(), passed(), written(), passed()])

    propose.main(["--from-selection", "--placement", "static-1x1"],
                 client=client, now=NOW)

    for segment_id in ("payroll-bureaus", "bookkeepers"):
        job = json.loads(job_path(repo, segment_id).read_text(encoding="utf-8"))
        assert job["placement"] == "static-1x1"


def test_a_malformed_concept_costs_the_sidecar_not_the_gated_copy(repo, tmp_path, capsys):
    """needs_numbers is what reel-engine reads to decide whether a figure may
    be spoken; a concept without one cannot be written into a selection, but
    the copy it produced has already passed the gate."""
    record = concept()
    del record["needs_numbers"]
    selection(record, path=tmp_path / "selection.json")

    assert propose.main(["--concept", "a01"],
                        client=StubClient([written(), passed()]), now=NOW) == 1

    assert job_path(repo, "payroll-bureaus").exists()
    assert not sidecar_path(repo, "payroll-bureaus").exists()
    assert "--regate" in capsys.readouterr().out


def test_the_id_file_survives_a_segment_the_backlog_does_not_carry(repo, tmp_path):
    """The finally covers every way out of the loop, not just ConfigError."""
    ids = tmp_path / "proposed.txt"
    selection(concept("a01", "payroll-bureaus"),
              concept("a02", "carpenters"),
              path=tmp_path / "selection.json")
    client = StubClient([written(), passed()])

    with pytest.raises(SystemExit):
        propose.main(["--from-selection", "--id-file", str(ids)],
                     client=client, now=NOW)

    assert ids.read_text(encoding="utf-8") == "payroll-bureaus"


def test_one_failed_concept_makes_the_whole_run_red(repo, tmp_path):
    selection(concept("a01", "payroll-bureaus"),
              concept("a02", "bookkeepers"),
              path=tmp_path / "selection.json")
    client = StubClient([
        written(headline=TOO_LONG),
        written(), passed(),
    ])

    assert propose.main(["--from-selection"], client=client, now=NOW) == 1
    assert job_path(repo, "bookkeepers").exists()


# --------------------------------------------------------------------------
# pick
# --------------------------------------------------------------------------

def test_pick_names_the_available_segments_for_an_unknown_id(repo):
    with pytest.raises(SystemExit) as caught:
        propose.pick("carpenters")
    assert "payroll-bureaus" in str(caught.value)


def test_pick_takes_the_highest_ranked_unused_row(repo):
    park(repo, "payroll-bureaus", stage="launched")
    assert propose.pick(None) == Segment(
        rank=2, id="bookkeepers", trade="Bookkeeping firms",
        questions=("invoice", "vat", "receipt"), note="bogholder, not revisor",
    )


def test_used_ids_is_approvals_own_definition():
    assert propose.used_ids is approval.used_ids


# --------------------------------------------------------------------------
# hygiene
# --------------------------------------------------------------------------

def _imported(tree) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update("%s.%s" % (node.module, a.name) for a in node.names)
    return names


def test_the_module_opens_no_socket_of_its_own():
    tree = ast.parse((ROOT / "engine" / "propose.py").read_text(encoding="utf-8"))
    imported = _imported(tree)
    for banned in ("socket", "ssl", "urllib", "http", "requests", "httpx",
                   "aiohttp", "google", "google.genai", "subprocess"):
        assert not any(name == banned or name.startswith(banned + ".")
                       for name in imported), banned


def test_the_module_reaches_the_model_only_through_write_and_gate():
    """No call site of its own: engine.write writes and engine.gate judges."""
    source = (ROOT / "engine" / "propose.py").read_text(encoding="utf-8")
    for token in ("call_model", "GeminiClient", "genai", "messages.create"):
        assert token not in source, token


def test_the_contract_flags_all_exist(repo, capsys):
    with pytest.raises(SystemExit):
        propose.main(["--help"])
    out = capsys.readouterr().out
    for flag in ("--segment", "--concept", "--from-selection", "--selection",
                 "--placement", "--regate", "--id-file", "--retries", "--force"):
        assert flag in out


def test_retries_two_allows_two_rewrites(repo):
    client = StubClient([written(), refused("rule 1"),
                         written(), refused("rule 3"),
                         written(), passed()])

    assert propose.main(["--segment", "payroll-bureaus", "--retries", "2"],
                        client=client, now=NOW) == 0
    assert client.remaining == 0
    # Each rewrite carried the reasons the attempt before it was refused.
    assert "rule 1" in client.sent(2)
    assert "rule 3" in client.sent(4)


def test_a_concept_written_for_another_segment_is_an_operator_error(repo, tmp_path, capsys):
    """--segment and --concept disagreeing is refused before any call."""
    selection(concept("a01", "payroll-bureaus"), path=tmp_path / "selection.json")

    assert propose.main(["--concept", "a01", "--segment", "bookkeepers"],
                        client=StubClient([]), now=NOW) == 1
    assert "not 'bookkeepers'" in capsys.readouterr().out


def test_nothing_is_written_outside_the_redirected_queue(repo):
    """The sidecar follows the job, not the job's ROOT-relative selection
    string - which is what a redirected queue is redirecting."""
    client = StubClient([written(), passed()])
    propose.main(["--segment", "payroll-bureaus"], client=client, now=NOW)

    job = json.loads(job_path(repo, "payroll-bureaus").read_text(encoding="utf-8"))
    assert job["creative_source"]["selection"] == "queue/proposed/payroll-bureaus.reel.json"
    assert sidecar_path(repo, "payroll-bureaus").exists()
    assert not (ROOT / "queue" / "proposed" / "payroll-bureaus.reel.json").exists()
