"""Our own launched ads as corpus records: is the record true, and does an ad
with nothing to say stay out of the corpus?

Everything here is offline. The job and the row are fixtures - copies of the
C3 and C6 examples in docs/CONTRACTS.md with knobs, not imports of anything -
and no test needs a key, a token or a socket, which is the point of the module
under test: it derives what it can prove and refuses to invent the rest, so
there is nothing for a model to be asked. An autouse fixture makes every
socket explode to hold it to that.
"""
import ast
import copy
import json
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine import approval, corpus, discover, feedback, learn

REPO = Path(__file__).resolve().parents[1]

SEGMENT = "audit-firms"
AD_ID = "1234"

# C3 after `approval launch`: the worked example's copy, restamped to a
# backlog segment, with one ad id pinned and launched_at written. Only the
# fields this module reads are load-bearing; the rest are here so the fixture
# is a complete job and a future reader of a field it does not read today
# fails loudly.
JOB = {
    "id": SEGMENT,
    "segment": SEGMENT,
    "concept_id": "a01",
    "pattern_ids": ["q03", "q07"],
    "placement": "reels-9x16",
    "offer": "guarantee",
    "hypothesis": "one sentence on what this ad tests; not gated",
    "primary_text": {
        "en": (
            "Every week a client asks for a certificate of cover, a renewal "
            "figure, or whether the tools left in the van overnight are "
            "covered.\n\nDoviLoop turns your own policy wordings, renewal terms "
            "and certificate process into a reply already waiting in each "
            "broker's Outlook drafts, in their own words.\n\nNothing sends "
            "until they read it. Nothing leaves Europe. If the drafts are not "
            "good enough to send, you do not pay and you keep the knowledge "
            "base."
        ),
        "da": "NEEDS_NATIVE_PROOFREAD",
        "lt": "NEEDS_NATIVE_PROOFREAD",
    },
    "headline": {
        "en": "Proof of cover, already drafted",
        "da": "NEEDS_NATIVE_PROOFREAD",
        "lt": "NEEDS_NATIVE_PROOFREAD",
    },
    "description": {
        "en": "Built for insurance brokers in Denmark and Lithuania",
        "da": "NEEDS_NATIVE_PROOFREAD",
        "lt": "NEEDS_NATIVE_PROOFREAD",
    },
    "cta": "LEARN_MORE",
    "destination": "https://doviloop.dev",
    "creative_source": {
        "kind": "reel",
        "repo": "reel-engine",
        "template": "reel-c",
        "selection": "queue/proposed/audit-firms.reel.json",
    },
    "proposed_at": "2026-09-22T09:03:00Z",
    "ads": {AD_ID: {"campaign_id": "5678", "adset_id": None}},
    "launched_at": "2026-09-29T10:00:00Z",
}

HOOK = (
    "Every week a client asks for a certificate of cover, a renewal figure, "
    "or whether the tools left in the van overnight are covered."
)

# C6, one row, exactly as docs/CONTRACTS.md prints it. Real-looking numbers: a
# row whose impressions are zero is exactly the thing this module refuses.
ROW = {
    "segment": SEGMENT,
    "ad_id": AD_ID,
    "campaign_id": "5678",
    "launched_at": "2026-09-29T10:00:00Z",
    "measured_at": "2026-10-06T05:02:00Z",
    "date_preset": "maximum",
    "metrics": {
        "impressions": 4100, "reach": 3300, "clicks": 51, "ctr": 1.24,
        "cpc": 0.61, "cpm": 7.6, "spend": 31.2, "plays_3s": 1200,
        "thruplays": 240, "p25": None, "p50": None, "p75": None, "p100": None,
        "results": 4, "cost_per_result": 7.8,
    },
    "derived": {"hook_rate": 0.293, "hold_rate": 0.2},
}

OWN = feedback.Own(page_id="1007614045762121", page_name="DoviLoop")

RECORD_ID = "fb-own-%s-%s" % (SEGMENT, AD_ID)


def job(**overrides) -> dict:
    fresh = copy.deepcopy(JOB)
    fresh.update(overrides)
    return fresh


def row(**overrides) -> dict:
    fresh = copy.deepcopy(ROW)
    fresh.update(overrides)
    return fresh


def with_metrics(**changes) -> dict:
    fresh = row()
    fresh["metrics"].update(changes)
    return fresh


def record(**kwargs) -> dict:
    kwargs.setdefault("own", OWN)
    return feedback.record_for(kwargs.pop("job", None) or job(),
                               kwargs.pop("row", None) or row(), **kwargs)


def measurements(*rows, schema=1) -> dict:
    return {
        "schema": schema,
        "generated_at": "2026-10-06T05:02:00Z",
        "rows": list(rows if rows else [ROW]),
    }


def write_measurements(path: Path, *rows, **kwargs) -> Path:
    path.write_text(json.dumps(measurements(*rows, **kwargs)), encoding="utf-8")
    return path


def write_seeds(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


FILLED_SEEDS = (
    "countries: [DK, LT]\npages: []\nqueries: []\nown:\n"
    '  page_id: "1007614045762121"\n  page_name: DoviLoop\n'
    "  ad_account_id: act_1\n"
)
BLANK_SEEDS = "countries: [DK, LT]\npages: []\nqueries: []\nown:\n  page_id:\n  page_name:\n  ad_account_id:\n"


@pytest.fixture(autouse=True)
def no_sockets(monkeypatch):
    """Nothing in this module may open one. If a test ever needs to, the
    module has grown a transport it must not have."""

    def explode(*args, **kwargs):
        raise AssertionError("engine.feedback tried to open a socket")

    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(socket, "create_connection", explode)


@pytest.fixture
def queue(tmp_path, monkeypatch) -> Path:
    """A throwaway queue with the four stage directories, the way the approval
    tests redirect the whole module: engine.approval reads QUEUE at call time."""
    root = tmp_path / "queue"
    for stage in approval.ALL_STAGES:
        (root / stage).mkdir(parents=True)
    monkeypatch.setattr(approval, "QUEUE", root)
    return root


def launch(queue: Path, segment: str, document: dict | None = None) -> Path:
    """Put a job in queue/launched/ the way approval.launch leaves it: keys in
    authored order, no sort_keys, trailing newline."""
    document = document if document is not None else job(id=segment, segment=segment)
    path = queue / "launched" / ("%s.json" % segment)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


@pytest.fixture
def workspace(tmp_path, queue):
    """Everything feed_back reads and writes, redirected: a launched job, a
    measurements file, a filled seeds file and an empty corpus."""
    launch(queue, SEGMENT)
    return {
        "queue": queue,
        "measurements": write_measurements(tmp_path / "measurements.json"),
        "seeds": write_seeds(tmp_path / "seeds.yaml", FILLED_SEEDS),
        "corpus": tmp_path / "corpus",
    }


def run(workspace, **kwargs) -> feedback.FeedbackRun:
    return feedback.feed_back(
        corpus_root=workspace["corpus"],
        measurements_path=workspace["measurements"],
        seeds_path=workspace["seeds"],
        **kwargs,
    )


# --- the record --------------------------------------------------------------


def test_a_launched_ad_and_its_row_become_a_record_the_corpus_accepts(tmp_path):
    """The real store, not a restated shape: if this round-trips, engine.learn
    and engine.score can read our own ads through the same door as everyone
    else's."""
    rec = record()
    assert corpus.validate(rec) is None
    path = corpus.save(rec, root=tmp_path)
    assert path.name == "meta-ad-%s.json" % RECORD_ID
    assert corpus.load(path).to_dict() == rec


def test_the_record_is_exactly_what_the_contract_lists():
    """Pinned whole, so a field that drifts shows up as a diff of the contract
    rather than as a downstream test that stopped meaning what it said."""
    rec = record()
    derived = rec["analysis"].pop("derived_from")
    assert rec == {
        "schema": 1,
        "id": RECORD_ID,
        "platform": "meta-ad",
        "url": "https://graph.facebook.com/1234/insights",
        "channel": "DoviLoop",
        "origin": "own",
        "fetched_at": "2026-10-06T05:02:00Z",
        "metrics": {
            "eu_total_reach": 3300,
            "days_running": 6,
            "active": True,
            "variants": 1,
            "page_id": "1007614045762121",
        },
        "analysis": {
            "copy": {
                "primary_text": JOB["primary_text"]["en"],
                "headline": "Proof of cover, already drafted",
                "description": "Built for insurance brokers in Denmark and Lithuania",
                "link_caption": "https://doviloop.dev",
                "words": 77,
            },
            "hook": {"words": 24, "text": HOOK, "device": "authored"},
            "structure": ["hook", "offer", "cta"],
            "offer": {"type": "guarantee", "text": ""},
            "proof": {"type": "none", "text": ""},
            "cta": {"type": "learn-more", "text": ""},
            "objections": [],
            "creative": {"kind": "authored"},
            "own_metrics": {"ctr": 1.24, "hook_rate": 0.293, "hold_rate": 0.2},
        },
        "model": "none (authored)",
    }
    assert derived["note"] == feedback.DERIVED_NOTE


def test_the_constants_are_the_ones_the_contract_names():
    assert feedback.ORIGIN == "own"
    assert feedback.MODEL == "none (authored)"
    assert feedback.PLATFORM == corpus.PLATFORMS[0] == "meta-ad"
    assert feedback.MEASUREMENTS_SCHEMA == 1
    assert feedback.HOOK_DEVICE == "authored"
    assert feedback.CREATIVE_KIND == "authored"
    assert feedback.ID_PREFIX == "fb-own-"


def test_own_is_an_origin_the_corpus_allows():
    assert "own" in corpus.ORIGINS
    assert record()["origin"] == "own"


def test_the_id_names_our_own_ad_the_segment_and_the_ad_id():
    """`fb-own-` so it can never collide with discover's `fb-<library id>`, and
    the ad id so two ads launched from one job are two records."""
    rec = record()
    assert rec["id"] == "fb-own-audit-firms-1234"
    assert rec["id"].startswith(feedback.ID_PREFIX)
    assert corpus.path_for(rec).name == "meta-ad-fb-own-audit-firms-1234.json"


def test_two_ads_from_one_job_are_two_records_not_a_duplicate_id(tmp_path):
    two = job(ads={"1234": {"campaign_id": "5678", "adset_id": None},
                   "1235": {"campaign_id": "5678", "adset_id": None}})
    for ad_id in ("1234", "1235"):
        corpus.save(feedback.record_for(two, row(ad_id=ad_id), own=OWN), root=tmp_path)
    assert [r.id for r in corpus.load_all(tmp_path)] == [
        "fb-own-audit-firms-1234", "fb-own-audit-firms-1235",
    ]


def test_the_id_and_the_bytes_are_stable_across_two_runs():
    """Nothing here reads the clock: re-running the step on an unchanged job
    and row has to rewrite the same bytes, or every weekly commit carries a
    diff that says nothing changed."""
    first, second = record(), record()
    assert first == second
    assert first["id"] == second["id"] == RECORD_ID
    dump = lambda r: json.dumps(r, sort_keys=True, indent=2, ensure_ascii=False)
    assert dump(first) == dump(second)


def test_now_is_accepted_and_changes_nothing():
    """The contract fixes now= on the signature; the record depends on the
    row's and the job's stamps only, so two different clocks give one record."""
    then = datetime(2026, 10, 6, 5, 2, tzinfo=timezone.utc)
    assert record(now=then) == record(now=then + timedelta(days=400)) == record()


def test_fetched_at_is_when_the_row_was_measured():
    """learn's generated_at is the newest fetched_at in the corpus, so this has
    to be the measurement's stamp and not a clock reading here."""
    assert record()["fetched_at"] == ROW["measured_at"]


def test_the_url_is_the_insights_edge_the_numbers_were_read_from():
    """The one read for our own ads (docs/CONTRACTS.md), the way a competitor
    record's url is the archive page it was read from. Not an Ad Library page:
    whether the Ads Manager id is also the Library id is unverified."""
    rec = record()
    assert rec["url"] == feedback.INSIGHTS_URL.format(ad_id=AD_ID)
    assert "graph.facebook.com/1234/insights" in rec["url"]
    assert "ads/library" not in rec["url"]


def test_the_model_field_says_no_model_read_this():
    """A record that named a model would be indistinguishable from one a model
    actually produced."""
    assert record()["model"] == "none (authored)"
    assert "none" in record()["model"]


# --- whose ad it is ----------------------------------------------------------


def test_the_channel_is_our_page_and_the_page_id_is_ours():
    rec = record(own=OWN)
    assert rec["channel"] == "DoviLoop"
    assert rec["metrics"]["page_id"] == "1007614045762121"


def test_a_discover_own_block_is_read_the_same_way():
    """The contract types `own` as discover.Own; the field names are the same,
    so the real thing passes through without this module importing it."""
    own = discover.Own(page_id="1007614045762121", page_name="DoviLoop",
                       ad_account_id="act_1")
    assert record(own=own) == record(own=OWN)


def test_a_blank_own_block_yields_an_empty_page_id_and_channel_own():
    """The shipped state of research/seeds.yaml. Not a crash and not a guess:
    page_id "" is true until somebody fills the block in, and "own" still says
    whose ad it is."""
    for blank in (None, feedback.Own(), feedback.Own(page_id="", page_name="  "),
                  discover.Own(), {}):
        rec = record(own=blank)
        assert rec["metrics"]["page_id"] == ""
        assert rec["channel"] == "own"
        assert corpus.validate(rec) is None


def test_a_mapping_own_block_is_read_too():
    rec = record(own={"page_id": "42", "page_name": "Us"})
    assert rec["metrics"]["page_id"] == "42"
    assert rec["channel"] == "Us"


# --- the numbers -------------------------------------------------------------


def test_the_reach_is_the_rows_reach():
    assert record()["metrics"]["eu_total_reach"] == 3300
    assert record(row=with_metrics(reach=12))["metrics"]["eu_total_reach"] == 12


def test_a_null_reach_stays_null_and_is_never_zero():
    """engine.measure writes absent as null. Here it stays null: learn leaves a
    null out of median_reach and says so; a 0 would count as an ad nobody saw."""
    rec = record(row=with_metrics(reach=None))
    assert rec["metrics"]["eu_total_reach"] is None
    assert corpus.validate(rec) is None
    skips = []
    document = learn.build([rec], on_skip=skips.append)
    assert document["corpus_size"] == 1
    assert any("eu_total_reach" in m and RECORD_ID in m for m in skips)


def test_a_reach_that_is_junk_is_refused_by_name():
    """corpus does not type-check inside metrics, so "3.3k" would reach learn
    and be dropped out of every median without anyone being told."""
    for junk in ("3.3k", True, 3300.5, float("nan")):
        with pytest.raises(feedback.SkippedAd, match="reach"):
            record(row=with_metrics(reach=junk))


def test_days_running_is_the_measured_window_in_whole_days():
    """The C6 example: launched 29 Sep 10:00, measured 6 Oct 05:02 - six days
    and nineteen hours, so 6. The window the numbers cover, not the age of the
    ad today: that would need the clock."""
    assert record()["metrics"]["days_running"] == 6
    same_day = record(row=row(measured_at="2026-09-30T09:59:59Z"))
    assert same_day["metrics"]["days_running"] == 0
    exactly = record(row=row(measured_at="2026-10-13T10:00:00Z"))
    assert exactly["metrics"]["days_running"] == 14


def test_the_window_honours_offsets_and_reads_a_naive_stamp_as_utc():
    plus_two = record(row=row(measured_at="2026-10-06T07:02:00+02:00"))
    assert plus_two["metrics"]["days_running"] == 6
    naive = record(row=row(measured_at="2026-10-06T05:02:00"))
    assert naive["metrics"]["days_running"] == 6


def test_a_measurement_before_the_launch_is_skipped_by_name():
    """A negative window means one of the two stamps is wrong; flooring it to
    zero would hide that in a field that looks like a day count."""
    with pytest.raises(feedback.SkippedAd, match="before launched_at") as excinfo:
        record(row=row(measured_at="2026-09-28T10:00:00Z"))
    assert SEGMENT in str(excinfo.value) and AD_ID in str(excinfo.value)


def test_an_unreadable_stamp_at_either_end_is_skipped_by_name():
    with pytest.raises(feedback.SkippedAd, match="launched_at"):
        record(job=job(launched_at=None))
    with pytest.raises(feedback.SkippedAd, match="launched_at"):
        record(job=job(launched_at="last Monday"))
    with pytest.raises(feedback.SkippedAd, match="measured_at"):
        record(row=row(measured_at=""))


def test_active_is_true_for_a_launched_ad():
    assert record()["metrics"]["active"] is True


def test_variants_is_the_number_of_launched_ads():
    three = job(ads={"1234": {"campaign_id": None, "adset_id": None},
                     "1235": {"campaign_id": None, "adset_id": None},
                     "1236": {"campaign_id": None, "adset_id": None}})
    assert record(job=three)["metrics"]["variants"] == 3
    assert record()["metrics"]["variants"] == 1


def test_a_row_for_an_ad_the_job_does_not_pin_is_skipped_by_name():
    """Crediting this copy with numbers from an ad it may not have earned is
    the wrong pin that looks correct forever."""
    with pytest.raises(feedback.SkippedAd, match="pins ad ids 1234") as excinfo:
        record(row=row(ad_id="9999"))
    assert excinfo.value.segment == SEGMENT
    assert excinfo.value.ad_id == "9999"
    with pytest.raises(feedback.SkippedAd, match="pins ad ids none"):
        record(job=job(ads={}))


def test_a_row_for_another_segment_is_skipped_by_name():
    with pytest.raises(feedback.SkippedAd, match="payroll-bureaus") as excinfo:
        record(row=row(segment="payroll-bureaus"))
    assert "audit-firms" in str(excinfo.value)


def test_a_row_with_no_ad_id_or_a_job_with_no_segment_is_skipped():
    with pytest.raises(feedback.SkippedAd, match="ad id"):
        record(row=row(ad_id=""))
    with pytest.raises(feedback.SkippedAd, match="segment"):
        record(job=job(segment=None), row=row(segment=None))


def test_a_segment_that_cannot_be_half_a_filename_is_refused():
    bad = job(segment="../../etc/passwd")
    with pytest.raises(feedback.SkippedAd, match="filename"):
        record(job=bad, row=row(segment="../../etc/passwd"))


# --- what this module refuses to write ---------------------------------------


def test_zero_impressions_is_skipped_by_name():
    """The named skip the brief asks for: nothing is written, and the message
    says which segment, which ad, and what to do."""
    with pytest.raises(feedback.SkippedAd, match="impressions") as excinfo:
        record(row=with_metrics(impressions=0))
    message = str(excinfo.value)
    assert "audit-firms" in message and "1234" in message
    assert "Measure it again" in message
    assert excinfo.value.segment == "audit-firms"
    assert excinfo.value.ad_id == "1234"


def test_null_or_missing_impressions_are_skipped_the_same_way():
    with pytest.raises(feedback.SkippedAd, match="impressions is None"):
        record(row=with_metrics(impressions=None))
    short = row()
    del short["metrics"]["impressions"]
    with pytest.raises(feedback.SkippedAd, match="impressions"):
        record(row=short)


def test_impressions_that_are_junk_are_refused():
    """True is an int in Python and would count as one impression; a NaN in a
    median poisons every value after it; a count is a whole number."""
    for junk in ("4.1k", True, float("nan"), float("inf"), 4100.5, -3):
        with pytest.raises(feedback.SkippedAd, match="impressions"):
            record(row=with_metrics(impressions=junk))


def test_a_row_with_no_metrics_object_is_skipped_by_name():
    with pytest.raises(feedback.SkippedAd, match="metrics") as excinfo:
        record(row=row(metrics=None))
    assert "audit-firms" in str(excinfo.value)


def test_a_job_short_of_its_english_copy_is_skipped():
    """A launched job passed the gate, which requires all three; one without
    is not the job that shipped, and a record from it would misdescribe the ad."""
    for key in ("primary_text", "headline", "description"):
        empty = job()
        empty[key]["en"] = "   "
        with pytest.raises(feedback.SkippedAd, match="%s.en" % key):
            record(job=empty)
        missing = job()
        del missing[key]
        with pytest.raises(feedback.SkippedAd, match=key):
            record(job=missing)


def test_a_bare_string_is_not_read_as_english():
    """Which language a bare string is in is exactly what nobody wrote down."""
    with pytest.raises(feedback.SkippedAd, match="headline is str"):
        record(job=job(headline="Proof of cover"))


def test_a_job_with_no_cta_or_no_offer_is_skipped():
    with pytest.raises(feedback.SkippedAd, match="cta"):
        record(job=job(cta=""))
    with pytest.raises(feedback.SkippedAd, match="offer"):
        record(job=job(offer=None))


# --- the analysis, and what it does not claim --------------------------------


def test_the_copy_is_the_jobs_english_verbatim_and_the_words_are_counted_here():
    copy_block = record()["analysis"]["copy"]
    assert copy_block["primary_text"] == JOB["primary_text"]["en"]
    assert copy_block["headline"] == JOB["headline"]["en"]
    assert copy_block["description"] == JOB["description"]["en"]
    assert copy_block["words"] == len(JOB["primary_text"]["en"].split()) == 77


def test_the_word_count_is_counted_not_trusted():
    short = job()
    short["primary_text"]["en"] = "One two   three\n\nfour."
    assert record(job=short)["analysis"]["copy"]["words"] == 4


def test_link_caption_is_the_destination_we_wrote():
    assert record()["analysis"]["copy"]["link_caption"] == "https://doviloop.dev"
    assert record(job=job(destination=None))["analysis"]["copy"]["link_caption"] == ""


def test_the_hook_is_the_first_sentence_counted():
    hook = record()["analysis"]["hook"]
    assert hook["text"] == HOOK
    assert hook["words"] == 24 == len(HOOK.split())
    assert hook["device"] == "authored"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("One. Two.", "One."),
        ("Wait... what?", "Wait..."),
        ("Really?! Yes.", "Really?!"),
        ("No punctuation\nSecond line.", "No punctuation"),
        ("Saves 3.5 hours a week. Really.", "Saves 3.5 hours a week."),
        ("See doviloop.dev today", "See doviloop.dev today"),
        ("  spaced   out  ", "spaced out"),
        ("First line,\r\nbroken mid-sentence.", "First line,"),
        ("", ""),
        (None, ""),
    ],
)
def test_first_sentence_is_a_boundary_not_a_judgement(text, expected):
    assert feedback.first_sentence(text) == expected


def test_the_hook_device_says_authored_rather_than_naming_a_move():
    """Which rhetorical device our hook "is" would be a guess, and a guessed
    label travels into next week's concept as evidence."""
    assert record()["analysis"]["hook"]["device"] == "authored"


def test_the_structure_follows_the_offer_and_claims_nothing_else():
    assert record()["analysis"]["structure"] == ["hook", "offer", "cta"]
    assert record(job=job(offer="none"))["analysis"]["structure"] == ["hook", "cta"]
    assert record(job=job(offer="demo"))["analysis"]["structure"] == ["hook", "offer", "cta"]


def test_the_cta_type_is_the_buttons_lowercase_hyphen_form():
    assert record()["analysis"]["cta"] == {"type": "learn-more", "text": ""}
    assert record(job=job(cta="BOOK_NOW"))["analysis"]["cta"]["type"] == "book-now"
    assert record(job=job(cta=" Sign_Up "))["analysis"]["cta"]["type"] == "sign-up"


def test_the_offer_type_is_the_jobs_offer_and_its_wording_is_not_picked():
    assert record()["analysis"]["offer"] == {"type": "guarantee", "text": ""}
    assert record(job=job(offer="design_partner"))["analysis"]["offer"]["type"] == "design_partner"


def test_proof_is_none_and_objections_are_empty():
    """Whether a line is proof, and which objection it answers, is written down
    nowhere this module can read."""
    analysis = record()["analysis"]
    assert analysis["proof"] == {"type": "none", "text": ""}
    assert analysis["objections"] == []


def test_the_creative_says_authored():
    assert record()["analysis"]["creative"] == {"kind": "authored"}


def test_own_metrics_are_copied_through_nulls_and_all():
    """The whole reason this stage exists: the click-through is real, and a
    rate the API did not give stays null - never 0, which learn would band as
    an ad nobody clicked."""
    assert record()["analysis"]["own_metrics"] == {
        "ctr": 1.24, "hook_rate": 0.293, "hold_rate": 0.2,
    }
    nulls = row(derived={"hook_rate": None, "hold_rate": None})
    nulls["metrics"]["ctr"] = None
    block = record(row=nulls)["analysis"]["own_metrics"]
    assert block == {"ctr": None, "hook_rate": None, "hold_rate": None}
    assert list(block) == list(feedback.OWN_METRIC_KEYS)


def test_a_row_with_no_derived_block_has_null_rates_not_zeros():
    block = record(row=row(derived=None))["analysis"]["own_metrics"]
    assert block["ctr"] == 1.24
    assert block["hook_rate"] is None and block["hold_rate"] is None


def test_a_ctr_that_is_junk_is_carried_for_learn_to_name_not_coerced_here():
    """One coercion, in engine.learn, which reports it by id and field; a
    second one here would be a second place for the two to disagree."""
    junk = with_metrics(ctr="1.2%")
    rec = record(row=junk)
    assert rec["analysis"]["own_metrics"]["ctr"] == "1.2%"
    skips = []
    learn.build([rec], on_skip=skips.append)
    assert any("own_metrics.ctr" in m and "1.2%" in m for m in skips)


def test_the_record_does_not_alias_the_row_or_the_job():
    """A record sharing the row's dict would change under whoever edits the
    measurement next."""
    source_row, source_job = row(), job()
    rec = feedback.record_for(source_job, source_row, own=OWN)
    source_row["metrics"]["ctr"] = 9.9
    source_row["derived"]["hook_rate"] = 0.0
    source_job["pattern_ids"].append("q99")
    source_job["primary_text"]["en"] = "changed"
    assert rec["analysis"]["own_metrics"] == {"ctr": 1.24, "hook_rate": 0.293, "hold_rate": 0.2}
    assert rec["analysis"]["derived_from"]["pattern_ids"] == ["q03", "q07"]
    assert rec["analysis"]["copy"]["primary_text"].startswith("Every week")


def test_the_derived_from_note_names_every_derived_field():
    """Whoever opens research/corpus/ next should not have to find this module
    to know which fields nobody analysed."""
    derived = record()["analysis"]["derived_from"]
    note = derived["note"]
    assert "not analysed" in note
    assert "no model call" in note
    for named in ("hook", "first sentence", "'authored'", "structure", "offer id",
                  "offer.text", "cta.text", "proof", "objections", "link_caption",
                  "days_running", "measured_at minus launched_at", "variants",
                  "page_id", "words counted here", "own_metrics", "nulls",
                  "engine/feedback.py"):
        assert named in note, named


def test_the_provenance_names_the_job_the_concept_and_the_patterns():
    derived = record()["analysis"]["derived_from"]
    assert derived["kind"] == "authored"
    assert derived["segment"] == SEGMENT
    assert derived["ad_id"] == AD_ID
    assert derived["campaign_id"] == "5678"
    assert derived["adset_id"] is None
    assert derived["concept_id"] == "a01"
    assert derived["pattern_ids"] == ["q03", "q07"]
    assert derived["placement"] == "reels-9x16"
    assert derived["creative_kind"] == "reel"
    assert derived["launched_at"] == JOB["launched_at"]


def test_the_provenance_rides_inside_analysis_because_the_top_level_is_closed():
    """corpus.validate rejects an unknown top-level key, so anything extra has
    to live in analysis - and this record still validates."""
    rec = record()
    assert "derived_from" not in rec and "own_metrics" not in rec
    assert set(rec) == set(corpus.REQUIRED_KEYS)
    assert corpus.validate(rec) is None


def test_non_ascii_copy_survives_the_store(tmp_path):
    """ensure_ascii stays off in the corpus so a proofread line is legible in
    review; the module itself stays ASCII (below), the data need not."""
    accented = job()
    accented["headline"]["en"] = "Proof of cover for Søren"
    rec = record(job=accented)
    path = corpus.save(rec, root=tmp_path)
    assert "Søren" in path.read_text(encoding="utf-8")
    assert corpus.load(path).to_dict() == rec


def test_the_real_example_job_makes_a_record(tmp_path):
    """No copy of the copy: creative/example-job.json as the gate ships it,
    restamped and launched the way approval would leave it."""
    example = json.loads((REPO / "creative" / "example-job.json").read_text(encoding="utf-8"))
    example.update(id=SEGMENT, segment=SEGMENT, ads=JOB["ads"],
                   launched_at=JOB["launched_at"])
    rec = feedback.record_for(example, row(), own=None)
    assert rec["analysis"]["hook"]["text"].startswith("Every week a client asks")
    assert rec["analysis"]["copy"]["headline"] == "Proof of cover, already drafted"
    assert corpus.load(corpus.save(rec, root=tmp_path)).to_dict() == rec


# --- the measurements file ---------------------------------------------------


def test_measurements_load_as_their_rows(tmp_path):
    path = write_measurements(tmp_path / "measurements.json")
    assert feedback.load_measurements(path) == [ROW]


def test_a_missing_measurements_file_says_what_to_run(tmp_path):
    with pytest.raises(FileNotFoundError, match="engine.measure"):
        feedback.load_measurements(tmp_path / "nowhere.json")


def test_a_measurements_file_from_another_schema_is_refused(tmp_path):
    """Reading schema 2 with schema 1's expectations mis-reads every field it
    thinks it recognises."""
    path = write_measurements(tmp_path / "measurements.json", schema=2)
    with pytest.raises(feedback.MeasurementsInvalid, match="schema"):
        feedback.load_measurements(path)


def test_measurements_that_are_not_json_name_the_file(tmp_path):
    path = tmp_path / "measurements.json"
    path.write_text("{ truncated", encoding="utf-8")
    with pytest.raises(feedback.MeasurementsInvalid, match="not valid JSON"):
        feedback.load_measurements(path)


def test_rows_that_are_not_a_list_are_refused(tmp_path):
    path = tmp_path / "measurements.json"
    path.write_text(json.dumps({"schema": 1, "rows": {"segment": "a"}}), encoding="utf-8")
    with pytest.raises(feedback.MeasurementsInvalid, match="rows"):
        feedback.load_measurements(path)
    path.write_text(json.dumps({"schema": 1, "rows": [ROW, "junk"]}), encoding="utf-8")
    with pytest.raises(feedback.MeasurementsInvalid, match=r"rows\[1\]"):
        feedback.load_measurements(path)
    path.write_text(json.dumps([ROW]), encoding="utf-8")
    with pytest.raises(feedback.MeasurementsInvalid, match="holds a list"):
        feedback.load_measurements(path)


# --- the seeds file's own block ----------------------------------------------


def test_the_shipped_seeds_file_has_a_blank_own_block_and_loads():
    """The real file, as committed: blank is the shipped state, so a fresh
    checkout feeds back with page_id "" and channel "own" rather than
    crashing."""
    own = feedback.load_own()
    assert own == feedback.Own()
    assert feedback.load_own(REPO / "research" / "seeds.yaml") == own


def test_a_filled_own_block_is_read(tmp_path):
    own = feedback.load_own(write_seeds(tmp_path / "seeds.yaml", FILLED_SEEDS))
    assert own == feedback.Own(page_id="1007614045762121", page_name="DoviLoop",
                               ad_account_id="act_1")


def test_an_unquoted_page_id_is_read_back_as_the_string_it_is(tmp_path):
    """YAML reads an unquoted number as an int; the id is a string of digits
    either way."""
    text = FILLED_SEEDS.replace('"1007614045762121"', "1007614045762121")
    assert feedback.load_own(write_seeds(tmp_path / "s.yaml", text)).page_id == "1007614045762121"


def test_a_page_id_that_is_not_digits_is_refused_with_the_fix(tmp_path):
    text = FILLED_SEEDS.replace('"1007614045762121"', "DoviLoop")
    with pytest.raises(feedback.SeedsInvalid, match="all digits"):
        feedback.load_own(write_seeds(tmp_path / "s.yaml", text))


def test_an_own_block_that_is_not_a_mapping_is_refused(tmp_path):
    with pytest.raises(feedback.SeedsInvalid, match="own is a str"):
        feedback.load_own(write_seeds(tmp_path / "s.yaml", "own: DoviLoop\n"))
    with pytest.raises(feedback.SeedsInvalid, match="page_id is a list"):
        feedback.load_own(write_seeds(tmp_path / "s.yaml", "own:\n  page_id: [1]\n"))


def test_an_empty_or_ownless_seeds_file_is_a_blank_block(tmp_path):
    assert feedback.load_own(write_seeds(tmp_path / "a.yaml", "")) == feedback.Own()
    assert feedback.load_own(write_seeds(tmp_path / "b.yaml", "pages: []\n")) == feedback.Own()
    assert feedback.load_own(write_seeds(tmp_path / "c.yaml", BLANK_SEEDS)) == feedback.Own()


def test_a_missing_seeds_file_is_named(tmp_path):
    with pytest.raises(FileNotFoundError, match="seeds"):
        feedback.load_own(tmp_path / "nowhere.yaml")


def test_seeds_that_are_not_yaml_are_refused(tmp_path):
    with pytest.raises(feedback.SeedsInvalid, match="not YAML"):
        feedback.load_own(write_seeds(tmp_path / "s.yaml", "own: [unclosed\n"))


# --- the launched queue as a whole -------------------------------------------


def test_feed_back_writes_the_record_for_the_measured_ad(workspace):
    result = run(workspace)
    assert result.skipped == []
    assert [p.name for p in result.written] == ["meta-ad-%s.json" % RECORD_ID]
    assert result.written[0].parent == workspace["corpus"]
    assert [r["id"] for r in result.records] == [RECORD_ID]
    assert result.records[0]["metrics"]["page_id"] == "1007614045762121"
    assert result.records[0]["channel"] == "DoviLoop"
    loaded = corpus.load_all(workspace["corpus"])
    assert [r.id for r in loaded] == [RECORD_ID]
    assert loaded[0].to_dict() == result.records[0]


def test_the_written_file_has_the_committed_json_shape(workspace):
    result = run(workspace)
    text = result.written[0].read_text(encoding="utf-8")
    assert text == json.dumps(result.records[0], sort_keys=True, indent=2,
                              ensure_ascii=False) + "\n"


def test_a_dry_run_names_the_paths_and_writes_nothing(workspace):
    result = run(workspace, dry_run=True)
    assert [p.name for p in result.written] == ["meta-ad-%s.json" % RECORD_ID]
    assert [r["id"] for r in result.records] == [RECORD_ID]
    assert not workspace["corpus"].exists()


def test_a_launched_ad_nobody_measured_is_reported_not_written_as_zeros(workspace):
    launch(workspace["queue"], "payroll-bureaus")
    result = run(workspace)
    assert [r["id"] for r in result.records] == [RECORD_ID]
    assert len(result.skipped) == 1
    assert "payroll-bureaus" in result.skipped[0]
    assert "not measured yet" in result.skipped[0]


def test_a_row_whose_job_is_not_launched_is_reported_not_dropped(workspace):
    write_measurements(workspace["measurements"], ROW, row(segment="ghost-segment"))
    result = run(workspace)
    assert [r["id"] for r in result.records] == [RECORD_ID]
    assert any("ghost-segment" in m and "queue/launched/ghost-segment.json" in m
               for m in result.skipped)


def test_a_row_with_no_segment_is_reported_by_position(workspace):
    write_measurements(workspace["measurements"], row(segment=""), ROW)
    result = run(workspace)
    assert [r["id"] for r in result.records] == [RECORD_ID]
    assert any(m.startswith("rows[0]") and "no segment" in m for m in result.skipped)


def test_one_bad_ad_does_not_cost_the_others_their_record(workspace):
    launch(workspace["queue"], "payroll-bureaus")
    dead = row(segment="payroll-bureaus")
    dead["metrics"]["impressions"] = 0
    write_measurements(workspace["measurements"], ROW, dead)
    result = run(workspace)
    assert [r["id"] for r in result.records] == [RECORD_ID]
    assert any("payroll-bureaus" in m and "impressions" in m for m in result.skipped)


def test_rows_for_one_job_are_handled_in_ad_id_order_whatever_the_file_order(workspace):
    two = job(ads={"1234": {"campaign_id": None, "adset_id": None},
                   "1200": {"campaign_id": None, "adset_id": None}})
    launch(workspace["queue"], SEGMENT, two)
    write_measurements(workspace["measurements"], ROW, row(ad_id="1200"))
    result = run(workspace)
    assert [r["id"] for r in result.records] == [
        "fb-own-audit-firms-1200", "fb-own-audit-firms-1234",
    ]
    assert all(r["metrics"]["variants"] == 2 for r in result.records)


def test_a_job_that_is_not_json_or_disagrees_with_its_name_is_reported(workspace):
    (workspace["queue"] / "launched" / ("%s.json" % SEGMENT)).write_text(
        "{ truncated", encoding="utf-8")
    result = run(workspace)
    assert result.records == []
    assert any(SEGMENT in m and "not JSON" in m for m in result.skipped)

    launch(workspace["queue"], SEGMENT, job(id="payroll-bureaus"))
    result = run(workspace)
    assert result.records == []
    assert any("filename says" in m for m in result.skipped)


def test_a_reel_selection_sidecar_in_the_launched_queue_is_not_a_job(workspace):
    """`<segment>.reel.json` travels with the job; a bare glob would read it
    as a second launched ad and fail on it. engine.approval filters it."""
    (workspace["queue"] / "launched" / ("%s.reel.json" % SEGMENT)).write_text(
        json.dumps({"schema": 1, "selected": ["a01"]}), encoding="utf-8")
    result = run(workspace)
    assert [r["id"] for r in result.records] == [RECORD_ID]
    assert result.skipped == []


def test_a_record_the_corpus_refuses_is_reported_not_half_written(workspace, monkeypatch):
    def refuse(record, root=None):
        raise corpus.CorpusInvalid("refused on purpose")

    monkeypatch.setattr(corpus, "save", refuse)
    result = run(workspace)
    assert result.records == [] and result.written == []
    assert any("refused on purpose" in m and AD_ID in m for m in result.skipped)
    assert not workspace["corpus"].exists()


def test_a_blank_own_block_feeds_back_without_crashing(workspace):
    write_seeds(workspace["seeds"], BLANK_SEEDS)
    result = run(workspace)
    assert result.skipped == []
    assert result.records[0]["metrics"]["page_id"] == ""
    assert result.records[0]["channel"] == "own"


def test_a_run_over_unchanged_inputs_rewrites_the_same_bytes(workspace):
    first = run(workspace)
    before = first.written[0].read_bytes()
    second = run(workspace)
    assert second.written == first.written
    assert second.written[0].read_bytes() == before
    assert first.records == second.records


def test_nothing_launched_is_an_empty_run_not_an_error(tmp_path, queue):
    result = feedback.feed_back(
        corpus_root=tmp_path / "corpus",
        measurements_path=write_measurements(tmp_path / "m.json"),
        seeds_path=write_seeds(tmp_path / "s.yaml", BLANK_SEEDS),
    )
    assert result.records == []
    assert any(SEGMENT in m and "queue/launched" in m for m in result.skipped)


def test_a_missing_measurements_file_stops_the_run_by_name(tmp_path, queue):
    with pytest.raises(FileNotFoundError, match="engine.measure"):
        feedback.feed_back(measurements_path=tmp_path / "nowhere.json",
                           seeds_path=write_seeds(tmp_path / "s.yaml", BLANK_SEEDS))


# --- the command line --------------------------------------------------------


def argv(workspace, *extra) -> list[str]:
    return [
        "--measurements", str(workspace["measurements"]),
        "--corpus", str(workspace["corpus"]),
        "--seeds", str(workspace["seeds"]),
        *extra,
    ]


def test_main_writes_and_reports(workspace, capsys):
    assert feedback.main(argv(workspace)) == 0
    out, err = capsys.readouterr()
    assert out.startswith("wrote ") and RECORD_ID in out
    assert "1 record(s) written, 0 skipped" in err
    assert (workspace["corpus"] / ("meta-ad-%s.json" % RECORD_ID)).exists()


def test_main_dry_run_prints_what_it_would_write_and_writes_nothing(workspace, capsys):
    assert feedback.main(argv(workspace, "--dry-run")) == 0
    out, err = capsys.readouterr()
    assert out.startswith("would write ") and RECORD_ID in out
    assert "1 record(s) to write, 0 skipped" in err
    assert not workspace["corpus"].exists()


def test_main_prints_skips_on_stderr(workspace, capsys):
    launch(workspace["queue"], "payroll-bureaus")
    assert feedback.main(argv(workspace)) == 0
    _out, err = capsys.readouterr()
    assert "skipped: payroll-bureaus: skipped - launched but not measured yet" in err
    assert "1 record(s) written, 1 skipped" in err


def test_main_exits_one_with_the_reason_when_a_file_cannot_be_read(workspace, capsys):
    workspace["measurements"].unlink()
    assert feedback.main(argv(workspace)) == 1
    _out, err = capsys.readouterr()
    assert "engine.measure" in err
    assert not workspace["corpus"].exists()

    write_measurements(workspace["measurements"], schema=2)
    assert feedback.main(argv(workspace)) == 1
    assert "schema" in capsys.readouterr().err

    write_measurements(workspace["measurements"])
    write_seeds(workspace["seeds"], "own: nope\n")
    assert feedback.main(argv(workspace)) == 1
    assert "own is a str" in capsys.readouterr().err


# --- the point of the exercise: learn counts our own ads ---------------------


def two_own_records() -> list[dict]:
    """Two of our own ads, measured at 7 and 8 days (both in learn's 7-27 day
    band) with click-throughs of 1.24 and 1.7 (both in its 1.0-1.9 band)."""
    first = record(row=row(measured_at="2026-10-06T10:00:00Z"))
    second_job = job(id="payroll-bureaus", segment="payroll-bureaus", offer="none",
                     ads={"2222": {"campaign_id": "5678", "adset_id": None}})
    second_row = row(segment="payroll-bureaus", ad_id="2222",
                     measured_at="2026-10-08T05:02:00Z")
    second_row["metrics"].update(impressions=9000, reach=7000, ctr=1.7)
    return [first, feedback.record_for(second_job, second_row, own=OWN)]


def test_learn_counts_our_own_ads_with_no_change_to_it():
    """engine.learn already filters by origin, so origin "own" needed nothing
    added to it - this is the assert that says so."""
    skips = []
    document = learn.build(two_own_records(), origin="own", on_skip=skips.append)
    assert document["corpus_size"] == 2
    assert skips == []
    hooks = [p for p in document["patterns"] if p["kind"] == "hook"]
    assert [p["device"] for p in hooks] == ["authored"]
    assert hooks[0]["evidence"] == [RECORD_ID, "fb-own-payroll-bureaus-2222"]


def test_our_own_click_through_becomes_a_pattern_with_our_own_ids_under_it():
    """The loop, closed: a number the Marketing API reported about an ad we
    launched reaches a corpus record and comes back out of engine.learn as a
    ctr band a concept can cite by id."""
    document = learn.build(two_own_records(), origin="own")
    ctr = [p for p in document["patterns"] if p["kind"] == "ctr"]
    assert [p["device"] for p in ctr] == ["ctr-pct:1.0-1.9"]
    assert ctr[0]["evidence"] == [RECORD_ID, "fb-own-payroll-bureaus-2222"]
    assert ctr[0]["n"] == 2
    assert ctr[0]["median_reach"] == 5150
    assert ctr[0]["median_days_running"] == 7
    assert "1.5%" in ctr[0]["description"]


def test_the_window_feeds_the_longevity_kind_like_discovers_days_running():
    document = learn.build(two_own_records(), origin="own")
    longevity = [p for p in document["patterns"] if p["kind"] == "longevity"]
    assert [p["device"] for p in longevity] == ["days:7-27"]
    assert longevity[0]["n"] == 2


def test_an_ad_nobody_read_the_click_through_of_supports_no_ctr_pattern():
    """A null is not a zero, end to end: two nulls banded as 0.0 would be
    MIN_SUPPORT for a band of their own, and patterns.json would carry an
    "ads nobody clicked" pattern built out of readings nobody took. And a
    null is not something to go and fix, so it is not reported either."""
    records = []
    for rec in two_own_records():
        rec["analysis"]["own_metrics"]["ctr"] = None
        records.append(rec)
    skips = []
    document = learn.build(records, origin="own", on_skip=skips.append)
    assert [p for p in document["patterns"] if p["kind"] == "ctr"] == []
    assert skips == []
    assert document["corpus_size"] == 2


def test_our_own_ads_do_not_leak_into_the_competitor_view():
    assert learn.build(two_own_records(), origin="competitor")["corpus_size"] == 0


def test_learn_stamps_the_document_from_the_measurement_not_the_clock():
    document = learn.build(two_own_records(), origin="own")
    assert document["generated_at"] == "2026-10-08T05:02:00Z"


def test_learns_own_fixture_and_this_modules_record_agree_on_the_shape():
    """tests/test_learn.py builds its own_metrics block by hand; the block this
    module writes has to be that block, or learn is being tested against a
    shape the corpus never holds."""
    block = record()["analysis"]["own_metrics"]
    assert set(block) == {"ctr", "hook_rate", "hold_rate"}


# --- the reason this module costs nothing to run -----------------------------


FORBIDDEN = (
    "engine.model",
    "engine.gate",
    "engine.discover",
    "engine.measure",
    "engine.oauth",
    "engine.analyse",
    "engine.score",
    "engine.concepts",
    "engine.write",
    "google",
    "google.genai",
    "google.generativeai",
    "urllib",
    "http",
    "httpx",
    "requests",
    "aiohttp",
    "socket",
    "ssl",
)


def imported_by(path: Path) -> set[str]:
    """Every module name the file imports, AST-parsed rather than executed,
    function bodies included: a lazy import is still an import.

    `from engine import approval, corpus` names two modules, not one, so the
    members of an `engine` import are expanded - otherwise a future
    `from engine import model` would hide behind the bare name "engine".
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            parent = node.module or ""
            names.add(parent)
            names.update("%s.%s" % (parent, alias.name) for alias in node.names)
    return names


def leaks(names) -> list[str]:
    """A set underneath: "google.genai" matches two entries in FORBIDDEN and
    is still one import."""
    return sorted(
        {
            name
            for name in names
            for bad in FORBIDDEN
            if name == bad or name.startswith(bad + ".")
        }
    )


def test_the_feedback_module_calls_no_model_and_reaches_no_network():
    """We wrote these ads. Paying a model to describe our own job file would
    buy a worse answer than the file it was guessing at."""
    assert leaks(imported_by(Path(feedback.__file__))) == []


def test_the_import_check_would_catch_the_imports_it_forbids(tmp_path):
    """A check that cannot fail is not a check - including one hidden in a
    function body."""
    decoy = tmp_path / "decoy.py"
    decoy.write_text(
        "from engine import model\nimport google.genai\n"
        "def later():\n    from engine import discover\n    import socket\n",
        encoding="utf-8",
    )
    assert leaks(imported_by(decoy)) == [
        "engine.discover", "engine.model", "google.genai", "socket",
    ]


def test_nothing_the_feedback_module_imports_can_reach_a_model_either():
    """A clean import list is worth nothing if engine.approval grows a model
    client next month. approval drives `gh` through subprocess for the
    workflows, which is not a socket of its own and is not called from here."""
    for name in sorted(imported_by(Path(feedback.__file__))):
        if not name.startswith("engine."):
            continue
        reached = __import__(name, fromlist=["_"])
        assert leaks(imported_by(Path(reached.__file__))) == [], name


def test_the_source_never_names_a_model_client_or_a_key():
    """The same tokens tests/test_learn.py forbids from the other end of the
    ctr path, so the two ends cannot drift apart."""
    source = Path(feedback.__file__).read_text(encoding="utf-8")
    for token in ("call_model", "GeminiClient", "genai", "api_key", "API_KEY",
                  "urlopen", "ads/library"):
        assert token not in source, token


def test_the_source_never_reads_the_clock():
    source = Path(feedback.__file__).read_text(encoding="utf-8")
    for token in ("datetime.now", "utcnow", "date.today", "time.time"):
        assert token not in source, token


def test_the_module_is_pure_ascii():
    """The repo's own rule for source files; the data it writes need not be."""
    source = Path(feedback.__file__).read_bytes()
    assert source.decode("ascii")


def test_the_learn_suites_coupling_test_will_run_against_this_file():
    """tests/test_learn.py skips its feedback check while the file is absent;
    it exists now, so that check is live and pointed here."""
    assert (REPO / "engine" / "feedback.py").exists()
