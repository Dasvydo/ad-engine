"""The weekly run, composed: six modules, one order, one report.

This module owns no behaviour of its own, so almost nothing here re-tests what
the six modules already prove. What is worth a test is the composition:

**The order holds end to end.** A candidate discovered becomes a record on
disk, becomes a pattern, becomes a cited concept, becomes one of three
selections - and each of the three outputs is actually written.

**One bad ad does not cost the others their run.** engine.analyse already
absorbs a skip; the property has to survive being wrapped, or the weekly run
dies every time the model refuses one ad's copy.

**A thin week never overwrites a good file.** research/patterns.json is the
accumulated model of the corpus. A week that discovers nothing has learned
nothing new, not un-learned everything - and the failure mode of getting that
wrong is silent and permanent.

**The budget is enforced where it is spent.** One model call per batch of
twelve, and a cap on the ads that go into batches, is what keeps a research
Monday at four calls rather than the free tier's whole day; the cap is
checked, not assumed, and so is the batching.

**The report is byte-stable.** With `now` pinned, the same inputs write the
same selection.json, patterns.json and corpus records - which is what makes a
weekly commit diff as what changed.

Every test is offline. The Ad Library transport is a callable that returns
dictionaries, the model client dispatches on the prompt it is handed, and no
test needs a key, a token or a socket.
"""
from __future__ import annotations

import ast
import copy
import json
import re
import socket
import types
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from engine import analyse, concepts, corpus, discover, fanout, learn, model, oauth, score
from tests.stubs import json_reply

ROOT = Path(__file__).resolve().parents[1]
FANOUT_SRC = Path(fanout.__file__).read_text(encoding="utf-8")

STAMP = "2026-09-18T06:00:00Z"
MOMENT = datetime(2026, 9, 18, 6, 0, 0, tzinfo=timezone.utc)
PAGE_ID = "1007614045762121"


# ---------------------------------------------------------------------------
# The two seams: an Ad Library transport and a model client. Neither opens a
# socket.
# ---------------------------------------------------------------------------


class FakeArchive:
    """A stand-in for discover._http: `(url, token) -> dict`.

    The same body answers every call - the page search and the keyword
    search both - because this suite is about what the pipeline does with
    the results; tests/test_discover.py owns how discovery spends its ledger
    getting them. First find wins inside discover, so one body returned
    twice is still one candidate per ad.
    """

    def __init__(self, ads=(), *, raises: Exception | None = None):
        self.ads = list(ads)
        self.raises = raises
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url: str, token: str) -> dict:
        self.calls.append((url, token))
        if self.raises is not None:
            raise self.raises
        return {"data": list(self.ads), "paging": {"cursors": {"before": "b", "after": "e"}}}

    @property
    def urls(self) -> list[str]:
        return [url for url, _ in self.calls]

    def params(self, index: int = 0) -> dict:
        return {k: v[0] for k, v in parse_qs(urlsplit(self.urls[index]).query).items()}


def ad(ad_id, *, page_id=PAGE_ID, page_name="Balance", reach=9000,
       start="2026-08-19T06:00:00+0000", stop=None,
       body="Bruger du stadig timer på bogføring hver uge? Vi gør dit regnskab bedre.",
       title="Se om vi kan gøre dit regnskab bedre",
       description="AI-drevet bogholderi til små virksomheder", caption="balance.dk") -> dict:
    """One raw archived ad as the API returns it. Thirty days before STAMP by
    default, so days_running is 30 and the outlier ratio is reach-driven."""
    record = {
        "id": str(ad_id),
        "page_id": page_id,
        "page_name": page_name,
        "ad_creation_time": start,
        "ad_delivery_start_time": start,
        "ad_creative_bodies": [body],
        "ad_creative_link_titles": [title],
        "ad_creative_link_descriptions": [description],
        "ad_creative_link_captions": [caption],
        "publisher_platforms": ["facebook", "instagram"],
        "languages": ["da"],
        "eu_total_reach": reach,
        "ad_snapshot_url": (
            "https://www.facebook.com/ads/archive/render_ad/?id=%s&access_token=snap" % ad_id
        ),
    }
    if stop is not None:
        record["ad_delivery_stop_time"] = stop
    return record


# Two ads on one page, thirty days each. Reach 9000 against 3000 gives outlier
# ratios of 3.0 and 0.333: the first beat its own page, the second did not.
ADS = [ad("961046237012883", reach=9000), ad("961046237012884", reach=3000)]
# A third at 1000 makes the ratios 4.5, 0.6 and 0.167, which is what the run
# ranks by when the cap bites.
ADS_THREE = ADS + [ad("961046237012885", reach=1000)]


def record_name(ad_id: str) -> str:
    return "meta-ad-fb-%s.json" % ad_id


ANALYSIS = {
    "copy": {"words": 13},
    "hook": {
        "words": 7,
        "text": "Bruger du stadig timer på bogføring hver uge?",
        "device": "question",
    },
    "structure": ["hook", "problem", "offer", "cta"],
    "offer": {"type": "none", "text": ""},
    "proof": {"type": "none", "text": ""},
    "cta": {"type": "learn-more", "text": "Se om vi kan gøre dit regnskab bedre"},
    "objections": ["we already have an accountant"],
}


class StubModel:
    """The engine's model client, stubbed for all three steps that use one.

    One client serves the whole run - that is the point of building it once in
    fanout and handing it down - so this stub has to answer three different
    prompts. It dispatches on what each prompt opens with rather than on call
    order, so re-ordering the pipeline moves the assertions rather than
    breaking the fixture.

    Every reply is a tests.stubs reply and leads with a thinking block, exactly
    as a real one does: code reaching for content[0].text raises here rather
    than in a live run.
    """

    def __init__(self, *, refuse=(), refuse_concepts: str | None = None,
                 stop_reason: str = "end_turn"):
        self.refuse = set(refuse)
        self.refuse_concepts = refuse_concepts
        self.stop_reason = stop_reason
        self.messages = types.SimpleNamespace(create=self._create)
        self.calls: list[tuple[str, str]] = []

    def kinds(self) -> list[str]:
        return [kind for kind, _ in self.calls]

    def prompt(self, kind: str) -> str:
        return next(text for name, text in self.calls if name == kind)

    def _create(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        if re.match(r"Read the \d+ Meta ad\(s\) below", prompt):
            kind, payload = "analyse", self._analysis(prompt)
        elif re.match(r"Write \d+ ad concepts for a Meta ad engine", prompt):
            kind, payload = "concepts", self._concepts(prompt)
        elif prompt.startswith("You are the editorial scorer on an ad engine"):
            kind, payload = "score", self._scores(prompt)
        else:
            raise AssertionError("no stub answers this prompt: %r" % prompt[:120])
        self.calls.append((kind, prompt))
        return json_reply(payload, stop_reason=self.stop_reason)

    def _analysis(self, prompt: str) -> dict:
        """One analysis per id in the ADS block, or the honest per-ad refusal
        engine.analyse turns into a skip."""
        block = prompt[prompt.index("ADS\n") + 4:prompt.index("\nReturn ONLY")]
        ids = [entry["id"] for entry in json.loads(block)]
        return {"ads": {
            cid: {"refuse": "this ad's copy is empty"} if cid in self.refuse
            else copy.deepcopy(ANALYSIS)
            for cid in ids
        }}

    def _concepts(self, prompt: str) -> dict:
        """N concepts that cite the patterns and segments actually in the prompt.

        Read back out of the prompt rather than hard-coded, because the ids
        depend on what this run's corpus produced - a concept citing an
        invented pattern is rejected by engine.concepts, correctly.
        """
        if self.refuse_concepts:
            return {"refuse": self.refuse_concepts}
        n = int(re.match(r"Write (\d+) ad concepts", prompt).group(1))
        patterns = sorted(set(re.findall(r'"id": "(q\d+)"', prompt)))
        segments = re.findall(r"^  \[([^\]]+)\]", prompt, re.M)
        assert patterns, "the concepts prompt carried no patterns"
        assert segments, "the concepts prompt carried no segments"
        written = []
        for index in range(n):
            segment = segments[index % len(segments)]
            written.append({
                "segment": segment,
                "angle": "the %s request that arrives every month" % segment,
                # No digits and no number words: engine/gate.py's claims policy
                # hard-fails those, and score refuses a concept that would die
                # at the gate.
                "hook": "The %s inbox asks for the same record again." % segment,
                "pattern_ids": [patterns[index % len(patterns)]],
                "placement": concepts.PLACEMENTS[index % len(concepts.PLACEMENTS)],
                "offer": "none",
                "needs_numbers": False,
            })
        return {"concepts": written}

    def _scores(self, prompt: str) -> dict:
        """Every concept in the one call gets the same editorial score.

        Read from after the CONCEPTS: marker, because the rubric's own worked
        example of the answer shape carries an id too.
        """
        payload = prompt.split("CONCEPTS:", 1)[-1]
        ids = re.findall(r'"id": "(a\d+)"', payload)
        return {"scores": [{"id": i, "score": 0.8, "reason": "stubbed"} for i in ids]}


class NoModel:
    """A client that fails the test if anything asks it for a call."""

    def __init__(self):
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        raise AssertionError("this path must not call a model")


# ---------------------------------------------------------------------------
# The repository the run reads and writes
# ---------------------------------------------------------------------------

BACKLOG = """# Segment backlog

| rank | id | trade | questions | note |
|---|---|---|---|---|
| 1 | payroll-bureaus | Payroll bureaus | payslip, holiday, tax-code | all lookups |
| 2 | bookkeepers | Bookkeeping firms | invoice, vat, receipt | all lookups |
| 3 | admin-firms | Outsourced back-office | invoice, scope, document | all lookups |
| 4 | audit-firms | Audit firms | deadline, fee, filing | all lookups |
"""

SEEDS = """
countries: [DK]
pages:
  - id: balance-dk
    name: Balance
    page_id: "1007614045762121"
    origin: icp-adjacent
queries:
  - regnskab
"""

# Seeds that ask discovery for nothing at all.
SEEDS_EMPTY = """
countries: [DK]
pages: []
queries: []
"""

# A seeds file that watches a competitor by page id, so the note about
# watching none of them does not fire.
SEEDS_WITH_COMPETITOR = """
countries: [DK]
pages:
  - id: balance-dk
    name: Balance
    page_id: "1007614045762121"
    origin: icp-adjacent
  - id: fyxer
    name: Fyxer
    page_id: "222"
    origin: competitor
    countries: [GB]
queries:
  - regnskab
"""


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    """No test here has a key or a token, and none may need one."""
    for name in model.KEY_NAMES + (oauth.META_ACCESS_TOKEN, oauth.META_TOKEN_ISSUED):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_sockets(monkeypatch):
    """Every test in this file runs with the network switched off at the
    socket, so a step that reached for one fails here rather than in CI."""
    def exploding(*args, **kwargs):
        raise AssertionError("the research run opened a socket")

    monkeypatch.setattr(socket, "socket", exploding)
    monkeypatch.setattr(socket, "create_connection", exploding)


@pytest.fixture
def repo(tmp_path) -> Path:
    """A stand-in repository: a corpus directory, a backlog, a seeds file, an
    empty queue and an empty creative/ so the scorer reads nothing real."""
    (tmp_path / "research" / "corpus").mkdir(parents=True)
    (tmp_path / "queue").mkdir()
    (tmp_path / "creative").mkdir()
    (tmp_path / "backlog.md").write_text(BACKLOG, encoding="utf-8")
    (tmp_path / "seeds.yaml").write_text(SEEDS, encoding="utf-8")
    return tmp_path


def paths(repo: Path) -> dict:
    """Every path the run touches, redirected into the stand-in repository.

    `evidence` is passed explicitly so the scorer reads an empty attestation
    set rather than the real claims/evidence.json.
    """
    return {
        "seeds_path": repo / "seeds.yaml",
        "corpus_root": repo / "research" / "corpus",
        "patterns_path": repo / "research" / "patterns.json",
        "backlog_path": repo / "backlog.md",
        "queue_root": repo / "queue",
        "creative_root": repo / "creative",
        "media_root": repo / "research" / "media",
        "report_path": repo / "research" / "selection.json",
        "evidence": {},
    }


def ad_client(api: FakeArchive, **kw) -> discover.AdLibraryClient:
    return discover.AdLibraryClient("test-token", transport=api, **kw)


def run_with(repo: Path, *, api=None, client=None, **over):
    kwargs = paths(repo)
    kwargs.update(
        client=client if client is not None else StubModel(),
        ad_client=ad_client(api if api is not None else FakeArchive(ADS)),
        now=STAMP,
    )
    kwargs.update(over)
    return fanout.run(**kwargs)


def plan_with(repo: Path, **over):
    kwargs = {
        "seeds_path": repo / "seeds.yaml",
        "corpus_root": repo / "research" / "corpus",
        "patterns_path": repo / "research" / "patterns.json",
        "backlog_path": repo / "backlog.md",
        "media_root": repo / "research" / "media",
        "now": STAMP,
    }
    kwargs.update(over)
    return fanout.plan(**kwargs)


def report_on_disk(repo: Path) -> dict:
    return json.loads((repo / "research" / "selection.json").read_text(encoding="utf-8"))


def corpus_files(repo: Path) -> list[str]:
    return sorted(p.name for p in (repo / "research" / "corpus").glob("*.json"))


# ---------------------------------------------------------------------------
# 0. The constants are the contract's
# ---------------------------------------------------------------------------


def test_the_contract_constants():
    assert fanout.SCHEMA == 1
    assert fanout.DEFAULT_REPORT == ROOT / "research" / "selection.json"
    # Two text batches, exactly: the default is the batch size's, not its own.
    assert fanout.DEFAULT_MAX_ADS == 24 == 2 * analyse.BATCH_SIZE
    assert fanout.COST_KEYS == ("model_calls", "ad_library_calls")


# ---------------------------------------------------------------------------
# 1. The composition: six modules, one order, three outputs
# ---------------------------------------------------------------------------


def test_the_run_writes_the_corpus_the_patterns_and_the_selection(repo):
    """The brief's scenario: an empty corpus, two seeded ads, and every
    output on disk with ok true."""
    report = run_with(repo)

    assert report.ok, report.failed
    assert corpus_files(repo) == [
        record_name("961046237012883"), record_name("961046237012884"),
    ]

    document = learn.load(repo / "research" / "patterns.json")
    assert document["corpus_size"] == 2
    assert document["patterns"], "the learn step wrote a document with no patterns"

    on_disk = report_on_disk(repo)
    assert on_disk["schema"] == fanout.SCHEMA
    assert on_disk["generated_at"] == STAMP
    assert on_disk["ok"] is True
    assert on_disk["dry_run"] is False
    assert len(on_disk["concepts"]) == concepts.DEFAULT_N
    assert len(on_disk["selected"]) == score.TOP_N


def test_a_candidate_becomes_a_record_a_pattern_a_concept_and_a_selection(repo):
    """The chain the whole front end exists for, checked link by link."""
    report = run_with(repo)

    assert report.counts["discovered"] == 2
    assert report.counts["new"] == 2
    assert report.counts["analysed"] == 2
    assert report.counts["corpus"] == 2
    assert report.counts["patterns"] >= 1
    assert report.counts["concepts"] == concepts.DEFAULT_N
    assert report.counts["selected"] == score.TOP_N

    # A selected concept cites a pattern that was measured off an ad this run
    # actually stored - not an id the model invented.
    document = learn.load(repo / "research" / "patterns.json")
    measured = {p["id"]: p for p in document["patterns"]}
    stored = {record.id for record in corpus.load_all(repo / "research" / "corpus")}
    winners = [c for c in report.concepts if c["id"] in report.selected]
    assert len(winners) == score.TOP_N
    for concept in winners:
        assert concept["pattern_ids"]
        for pattern_id in concept["pattern_ids"]:
            assert pattern_id in measured
            assert set(measured[pattern_id]["evidence"]) <= stored


def test_the_records_written_are_what_discovery_found_and_the_model_read(repo):
    """The record on disk is the candidate's facts plus the model's reading:
    the Ad Library url, the page's outlier ratio, and a fetched_at pinned to
    the run's clock rather than the machine's."""
    run_with(repo)

    record = corpus.load(repo / "research" / "corpus" / record_name("961046237012883"))
    assert record.url == discover.LIBRARY_URL + "961046237012883"
    assert record.origin == "icp-adjacent"
    assert record.metrics["days_running"] == 30
    assert record.analysis["outlier_ratio"] == 3.0
    assert record.analysis["hook"]["device"] == "question"
    assert record.analysis["creative"] == {"kind": analyse.TEXT_ONLY}
    assert record.fetched_at == STAMP


def test_it_calls_the_modules_rather_than_reimplementing_them():
    """It orchestrates. A prompt, a transport or a schema defined here would
    mean a second place to change when one of the six changes."""
    tree = ast.parse(FANOUT_SRC)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "engine"
        for alias in node.names
    }
    assert {"discover", "analyse", "corpus", "learn", "concepts", "score", "backlog"} <= imported

    # No model call and no transport of its own: it builds one client and hands
    # it down. Every call in this engine goes through engine.model, and the
    # modules this one composes are where that happens - so a provider SDK or
    # an HTTP library imported here would mean a seventh place to change the
    # day either moves.
    top = {
        name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for name in [alias.name for alias in node.names]
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not top & {"google", "urllib", "http", "requests", "httpx", "socket",
                      "ssl", "subprocess", "yaml"}
    assert "call_model" not in FANOUT_SRC
    assert "INSTRUCTION" not in FANOUT_SRC and "RUBRIC" not in FANOUT_SRC
    # And nothing here fetches a snapshot or names the page that renders one.
    assert "ads/library" not in FANOUT_SRC and "snapshot_url" not in FANOUT_SRC


def test_one_client_serves_every_step_that_needs_one(repo):
    stub = StubModel()
    run_with(repo, client=stub)

    # Two ads in ONE batch, one concepts call, one editorial call. Never one
    # call per ad and never one per concept - that is the free tier's daily
    # allowance, spent twelve times over to buy the same answer.
    assert stub.kinds() == ["analyse", "concepts", "score"]


def test_the_analysis_is_batched_and_the_batch_is_one_call(repo):
    """Twelve is one call. Thirteen is two. The ledger counts calls, not ads."""
    ads = [ad("96104623701%04d" % i, reach=1000 * (i + 1)) for i in range(13)]
    stub = StubModel()
    report = run_with(repo, api=FakeArchive(ads), client=stub, max_ads=13)

    assert report.counts["analysed"] == 13
    assert stub.kinds().count("analyse") == 2
    assert report.cost["model_calls"] == 2 + 1 + 1


def test_no_transport_call_ever_targets_the_ads_library_page(repo):
    """The scope's rule, re-checked at the top of the pipeline: the archive
    hands back a snapshot url for every ad, and nothing requests it."""
    api = FakeArchive(ADS)
    run_with(repo, api=api)

    assert api.calls, "discovery made no call at all"
    for url in api.urls:
        assert url.startswith(discover.API), url
        assert "facebook.com/ads/library" not in url
        assert "render_ad" not in url
        assert "access_token" not in url


# ---------------------------------------------------------------------------
# 2. A skipped or failing ad does not abort the run
# ---------------------------------------------------------------------------


def test_an_ad_the_model_refused_is_reported_and_the_run_carries_on(repo):
    report = run_with(
        repo, api=FakeArchive(ADS_THREE), client=StubModel(refuse={"fb-961046237012884"})
    )

    assert report.counts["analysed"] == 2
    assert report.ok, "a skip is not a failure"
    assert any("fb-961046237012884" in line and "empty" in line for line in report.skipped)
    assert all(line.startswith("analyse: ") for line in report.skipped if "961046237012884" in line)
    assert not (repo / "research" / "corpus" / record_name("961046237012884")).exists()
    # And the run still produced its three concepts from what it could read.
    assert report.counts["selected"] == score.TOP_N
    # A refusal the model answered with is a call that was spent: the batch
    # is still one call.
    assert report.cost["model_calls"] == 1 + 1 + 1


def test_a_record_that_cannot_be_written_does_not_cost_the_others_their_place(
    repo, monkeypatch
):
    """The same property one step further down: an unwritable record is one
    record, not the batch."""
    real = corpus.save

    def flaky(record, root=None):
        if record["id"] == "fb-961046237012885":
            raise OSError("no space left on device")
        return real(record, root)

    monkeypatch.setattr(corpus, "save", flaky)
    report = run_with(repo, api=FakeArchive(ADS_THREE))

    assert report.counts["analysed"] == 2
    assert any(
        "fb-961046237012885" in line and "no space left" in line for line in report.skipped
    )
    assert report.counts["corpus"] == 2
    assert report.counts["selected"] == score.TOP_N


def test_every_skip_is_carried_into_the_committed_report(repo):
    """The report is the record. A skip that only reached stderr is a skip
    nobody reads on a Monday morning six weeks later."""
    report = run_with(
        repo, api=FakeArchive(ADS_THREE), client=StubModel(refuse={"fb-961046237012885"})
    )

    on_disk = report_on_disk(repo)
    assert on_disk["skipped"] == report.skipped
    # The refused ad, and the note that no competitor is seeded.
    assert len(on_disk["skipped"]) >= 2
    assert on_disk["ok"] is True


def test_a_days_window_that_is_not_positive_is_reported_not_raised(repo):
    """engine.discover refuses --days 0 by ValueError; the run reports it as
    a discovery failure and still learns from what is on disk."""
    run_with(repo)
    api = FakeArchive(ADS)

    report = run_with(repo, api=api, days=0)

    assert not report.ok
    assert any(line.startswith("discover: ") and "days" in line for line in report.failed)
    assert api.calls == []
    assert report.counts["corpus"] == 2
    assert report.counts["selected"] == score.TOP_N


# ---------------------------------------------------------------------------
# 3. The budget: the cap is spent on the best ads, and never twice
# ---------------------------------------------------------------------------


def test_only_max_ads_are_analysed_best_outlier_ratio_first(repo):
    stub = StubModel()
    report = run_with(repo, api=FakeArchive(ADS_THREE), client=stub, max_ads=2)

    assert report.counts["discovered"] == 3
    assert report.counts["new"] == 3
    assert report.counts["analysed"] == 2
    assert stub.kinds().count("analyse") == 1

    # The two that beat their own page, not the two that sorted first.
    assert corpus_files(repo) == [
        record_name("961046237012883"), record_name("961046237012884"),
    ]
    assert report.ok


def test_fresh_candidates_rank_by_outlier_ratio_then_days_running_then_id(repo):
    """Three ads on three different pages have no baseline, so every ratio is
    NO_BASELINE and the tie falls to days running, then to id. Found through
    the query, since none of the pages is seeded."""
    ads = [
        ad("333", page_id="3", page_name="C", start="2026-08-19T06:00:00+0000"),  # 30 days
        ad("111", page_id="1", page_name="A", start="2026-07-20T06:00:00+0000"),  # 60 days
        ad("222", page_id="2", page_name="B", start="2026-08-19T06:00:00+0000"),  # 30 days
    ]
    report = run_with(repo, api=FakeArchive(ads), max_ads=2)

    assert report.counts["discovered"] == 3
    assert corpus_files(repo) == [record_name("111"), record_name("222")]
    for record in corpus.load_all(repo / "research" / "corpus"):
        assert record.analysis["outlier_ratio"] == discover.NO_BASELINE


def test_a_candidate_already_in_the_corpus_is_never_analysed_twice(repo):
    first = StubModel()
    run_with(repo, client=first)
    assert first.kinds().count("analyse") == 1
    before = {
        p.name: p.read_bytes() for p in (repo / "research" / "corpus").glob("*.json")
    }

    second = StubModel()
    again = run_with(repo, client=second)

    assert second.kinds().count("analyse") == 0, "a second call bought a record we had"
    assert again.counts["discovered"] == 2
    assert again.counts["new"] == 0
    assert again.counts["analysed"] == 0
    assert again.counts["corpus"] == 2
    assert again.ok
    # And nothing in the corpus was rewritten, so the committed files do not
    # churn `fetched_at` on every weekly run.
    after = {
        p.name: p.read_bytes() for p in (repo / "research" / "corpus").glob("*.json")
    }
    assert after == before


def test_the_report_counts_what_the_run_spent(repo):
    report = run_with(repo)

    # One batch of two ads, one concepts call, one editorial call.
    assert report.cost["model_calls"] == 3
    # One page search and one keyword search, one result page each - and the
    # estimate priced two searches at up to two pages each before the run.
    assert report.cost["ad_library_calls"] == 2
    assert report.estimate["searches"] == 2
    assert report.estimate["ad_library_calls"] == 2 * discover.DEFAULT_MAX_PAGES
    assert report.estimate["budget"] == discover.HOURLY_BUDGET_CALLS


def test_the_ad_library_ledger_is_this_runs_delta_not_the_clients_total(repo):
    """A client handed in with calls already on its ledger reports only what
    this run spent, so a shared quota is not counted twice."""
    api = FakeArchive(ADS)
    client = ad_client(api, quota=discover.Quota(50, spent=5))

    report = run_with(repo, ad_client=client)

    assert client.quota.spent == 7
    assert report.cost["ad_library_calls"] == 2


def test_a_budget_the_seeds_cannot_fit_refuses_discovery_and_keeps_nothing_partial(repo):
    """engine.discover charges before the socket and raises rather than
    returning half; the run reports it and learns from the corpus it had."""
    run_with(repo)
    api = FakeArchive(ADS)

    report = run_with(repo, api=api, ad_client=ad_client(api, budget=1))

    assert not report.ok
    assert any(line.startswith("discover: ") and "budget" in line for line in report.failed)
    assert report.counts["discovered"] == 0
    assert report.cost["ad_library_calls"] == 1
    assert report.counts["selected"] == score.TOP_N


def test_days_narrows_the_window_discovery_asks_for(repo):
    api = FakeArchive(ADS)
    run_with(repo, api=api, days=7)

    for index in range(len(api.calls)):
        assert api.params(index)["ad_delivery_date_min"] == "2026-09-11"


# ---------------------------------------------------------------------------
# 4. A thin week never overwrites a good file
# ---------------------------------------------------------------------------


def test_a_week_that_discovers_nothing_leaves_the_patterns_file_alone(repo):
    run_with(repo)  # a good week, which writes patterns.json
    good = (repo / "research" / "patterns.json").read_text(encoding="utf-8")

    (repo / "seeds.yaml").write_text(SEEDS_EMPTY, encoding="utf-8")
    api = FakeArchive([])
    report = run_with(repo, api=api)

    assert (repo / "research" / "patterns.json").read_text(encoding="utf-8") == good
    assert not report.ok, "a week that discovered nothing must not report success"
    assert any("seeds.yaml" in line and "asks for nothing" in line for line in report.failed)
    assert any("page_id" in line for line in report.failed)
    assert api.calls == []


def test_a_seeded_search_that_returns_nothing_names_the_window_and_the_countries(repo):
    run_with(repo)

    report = run_with(repo, api=FakeArchive([]), days=14)

    assert not report.ok
    line = next(l for l in report.failed if l.startswith("discover: "))
    assert "returned no candidate" in line
    assert "14 day(s)" in line and "--days" in line
    assert "countries" in line and "seeds.yaml" in line


def test_discovery_finding_nothing_does_not_stop_the_run_using_what_it_has(repo):
    """Reported, and then carried past. The corpus still holds evidence, and a
    week with no new ad can still fan out."""
    run_with(repo)

    report = run_with(repo, api=FakeArchive([]))

    assert report.counts["discovered"] == 0
    assert report.counts["corpus"] == 2
    assert report.counts["selected"] == score.TOP_N, "it stopped instead of continuing"
    assert not report.ok, "a degraded run still has to go red"


def test_a_failed_discovery_still_learns_from_the_corpus_on_disk_and_exits_1(repo):
    """An API error mid-discovery - a dead token, a 500 - is a failed stage,
    not a dead run: the concepts and the selection still come out of the
    corpus on disk, the report says what failed, and the exit code is 1."""
    run_with(repo)
    api = FakeArchive(ADS, raises=RuntimeError("HTTP 500 from graph.facebook.com"))

    report = run_with(repo, api=api)

    assert not report.ok
    failure = next(l for l in report.failed if l.startswith("discover: "))
    assert "HTTP 500" in failure
    assert "test-token" not in failure, "the token leaked into the report"
    assert report.counts["discovered"] == 0
    assert report.counts["corpus"] == 2
    assert report.counts["concepts"] == concepts.DEFAULT_N
    assert report.counts["selected"] == score.TOP_N
    # The one call that failed was still charged: the ledger counts before
    # the socket.
    assert report.cost["ad_library_calls"] == 1

    on_disk = report_on_disk(repo)
    assert on_disk["ok"] is False
    assert on_disk["failed"] == report.failed
    assert len(on_disk["selected"]) == score.TOP_N


def test_a_corpus_too_small_to_support_a_pattern_writes_nothing(repo):
    """learn.MIN_SUPPORT is 2. One ad cannot make a pattern, and a patterns
    document with no patterns in it is not a fact - it is a loss."""
    report = run_with(repo, api=FakeArchive(ADS[:1]))

    assert report.counts["corpus"] == 1
    assert report.counts["patterns"] == 0
    assert not (repo / "research" / "patterns.json").exists()
    assert not report.ok
    assert any("%d or more" % learn.MIN_SUPPORT in line for line in report.failed)
    # Reported, and the corpus it did build is still on disk for next week.
    assert (repo / "research" / "corpus" / record_name("961046237012883")).exists()


def test_a_corpus_below_min_support_leaves_an_existing_patterns_file_untouched(repo):
    """The brief's case: a good patterns.json from an earlier week, and a
    corpus that this week cannot support a pattern from. The file stays, the
    reason is reported, and the run goes red."""
    good_repo = repo / "earlier"
    for name in ("research/corpus", "queue", "creative"):
        (good_repo / name).mkdir(parents=True)
    (good_repo / "backlog.md").write_text(BACKLOG, encoding="utf-8")
    (good_repo / "seeds.yaml").write_text(SEEDS, encoding="utf-8")
    run_with(good_repo)
    good = (good_repo / "research" / "patterns.json").read_text(encoding="utf-8")
    (repo / "research" / "patterns.json").write_text(good, encoding="utf-8")

    report = run_with(repo, api=FakeArchive(ADS[:1]), client=StubModel())

    assert (repo / "research" / "patterns.json").read_text(encoding="utf-8") == good
    assert not report.ok
    line = next(l for l in report.failed if l.startswith("learn: "))
    assert "1 corpus record(s)" in line
    assert "%d or more" % learn.MIN_SUPPORT in line
    assert str(repo / "research" / "patterns.json") in line
    assert "left exactly as it is" in line
    assert report.counts["patterns"] == 0
    assert report.counts["concepts"] == 0
    assert report_on_disk(repo)["ok"] is False


def test_origin_narrows_what_the_learn_step_counts(repo):
    """Every seeded ad is icp-adjacent, so learning from competitors only
    counts nothing - and says so rather than writing an empty document."""
    report = run_with(repo, origin="competitor")

    assert not report.ok
    line = next(l for l in report.failed if l.startswith("learn: "))
    assert "0 corpus record(s) of origin 'competitor'" in line
    assert not (repo / "research" / "patterns.json").exists()
    assert report.counts["corpus"] == 2


def test_an_unchanged_corpus_does_not_rewrite_the_patterns_file(repo):
    """learn stamps generated_at from the corpus, not the clock, so a second
    run over the same records is the same bytes - and the same bytes are not
    a write."""
    run_with(repo)
    path = repo / "research" / "patterns.json"
    good = path.read_bytes()
    path.write_bytes(good)  # settle the clock so a rewrite would be visible
    stamp = path.stat().st_mtime_ns

    again = run_with(repo)

    assert again.ok
    assert path.read_bytes() == good
    assert path.stat().st_mtime_ns == stamp


def test_a_missing_model_key_stops_the_run_before_it_spends_an_ad_library_call(repo):
    api = FakeArchive(ADS)

    # No client is injected here, deliberately: this is the one test that lets
    # the run build its own and find there is no key to build it with.
    report = fanout.run(**paths(repo), ad_client=ad_client(api), now=STAMP)

    assert not report.ok
    assert any("GEMINI_API_KEY" in line for line in report.failed)
    assert any("aistudio.google.com" in line for line in report.failed)
    assert api.calls == [], "it spent a call on a discovery it could never analyse"
    assert report_on_disk(repo)["ok"] is False


def test_a_missing_meta_token_is_a_reported_discovery_failure_not_a_traceback(repo):
    """No ad client injected: the run builds one through engine.oauth, which
    refuses by name with no token in the environment. Reported as the
    discovery stage failing; the model key is never the thing that leaks."""
    run_with(repo)

    report = fanout.run(**paths(repo), client=StubModel(), now=STAMP)

    assert not report.ok
    line = next(l for l in report.failed if l.startswith("discover: "))
    assert oauth.META_ACCESS_TOKEN in line
    assert report.counts["corpus"] == 2
    assert report.counts["selected"] == score.TOP_N
    assert report.cost["ad_library_calls"] == 0


def test_a_model_refusal_in_concepts_is_reported_and_the_report_is_still_written(repo):
    stub = StubModel(refuse_concepts="every segment's questions read as judgement calls")
    report = run_with(repo, client=stub)

    assert not report.ok
    line = next(l for l in report.failed if l.startswith("concepts: "))
    assert "refused" in line and "judgement calls" in line
    # The corpus and the patterns were still written: the failure is the
    # concepts stage, not the research before it.
    assert report.counts["corpus"] == 2
    assert report.counts["patterns"] >= 1
    assert (repo / "research" / "patterns.json").exists()
    assert report.counts["concepts"] == 0
    assert report.counts["selected"] == 0
    assert stub.kinds() == ["analyse", "concepts"], "it scored concepts it never had"
    # Charged: the model answered before the reply was refused.
    assert report.cost["model_calls"] == 2

    on_disk = report_on_disk(repo)
    assert on_disk["ok"] is False
    assert on_disk["concepts"] == []
    assert on_disk["selected"] == []
    assert on_disk["scorecards"] == []
    assert on_disk["failed"] == report.failed


def test_a_truncated_editorial_reply_is_a_reported_score_failure_with_the_concepts_kept(repo):
    """The concepts cost a call; an operator who has to re-run wants to see
    them even though the scorer refused the reply."""
    class Truncating(StubModel):
        def _create(self, **kwargs):
            reply = super()._create(**kwargs)
            if self.calls[-1][0] == "score":
                return json_reply({"scores": []}, stop_reason="max_tokens")
            return reply

    report = run_with(repo, client=Truncating())

    assert not report.ok
    assert any(l.startswith("score: ") and "max_tokens" in l for l in report.failed)
    assert len(report.concepts) == concepts.DEFAULT_N
    assert report.selected == []
    assert report_on_disk(repo)["concepts"] == report.concepts


def test_a_provider_fault_is_reported_as_the_stage_it_hit(repo):
    """model.ConfigError (a CapacityError is one) propagates out of the
    modules as itself, and the run names the stage rather than dying."""
    class OutOfCapacity(StubModel):
        def _create(self, **kwargs):
            if kwargs["messages"][0]["content"].startswith("Read the"):
                raise model.CapacityError("Gemini is out of capacity right now (503)")
            return super()._create(**kwargs)

    run_with(repo)  # a corpus to fall back on
    (repo / "research" / "corpus" / record_name("961046237012884")).unlink()
    report = run_with(repo, client=OutOfCapacity())

    assert not report.ok
    assert any(l.startswith("analyse: ") and "capacity" in l for l in report.failed)
    # The corpus it had still fanned out - one record short, so the patterns
    # step is the next stage to say so.
    assert report.counts["corpus"] == 1


def test_the_report_is_written_even_when_a_stage_failed(repo):
    """A stale report is how the same three concepts get filed twice."""
    (repo / "seeds.yaml").write_text(SEEDS_EMPTY, encoding="utf-8")

    report = run_with(repo, api=FakeArchive([]), client=NoModel())

    on_disk = report_on_disk(repo)
    assert on_disk["ok"] is False
    assert on_disk["selected"] == []
    assert on_disk["failed"] == report.failed
    assert on_disk["generated_at"] == STAMP


# ---------------------------------------------------------------------------
# 5. The selection report
# ---------------------------------------------------------------------------


def test_the_report_carries_a_scorecard_for_every_concept_not_only_the_winners(repo):
    """A selection nobody can audit is an oracle."""
    report = run_with(repo)
    on_disk = report_on_disk(repo)

    assert len(on_disk["scorecards"]) == concepts.DEFAULT_N
    assert [c["id"] for c in on_disk["scorecards"] if c["selected"]] == on_disk["selected"]
    for card in on_disk["scorecards"]:
        assert card["verdict"], "a scorecard with no verdict cannot be argued with"
        assert set(card["scores"]) == set(score.DIMENSIONS)
        assert card["placement"] in concepts.PLACEMENTS


def test_the_report_carries_the_concept_records_the_winners_are(repo):
    """The ids alone would point at nothing: the concepts exist in memory for
    one run, and the step that files them as jobs reads this file."""
    report = run_with(repo)
    on_disk = report_on_disk(repo)

    by_id = {c["id"]: c for c in on_disk["concepts"]}
    assert len(by_id) == concepts.DEFAULT_N
    for concept_id in on_disk["selected"]:
        concept = by_id[concept_id]
        assert set(concept) == set(concepts.KEYS)
        assert concept["segment"] and concept["hook"] and concept["pattern_ids"]
        assert concept["placement"] in concepts.PLACEMENTS


def test_the_winners_are_spread_across_segments(repo):
    """Three winners are three ads for three trades, not three for one -
    score's spread, checked through the composition."""
    report = run_with(repo)
    by_id = {c["id"]: c for c in report.concepts}
    segments = [by_id[i]["segment"] for i in report.selected]
    assert len(set(segments)) == len(segments) == score.TOP_N


def test_the_report_is_written_the_way_every_committed_file_here_is(repo):
    """Sorted keys and a trailing newline, so a weekly commit diffs as the
    fields that changed rather than as a reordered blob."""
    run_with(repo)
    text = (repo / "research" / "selection.json").read_text(encoding="utf-8")

    assert text.endswith("}\n")
    assert text == learn.dumps(json.loads(text))
    assert text == json.dumps(json.loads(text), sort_keys=True, indent=2,
                              ensure_ascii=False) + "\n"


def test_the_report_carries_every_key_the_summary_and_the_workflow_read(repo):
    on_disk = report_on_disk(run_with(repo) and repo)
    assert set(on_disk) == {
        "schema", "generated_at", "dry_run", "ok", "counts", "cost", "estimate",
        "failed", "skipped", "selected", "concepts", "scorecards",
    }
    assert set(on_disk["cost"]) == set(fanout.COST_KEYS)
    assert {"discovered", "new", "analysed", "corpus", "patterns", "concepts",
            "selected", "seed_pages", "seed_queries", "seed_competitors",
            "creatives"} <= set(on_disk["counts"])


def test_the_report_is_byte_stable_for_identical_inputs(tmp_path):
    """With `now` pinned, two runs over the same inputs write the same
    selection.json, the same patterns.json and the same corpus records - the
    property that makes an unchanged week commit nothing."""
    outputs = []
    for name in ("one", "two"):
        repo = tmp_path / name
        for sub in ("research/corpus", "queue", "creative"):
            (repo / sub).mkdir(parents=True)
        (repo / "backlog.md").write_text(BACKLOG, encoding="utf-8")
        (repo / "seeds.yaml").write_text(SEEDS, encoding="utf-8")
        report = run_with(repo)
        assert report.ok, report.failed
        # The one legitimate difference: the note about watching no competitor
        # names the seeds file by path, and the two stand-in repositories are
        # two directories. In the real tree it is always research/seeds.yaml.
        outputs.append({
            path.relative_to(repo).as_posix():
                path.read_bytes().replace(str(repo).encode("utf-8"), b"<repo>")
            for path in sorted((repo / "research").rglob("*.json"))
        })

    assert outputs[0] == outputs[1]
    assert "research/selection.json" in outputs[0]
    assert "research/patterns.json" in outputs[0]
    assert len(outputs[0]) == 2 + len(ADS)


def test_the_summary_reads_the_report_not_the_clock(repo):
    report = run_with(repo)
    summary = report.summary()

    assert summary.startswith("research run %s: %d concept(s) selected" % (STAMP, score.TOP_N))
    assert "discovered 2 candidate(s), 2 not yet analysed, 2 analysed here" in summary
    assert "spent 3 model call(s) and 2 Ad Library call(s)" in summary
    assert ", ".join(report.selected) in summary
    assert "skipped 1:" in summary and "competitor" in summary
    assert "FAILED" not in summary


def test_a_report_line_names_a_file_relative_to_the_tree_it_is_committed_in(tmp_path):
    """The committed report must not carry a runner's absolute checkout path;
    a file outside the tree (every test's tmp_path) stays as given."""
    assert fanout._where(None, discover.SEEDS_PATH) == "research/seeds.yaml"
    assert fanout._where(ROOT / "research" / "patterns.json", learn.DEFAULT_PATH) == (
        "research/patterns.json"
    )
    assert fanout._where(str(ROOT / "research" / "seeds.yaml"), discover.SEEDS_PATH) == (
        "research/seeds.yaml"
    )
    outside = tmp_path / "seeds.yaml"
    assert fanout._where(outside, discover.SEEDS_PATH) == str(outside)


def test_now_accepts_the_shapes_the_other_modules_accept():
    """A datetime (aware or naive), a date, an ISO string with Z or an offset,
    or None for the clock - one reading, three consumers."""
    assert fanout._moment(STAMP) == MOMENT
    assert fanout._moment("2026-09-18T08:00:00+02:00") == MOMENT
    assert fanout._moment(MOMENT) == MOMENT
    assert fanout._moment(datetime(2026, 9, 18, 6, 0, 0)) == MOMENT
    assert fanout._moment(MOMENT.date()) == datetime(2026, 9, 18, tzinfo=timezone.utc)
    assert fanout._moment(None).tzinfo is timezone.utc
    assert fanout._stamp(MOMENT) == STAMP
    with pytest.raises(TypeError):
        fanout._moment(1726000000)


# ---------------------------------------------------------------------------
# 6. The dry run: a preflight that spends nothing
# ---------------------------------------------------------------------------


def test_the_dry_run_makes_no_call_and_writes_nothing(repo, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("the preflight must not open a socket or read a token")

    monkeypatch.setattr(discover, "_http", explode)
    monkeypatch.setattr(discover, "AdLibraryClient", explode)
    monkeypatch.setattr(model, "client", explode)
    before = sorted(p.name for p in (repo / "research").iterdir())

    report = plan_with(repo)

    assert report.dry_run is True
    assert report.cost == {"model_calls": 0, "ad_library_calls": 0}
    assert sorted(p.name for p in (repo / "research").iterdir()) == before
    assert not (repo / "research" / "selection.json").exists()
    assert not (repo / "research" / "patterns.json").exists()
    assert report.generated_at == STAMP


def test_the_dry_run_prices_the_run_before_it_happens(repo):
    report = plan_with(repo, budget=50)

    # One seeded page and one keyword query: two searches, each paged up to
    # DEFAULT_MAX_PAGES, and one call each at the floor.
    assert report.estimate["searches"] == 2
    assert report.estimate["page_calls"] == 1
    assert report.estimate["query_calls"] == 1
    assert report.estimate["ad_library_calls"] == 2 * discover.DEFAULT_MAX_PAGES
    assert report.estimate["max_pages"] == discover.DEFAULT_MAX_PAGES
    assert report.estimate["budget"] == 50
    # Twenty-four ads with nothing hand-saved is two text batches, plus the
    # concepts call and the editorial call.
    assert report.estimate["max_ads"] == fanout.DEFAULT_MAX_ADS
    assert report.estimate["model_calls"] == 2 + 2
    assert report.counts["segments"] == 4
    assert report.counts["seed_pages"] == 1
    assert report.counts["seed_queries"] == 1
    assert report.counts["seed_competitors"] == 0
    assert report.counts["concepts"] == concepts.DEFAULT_N
    assert report.counts["selected"] == score.TOP_N
    assert report.ok, report.failed


def test_the_model_call_ceiling_counts_hand_saved_creatives(repo):
    """Every creative on disk is ASSUMED to be among the chosen - nothing can
    know before discovery - so the ceiling is one call per file plus the
    batches for the rest."""
    media = repo / "research" / "media"
    media.mkdir()
    for name in ("fb-1.mp4", "fb-2.JPG", "fb-3.webm", "README.md", "notes.txt"):
        (media / name).write_bytes(b"\x00")

    report = plan_with(repo)

    assert report.counts["creatives"] == 3
    # 3 media calls + ceil(21 / 12) = 2 batches + concepts + editorial.
    assert report.estimate["model_calls"] == 3 + 2 + 2

    capped = plan_with(repo, max_ads=2)
    assert capped.estimate["model_calls"] == 2 + 0 + 2

    nothing = plan_with(repo, max_ads=0)
    assert nothing.estimate["model_calls"] == 2


def test_the_shipped_seeds_file_prices_under_the_workflow_budget():
    """docs/COST.md: two pages and five queries at two result pages each is
    under twenty calls, and research.yml passes --budget 150."""
    seeds = discover.load_seeds()
    estimate = fanout._estimate(
        fanout._seed_plan(seeds), max_ads=fanout.DEFAULT_MAX_ADS, budget=150, creatives=0,
    )
    # Re-derived, not hardcoded. This asserted searches == 6 and calls == 12,
    # which described a seed file holding two pages and five queries, and went
    # red the day eleven real page ids were added - a test failing because the
    # work went well. What docs/COST.md actually promises is HEADROOM: a sweep
    # and a same-hour re-run both fit inside the hourly allowance, and
    # research.yml passes --budget 150 against a ceiling of 200.
    pages = len(seeds.pages)
    expected_searches = -(-pages // discover.MAX_PAGE_IDS_PER_CALL) + len(seeds.queries)
    assert estimate["searches"] == expected_searches
    assert estimate["ad_library_calls"] == expected_searches * discover.DEFAULT_MAX_PAGES
    assert estimate["ad_library_calls"] < 20 <= 150
    assert estimate["model_calls"] == 4


def test_the_dry_run_names_that_no_competitor_is_watched(repo):
    """The shipped seeds file watches two icp-adjacent pages and no
    competitor - the two competitors are commented out with blank ids, on
    purpose. The preflight says so; it is a note, not a failure."""
    report = plan_with(repo)

    assert report.ok
    note = next(l for l in report.skipped if "competitor" in l)
    assert note.startswith("discover: ")
    assert "page_id" in note
    assert str(repo / "seeds.yaml") in note
    assert "search matches creative text" in note

    (repo / "seeds.yaml").write_text(SEEDS_WITH_COMPETITOR, encoding="utf-8")
    watched = plan_with(repo)
    assert not any("competitor" in l for l in watched.skipped)
    assert watched.counts["seed_competitors"] == 1


def test_the_dry_run_refuses_to_select_more_concepts_than_it_writes(repo):
    report = plan_with(repo, n_concepts=2, top=3)

    assert not report.ok
    assert any("--select" in line for line in report.failed)


def test_the_dry_run_refuses_a_budget_that_cannot_pay_for_the_searches(repo):
    report = plan_with(repo, budget=3)

    assert not report.ok
    line = next(l for l in report.failed if "--budget" in l)
    assert "2 search(es)" in line and "up to 4" in line
    assert "keeps nothing" in line


def test_the_dry_run_with_an_empty_corpus_and_nothing_seeded_is_a_blocker(repo):
    (repo / "seeds.yaml").write_text(SEEDS_EMPTY, encoding="utf-8")

    report = plan_with(repo)

    assert not report.ok
    assert any("asks for nothing" in line and "seeds.yaml" in line for line in report.failed)
    # No note about competitors on top: the file asks for nothing at all, and
    # one message that names the fix is better than two.
    assert report.skipped == []


def test_the_dry_run_with_a_corpus_and_nothing_seeded_is_only_a_note(repo):
    """A corpus on disk can still fan out with nothing new discovered; the
    preflight does not call that a blocker."""
    run_with(repo)
    (repo / "seeds.yaml").write_text(SEEDS_EMPTY, encoding="utf-8")

    report = plan_with(repo)

    assert report.ok, report.failed
    assert report.counts["corpus"] == 2
    assert report.counts["patterns"] >= 1


def test_the_dry_run_reports_a_missing_seeds_file_and_a_bad_backlog_by_name(repo):
    (repo / "seeds.yaml").unlink()
    (repo / "backlog.md").write_text("| 1 | x | Trade | one, two | note |\n", encoding="utf-8")

    report = plan_with(repo)

    assert not report.ok
    assert any(l.startswith("discover: ") and "seeds.yaml" in l for l in report.failed)
    assert any(l.startswith("concepts: ") and "questions" in l for l in report.failed)


def test_the_dry_run_reports_an_unreadable_patterns_file_and_tolerates_a_missing_one(repo):
    first = plan_with(repo)
    assert first.counts["patterns"] == 0 and first.ok

    (repo / "research" / "patterns.json").write_text("{not json", encoding="utf-8")
    report = plan_with(repo)

    assert not report.ok
    assert any(l.startswith("learn: ") for l in report.failed)


def test_the_dry_run_summary_prices_in_ad_library_calls(repo):
    summary = plan_with(repo).summary()

    assert summary.startswith("research preflight %s: ok" % STAMP)
    assert "seeds ask for 1 page search(es) over 1 seeded page(s) and 1 quer(ies)" in summary
    assert "0 corpus record(s), 0 pattern(s), 4 segment(s), 0 hand-saved creative(s)" in summary
    assert "analyse up to 24 ad(s), write 12 concept(s), select 3" in summary
    assert "spend up to 4 model call(s) and 4 of %d Ad Library call(s)" % (
        discover.HOURLY_BUDGET_CALLS
    ) in summary


# ---------------------------------------------------------------------------
# 7. The CLI
# ---------------------------------------------------------------------------


def cli(repo: Path, *extra: str) -> list[str]:
    return [
        "--seeds", str(repo / "seeds.yaml"),
        "--corpus", str(repo / "research" / "corpus"),
        "--patterns", str(repo / "research" / "patterns.json"),
        "--backlog", str(repo / "backlog.md"),
        "--queue", str(repo / "queue"),
        "--media-root", str(repo / "research" / "media"),
        "--out", str(repo / "research" / "selection.json"),
        *extra,
    ]


@pytest.fixture
def live(monkeypatch):
    """What a live CLI run needs and the tests cannot inject: a model client
    behind fanout._client, a transport behind discover._http, and a Meta
    token issued today so engine.oauth hands it over without a warning."""
    api = FakeArchive(ADS)
    monkeypatch.setattr(fanout, "_client", lambda: StubModel())
    monkeypatch.setattr(discover, "_http", api)
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, "test-token")
    monkeypatch.setenv(
        oauth.META_TOKEN_ISSUED, datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    return api


def test_the_cli_puts_the_document_on_stdout_and_the_summary_on_stderr(
    repo, live, capsys
):
    """engine/discover.py's convention: stdout carries exactly one thing under
    --json, so a caller can pipe it into a parser."""
    code = fanout.main(cli(repo, "--json"))
    out, err = capsys.readouterr()

    assert code == 0
    document = json.loads(out)
    assert document["ok"] is True
    assert len(document["selected"]) == score.TOP_N
    assert out.count("{") > 1 and "research run" not in out
    assert "research run" in err
    assert "test-token" not in out + err
    # The document on stdout is the document on disk.
    assert out == (repo / "research" / "selection.json").read_text(encoding="utf-8")
    # And the live CLI path went through the real ledger.
    assert len(live.calls) == 2


def test_the_cli_writes_only_the_summary_without_json(repo, live, capsys):
    code = fanout.main(cli(repo))
    out, err = capsys.readouterr()

    assert code == 0
    assert "research run" in out
    assert err == ""


def test_the_cli_exit_code_says_whether_a_stage_could_run(repo, live, capsys):
    """Nonzero means "a stage could not run", not "nothing was produced" -
    research.yml commits before it reads this."""
    (repo / "seeds.yaml").write_text(SEEDS_EMPTY, encoding="utf-8")

    assert fanout.main(cli(repo)) == 1
    out, _ = capsys.readouterr()
    # Two stages could not run - nothing seeded, and a corpus too small to
    # learn from - and both are named.
    assert "FAILED 2:" in out
    assert "asks for nothing" in out and "%d or more" % learn.MIN_SUPPORT in out
    assert (repo / "research" / "selection.json").exists()


def test_the_cli_reports_a_failed_discovery_and_exits_1_with_the_corpus_fanned_out(
    repo, live, capsys, monkeypatch
):
    assert fanout.main(cli(repo, "--json")) == 0
    capsys.readouterr()
    monkeypatch.setattr(discover, "_http", FakeArchive([], raises=RuntimeError("HTTP 500")))

    code = fanout.main(cli(repo, "--json"))
    out, err = capsys.readouterr()

    assert code == 1
    document = json.loads(out)
    assert document["ok"] is False
    assert any(l.startswith("discover: ") for l in document["failed"])
    assert len(document["selected"]) == score.TOP_N
    assert "FAILED 1:" in err


def test_the_cli_flags_an_operator_needs_are_all_there(repo, monkeypatch, capsys):
    """A budget, a cap, a concept count, how many to select, a window, an
    origin, every path, a dry run and --json - and the dry run reads no
    token and opens no socket."""
    monkeypatch.setattr(discover, "_http", lambda url, token: pytest.fail("no socket"))

    code = fanout.main(
        cli(repo, "--dry-run", "--json", "--budget", "50", "--concepts", "8",
            "--select", "2", "--max-ads", "5", "--days", "7", "--origin", "own")
    )
    out, err = capsys.readouterr()
    document = json.loads(out)

    assert code == 0
    assert document["dry_run"] is True
    assert document["counts"]["concepts"] == 8
    assert document["counts"]["selected"] == 2
    # Five ads is one batch; plus the concepts call and the editorial call.
    assert document["estimate"]["model_calls"] == 3
    assert document["estimate"]["max_ads"] == 5
    assert document["estimate"]["budget"] == 50
    assert "research preflight" in err
    assert not (repo / "research" / "selection.json").exists()


def test_the_cli_refuses_an_origin_outside_the_corpus_enum(repo, capsys):
    with pytest.raises(SystemExit) as raised:
        fanout.main(cli(repo, "--dry-run", "--origin", "youtube"))
    assert raised.value.code == 2
    capsys.readouterr()


def test_the_cli_honours_the_concept_and_selection_counts(repo, live, capsys):
    code = fanout.main(cli(repo, "--json", "--concepts", "6", "--select", "2"))
    out, _ = capsys.readouterr()
    document = json.loads(out)

    assert code == 0
    assert len(document["concepts"]) == 6
    assert len(document["selected"]) == 2


def test_the_cli_defaults_are_the_contract_defaults(repo, live, capsys):
    """--max-ads 24, --budget 200, --concepts 12, --select 3: the numbers
    docs/COST.md prices a Monday against."""
    code = fanout.main(cli(repo, "--json"))
    out, _ = capsys.readouterr()
    document = json.loads(out)

    assert code == 0
    assert document["estimate"]["max_ads"] == 24
    assert document["estimate"]["budget"] == discover.HOURLY_BUDGET_CALLS
    assert len(document["concepts"]) == concepts.DEFAULT_N
    assert len(document["selected"]) == score.TOP_N
