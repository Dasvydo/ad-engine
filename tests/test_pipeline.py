"""The whole loop, end to end, offline: the seams, not the modules.

Every other test file in this repository proves one module correct against its
own fixtures. None of them proves that the record one module WRITES is the
record the next one READS - and that is the failure this repository's sibling
recorded four times in its RUN-STATE.md, in its own words: "a seam built for a
consumer nobody wrote". A field is written, copied faithfully, and read by
nobody; every part is green and the whole thing is inert.

So this file drives one value through every stage:

    Ad Library JSON -> discover.discover() -> candidates (C2)
                    -> analyse.analyse_all() -> corpus records (C1) -> corpus.save()
                    -> learn.build() -> patterns (C5)
                    -> concepts.generate() -> concepts (C4) citing REAL pattern ids
                    -> score.select() -> a selection with scorecards
                    -> write.generate() -> a job (C3) that gate.structural() PASSES
                    -> approval: proposed -> built -> launched, ad ids pinned
                    -> measure.measurement() -> a row (C6)
                    -> feedback.record_for() -> an own record (C1)
                    -> learn.build() -> a ctr pattern a concept can cite

and asserts at each join that the NEXT stage read what the previous one wrote,
by value and not by shape. `test_the_whole_loop` walks the chain in one test,
because a chain broken in the middle has to fail as a chain; the tests after it
pin individual joins so a break says which one.

Everything is offline. The Ad Library is a stub transport, every model call is
tests.stubs.StubClient, every root is a tmp_path, engine.approval.QUEUE is
monkeypatched, and every clock is pinned with now=/today=. No key, no token, no
socket.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine import (
    analyse,
    approval,
    backlog,
    concepts,
    corpus,
    discover,
    feedback,
    gate,
    learn,
    measure,
    score,
    write,
)
from tests.stubs import StubClient, json_reply

ROOT = Path(__file__).resolve().parents[1]

# Every clock in this file. Pinned so the corpus, the patterns document, the
# job, the measurement row and the own record all agree with each other and
# re-running the file rewrites the same bytes.
TODAY = datetime(2026, 9, 18, 6, 0, 0, tzinfo=timezone.utc)
PROPOSED_AT = datetime(2026, 9, 19, 9, 3, 0, tzinfo=timezone.utc)
LAUNCHED_AT = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
MEASURED_AT = datetime(2026, 9, 27, 5, 2, 0, tzinfo=timezone.utc)

SEGMENT_ID = "payroll-bureaus"
SEEDED_PAGE_ID = "1007614045762121"
OTHER_PAGE_ID = "2229998887776"

# Two ads on OUR page. Two, not one, because engine.learn needs MIN_SUPPORT
# records to mint a pattern, and step 10 of this walk is a ctr pattern.
AD_IDS = ("778899", "778900")
CAMPAIGN_ID = "556677"
ADSET_ID = "334455"


# ---------------------------------------------------------------------------
# Step 1 fixtures: the Ad Library, stubbed
# ---------------------------------------------------------------------------

SEEDS_YAML = """
countries: [DK]
pages:
  - id: balance-dk
    name: Balance - Your AI Powered Accountants
    page_id: "%s"
    origin: icp-adjacent
    countries: [DK]
queries:
  - query: regnskab
    countries: [DK]
    languages: [da]
own:
  page_id: "5550001"
  page_name: DoviLoop
  ad_account_id: act_9090909
""" % SEEDED_PAGE_ID


def _ad(ad_id, page_id, page_name, *, body, headline, start, stop=None, reach):
    """One row of the archive's `data` list, in the shape discover.FIELDS asks
    for. Written here rather than imported so a change to discover's reader
    shows up as a failure at this seam."""
    return {
        "id": ad_id,
        "page_id": page_id,
        "page_name": page_name,
        "ad_creation_time": start,
        "ad_delivery_start_time": start,
        "ad_delivery_stop_time": stop,
        "ad_snapshot_url": "https://www.facebook.com/ads/library/?id=%s" % ad_id,
        "ad_creative_bodies": [body],
        "ad_creative_link_titles": [headline],
        "ad_creative_link_descriptions": ["Bogholderi for mindre virksomheder"],
        "ad_creative_link_captions": ["balance.dk"],
        "publisher_platforms": ["facebook", "instagram"],
        "languages": ["da"],
        "eu_total_reach": reach,
    }


# The seeded PAGE search: two ads from the page seeds.yaml names. Two, so the
# page is its own baseline and add_outlier_ratios has something to divide by.
PAGE_SEARCH = {
    "data": [
        _ad("961046237012883", SEEDED_PAGE_ID, "Balance - Your AI Powered Accountants",
            body="Bruger du stadig en hel aften pa at samle bilag?",
            headline="Bogforing uden aftenarbejde",
            start="2026-06-10T00:00:00+0000", reach=42000),
        _ad("961046237012884", SEEDED_PAGE_ID, "Balance - Your AI Powered Accountants",
            body="Dine kunder sporger om det samme hver maned.",
            headline="Svar der allerede ligger klar",
            start="2026-08-20T00:00:00+0000", reach=9000),
    ]
}

# The KEYWORD search: two ads from a page nobody seeded. They arrive
# icp-adjacent because that is what a bare query means.
QUERY_SEARCH = {
    "data": [
        _ad("771122334455667", OTHER_PAGE_ID, "GoSimple",
            body="Regnskabet ligger og venter, og maneden er ved at vaere slut.",
            headline="Fa regnskabet af bordet",
            start="2026-04-02T00:00:00+0000", reach=31000),
        _ad("771122334455668", OTHER_PAGE_ID, "GoSimple",
            body="Hvem svarer pa kundernes mails, mens du laver arsregnskabet?",
            headline="Mailen passer sig selv",
            start="2026-09-01T00:00:00+0000", stop="2026-09-15T00:00:00+0000",
            reach=4000),
    ]
}


class RecordingTransport:
    """`transport(url, token) -> dict`, dispatching on what the URL asks for.

    Records every URL so a test can assert - as tests/test_discover.py does for
    its own reasons - that nothing here ever reaches facebook.com/ads/library,
    and that the token never travels in a URL.
    """

    def __init__(self):
        self.urls: list[str] = []

    def __call__(self, url: str, token: str) -> dict:
        self.urls.append(url)
        if "search_page_ids" in url:
            return PAGE_SEARCH
        if "search_terms" in url:
            return QUERY_SEARCH
        raise AssertionError(
            "the transport was called with a URL that is neither a page search "
            "nor a keyword search: %r" % url
        )


# ---------------------------------------------------------------------------
# Step 2 fixtures: the analyst, stubbed
# ---------------------------------------------------------------------------

# One shared objection, so engine.learn has an objection pattern; two hook
# devices, two length bands and two offer types, each held by two ads, so the
# patterns document comes back with several kinds rather than one.
OBJECTION = "We already have a template for this."

ANALYSES = {
    "fb-961046237012883": {
        "copy": {"words": 48},
        "hook": {"words": 9, "text": "Bruger du stadig en hel aften pa at samle bilag?",
                 "device": "question"},
        "structure": ["hook", "problem", "offer", "cta"],
        "offer": {"type": "demo", "text": "Book et kort mode"},
        "proof": {"type": "none", "text": ""},
        "cta": {"type": "learn-more", "text": "Lees mere"},
        "objections": [OBJECTION],
    },
    "fb-961046237012884": {
        "copy": {"words": 45},
        "hook": {"words": 8, "text": "Dine kunder sporger om det samme hver maned.",
                 "device": "question"},
        "structure": ["hook", "problem", "offer", "cta"],
        "offer": {"type": "demo", "text": "Book et kort mode"},
        "proof": {"type": "none", "text": ""},
        "cta": {"type": "learn-more", "text": "Lees mere"},
        "objections": [OBJECTION],
    },
    "fb-771122334455667": {
        "copy": {"words": 84},
        "hook": {"words": 11,
                 "text": "Regnskabet ligger og venter, og maneden er ved at vaere slut.",
                 "device": "cost-of-inaction"},
        "structure": ["hook", "agitate", "cta"],
        "offer": {"type": "none", "text": ""},
        "proof": {"type": "none", "text": ""},
        "cta": {"type": "learn-more", "text": "Lees mere"},
        "objections": [OBJECTION],
    },
    "fb-771122334455668": {
        "copy": {"words": 81},
        "hook": {"words": 10,
                 "text": "Hvem svarer pa kundernes mails, mens du laver arsregnskabet?",
                 "device": "cost-of-inaction"},
        "structure": ["hook", "agitate", "cta"],
        "offer": {"type": "none", "text": ""},
        "proof": {"type": "none", "text": ""},
        "cta": {"type": "learn-more", "text": "Lees mere"},
        "objections": [OBJECTION],
    },
}


# ---------------------------------------------------------------------------
# Steps 4-6 fixtures: the writers, stubbed
# ---------------------------------------------------------------------------

# The copy the writer "returns". It has to survive engine/gate.py for real:
# under the character limits, no digit and no number WORD (gate.NUM_RE counts
# "one" and "double" as numbers), no refused construction, and the guarantee
# worded as claims/evidence.json's own safe phrasing.
PRIMARY_TEXT = (
    "Every week a payroll client asks for a payslip copy, a holiday balance, "
    "or which tax code applies to a new starter.\n\n"
    "DoviLoop turns your own payroll notes and handbook into a reply already "
    "waiting in the bureau's Outlook drafts, in your own words.\n\n"
    "Nothing sends until your team reads it. If the drafts are not good "
    "enough to send, you do not pay and you keep the knowledge base."
)
HEADLINE = "Payslip questions, already drafted"
DESCRIPTION = "Built for payroll bureaus in Denmark and Lithuania"
HYPOTHESIS = (
    "A hook naming the payslip request outpulls the generic admin framing."
)


def written_reply() -> dict:
    """Exactly write.AUTHORED, as bare English strings, which is what
    engine/write.py's `_authored_from` demands and nothing more."""
    return {
        "primary_text": PRIMARY_TEXT,
        "headline": HEADLINE,
        "description": DESCRIPTION,
        "cta": "Learn more",
        "hypothesis": HYPOTHESIS,
    }


def concept_reply(pattern_ids, *, segment=SEGMENT_ID, placement="reels-9x16"):
    """Two concepts for the concept writer's single call, citing pattern ids
    the caller took out of the patterns document the learn step actually
    minted. Nothing here invents an id: an invented citation is the exact
    failure engine/concepts.py refuses, and a test that hard-coded "q01" would
    stop proving that learn and concepts meet."""
    return {"concepts": [
        {
            "segment": segment,
            "angle": ("Payroll bureaus answer the same payslip and holiday "
                      "questions for every client, every month."),
            "hook": "The payslip request that lands again every single month.",
            "pattern_ids": list(pattern_ids),
            "placement": placement,
            "offer": "guarantee",
            "needs_numbers": False,
        },
        {
            "segment": segment,
            "angle": ("Bureaus lose their mornings to holiday balance "
                      "questions they have already answered."),
            "hook": "Your holiday balance inbox, answered while you work.",
            "pattern_ids": list(pattern_ids[:1]),
            "placement": "static-1x1",
            "offer": "none",
            "needs_numbers": False,
        },
    ]}


def editorial_reply(concept_list):
    """A score for every concept, keyed by the ids engine/concepts.py stamped."""
    return {"scores": [
        {"id": c["id"], "score": 0.9 - 0.1 * index,
         "reason": "names a moment in the payroll week"}
        for index, c in enumerate(concept_list)
    ]}


# ---------------------------------------------------------------------------
# Step 8 fixtures: the insights edge, stubbed
# ---------------------------------------------------------------------------

def insights_body(*, impressions, clicks, ctr):
    """One object as measure.MeasureClient.insights() returns it. The field
    names are engine/measure.py's INSIGHT_FIELDS, which carry their own
    TODO(integration) - this test pins the READER against them, not the API."""
    return {
        "impressions": str(impressions),
        "reach": str(int(impressions * 0.8)),
        "clicks": str(clicks),
        "ctr": str(ctr),
        "cpc": "0.61",
        "cpm": "7.6",
        "spend": "31.2",
        "actions": [
            {"action_type": "video_view", "value": str(int(impressions * 0.29))},
            {"action_type": "link_click", "value": str(clicks)},
        ],
        "cost_per_action_type": [
            {"action_type": "link_click", "value": "0.61"},
        ],
        "video_thruplay_watched_actions": [{"action_type": "video_view",
                                            "value": str(int(impressions * 0.06))}],
    }


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A whole engine's worth of roots, none of them the repository's.

    engine.approval reads QUEUE through queue_dir() at call time, so patching
    the module global redirects approval, measure and propose together - the
    same trick tests/test_approval.py uses, and the reason this test can move a
    job through three stages without touching the committed queue/.
    """
    for stage in approval.ALL_STAGES:
        (tmp_path / "queue" / stage).mkdir(parents=True)
    (tmp_path / "corpus").mkdir()
    (tmp_path / "creative").mkdir()
    (tmp_path / "seeds.yaml").write_text(SEEDS_YAML, encoding="utf-8")
    monkeypatch.setattr(approval, "QUEUE", tmp_path / "queue")
    return tmp_path


def _segment() -> backlog.Segment:
    """The real backlog row, read from the committed queue/backlog.md.

    Read rather than invented: engine/score.py's _icp_fit scores a concept 0
    for a segment that is not a row in that file, so a made-up segment would
    make this walk pass for the wrong reason.
    """
    rows = {s.id: s for s in backlog.load()}
    assert SEGMENT_ID in rows, (
        "%s is no longer a row in queue/backlog.md; this walk needs a real "
        "segment because engine/score.py scores an unknown one at zero"
        % SEGMENT_ID
    )
    return rows[SEGMENT_ID]


def _discover(tree) -> list[dict]:
    transport = RecordingTransport()
    seeds = discover.load_seeds(tree / "seeds.yaml")
    client = discover.AdLibraryClient("test-token", transport=transport)
    return discover.discover(seeds, client=client, today=TODAY), transport


def _analyse_and_save(candidates, tree) -> list[dict]:
    client = StubClient([json_reply({"ads": {c["id"]: ANALYSES[c["id"]]
                                             for c in candidates}})])
    run = analyse.analyse_all(
        candidates, client=client, media_root=tree / "media", now=TODAY
    )
    assert run.skipped == [], run.skipped
    for record in run.records:
        corpus.save(record, tree / "corpus")
    return run.records


def _patterns(tree) -> dict:
    document = learn.build(corpus.load_all(tree / "corpus"))
    learn.write(document, tree / "patterns.json")
    return document


def _context(tree) -> score.Context:
    return score.load_context(
        patterns_path=tree / "patterns.json",
        queue_root=tree / "queue",
        creative_root=tree / "creative",
        evidence=gate.load_attestations(),
    )


def _file_job(job: dict, stage: str = "proposed") -> Path:
    """Write a C3 job into the (patched) queue exactly as engine/propose.py
    would: authored key order, two-space indent, trailing newline."""
    path = approval.queue_dir(stage) / ("%s.json" % job["segment"])
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


# ===========================================================================
# THE WALK
# ===========================================================================

def test_the_whole_loop(tree):
    """One value, ten stages, every join asserted by value.

    Read the asserts, not the plumbing: each one names the field the previous
    stage wrote and the place this one read it.
    """
    # --- 1. the Ad Library -> candidates (C2) ------------------------------
    candidates, transport = _discover(tree)

    assert len(transport.urls) == 2, (
        "one page search and one keyword search; got %s" % transport.urls
    )
    assert not any("facebook.com/ads/library" in u for u in transport.urls)
    assert not any("test-token" in u for u in transport.urls), (
        "the token travels in the Authorization header, never in a URL"
    )
    assert [c["id"] for c in candidates] == [
        "fb-961046237012883", "fb-961046237012884",
        "fb-771122334455667", "fb-771122334455668",
    ]

    seeded = candidates[0]
    # The seeded page's origin reached the record, and the archive's page_name
    # became the channel.
    assert seeded["origin"] == "icp-adjacent"
    assert seeded["channel"] == "Balance - Your AI Powered Accountants"
    assert seeded["metrics"]["page_id"] == SEEDED_PAGE_ID
    # days_running is `today - ad_delivery_start_time`, pinned by today=.
    assert seeded["metrics"]["days_running"] == 100
    # The query's ads arrived icp-adjacent, from a page nobody seeded.
    assert candidates[2]["metrics"]["page_id"] == OTHER_PAGE_ID
    # The stopped ad is the one the archive gave a stop time.
    assert candidates[3]["metrics"]["active"] is False
    # outlier_ratio is each ad against the OTHER ads of its own page, so an
    # ad reaching more per day than its page-mate scores above 1.
    assert seeded["outlier_ratio"] > 1.0

    # --- 2. candidates -> corpus records (C1) ------------------------------
    records = _analyse_and_save(candidates, tree)
    assert len(records) == 4

    first = records[0]
    # The candidate's own facts travelled; the model did not get to restate
    # them. analyse.py copies metrics wholesale and copy verbatim.
    assert first["id"] == seeded["id"]
    assert first["origin"] == seeded["origin"]
    assert first["metrics"]["days_running"] == seeded["metrics"]["days_running"]
    assert first["analysis"]["copy"]["primary_text"] == seeded["copy"]["primary_text"]
    # ...and the one thing the model WAS asked to add is the model's.
    assert first["analysis"]["copy"]["words"] == 48
    assert first["analysis"]["hook"]["device"] == "question"
    assert first["fetched_at"] == "2026-09-18T06:00:00Z"

    # On disk, and readable back as the same record.
    saved = corpus.load(corpus.path_for(first, tree / "corpus"))
    assert saved.to_dict() == first

    # --- 3. corpus -> patterns (C5) ----------------------------------------
    patterns = _patterns(tree)
    assert patterns["schema"] == learn.SCHEMA
    assert patterns["corpus_size"] == 4

    kinds = {p["kind"] for p in patterns["patterns"]}
    assert len(kinds) >= 2, (
        "the learn step found only %s over four analysed ads" % sorted(kinds)
    )
    # The devices below are the analyses above, counted: two ads opened with a
    # question, and every one of the four answered the same objection.
    devices = {(p["kind"], p["device"]): p for p in patterns["patterns"]}
    assert devices[("hook", "question")]["n"] == 2
    assert devices[("hook", "question")]["evidence"] == [
        "fb-961046237012883", "fb-961046237012884"
    ]
    assert devices[("cta", "learn-more")]["n"] == 4

    # --- 4. patterns -> concepts (C4) --------------------------------------
    minted = [p["id"] for p in patterns["patterns"]][:2]
    concept_client = StubClient([json_reply(concept_reply(minted))])
    written = concepts.generate(
        patterns, [_segment()], n=2, client=concept_client
    )

    assert [c["id"] for c in written] == ["a01", "a02"]
    # The citation is the whole reason this stage exists: every id a concept
    # names is an id the learn step actually minted, in the file on disk.
    assert written[0]["pattern_ids"] == minted
    assert set(written[0]["pattern_ids"]) <= {p["id"] for p in patterns["patterns"]}
    assert written[0]["segment"] == SEGMENT_ID

    # --- 5. concepts -> a selection with scorecards ------------------------
    score_client = StubClient([json_reply(editorial_reply(written))])
    selection = score.select(
        written, context=_context(tree), client=score_client, top=1
    )

    assert selection.model_calls == 1
    assert len(selection.selected) == 1
    assert len(selection.scorecards) == 2
    chosen = selection.selected[0]
    assert chosen["id"] == "a01"
    # The scorer read the patterns file the learn step wrote: a concept citing
    # ids that are in it scores above zero on evidence.
    card = next(c for c in selection.scorecards if c.id == "a01")
    assert card.scores["pattern_evidence"] > 0.0
    assert card.scores["claims_survivability"] == 1.0
    assert card.scores["icp_fit"] == 1.0, (
        "all three of this segment's backlog tags read as lookups"
    )
    assert card.scores["editorial"] == pytest.approx(0.9)
    assert card.selected is True
    assert selection.as_dict()["selected"] == ["a01"]

    # --- 6. the selected concept -> a job (C3) the gate passes -------------
    write_client = StubClient([json_reply(written_reply())])
    job = write.generate(
        _segment(), concept=chosen, patterns=patterns["patterns"],
        client=write_client, now=PROPOSED_AT,
    )

    verdict = gate.structural(job)
    assert verdict.ok, verdict.failures

    # The concept reached the job, by value, in the three places it has to.
    assert job["concept_id"] == "a01"
    assert job["pattern_ids"] == minted
    assert job["placement"] == chosen["placement"]
    assert job["offer"] == chosen["offer"] == "guarantee"
    assert job["segment"] == job["id"] == SEGMENT_ID
    assert job["proposed_at"] == "2026-09-19T09:03:00Z"
    assert job["ads"] == {} and job["launched_at"] is None
    # ...and the placement decided the creative, rather than a hardcoded
    # template. This is the sibling's recorded defect, guarded here by value.
    assert job["creative_source"]["kind"] == "reel"
    assert job["creative_source"]["template"] == "reel-c"
    assert job["creative_source"]["selection"] == (
        "queue/proposed/%s.reel.json" % SEGMENT_ID
    )

    # The sidecar reel-engine renders from names the same concept.
    sidecar = write.reel_selection(chosen, _segment(), now=PROPOSED_AT)
    assert sidecar["selected"] == ["a01"]
    assert sidecar["concepts"][0]["format"] == write.FORMAT_BY_PLACEMENT[
        chosen["placement"]
    ]
    assert sidecar["concepts"][0]["hook"] == chosen["hook"]

    # --- 7. proposed -> built -> launched, with the ad ids pinned ----------
    _file_job(job, "proposed")
    (approval.queue_dir("proposed") / ("%s.reel.json" % SEGMENT_ID)).write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    assert approval.locate(SEGMENT_ID).stage == "proposed"
    built = approval.advance(SEGMENT_ID, "built")
    assert built.stage == "built"
    # The sidecar travelled with the JSON, which is what build.yml renders from.
    assert built.reel_selection.exists()

    launched = approval.launch(
        SEGMENT_ID,
        {ad: {"campaign_id": CAMPAIGN_ID, "adset_id": ADSET_ID} for ad in AD_IDS},
        now=LAUNCHED_AT,
    )
    assert launched.stage == "launched"
    live = approval.load_job(launched)
    assert sorted(live["ads"]) == sorted(AD_IDS)
    assert live["ads"][AD_IDS[0]]["campaign_id"] == CAMPAIGN_ID
    assert live["launched_at"] == "2026-09-20T10:00:00Z"
    # The copy that went out is byte-identical to the copy the gate passed.
    assert live["primary_text"]["en"] == job["primary_text"]["en"]
    # measure reads queue/launched through the same patched QUEUE.
    assert [j.segment_id for j in measure.launched_jobs()] == [SEGMENT_ID]

    # --- 8. the insights edge -> a measurement row (C6) --------------------
    rows = [
        measure.measurement(
            segment=SEGMENT_ID,
            ad_id=ad_id,
            campaign_id=live["ads"][ad_id]["campaign_id"],
            launched_at=live["launched_at"],
            insights=insights_body(impressions=4100 + index * 300,
                                   clicks=51 + index * 4, ctr=1.24 + index * 0.1),
            now=MEASURED_AT,
        )
        for index, ad_id in enumerate(AD_IDS)
    ]

    row = rows[0]
    # launched_at came out of the job approval.launch stamped, not the clock.
    assert row["launched_at"] == live["launched_at"]
    assert row["measured_at"] == "2026-09-27T05:02:00Z"
    assert row["date_preset"] == "maximum"
    assert row["metrics"]["impressions"] == 4100
    assert row["metrics"]["ctr"] == pytest.approx(1.24)
    # plays_3s is read out of `actions` where action_type == "video_view";
    # results out of the first of lead/schedule/contact/link_click.
    assert row["metrics"]["plays_3s"] == 1189
    assert row["metrics"]["results"] == 51
    assert row["metrics"]["cost_per_result"] == pytest.approx(0.61)
    # Absent is null, never 0: this body carries no quartiles.
    assert row["metrics"]["p25"] is None
    assert row["derived"]["hook_rate"] == pytest.approx(0.29, abs=0.01)
    assert row["derived"]["hold_rate"] == pytest.approx(0.207, abs=0.01)

    measure.write_measurements(rows, tree / "measurements.json", now=MEASURED_AT)
    reloaded = measure.load(tree / "measurements.json")["rows"]
    assert [r["ad_id"] for r in reloaded] == sorted(AD_IDS)

    # --- 9. job + row -> own corpus records (C1) ---------------------------
    own = feedback.load_own(tree / "seeds.yaml")
    own_records = [feedback.record_for(live, r, own=own) for r in rows]

    mine = own_records[0]
    assert mine["id"] == "fb-own-%s-%s" % (SEGMENT_ID, AD_IDS[0])
    assert mine["origin"] == "own"
    assert mine["model"] == "none (authored)"
    assert mine["channel"] == "DoviLoop", "the seeds' own: block reached the record"
    assert mine["metrics"]["page_id"] == "5550001"
    # The measurement's numbers, not a second reading of them.
    assert mine["metrics"]["eu_total_reach"] == row["metrics"]["reach"]
    assert mine["metrics"]["days_running"] == 6, "measured_at - launched_at, floored"
    assert mine["metrics"]["variants"] == len(AD_IDS)
    assert mine["analysis"]["own_metrics"]["ctr"] == row["metrics"]["ctr"]
    # The copy is the job's English, and the hook is its first sentence.
    assert mine["analysis"]["copy"]["primary_text"] == live["primary_text"]["en"]
    assert mine["analysis"]["hook"]["text"].startswith("Every week a payroll client")
    assert mine["analysis"]["cta"]["type"] == "learn-more"
    assert mine["analysis"]["offer"]["type"] == "guarantee"
    assert mine["analysis"]["structure"] == ["hook", "offer", "cta"]

    for record in own_records:
        corpus.save(record, tree / "corpus")

    # --- 10. the corpus, learned again -> a ctr pattern a concept can cite --
    after = learn.build(corpus.load_all(tree / "corpus"))
    assert after["corpus_size"] == 6

    ctr_patterns = [p for p in after["patterns"] if p["kind"] == "ctr"]
    assert ctr_patterns, (
        "engine.learn found no ctr pattern over %d own records carrying "
        "analysis.own_metrics.ctr; the loop does not close"
        % len(own_records)
    )
    ctr = ctr_patterns[0]
    assert ctr["device"] == "ctr-pct:1.0-1.9"
    assert ctr["evidence"] == sorted(r["id"] for r in own_records)
    assert ctr["n"] == len(own_records)

    # ...and a concept can cite it: the same call as step 4, over the grown
    # patterns document, with the ctr pattern's id in pattern_ids.
    learn.write(after, tree / "patterns.json")
    closing = concepts.generate(
        after, [_segment()], n=2,
        client=StubClient([json_reply(concept_reply([ctr["id"]]))]),
    )
    assert closing[0]["pattern_ids"] == [ctr["id"]]

    # The scorer reads it out of the file as evidence like any other pattern.
    cited = _context(tree).patterns[ctr["id"]]
    assert cited["n"] == len(own_records)


# ===========================================================================
# THE JOINS, one at a time
# ===========================================================================

def test_discover_writes_exactly_what_analyse_reads(tree):
    """C2 -> analyse. analyse._check_candidates names every key it needs; a
    candidate discover builds must carry all of them."""
    candidates, _ = _discover(tree)
    for candidate in candidates:
        for key in analyse.CANDIDATE_KEYS:
            assert key in candidate, "discover wrote no %r" % key
    # No exception: the reader accepts the writer's output as it stands.
    assert analyse._check_candidates(candidates) == [c["id"] for c in candidates]


def test_analyse_writes_exactly_what_corpus_and_learn_read(tree):
    """C1 -> corpus.validate -> learn. A record analyse returns is already
    valid, and every key learn counts is one analyse wrote."""
    candidates, _ = _discover(tree)
    records = _analyse_and_save(candidates, tree)
    for record in records:
        corpus.validate(record)  # raises CorpusInvalid if the seam has a hole

    skips: list[str] = []
    document = learn.build(records, on_skip=skips.append)
    assert skips == [], "learn could not read what analyse wrote: %s" % skips
    assert document["patterns"], "no pattern at all over four analysed ads"


def test_concepts_cannot_cite_a_pattern_learn_did_not_mint(tree):
    """The citation seam has teeth. If concepts accepted an invented id, step 4
    of the walk above would prove nothing."""
    candidates, _ = _discover(tree)
    _analyse_and_save(candidates, tree)
    patterns = _patterns(tree)
    assert "q99" not in {p["id"] for p in patterns["patterns"]}

    client = StubClient([json_reply(concept_reply(["q99"]))])
    with pytest.raises(concepts.UnknownPatternError) as caught:
        concepts.generate(patterns, [_segment()], n=2, client=client)
    assert "q99" in str(caught.value)


def test_the_placement_the_concept_chose_decides_the_creative(tree):
    """The sibling's recorded defect, guarded: engine/propose.py there
    hardcoded `--template reel-c`, so every reel came out identical and every
    test passed. Here a static concept must produce a still."""
    reel = write.generate(
        _segment(),
        concept={"id": "a01", "segment": SEGMENT_ID, "placement": "reels-9x16",
                 "offer": "guarantee", "pattern_ids": ["q01"],
                 "angle": "...", "hook": "...", "needs_numbers": False},
        client=StubClient([json_reply(written_reply())]), now=PROPOSED_AT,
    )
    still = write.generate(
        _segment(),
        concept={"id": "a02", "segment": SEGMENT_ID, "placement": "static-1x1",
                 "offer": "none", "pattern_ids": ["q01"],
                 "angle": "...", "hook": "...", "needs_numbers": False},
        client=StubClient([json_reply(written_reply())]), now=PROPOSED_AT,
    )

    assert reel["creative_source"]["kind"] == "reel"
    assert still["creative_source"]["kind"] == "still"
    assert reel["creative_source"] != still["creative_source"]
    # ...and the offer travelled too, rather than being stamped from a default.
    assert reel["offer"] == "guarantee" and still["offer"] == "none"
    assert gate.structural(reel).ok and gate.structural(still).ok


def test_launch_pins_the_ids_measure_looks_up(tree):
    """approval.launch -> measure/feedback. The `ads` map is the only record of
    which ad carried which copy; feedback refuses a row it does not pin."""
    job = write.generate(
        _segment(),
        concept={"id": "a01", "segment": SEGMENT_ID, "placement": "reels-9x16",
                 "offer": "guarantee", "pattern_ids": ["q01"],
                 "angle": "...", "hook": "...", "needs_numbers": False},
        client=StubClient([json_reply(written_reply())]), now=PROPOSED_AT,
    )
    _file_job(job, "built")
    approval.launch(SEGMENT_ID, {AD_IDS[0]: {"campaign_id": CAMPAIGN_ID,
                                             "adset_id": ADSET_ID}},
                    now=LAUNCHED_AT)
    live = approval.load_job(approval.locate(SEGMENT_ID))

    row = measure.measurement(
        segment=SEGMENT_ID, ad_id=AD_IDS[0], campaign_id=CAMPAIGN_ID,
        launched_at=live["launched_at"],
        insights=insights_body(impressions=4100, clicks=51, ctr=1.24),
        now=MEASURED_AT,
    )
    assert feedback.record_for(live, row, own=None)["id"].endswith(AD_IDS[0])

    # A row for an ad this job never launched is refused by name, not credited
    # to this copy.
    stray = dict(row, ad_id="999999")
    with pytest.raises(feedback.SkippedAd) as caught:
        feedback.record_for(live, stray, own=None)
    assert "999999" in str(caught.value) or "pins ad ids" in str(caught.value)


def test_a_null_ctr_never_becomes_a_zero_band(tree):
    """measure -> feedback -> learn, for the reading nobody could take. An ad
    with impressions but no ctr must not land in the bottom band as an ad
    nobody clicked."""
    body = insights_body(impressions=4100, clicks=0, ctr=1.24)
    body.pop("ctr")
    row = measure.measurement(
        segment=SEGMENT_ID, ad_id=AD_IDS[0], campaign_id=CAMPAIGN_ID,
        launched_at="2026-09-20T10:00:00Z", insights=body, now=MEASURED_AT,
    )
    assert row["metrics"]["ctr"] is None

    job = write.generate(
        _segment(),
        concept={"id": "a01", "segment": SEGMENT_ID, "placement": "reels-9x16",
                 "offer": "guarantee", "pattern_ids": ["q01"],
                 "angle": "...", "hook": "...", "needs_numbers": False},
        client=StubClient([json_reply(written_reply())]), now=PROPOSED_AT,
    )
    _file_job(job, "built")
    approval.launch(SEGMENT_ID, {AD_IDS[0]: {"campaign_id": None, "adset_id": None}},
                    now=LAUNCHED_AT)
    live = approval.load_job(approval.locate(SEGMENT_ID))

    record = feedback.record_for(live, row, own=None)
    assert record["analysis"]["own_metrics"]["ctr"] is None

    skips: list[str] = []
    document = learn.build([record, dict(record, id=record["id"] + "-b")],
                           on_skip=skips.append)
    assert not [p for p in document["patterns"] if p["kind"] == "ctr"], (
        "a null ctr was banded; engine/learn.py must leave it out entirely"
    )
