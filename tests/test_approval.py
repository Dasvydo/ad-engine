"""engine.approval is the swappable seam. Its decision half is pure - queue
directory membership and a small table - so all of it is testable with no
network, no `gh`, and no GitHub.

Adapted from reel-engine/tests/test_approval.py: the stages are
proposed/built/launched, the terminal move pins Meta ad ids instead of post
URLs, and a job has two sidecars (the still and the reel selection).
"""
import ast
import json
import re
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import engine.approval as approval
import engine.backlog as backlog

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "creative" / "example-job.json"

# A segment that is on queue/backlog.md; the last test here checks it stays so.
SEGMENT = "audit-firms"

NOW = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def queue(tmp_path, monkeypatch):
    """A throwaway queue/ with all four stages, wired in as the real one.

    Everything reads QUEUE through queue_dir() at call time, so patching the
    module global here redirects approval AND propose AND measure together.
    """
    for stage in approval.ALL_STAGES:
        (tmp_path / stage).mkdir()
    monkeypatch.setattr(approval, "QUEUE", tmp_path)
    return tmp_path


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def place(queue_root: Path, stage: str, segment_id: str, **overrides) -> Path:
    """Put a real, gate-passing C3 job into a stage, named for the segment.

    The example job is a trade outside the backlog by design, so its id and
    segment are restamped to the filename: the filename is the segment.
    """
    job = example()
    job["id"] = job["segment"] = segment_id
    job.update(overrides)
    dest = queue_root / stage / ("%s.json" % segment_id)
    dest.write_text(
        json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return dest


def place_sidecars(queue_root: Path, stage: str, segment_id: str) -> tuple[Path, Path]:
    still = queue_root / stage / ("%s.jpg" % segment_id)
    still.write_bytes(b"not really a jpeg")
    selection = queue_root / stage / ("%s.reel.json" % segment_id)
    selection.write_text(
        json.dumps({"schema": 1, "selected": ["a01"]}) + "\n", encoding="utf-8"
    )
    return still, selection


# --- stages and the directory ---------------------------------------------


def test_the_stages_are_the_contract_ones():
    assert approval.LIVE_STAGES == ("proposed", "built", "launched")
    assert approval.REJECTED == "rejected"
    assert approval.ALL_STAGES == ("proposed", "built", "launched", "rejected")
    assert approval.STAGE_LABEL == {
        "proposed": "stage:copy", "built": "stage:creative"}
    assert approval.GO == "go" and approval.NO == "no"
    assert approval.LAUNCHED_AT == "launched_at"


def test_the_shipped_queue_has_every_stage_directory():
    """Empty directories do not survive git; a .gitkeep in each one does."""
    for stage in approval.ALL_STAGES:
        assert (approval.queue_dir(stage) / ".gitkeep").exists(), stage


def test_used_ids_is_the_union_of_the_three_live_stages(queue):
    place(queue, "proposed", "audit-firms")
    place(queue, "built", "admin-firms")
    place(queue, "launched", "accountants")
    assert approval.used_ids() == {
        "audit-firms", "admin-firms", "accountants"}


def test_a_parked_draft_does_not_mark_its_segment_used(queue):
    """queue/rejected/ never passed the gate, so its segment stays in the
    backlog and propose picks it again."""
    place(queue, "rejected", "audit-firms")
    assert approval.used_ids() == set()


def test_a_reel_selection_sidecar_is_not_a_job(queue):
    """propose writes <segment>.reel.json beside <segment>.json. It ends in
    .json, so a bare glob would count it as a second job called
    'audit-firms.reel' - and propose would see the segment used twice."""
    place(queue, "proposed", SEGMENT)
    place_sidecars(queue, "proposed", SEGMENT)

    assert approval.used_ids() == {SEGMENT}
    assert [job.segment_id for job in approval.jobs_in("proposed")] == [SEGMENT]
    with pytest.raises(LookupError, match="no job"):
        approval.locate("%s.reel" % SEGMENT)
    assert approval.is_job_file(Path("x.json"))
    assert not approval.is_job_file(Path("x.reel.json"))
    assert not approval.is_job_file(Path("x.jpg"))


def test_jobs_in_an_absent_directory_is_empty(queue):
    (queue / "built").rmdir()
    assert approval.jobs_in("built") == []
    assert approval.used_ids() == set()


def test_locate_reports_the_stage_from_the_directory(queue):
    place(queue, "built", SEGMENT)
    job = approval.locate(SEGMENT)
    assert job.stage == "built"
    assert job.segment_id == SEGMENT
    assert job.path.name == "%s.json" % SEGMENT


def test_locate_raises_when_there_is_no_job(queue):
    with pytest.raises(LookupError, match="no job"):
        approval.locate(SEGMENT)


def test_locate_raises_when_a_segment_has_two_jobs(queue):
    """Two directories claiming one segment means its stage is undefined, and
    a `go` tap would be ambiguous. That must never be guessed."""
    place(queue, "proposed", SEGMENT)
    place(queue, "built", SEGMENT)
    with pytest.raises(LookupError, match="two jobs|undefined"):
        approval.locate(SEGMENT)


def test_a_job_knows_its_sidecars_and_its_label(queue):
    place(queue, "proposed", SEGMENT)
    job = approval.locate(SEGMENT)
    assert job.still.name == "%s.jpg" % SEGMENT
    assert job.reel_selection.name == "%s.reel.json" % SEGMENT
    assert job.still.parent == job.path.parent
    assert job.reel_selection.parent == job.path.parent
    assert job.sidecars == (job.still, job.reel_selection)
    assert job.label == "stage:copy"
    assert approval.Job("x", Path("q/built/x.json"), "built").label == "stage:creative"
    assert approval.Job("x", Path("q/launched/x.json"), "launched").label is None


def test_a_dotted_segment_id_keeps_its_sidecar_names():
    job = approval.Job("a.b", Path("q/proposed/a.b.json"), "proposed")
    assert job.still.name == "a.b.jpg"
    assert job.reel_selection.name == "a.b.reel.json"


def test_queue_dir_rejects_an_unknown_stage(queue):
    with pytest.raises(ValueError, match="unknown stage"):
        approval.queue_dir("rendered")


# --- load_job -------------------------------------------------------------


def test_load_job_reads_the_example_under_its_own_name(queue):
    dest = queue / "proposed" / "insurance-brokers.json"
    dest.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    job = approval.Job("insurance-brokers", dest, "proposed")
    assert approval.load_job(job)["headline"]["en"] == example()["headline"]["en"]


def test_load_job_refuses_a_file_whose_segment_disagrees_with_its_name(queue):
    """The filename is the segment. A file that says otherwise inside was
    renamed by hand or stamped wrong, and every later step would carry the
    wrong trade."""
    dest = queue / "proposed" / ("%s.json" % SEGMENT)
    dest.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="filename says"):
        approval.load_job(approval.Job(SEGMENT, dest, "proposed"))


def test_load_job_refuses_a_file_that_is_not_json(queue):
    dest = queue / "proposed" / ("%s.json" % SEGMENT)
    dest.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not JSON"):
        approval.load_job(approval.Job(SEGMENT, dest, "proposed"))


def test_load_job_refuses_a_json_list(queue):
    dest = queue / "proposed" / ("%s.json" % SEGMENT)
    dest.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="not an ad job"):
        approval.load_job(approval.Job(SEGMENT, dest, "proposed"))


# --- decision -------------------------------------------------------------


def test_go_on_a_proposal_builds(queue):
    place(queue, "proposed", SEGMENT)
    action = approval.decide(approval.locate(SEGMENT), approval.GO)
    assert action.kind == "build"
    assert action.job.stage == "proposed"


def test_go_on_a_built_job_launches(queue):
    """The same label, the same payload. Only the directory differs."""
    place(queue, "built", SEGMENT)
    action = approval.decide(approval.locate(SEGMENT), approval.GO)
    assert action.kind == "launch"


@pytest.mark.parametrize("stage", ["proposed", "built"])
def test_no_rejects_at_either_tap(queue, stage):
    place(queue, stage, SEGMENT)
    action = approval.decide(approval.locate(SEGMENT), approval.NO)
    assert action.kind == "reject"


def test_a_launched_job_takes_no_action(queue):
    """Terminal. There is nothing after launch, and guessing would be worse
    than stopping."""
    place(queue, "launched", SEGMENT)
    job = approval.locate(SEGMENT)
    for label in (approval.GO, approval.NO):
        with pytest.raises(ValueError, match="launched"):
            approval.decide(job, label)


def test_an_unknown_label_is_not_silently_ignored(queue):
    place(queue, "proposed", SEGMENT)
    with pytest.raises(ValueError, match="wontfix"):
        approval.decide(approval.locate(SEGMENT), "wontfix")


def test_the_decision_table_is_exactly_the_contract(queue):
    table = {}
    for stage in approval.LIVE_STAGES:
        job = approval.Job(SEGMENT, queue / stage / "x.json", stage)
        for label in (approval.GO, approval.NO):
            try:
                table[(stage, label)] = approval.decide(job, label).kind
            except ValueError:
                table[(stage, label)] = None
    assert table == {
        ("proposed", "go"): "build",
        ("proposed", "no"): "reject",
        ("built", "go"): "launch",
        ("built", "no"): "reject",
        ("launched", "go"): None,
        ("launched", "no"): None,
    }


# --- the marker -----------------------------------------------------------


def test_the_marker_is_the_contract_pattern():
    assert approval.MARKER_RE.pattern == (
        r"<!--\s*doviloop-ad:\s*([A-Za-z0-9._-]+)\s*-->")
    assert approval.marker(SEGMENT) == "<!-- doviloop-ad: %s -->" % SEGMENT


def test_the_marker_round_trips_through_a_body():
    body = "some prose\n\n%s\n\nmore prose" % approval.marker(SEGMENT)
    assert approval.segment_of(body) == SEGMENT


def test_the_marker_tolerates_loose_whitespace():
    assert approval.segment_of("<!--doviloop-ad:payroll-bureaus-->") == "payroll-bureaus"
    assert approval.segment_of("<!--  doviloop-ad:   a.b_c-1  -->") == "a.b_c-1"


def test_a_body_without_a_marker_raises():
    """An issue this engine did not open cannot be resolved to a segment, and
    guessing from the title would act on the wrong ad."""
    with pytest.raises(ValueError, match="marker"):
        approval.segment_of("I opened this by hand")
    with pytest.raises(ValueError, match="marker"):
        approval.segment_of(None)


def test_the_reel_loops_marker_is_not_ours():
    """Two repositories, two issue trackers, two markers. A reel issue pasted
    into this repository must not resolve."""
    with pytest.raises(ValueError, match="marker"):
        approval.segment_of("<!-- doviloop-job: audit-firms -->")


# --- composition ----------------------------------------------------------


def test_the_proposal_carries_copy_rationale_marker_and_still(queue):
    segment = approval.segment_named(SEGMENT)
    job = example()
    job["id"] = job["segment"] = SEGMENT
    job["concept_id"] = "a03"
    job["pattern_ids"] = ["q03", "q07"]
    title, body = approval.compose_proposal(
        segment, job, "https://example.invalid/still.jpg")

    # Derived: the title carries the segment's trade, and hardcoding it is
    # how the sibling's file rotted when the ICP lock changed which segments
    # exist.
    trade = next(x.trade for x in backlog.load() if x.id == SEGMENT)
    assert title == "Ad: %s (%s)" % (trade, SEGMENT)
    assert body.startswith(approval.marker(SEGMENT))
    assert "![still frame](https://example.invalid/still.jpg)" in body
    assert job["primary_text"]["en"] in body
    assert job["headline"]["en"] in body
    assert job["description"]["en"] in body
    assert "`reels-9x16`" in body
    assert "`guarantee`" in body
    assert "`LEARN_MORE`" in body
    assert job["hypothesis"] in body
    assert "`a03`" in body
    assert "`q03`" in body and "`q07`" in body
    # The rationale: why this segment, in the operator's own words.
    assert "Rank %d" % segment.rank in body
    for question in segment.questions:
        assert question in body
    assert segment.note in body
    # The two taps, and what each does.
    assert "`go`" in body and "build" in body
    assert "`no`" in body and "reject" in body
    # Only English goes on the issue.
    assert "NEEDS_NATIVE_PROOFREAD" not in body


def test_the_proposal_omits_the_image_line_when_there_is_no_still(queue):
    """propose.yml opens the issue before anything is rendered; build.yml
    comments the frame in later. A broken image at the top of the issue is
    worse than none."""
    segment = approval.segment_named(SEGMENT)
    job = example()
    for still_url in (None, "", "   "):
        title, body = approval.compose_proposal(segment, job, still_url)
        assert "![" not in body
        assert "](" not in body.split("## Copy")[0]
        assert title == "Ad: %s (%s)" % (segment.trade, segment.id)
        assert approval.marker(SEGMENT) in body
        assert job["headline"]["en"] in body


def test_the_proposal_omits_provenance_when_the_job_has_none(queue):
    """A hand-written job has no concept and cites no pattern; the section is
    absent rather than a row of blanks that looks like missing data."""
    segment = approval.segment_named(SEGMENT)
    job = example()
    job["concept_id"] = ""
    job["pattern_ids"] = []
    _, body = approval.compose_proposal(segment, job, None)
    assert "## Provenance" not in body
    assert "Concept" not in body

    job["concept_id"] = "a01"
    _, body = approval.compose_proposal(segment, job, None)
    assert "## Provenance" in body
    assert "Concept `a01`" in body
    assert "patterns" not in body.split("## Provenance")[1].split("## Why")[0]


def test_the_proposal_survives_bare_string_copy_and_missing_keys(queue):
    """Composition reads what is there and never raises on a shape the gate
    would have refused anyway; the issue is a view, not a validator."""
    segment = approval.segment_named(SEGMENT)
    job = {"headline": "A bare string", "primary_text": None}
    _, body = approval.compose_proposal(segment, job, None)
    assert "A bare string" in body
    assert "**Hypothesis**" not in body
    assert "## Hypothesis\n\n-\n" in body


def test_segment_named_returns_the_backlog_row():
    segment = approval.segment_named(SEGMENT)
    assert isinstance(segment, backlog.Segment)
    assert segment.id == SEGMENT
    assert len(segment.questions) == 3


def test_segment_named_raises_for_an_unlisted_id():
    with pytest.raises(LookupError, match="backlog"):
        approval.segment_named("no-such-trade")


def test_the_example_job_is_deliberately_off_the_backlog():
    """creative/example-job.json is the writer's worked example and must never
    be mistaken for a live draft, so its segment is not a backlog row."""
    with pytest.raises(LookupError, match="backlog"):
        approval.segment_named(example()["segment"])


# --- movement -------------------------------------------------------------


def test_advance_moves_the_json_and_both_sidecars_together(queue):
    place(queue, "proposed", SEGMENT)
    place_sidecars(queue, "proposed", SEGMENT)

    job = approval.advance(SEGMENT, "built")

    assert job.stage == "built"
    assert job.path == queue / "built" / ("%s.json" % SEGMENT)
    for name in ("%s.json", "%s.jpg", "%s.reel.json"):
        assert (queue / "built" / (name % SEGMENT)).exists(), name
        assert not (queue / "proposed" / (name % SEGMENT)).exists(), name
    assert json.loads(job.reel_selection.read_text(encoding="utf-8")) == {
        "schema": 1, "selected": ["a01"]}
    assert approval.locate(SEGMENT).stage == "built"


def test_advance_moves_a_job_that_has_no_sidecars(queue):
    """A copy-only job (creative_source.kind == none) has neither a still nor
    a selection; nothing is invented for it."""
    place(queue, "proposed", SEGMENT)
    job = approval.advance(SEGMENT, "built")
    assert job.stage == "built"
    assert not job.still.exists()
    assert not job.reel_selection.exists()
    assert sorted(p.name for p in (queue / "built").iterdir()) == [
        "%s.json" % SEGMENT]


def test_advance_refuses_to_land_on_an_occupied_slot(queue):
    place(queue, "proposed", SEGMENT)
    place(queue, "built", SEGMENT)
    # locate() already refuses an ambiguous segment, which is the guard here.
    with pytest.raises(LookupError):
        approval.advance(SEGMENT, "built")


def test_advance_refuses_an_unknown_stage(queue):
    place(queue, "proposed", SEGMENT)
    with pytest.raises(ValueError, match="cannot advance to 'rendered'"):
        approval.advance(SEGMENT, "rendered")
    with pytest.raises(ValueError, match="cannot advance to 'rejected'"):
        approval.advance(SEGMENT, "rejected")
    assert approval.locate(SEGMENT).stage == "proposed"


def test_advance_never_reaches_launched(queue):
    """queue/launched/ means "ad ids pinned". advance() has none to pin, so
    the only way in is launch(); the refusal names it."""
    place(queue, "built", SEGMENT)
    with pytest.raises(ValueError, match="launch --segment %s" % SEGMENT):
        approval.advance(SEGMENT, "launched")
    assert approval.locate(SEGMENT).stage == "built"


def test_launch_pins_the_ad_ids_and_records_when_it_went_live(queue):
    """launched/ is never rebuilt, so it is the one place an annotation is
    safe. The ids are the twin of the reel job's `videos` map: guessed once,
    by a human, and every measurement is an exact lookup."""
    place(queue, "built", SEGMENT)
    place_sidecars(queue, "built", SEGMENT)

    job = approval.launch(
        SEGMENT,
        {"120210": {"campaign_id": "5678", "adset_id": "91011"}},
        now=NOW,
    )

    assert job.stage == "launched"
    assert job.path == queue / "launched" / ("%s.json" % SEGMENT)
    assert job.still.exists() and job.reel_selection.exists()
    written = json.loads(job.path.read_text(encoding="utf-8"))
    assert written["ads"] == {
        "120210": {"campaign_id": "5678", "adset_id": "91011"}}
    assert written[approval.LAUNCHED_AT] == "2026-09-29T10:00:00Z"
    # An RFC3339 instant in UTC, the shape engine.measure parses.
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                        written[approval.LAUNCHED_AT])
    # The gated copy is untouched, and so is the key order: a launch is a
    # two-line diff, not a reshuffle.
    assert written["headline"] == example()["headline"]
    assert list(written) == list(example())
    assert job.path.read_text(encoding="utf-8").endswith("}\n")


def test_launch_fills_in_null_for_ids_it_was_not_given(queue):
    """Both inner keys are always present so a reader indexes them without a
    KeyError; an id not given is null, never "" and never guessed."""
    place(queue, "built", SEGMENT)
    job = approval.launch(SEGMENT, {"120210": {"campaign_id": "5678"}}, now=NOW)
    written = json.loads(job.path.read_text(encoding="utf-8"))
    assert written["ads"] == {
        "120210": {"campaign_id": "5678", "adset_id": None}}

    place(queue, "built", "accountants")
    job = approval.launch("accountants", {"7": None, 8: {"adset_id": " 9 "}}, now=NOW)
    written = json.loads(job.path.read_text(encoding="utf-8"))
    assert written["ads"] == {
        "7": {"campaign_id": None, "adset_id": None},
        "8": {"campaign_id": None, "adset_id": "9"},
    }


def test_launch_takes_now_from_the_caller_in_any_timezone(queue):
    place(queue, "built", SEGMENT)
    east = datetime(2026, 9, 29, 12, 30, 0, tzinfo=timezone(timedelta(hours=2)))
    job = approval.launch(SEGMENT, {"1": {}}, now=east)
    assert json.loads(job.path.read_text())["launched_at"] == "2026-09-29T10:30:00Z"

    place(queue, "built", "accountants")
    naive = datetime(2026, 9, 29, 10, 30, 0)  # naive is read as UTC
    job = approval.launch("accountants", {"1": {}}, now=naive)
    assert json.loads(job.path.read_text())["launched_at"] == "2026-09-29T10:30:00Z"


def test_launch_defaults_to_the_clock(queue):
    place(queue, "built", SEGMENT)
    before = datetime.now(timezone.utc).replace(microsecond=0)
    job = approval.launch(SEGMENT, {"1": {}})
    stamp = json.loads(job.path.read_text())["launched_at"]
    when = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert before <= when <= datetime.now(timezone.utc) + timedelta(seconds=1)


def test_launch_refuses_from_proposed_and_leaves_the_queue_untouched(queue):
    """A proposal has no creative to have launched. The refusal names the
    tap that gets it to built."""
    place(queue, "proposed", SEGMENT)
    place_sidecars(queue, "proposed", SEGMENT)
    with pytest.raises(ValueError, match="queue/proposed, not queue/built"):
        approval.launch(SEGMENT, {"1": {}}, now=NOW)
    assert approval.locate(SEGMENT).stage == "proposed"
    assert (queue / "proposed" / ("%s.jpg" % SEGMENT)).exists()
    assert not any((queue / "launched").glob("*"))
    written = json.loads((queue / "proposed" / ("%s.json" % SEGMENT)).read_text())
    assert written["ads"] == {} and written["launched_at"] is None


def test_launch_refuses_a_job_that_is_already_launched(queue):
    place(queue, "launched", SEGMENT, ads={"1": {"campaign_id": None, "adset_id": None}})
    with pytest.raises(ValueError, match="already pinned"):
        approval.launch(SEGMENT, {"2": {}}, now=NOW)
    written = json.loads((queue / "launched" / ("%s.json" % SEGMENT)).read_text())
    assert list(written["ads"]) == ["1"]


def test_launch_refuses_no_ad_ids(queue):
    """A launched job without an ad id is a record engine.measure can never
    look up; the stub of the reel loop's `publish` with no posts does not
    carry over."""
    place(queue, "built", SEGMENT)
    for ads in ({}, None, []):
        with pytest.raises(ValueError, match="at least one ad id"):
            approval.launch(SEGMENT, ads, now=NOW)
    assert approval.locate(SEGMENT).stage == "built"


@pytest.mark.parametrize("bad", ["", " ", "abc", "12a", "act_123", "1 2"])
def test_launch_refuses_an_ad_id_that_is_not_a_meta_id(queue, bad):
    place(queue, "built", SEGMENT)
    with pytest.raises(ValueError, match="not a Meta id"):
        approval.launch(SEGMENT, {bad: {}}, now=NOW)
    assert approval.locate(SEGMENT).stage == "built"


def test_launch_refuses_a_campaign_or_adset_id_that_is_not_a_meta_id(queue):
    place(queue, "built", SEGMENT)
    with pytest.raises(ValueError, match="campaign_id 'c1'"):
        approval.launch(SEGMENT, {"1": {"campaign_id": "c1"}}, now=NOW)
    with pytest.raises(ValueError, match="adset_id 'x'"):
        approval.launch(SEGMENT, {"1": {"adset_id": "x"}}, now=NOW)
    with pytest.raises(ValueError, match="campaign_id, adset_id"):
        approval.launch(SEGMENT, {"1": "5678"}, now=NOW)
    assert approval.locate(SEGMENT).stage == "built"


def test_launch_refuses_a_job_file_it_cannot_read_before_moving_it(queue):
    """Read, then move, then write. The sibling moved first, so a broken file
    ended up in the terminal directory with nothing written into it."""
    path = queue / "built" / ("%s.json" % SEGMENT)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="not JSON"):
        approval.launch(SEGMENT, {"1": {}}, now=NOW)
    assert path.exists()
    assert not (queue / "launched" / ("%s.json" % SEGMENT)).exists()


def test_launch_refuses_a_job_whose_segment_field_disagrees(queue):
    path = queue / "built" / ("%s.json" % SEGMENT)
    path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="filename says"):
        approval.launch(SEGMENT, {"1": {}}, now=NOW)
    assert path.exists()


def test_drop_removes_the_job_and_its_sidecars(queue):
    place(queue, "proposed", SEGMENT)
    place_sidecars(queue, "proposed", SEGMENT)

    job = approval.drop(SEGMENT)

    assert job.stage == "proposed"
    assert approval.used_ids() == set()
    assert list((queue / "proposed").iterdir()) == []
    # Not parked: a human `no` passed the gate and was simply not wanted, so
    # offering it back for --regate would be wrong.
    assert not (queue / "rejected" / ("%s.json" % SEGMENT)).exists()


def test_drop_works_from_built_too(queue):
    place(queue, "built", SEGMENT)
    approval.drop(SEGMENT)
    assert approval.used_ids() == set()


def test_drop_refuses_a_launched_job(queue):
    place(queue, "launched", SEGMENT)
    with pytest.raises(ValueError, match="launched"):
        approval.drop(SEGMENT)
    assert (queue / "launched" / ("%s.json" % SEGMENT)).exists()


def test_drop_raises_when_there_is_nothing_to_drop(queue):
    with pytest.raises(LookupError, match="no job"):
        approval.drop(SEGMENT)


# --- transport ------------------------------------------------------------


class FakeApprovals:
    """Records calls in order. Implements Approvals with no network at all -
    which is exactly the shape a Telegram bridge will take."""

    def __init__(self, body: str = "", ref: str = "7"):
        self.calls: list[tuple] = []
        self._body = body
        self._ref = ref

    def open(self, *, title, body, labels):
        self.calls.append(("open", title, body, tuple(labels)))
        return self._ref

    def comment(self, ref, body):
        self.calls.append(("comment", ref, body))

    def add_label(self, ref, label):
        self.calls.append(("add_label", ref, label))

    def remove_label(self, ref, label):
        self.calls.append(("remove_label", ref, label))

    def close(self, ref, comment):
        self.calls.append(("close", ref, comment))

    def body_of(self, ref):
        self.calls.append(("body_of", ref))
        return self._body


def test_open_composes_and_labels_the_issue_stage_copy(queue, capsys):
    place(queue, "proposed", SEGMENT)
    fake = FakeApprovals()

    assert approval.main(
        ["open", "--segment", SEGMENT,
         "--still-url", "https://x.invalid/s.jpg"],
        backend=fake,
    ) == 0

    kind, title, body, labels = fake.calls[0]
    assert kind == "open"
    trade = next(x.trade for x in backlog.load() if x.id == SEGMENT)
    assert title == "Ad: %s (%s)" % (trade, SEGMENT)
    assert approval.marker(SEGMENT) in body
    assert "https://x.invalid/s.jpg" in body
    assert example()["headline"]["en"] in body
    assert labels == ("stage:copy",)
    out = capsys.readouterr().out
    assert "issue=7" in out and "segment=%s" % SEGMENT in out


def test_open_without_a_still_url_is_the_propose_yml_case(queue):
    """The issue is opened before anything is rendered."""
    place(queue, "proposed", SEGMENT)
    fake = FakeApprovals()
    assert approval.main(["open", "--segment", SEGMENT], backend=fake) == 0
    _, _, body, _ = fake.calls[0]
    assert "![" not in body
    assert approval.marker(SEGMENT) in body


def test_open_refuses_a_job_that_is_not_a_proposal(queue, capsys):
    place(queue, "built", SEGMENT)
    fake = FakeApprovals()
    assert approval.main(["open", "--segment", SEGMENT], backend=fake) == 1
    assert fake.calls == []
    assert "queue/built" in capsys.readouterr().err


def test_open_refuses_a_segment_off_the_backlog(queue, capsys):
    """The example job's trade. There is no row to say why this segment, and
    no issue is opened on a segment nobody ranked."""
    place(queue, "proposed", "insurance-brokers")
    fake = FakeApprovals()
    assert approval.main(["open", "--segment", "insurance-brokers"], backend=fake) == 1
    assert fake.calls == []
    assert "backlog" in capsys.readouterr().err


def test_resolve_reads_the_marker_and_confirms_the_directory(queue, capsys):
    place(queue, "proposed", SEGMENT)
    fake = FakeApprovals(body=approval.marker(SEGMENT))

    assert approval.main(
        ["resolve", "--issue", "7", "--expect", "proposed"], backend=fake) == 0

    assert fake.calls == [("body_of", "7")]
    out = capsys.readouterr().out
    assert "segment=%s" % SEGMENT in out
    assert "stage=proposed" in out
    assert "path=%s" % (queue / "proposed" / ("%s.json" % SEGMENT)) in out


def test_resolve_hard_fails_when_the_directory_disagrees(queue, capsys):
    """The label said stage:copy; the job is already built. That is a corrupt
    state, and building it again would overwrite an approved creative."""
    place(queue, "built", SEGMENT)
    fake = FakeApprovals(body=approval.marker(SEGMENT))

    assert approval.main(
        ["resolve", "--issue", "7", "--expect", "proposed"], backend=fake) == 1
    assert "queue/built" in capsys.readouterr().err


def test_resolve_without_expect_accepts_any_live_stage(queue):
    for stage in approval.LIVE_STAGES:
        place(queue, stage, SEGMENT)
        fake = FakeApprovals(body=approval.marker(SEGMENT))
        assert approval.main(["resolve", "--issue", "7"], backend=fake) == 0
        (queue / stage / ("%s.json" % SEGMENT)).unlink()


def test_resolve_fails_cleanly_on_an_issue_without_a_marker(queue, capsys):
    fake = FakeApprovals(body="opened by hand")
    assert approval.main(["resolve", "--issue", "7"], backend=fake) == 1
    assert "marker" in capsys.readouterr().err


def test_resolve_writes_github_output_when_actions_is_driving(
    queue, tmp_path, monkeypatch
):
    place(queue, "proposed", SEGMENT)
    output = tmp_path / "gh-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    fake = FakeApprovals(body=approval.marker(SEGMENT))

    approval.main(["resolve", "--issue", "7"], backend=fake)

    written = output.read_text(encoding="utf-8")
    assert "segment=%s\n" % SEGMENT in written
    assert "stage=proposed\n" in written


def test_emit_prints_and_appends_to_github_output(tmp_path, monkeypatch, capsys):
    output = tmp_path / "gh-output"
    output.write_text("earlier=1\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    approval._emit(a="1", b="two")

    assert capsys.readouterr().out == "a=1\nb=two\n"
    # Appended, never truncated: earlier steps' outputs survive.
    assert output.read_text(encoding="utf-8") == "earlier=1\na=1\nb=two\n"


def test_emit_only_prints_when_actions_is_not_driving(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    approval._emit(a="1")
    assert capsys.readouterr().out == "a=1\n"


def test_advance_via_the_cli_moves_to_built(queue, capsys):
    place(queue, "proposed", SEGMENT)
    assert approval.main(
        ["advance", "--segment", SEGMENT, "--to", "built"],
        backend=FakeApprovals(),
    ) == 0
    assert approval.locate(SEGMENT).stage == "built"
    assert "stage=built" in capsys.readouterr().out


def test_advance_via_the_cli_does_not_offer_launched(queue, capsys):
    place(queue, "built", SEGMENT)
    with pytest.raises(SystemExit) as exc:
        approval.main(
            ["advance", "--segment", SEGMENT, "--to", "launched"],
            backend=FakeApprovals(),
        )
    assert exc.value.code == 2
    assert approval.locate(SEGMENT).stage == "built"


def test_label_can_swap_go_for_the_next_stage(queue):
    fake = FakeApprovals()
    assert approval.main(
        ["label", "--issue", "7", "--remove", "go", "--add", "stage:creative"],
        backend=fake,
    ) == 0
    assert fake.calls == [
        ("remove_label", "7", "go"), ("add_label", "7", "stage:creative")]


def test_drop_via_the_cli_removes_the_job(queue, capsys):
    place(queue, "proposed", SEGMENT)
    assert approval.main(
        ["drop", "--segment", SEGMENT], backend=FakeApprovals()) == 0
    assert approval.used_ids() == set()
    assert "dropped=" in capsys.readouterr().out


def test_drop_via_the_cli_refuses_a_launched_job(queue, capsys):
    place(queue, "launched", SEGMENT)
    assert approval.main(
        ["drop", "--segment", SEGMENT], backend=FakeApprovals()) == 1
    assert "launched" in capsys.readouterr().err
    assert approval.locate(SEGMENT).stage == "launched"


def test_launch_via_the_cli_takes_repeatable_ad_triples(queue, capsys, monkeypatch):
    place(queue, "built", SEGMENT)
    assert approval.main(
        ["launch", "--segment", SEGMENT,
         "--ad", "1001:2002:3003", "--ad", "1002:2002", "--ad", "1003"],
        backend=FakeApprovals(),
    ) == 0
    written = json.loads(
        (queue / "launched" / ("%s.json" % SEGMENT)).read_text(encoding="utf-8"))
    assert written["ads"] == {
        "1001": {"campaign_id": "2002", "adset_id": "3003"},
        "1002": {"campaign_id": "2002", "adset_id": None},
        "1003": {"campaign_id": None, "adset_id": None},
    }
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", written["launched_at"])
    out = capsys.readouterr().out
    assert "stage=launched" in out
    assert "ads=1001,1002,1003" in out


def test_parse_ad_arg_reads_the_three_slots():
    assert approval.parse_ad_arg("1") == (
        "1", {"campaign_id": None, "adset_id": None})
    assert approval.parse_ad_arg("1:2") == (
        "1", {"campaign_id": "2", "adset_id": None})
    assert approval.parse_ad_arg("1:2:3") == (
        "1", {"campaign_id": "2", "adset_id": "3"})
    # A blank middle slot is "not given", as launch.yml joins three inputs.
    assert approval.parse_ad_arg("1::3") == (
        "1", {"campaign_id": None, "adset_id": "3"})
    assert approval.parse_ad_arg(" 1 : 2 ") == (
        "1", {"campaign_id": "2", "adset_id": None})


def test_parse_ad_arg_refuses_a_blank_id_or_a_fourth_slot():
    with pytest.raises(ValueError, match="ID\\[:campaign_id"):
        approval.parse_ad_arg(":2:3")
    with pytest.raises(ValueError, match="at most two colons"):
        approval.parse_ad_arg("1:2:3:4")


def test_launch_via_the_cli_requires_an_ad(queue):
    place(queue, "built", SEGMENT)
    with pytest.raises(SystemExit) as exc:
        approval.main(["launch", "--segment", SEGMENT], backend=FakeApprovals())
    assert exc.value.code == 2
    assert approval.locate(SEGMENT).stage == "built"


def test_launch_via_the_cli_refuses_a_repeated_ad_id(queue, capsys):
    place(queue, "built", SEGMENT)
    assert approval.main(
        ["launch", "--segment", SEGMENT, "--ad", "1:2", "--ad", "1:3"],
        backend=FakeApprovals(),
    ) == 1
    assert "given twice" in capsys.readouterr().err
    assert approval.locate(SEGMENT).stage == "built"


def test_launch_via_the_cli_refuses_from_proposed(queue, capsys):
    place(queue, "proposed", SEGMENT)
    assert approval.main(
        ["launch", "--segment", SEGMENT, "--ad", "1"], backend=FakeApprovals()) == 1
    assert "queue/built" in capsys.readouterr().err
    assert approval.locate(SEGMENT).stage == "proposed"


def test_a_malformed_ad_arg_is_refused_before_anything_moves(queue, capsys):
    place(queue, "built", SEGMENT)
    assert approval.main(
        ["launch", "--segment", SEGMENT, "--ad", "abc"], backend=FakeApprovals()) == 1
    assert "not a Meta id" in capsys.readouterr().err
    assert (queue / "built" / ("%s.json" % SEGMENT)).exists()


def test_comment_reads_the_body_from_a_file(queue, tmp_path):
    body = tmp_path / "body.md"
    body.write_text("rendered: see the artifact", encoding="utf-8")
    fake = FakeApprovals()
    assert approval.main(
        ["comment", "--issue", "7", "--body-file", str(body)], backend=fake) == 0
    assert fake.calls == [("comment", "7", "rendered: see the artifact")]


def test_close_posts_the_reason_before_closing(queue, tmp_path):
    reason = tmp_path / "why.md"
    reason.write_text("rejected by hand", encoding="utf-8")
    fake = FakeApprovals()

    assert approval.main(
        ["close", "--issue", "7", "--comment-file", str(reason)], backend=fake) == 0
    assert fake.calls == [("close", "7", "rejected by hand")]


def test_close_without_a_comment_file_passes_an_empty_comment(queue):
    fake = FakeApprovals()
    assert approval.main(["close", "--issue", "7"], backend=fake) == 0
    assert fake.calls == [("close", "7", "")]


# --- GitHubIssues ---------------------------------------------------------


def test_github_issues_reads_the_number_out_of_the_created_url():
    seen = []

    def runner(cmd, **kwargs):
        seen.append(cmd)
        return types.SimpleNamespace(
            returncode=0,
            stdout="https://github.com/o/r/issues/42\n",
            stderr="",
        )

    backend = approval.GitHubIssues(repo="o/r", runner=runner)
    assert backend.open(title="t", body="b", labels=["stage:copy"]) == "42"
    assert seen[0][:3] == ["gh", "issue", "create"]
    assert "--repo" in seen[0] and "o/r" in seen[0]
    assert "--label" in seen[0] and "stage:copy" in seen[0]


def test_github_issues_reads_the_repo_from_the_actions_environment(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "Dasvydo/ad-engine")
    seen = []

    def runner(cmd, **kwargs):
        seen.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    approval.GitHubIssues(runner=runner).add_label("7", "go")
    assert seen == [["gh", "issue", "edit", "7", "--add-label", "go",
                     "--repo", "Dasvydo/ad-engine"]]


def test_github_issues_close_comments_first_then_closes():
    seen = []

    def runner(cmd, **kwargs):
        seen.append(cmd[:3])
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    backend = approval.GitHubIssues(repo="o/r", runner=runner)
    backend.close("7", "done")
    assert seen == [["gh", "issue", "comment"], ["gh", "issue", "close"]]

    seen.clear()
    backend.close("7", "")
    assert seen == [["gh", "issue", "close"]]


def test_github_issues_body_of_parses_the_json_view():
    def runner(cmd, **kwargs):
        assert cmd[:6] == ["gh", "issue", "view", "7", "--json", "body"]
        return types.SimpleNamespace(
            returncode=0, stdout=json.dumps({"body": approval.marker("x")}), stderr="")

    backend = approval.GitHubIssues(repo="o/r", runner=runner)
    assert backend.body_of("7") == approval.marker("x")


def test_github_issues_raises_when_no_issue_number_comes_back():
    def runner(cmd, **kwargs):
        return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")

    backend = approval.GitHubIssues(repo="o/r", runner=runner)
    with pytest.raises(RuntimeError, match="issue number"):
        backend.open(title="t", body="b", labels=[])


def test_github_issues_raises_with_the_stderr_on_failure():
    def runner(cmd, **kwargs):
        return types.SimpleNamespace(
            returncode=1, stdout="", stderr="could not resolve repo")

    backend = approval.GitHubIssues(repo="o/r", runner=runner)
    with pytest.raises(RuntimeError, match="could not resolve repo"):
        backend.body_of("7")


def test_a_missing_gh_binary_is_a_message_not_a_traceback():
    """FileNotFoundError is an OSError, not a RuntimeError, so without the
    catch in _gh it escapes main()'s handler and prints a stack trace at the
    one moment someone needs to be told to install gh."""
    def runner(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "gh")

    backend = approval.GitHubIssues(repo="o/r", runner=runner)
    with pytest.raises(RuntimeError, match="cli.github.com"):
        backend.body_of("7")


def test_the_cli_exits_one_when_gh_is_missing(queue, capsys):
    """The end the workflow actually sees: a clean exit 1 with a reason."""
    def runner(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "gh")

    backend = approval.GitHubIssues(repo="o/r", runner=runner)
    assert approval.main(["resolve", "--issue", "7"], backend=backend) == 1
    assert "gh" in capsys.readouterr().err


def test_github_issues_body_files_survive_backticks_and_newlines(tmp_path):
    """Issue bodies are multi-line markdown full of backticks. argv would
    mangle them; a file does not - and the file is gone afterwards."""
    captured = {}

    def runner(cmd, **kwargs):
        if "--body-file" in cmd:
            path = cmd[cmd.index("--body-file") + 1]
            captured["path"] = path
            captured["body"] = Path(path).read_text(encoding="utf-8")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    body = "line one\n\n```\n`backticks` and \"quotes\"\n```\n"
    approval.GitHubIssues(repo="o/r", runner=runner).comment("7", body)
    assert captured["body"] == body
    assert not Path(captured["path"]).exists()


# --- hygiene --------------------------------------------------------------


def test_the_fixture_segment_is_still_on_the_backlog():
    """reel-engine's copy of this file rotted when an ICP lock parked its
    fixture segment and three tests failed looking like an approval bug. One
    obvious failure beats three misleading ones."""
    ids = [segment.id for segment in backlog.load()]
    assert SEGMENT in ids, (
        "the fixture uses %r, no longer in queue/backlog.md (live: %s). "
        "Repoint it at a live one." % (SEGMENT, ", ".join(ids))
    )


def test_the_module_opens_no_socket_and_calls_no_model():
    """approval talks to GitHub through the gh CLI and to nothing else. The
    only process it starts is gh; the only network it needs is gh's."""
    tree = ast.parse((ROOT / "engine" / "approval.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update("%s.%s" % (node.module, a.name) for a in node.names)
    forbidden = ("urllib", "http", "socket", "requests", "httpx", "google",
                 "ssl", "engine.model")
    for name in imported:
        for bad in forbidden:
            assert not (name == bad or name.startswith(bad + ".")), name
    assert "engine.backlog" in imported
