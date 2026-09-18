"""Patterns: what actually repeats in the ad corpus, counted rather than asserted.

Two properties carry most of this file. A pattern must be traceable - every one
carries the ids it came from and the count of ads behind it - and the generator
must be boring: the same corpus has to produce the same bytes, every run, or
the weekly commit is noise.

The record() helper below is a copy of the C1 example in tests/test_corpus.py
with knobs, not an import of it: each suite pins its own contract.
"""
import ast
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from engine import corpus, learn

REPO = Path(__file__).resolve().parents[1]


SECTIONS = ("hook", "problem", "offer", "cta")


def record(
    rid,
    *,
    origin="icp-adjacent",
    fetched_at="2026-09-14T00:00:00Z",
    days_running=41,
    reach=12000,
    hook_device="question",
    hook_words=9,
    hook_text="Bruger du stadig timer på bogføring hver uge?",
    words=48,
    sections=SECTIONS,
    cta_type="learn-more",
    cta_text="Se om vi kan gøre dit regnskab bedre",
    offer_type="none",
    offer_text="",
    proof_type="none",
    proof_text="",
    objections=("we already have an accountant",),
    **overrides,
):
    """One C1 record. Valid enough for corpus.save(), so the same fixtures
    prove the round trip through the real store."""
    data = {
        "schema": 1,
        "id": rid,
        "platform": "meta-ad",
        "url": f"https://www.facebook.com/ads/library/?id={rid}",
        "channel": "Balance - Your AI Powered Accountants",
        "origin": origin,
        "fetched_at": fetched_at,
        "metrics": {
            "eu_total_reach": reach,
            "days_running": days_running,
            "active": True,
            "variants": 3,
            "page_id": "1007614045762121",
            "publisher_platforms": ["facebook", "instagram"],
            "languages": ["da"],
            "countries": ["DK"],
        },
        "analysis": {
            "copy": {
                "primary_text": hook_text + " Vi gør dit regnskab bedre og billigere.",
                "headline": "Se om vi kan gøre dit regnskab bedre",
                "description": "AI-drevet bogholderi til små virksomheder",
                "link_caption": "balance.dk",
                "words": words,
            },
            "hook": {"words": hook_words, "text": hook_text, "device": hook_device},
            "structure": list(sections),
            "offer": {"type": offer_type, "text": offer_text},
            "proof": {"type": proof_type, "text": proof_text},
            "cta": {"type": cta_type, "text": cta_text},
            "objections": list(objections),
            "creative": {"kind": "text-only"},
            "outlier_ratio": 2.4,
        },
        "model": "gemini-3.6-flash",
    }
    data.update(copy.deepcopy(overrides))
    return data


def corpus_of(*records):
    """A small corpus where every device repeats at least twice."""
    return list(records)


def own_metrics(ctr, **overrides):
    """The own_metrics block engine.feedback writes from a C6 measurement row.
    Every field a provider did not give is null - never 0."""
    block = {"ctr": ctr, "hook_rate": None, "hold_rate": None}
    block.update(overrides)
    return block


def with_own_metrics(rid, block, **kwargs):
    """One record carrying `block` at analysis.own_metrics, the way a measured
    ad of our own reaches the corpus."""
    kwargs.setdefault("origin", "own")
    row = record(rid, model="none (authored)", **kwargs)
    row["analysis"]["own_metrics"] = copy.deepcopy(block)
    row["analysis"]["creative"] = {"kind": "authored"}
    return row


def measured(rid, ctr, **kwargs):
    """One ad of our own whose click-through rate read this (in percent)."""
    return with_own_metrics(rid, own_metrics(ctr), **kwargs)


# Both in the 60-119 day band, so the fixture produces every kind but ctr.
PAIR = [
    record("fb-aaa", days_running=90, reach=40000),
    record("fb-bbb", days_running=60, reach=20000),
]


def devices(document, kind=None):
    return [
        p["device"]
        for p in document["patterns"]
        if kind is None or p["kind"] == kind
    ]


def pattern(document, kind, device):
    for entry in document["patterns"]:
        if entry["kind"] == kind and entry["device"] == device:
            return entry
    raise AssertionError(
        f"no {kind} pattern {device!r} in {devices(document, kind)}"
    )


# --- the fixtures are real C1 records -------------------------------------


def test_the_fixture_record_is_a_valid_c1_record():
    """If the helper drifted from the contract, every test below would be
    proving learn against a shape the corpus never holds."""
    corpus.validate(record("fb-aaa"))
    corpus.validate(measured("fb-own-payroll-bureaus-1234", 1.24))


# --- the free path: no model, anywhere -----------------------------------


# engine.model is the one way into a paid call; engine.gate imports it, and
# engine.discover, engine.measure and engine.oauth are the modules that can
# open a socket. A network library here would mean this module could grow one
# later.
FORBIDDEN = (
    "engine.model",
    "engine.gate",
    "engine.discover",
    "engine.measure",
    "engine.oauth",
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


def imported_names(path: Path) -> set[str]:
    """Every dotted name a source file imports.

    `from engine import model` is expanded to "engine.model" rather than left
    as "engine": recording the bare package would let exactly the import these
    tests exist to catch pass unnoticed.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            parent = node.module or ""
            names.add(parent)
            names.update(f"{parent}.{alias.name}".strip(".") for alias in node.names)
    return names


def leaked_imports(path: Path) -> list[str]:
    """The forbidden imports in one file, named once each: "google.genai"
    matches two entries in FORBIDDEN and is still one import."""
    return sorted(
        {
            name
            for name in imported_names(path)
            for bad in FORBIDDEN
            if name == bad or name.startswith(bad + ".")
        }
    )


def test_the_learn_module_imports_no_model_and_no_network():
    """Aggregation is arithmetic. A pattern is a count, not an opinion - and a
    count costs nothing, which is half of why this module exists."""
    leaked = leaked_imports(Path(learn.__file__))
    assert leaked == [], f"engine/learn.py imports {leaked}"


def test_the_import_check_would_catch_the_imports_it_forbids(tmp_path):
    """A check that cannot fail is not a check."""
    decoy = tmp_path / "decoy.py"
    decoy.write_text(
        "from engine import model\nimport google.genai\nfrom urllib.request "
        "import urlopen\nimport socket\n",
        encoding="utf-8",
    )
    assert leaked_imports(decoy) == [
        "engine.model", "google.genai", "socket", "urllib.request",
        "urllib.request.urlopen",
    ]


def test_the_module_that_carries_ctr_in_is_as_free_as_this_one():
    """A ctr band is only as free as the path that feeds it: the reading is
    read off a measurements file by engine.feedback, written into a corpus
    record, and counted here. Neither end may grow a client, so the same AST
    check is pointed at the other end of that path."""
    path = REPO / "engine" / "feedback.py"
    if not path.exists():
        pytest.skip("engine/feedback.py is not in this checkout yet")
    leaked = leaked_imports(path)
    assert leaked == [], f"engine/feedback.py imports {leaked}"
    source = path.read_text(encoding="utf-8")
    for token in ("call_model", "GeminiClient", "genai", "api_key", "API_KEY"):
        assert token not in source, f"engine/feedback.py mentions {token}"


def test_the_source_never_names_a_model_client():
    """An import is not the only way to reach one; a late import inside a
    function would not show up as a module-level name."""
    source = Path(learn.__file__).read_text(encoding="utf-8")
    for token in ("call_model", "GeminiClient", "genai", "api_key", "API_KEY"):
        assert token not in source, f"engine/learn.py mentions {token}"


# --- contract C5 ---------------------------------------------------------


DOCUMENT_KEYS = {"schema", "generated_at", "corpus_size", "patterns"}
PATTERN_KEYS = {
    "id", "kind", "device", "description", "evidence",
    "median_days_running", "median_reach", "n",
}


def test_the_document_carries_exactly_the_contract_keys():
    document = learn.build(PAIR)
    assert set(document) == DOCUMENT_KEYS
    assert document["schema"] == learn.SCHEMA == 1
    assert document["corpus_size"] == 2


def test_every_pattern_carries_exactly_the_contract_keys():
    document = learn.build(PAIR)
    assert document["patterns"], "the fixture should produce patterns"
    for entry in document["patterns"]:
        assert set(entry) == PATTERN_KEYS, entry


def test_the_contract_field_types_are_what_a_consumer_reads():
    for entry in learn.build(PAIR)["patterns"]:
        assert isinstance(entry["id"], str)
        assert isinstance(entry["kind"], str)
        assert isinstance(entry["device"], str)
        assert isinstance(entry["description"], str)
        assert isinstance(entry["evidence"], list)
        # bool is an int in Python, and a True here would serialise as `true`.
        for key in ("median_days_running", "median_reach", "n"):
            assert isinstance(entry[key], int), (key, entry)
            assert not isinstance(entry[key], bool), (key, entry)


def test_the_contract_constants_are_the_ones_the_contract_names():
    assert learn.SCHEMA == 1
    assert learn.MIN_SUPPORT == 2
    assert learn.EPOCH == "1970-01-01T00:00:00Z"
    assert learn.KINDS == (
        "hook", "length", "structure", "cta", "offer", "proof", "objection",
        "longevity", "ctr",
    )
    assert learn.LENGTH_EDGES == (20, 50, 100, 200)
    assert learn.LONGEVITY_EDGES == (7, 28, 60, 120)
    assert learn.CTR_BANDS == (
        (0.5, "0-0.4"), (1.0, "0.5-0.9"), (2.0, "1.0-1.9"), (None, "2.0+"),
    )


def test_the_default_path_is_the_one_the_contract_names():
    assert learn.DEFAULT_PATH.name == "patterns.json"
    assert learn.DEFAULT_PATH.parent.name == "research"
    assert learn.DEFAULT_PATH == learn.ROOT / "research" / "patterns.json"


def test_the_nine_contract_kinds_are_all_produced():
    """Every kind at once needs two measured ads of our own, because ctr is
    only ever read off our own account. engine/concepts.py checks a pattern's
    keys and deliberately not its kind, so a tenth kind would need no schema
    bump."""
    document = learn.build([measured("fb-own-a", 0.7), measured("fb-own-b", 0.8)])
    assert {p["kind"] for p in document["patterns"]} == set(learn.KINDS)


def test_a_corpus_nobody_could_read_the_ctr_of_produces_the_other_eight():
    """Which is nearly every corpus: a ctr pattern appears only where a record
    carries a reading, and is never invented for one that does not."""
    assert {p["kind"] for p in learn.build(PAIR)["patterns"]} == set(learn.KINDS) - {
        "ctr"
    }


# --- evidence: every claim traces back to real ads ------------------------


def test_n_is_the_number_of_supporting_ads():
    document = learn.build(corpus_of(*PAIR, record("fb-ccc", days_running=9)))
    hook = pattern(document, "hook", "question")
    assert hook["n"] == 3
    assert hook["evidence"] == ["fb-aaa", "fb-bbb", "fb-ccc"]


def test_n_and_evidence_can_never_disagree():
    for entry in learn.build(corpus_of(*PAIR, record("fb-ccc")))["patterns"]:
        assert entry["n"] == len(entry["evidence"]), entry


def test_evidence_is_sorted_corpus_ids_with_no_repeats():
    ids = {r["id"] for r in PAIR}
    for entry in learn.build(PAIR)["patterns"]:
        assert entry["evidence"] == sorted(entry["evidence"])
        assert len(set(entry["evidence"])) == len(entry["evidence"])
        assert set(entry["evidence"]) <= ids


def test_one_ad_that_raises_an_objection_twice_is_still_one_ad():
    """Otherwise a single ad could carry a pattern on its own."""
    doubled = record("fb-aaa", objections=["Too expensive", "too expensive!"])
    document = learn.build([doubled, record("fb-bbb", objections=["not for us"])])
    assert "too expensive" not in devices(document, "objection")


def test_a_section_an_ad_returns_to_is_counted_once():
    twice = ("hook", "offer", "proof", "offer", "cta")
    document = learn.build([
        record("fb-aaa", sections=twice),
        record("fb-bbb", sections=twice),
    ])
    assert pattern(document, "structure", "section:offer")["n"] == 2
    assert pattern(document, "structure", "section:offer")["evidence"] == [
        "fb-aaa", "fb-bbb",
    ]


def test_median_days_running_is_the_median_of_the_supporting_ads():
    records = [
        record("fb-aaa", days_running=10),
        record("fb-bbb", days_running=90),
        record("fb-ccc", days_running=30),
    ]
    assert pattern(learn.build(records), "hook", "question")["median_days_running"] == 30


def test_median_reach_is_the_median_of_the_supporting_ads():
    records = [
        record("fb-aaa", reach=100),
        record("fb-bbb", reach=300),
        record("fb-ccc", reach=200),
    ]
    assert pattern(learn.build(records), "hook", "question")["median_reach"] == 200


def test_an_even_split_medians_to_a_whole_number():
    """Half a day in a committed file is noise; the median of 41 and 60 is
    written as 50, not 50.5."""
    document = learn.build([record("fb-aaa", days_running=41, reach=1001),
                            record("fb-bbb", days_running=60, reach=1002)])
    hook = pattern(document, "hook", "question")
    assert hook["median_days_running"] == 50
    assert hook["median_reach"] == 1001


# --- one ad is an anecdote ------------------------------------------------


def test_a_device_seen_once_is_left_out():
    document = learn.build([
        record("fb-aaa", hook_device="question"),
        record("fb-bbb", hook_device="question"),
        record("fb-ccc", hook_device="lonely-device"),
    ])
    assert "lonely-device" not in devices(document, "hook")
    assert "question" in devices(document, "hook")


def test_a_device_seen_twice_is_kept():
    document = learn.build([
        record("fb-aaa", hook_device="named-enemy"),
        record("fb-bbb", hook_device="named-enemy"),
    ])
    assert pattern(document, "hook", "named-enemy")["n"] == learn.MIN_SUPPORT


def test_nothing_in_a_document_is_supported_by_fewer_than_two_ads():
    records = [
        record(f"fb-{i:02d}", hook_device=f"device-{i}", offer_type=f"offer-{i}",
               proof_type=f"proof-{i}", cta_type=f"cta-{i}", words=i * 60,
               days_running=i * 30, objections=[f"objection {i}"],
               sections=("hook",) + ("problem",) * i + ("cta",))
        for i in range(6)
    ]
    document = learn.build(records)
    for entry in document["patterns"]:
        assert entry["n"] >= 2, entry
    # And the floor really bit: every per-ad device above was unique.
    assert devices(document, "hook") == []
    assert devices(document, "offer") == []


def test_a_single_ad_corpus_produces_no_patterns_at_all():
    document = learn.build([record("fb-aaa")])
    assert document["corpus_size"] == 1
    assert document["patterns"] == []


def test_the_support_floor_is_two():
    assert learn.MIN_SUPPORT == 2


# --- determinism ---------------------------------------------------------


def test_generating_twice_produces_byte_identical_files(tmp_path):
    """The weekly workflow commits this file. A generator that reordered
    anything would put a diff in every run that says nothing changed."""
    records = corpus_of(*PAIR, record("fb-ccc", hook_device="named-enemy"),
                        record("fb-ddd", hook_device="named-enemy"),
                        measured("fb-own-eee", 0.7),
                        measured("fb-own-fff", 0.8))
    first = learn.write(learn.build(records), tmp_path / "first.json")
    second = learn.write(learn.build(records), tmp_path / "second.json")
    assert first.read_bytes() == second.read_bytes()


def test_the_input_order_does_not_reach_the_output(tmp_path):
    """Records arrive sorted from load_all(), but a caller holding its own
    list must not get to decide the order of the evidence."""
    records = [
        record("fb-aaa", days_running=120, reach=40000),
        record("fb-bbb", days_running=60, hook_device="named-enemy"),
        record("fb-ccc", days_running=90, hook_device="named-enemy"),
        measured("fb-own-ddd", 0.7, days_running=12, reach=4120),
        measured("fb-own-eee", 0.8, days_running=14, reach=9000),
    ]
    forwards = learn.dumps(learn.build(records))
    backwards = learn.dumps(learn.build(list(reversed(records))))
    shuffled = learn.dumps(learn.build(
        [records[3], records[1], records[4], records[0], records[2]]
    ))
    assert forwards == backwards == shuffled


def test_two_processes_with_different_hash_seeds_write_the_same_bytes(tmp_path):
    """The comparison above runs in one process, where every set iterates the
    same way whatever the code does - so it cannot see a hash-order leak at
    all. PYTHONHASHSEED changes how strings hash, which is exactly what would
    shuffle output that came out of a set, and the weekly workflow runs in a
    fresh process every time."""
    root = tmp_path / "corpus"
    for entry in (
        record("fb-aaa", days_running=120, reach=40000),
        record("fb-bbb", days_running=60, reach=20000),
        record("fb-ccc", hook_device="named-enemy", objections=["too expensive"]),
        record("fb-ddd", hook_device="named-enemy", objections=["Too expensive!"]),
        # Two measured ads of our own, so the ctr kind is inside the proof
        # too: its groups come out of a dict keyed by a band string, exactly
        # like every other family's.
        measured("fb-own-eee", 0.7),
        measured("fb-own-fff", 0.8),
    ):
        corpus.save(entry, root=root)

    written = []
    for seed in ("0", "1", "424242"):
        out = tmp_path / f"patterns-{seed}.json"
        result = subprocess.run(
            [sys.executable, "-m", "engine.learn",
             "--corpus", str(root), "--out", str(out)],
            cwd=str(REPO),
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        written.append(out.read_bytes())
    assert written[0] == written[1] == written[2]


def test_generated_at_comes_from_the_corpus_not_the_clock():
    records = [
        record("fb-aaa", fetched_at="2026-09-14T00:00:00Z"),
        record("fb-bbb", fetched_at="2026-09-21T09:30:00Z"),
    ]
    assert learn.build(records)["generated_at"] == "2026-09-21T09:30:00Z"


def test_an_empty_corpus_still_produces_a_stable_document():
    document = learn.build([])
    assert document == {
        "schema": 1,
        "generated_at": learn.EPOCH,
        "corpus_size": 0,
        "patterns": [],
    }


def test_a_caller_can_still_stamp_the_document_itself():
    document = learn.build(PAIR, generated_at="2026-01-01T00:00:00Z")
    assert document["generated_at"] == "2026-01-01T00:00:00Z"


def test_the_quoted_example_is_the_longest_running_ad_not_the_first():
    """Longevity is the archive's one money-backed vote; the ad whose
    advertiser kept paying for it is the example worth reading."""
    records = [
        record("fb-aaa", days_running=9, reach=900000, hook_text="The launch."),
        record("fb-bbb", days_running=130, reach=1000, hook_text="The one that stayed."),
    ]
    description = pattern(learn.build(records), "hook", "question")["description"]
    assert "The one that stayed." in description
    assert "The launch." not in description


def test_reach_breaks_a_tie_on_days_running_and_id_breaks_the_rest():
    tied = [
        record("fb-bbb", days_running=30, reach=500, hook_text="Reached fewer."),
        record("fb-aaa", days_running=30, reach=9000, hook_text="Reached more."),
    ]
    assert "Reached more." in pattern(learn.build(tied), "hook", "question")["description"]
    flat = [
        record("fb-bbb", days_running=30, reach=500, hook_text="Second by id."),
        record("fb-aaa", days_running=30, reach=500, hook_text="First by id."),
    ]
    assert "First by id." in pattern(learn.build(flat), "hook", "question")["description"]


def test_a_long_quote_is_clipped_so_one_primary_text_cannot_dominate():
    records = [record("fb-aaa", hook_text="word " * 80),
               record("fb-bbb", hook_text="word " * 80)]
    description = pattern(learn.build(records), "hook", "question")["description"]
    assert len(description) < 200
    assert description.endswith('..."')


# --- ids -----------------------------------------------------------------


def test_ids_are_q01_upwards_in_the_order_the_file_is_written():
    document = learn.build(PAIR)
    ids = [p["id"] for p in document["patterns"]]
    assert ids == [f"q{n:02d}" for n in range(1, len(ids) + 1)]


def test_ids_never_wear_the_reel_prefix():
    """A concept must not be able to cite a reel-engine pattern by accident."""
    for entry in learn.build(PAIR)["patterns"]:
        assert entry["id"].startswith("q"), entry["id"]
        assert not entry["id"].startswith("p"), entry["id"]


def test_ids_follow_sorted_content_not_support():
    """Numbering by n would renumber the whole file whenever one new ad
    changed the ranking, and last week's concept would cite a pattern it was
    never derived from."""
    document = learn.build(corpus_of(*PAIR, record("fb-ccc")))
    order = [(learn.KINDS.index(p["kind"]), p["device"]) for p in document["patterns"]]
    assert order == sorted(order)


def test_ids_widen_past_ninety_nine_so_they_still_sort():
    """"q100" sorts before "q99" as text; a fixed width of two would quietly
    break any consumer that sorts ids."""
    many = [f"objection number {n}" for n in range(100)]
    document = learn.build([
        record("fb-aaa", objections=many),
        record("fb-bbb", objections=many),
    ])
    ids = [p["id"] for p in document["patterns"]]
    assert len(ids) > 99
    assert ids[0] == "q001"
    assert ids == sorted(ids)


# --- metrics that engine.corpus never type-checked ------------------------


def test_a_non_numeric_day_count_does_not_crash_the_run():
    """corpus.validate() accepts days_running: "a while"; dying inside
    statistics.median would name neither the record nor the field."""
    messages = []
    document = learn.build(
        [record("fb-aaa", days_running="a while"), record("fb-bbb", days_running=60)],
        on_skip=messages.append,
    )
    assert pattern(document, "hook", "question")["median_days_running"] == 60
    assert any("fb-aaa" in m and "days_running" in m for m in messages), messages


def test_a_non_numeric_reach_does_not_crash_the_run():
    messages = []
    document = learn.build(
        [record("fb-aaa", reach="lots"), record("fb-bbb", reach=20000)],
        on_skip=messages.append,
    )
    assert pattern(document, "hook", "question")["median_reach"] == 20000
    assert any("fb-aaa" in m and "eu_total_reach" in m for m in messages), messages


def test_an_ad_with_an_unusable_day_count_is_still_evidence():
    """The pattern really is in that ad; only its day count is unreadable."""
    document = learn.build([record("fb-aaa", days_running="a while"),
                            record("fb-bbb", days_running="a while")])
    hook = pattern(document, "hook", "question")
    assert hook["evidence"] == ["fb-aaa", "fb-bbb"]
    assert hook["median_days_running"] == 0
    assert hook["median_reach"] == 12000
    # But it is in no longevity band: a band needs a number to fall into.
    assert devices(document, "longevity") == []


def test_a_boolean_metric_is_not_read_as_one_day():
    document = learn.build([record("fb-aaa", days_running=True, reach=True),
                            record("fb-bbb", days_running=50, reach=500)])
    hook = pattern(document, "hook", "question")
    assert hook["median_days_running"] == 50
    assert hook["median_reach"] == 500


def test_a_numeric_string_metric_is_read_rather_than_thrown_away():
    document = learn.build([record("fb-aaa", days_running="40", reach="400"),
                            record("fb-bbb", days_running="20", reach="200")])
    hook = pattern(document, "hook", "question")
    assert hook["median_days_running"] == 30
    assert hook["median_reach"] == 300


@pytest.mark.parametrize("days", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_day_count_is_refused_rather_than_crashing(days):
    """The math.isfinite guard is load-bearing: NaN raises ValueError and
    Infinity raises OverflowError on the way to an int - in a weekly job,
    over a corpus nobody hand-checked."""
    skips = []
    document = learn.build(
        [record("fb-a", days_running=days), record("fb-b", days_running=50)],
        on_skip=skips.append,
    )
    assert document["patterns"], "a bad day count emptied the patterns"
    for entry in document["patterns"]:
        assert isinstance(entry["median_days_running"], int)
        assert entry["median_days_running"] == 50
    assert any("fb-a" in line for line in skips), skips


def test_a_zero_reach_is_a_reading_not_an_absence():
    """discover writes 0 when the archive omits eu_total_reach - never null -
    so 0 is a number here and medians like one."""
    messages = []
    document = learn.build([record("fb-aaa", reach=0), record("fb-bbb", reach=0)],
                           on_skip=messages.append)
    assert pattern(document, "hook", "question")["median_reach"] == 0
    assert messages == []


def test_non_numeric_words_are_reported_and_skipped():
    messages = []
    document = learn.build(
        [record("fb-aaa", words="short"), record("fb-bbb", words="short")],
        on_skip=messages.append,
    )
    assert devices(document, "length") == []
    assert any("fb-aaa" in m and "copy.words" in m for m in messages), messages
    # Only the length band is lost; the ad is still evidence elsewhere.
    assert pattern(document, "hook", "question")["n"] == 2


def test_a_metrics_block_that_is_not_an_object_is_reported():
    messages = []
    document = learn.build([record("fb-aaa", metrics=[1, 2]), record("fb-bbb")],
                           on_skip=messages.append)
    assert any("fb-aaa" in m and "metrics" in m for m in messages), messages
    assert pattern(document, "hook", "question")["n"] == 2


def test_an_analysis_block_that_is_not_an_object_is_reported():
    messages = []
    document = learn.build([record("fb-aaa", analysis="none"), record("fb-bbb")],
                           on_skip=messages.append)
    assert document["corpus_size"] == 2
    # Longevity is read off metrics and still repeats; nothing under analysis
    # can, because one ad is all that has an analysis.
    assert {p["kind"] for p in document["patterns"]} <= {"longevity"}
    assert any("fb-aaa" in m and "analysis" in m for m in messages), messages


def test_a_structure_entry_that_is_not_a_label_is_reported():
    messages = []
    document = learn.build(
        [record("fb-aaa", sections=({"label": "hook"}, "cta")),
         record("fb-bbb", sections=("cta",))],
        on_skip=messages.append,
    )
    assert any("fb-aaa" in m and "structure[0]" in m for m in messages), messages
    # The unreadable entry holds no place: cta is position 1 in both ads.
    assert "median position 1.0" in pattern(document, "structure", "section:cta")[
        "description"
    ]


def test_an_objection_that_is_not_a_string_is_reported():
    messages = []
    learn.build([record("fb-aaa", objections=[{"text": "too expensive"}]),
                 record("fb-bbb")], on_skip=messages.append)
    assert any("fb-aaa" in m and "objections[0]" in m for m in messages), messages


def test_a_blank_hook_device_is_reported_rather_than_counted():
    messages = []
    document = learn.build([record("fb-aaa", hook_device="  "),
                            record("fb-bbb", hook_device="  ")],
                           on_skip=messages.append)
    assert devices(document, "hook") == []
    assert any("hook.device" in m for m in messages), messages


@pytest.mark.parametrize("key, knob", [
    ("cta", "cta_type"), ("offer", "offer_type"), ("proof", "proof_type"),
])
def test_a_blank_type_is_reported_rather_than_counted(key, knob):
    messages = []
    document = learn.build([record("fb-aaa", **{knob: ""}),
                            record("fb-bbb", **{knob: None})],
                           on_skip=messages.append)
    assert devices(document, key) == []
    assert sum(f"{key}.type" in m for m in messages) == 2, messages


def test_skipping_is_silent_when_nobody_asked_for_the_reports():
    """No on_skip is the normal case; it must not raise."""
    assert learn.build([record("fb-aaa", days_running="a while")])["corpus_size"] == 1


def test_a_skipped_value_is_reported_once_not_once_per_kind():
    """days_running feeds every median and the longevity band; an operator
    should read one line about it, not nine."""
    messages = []
    learn.build([record("fb-aaa", days_running="a while"), record("fb-bbb")],
                on_skip=messages.append)
    assert len([m for m in messages if "days_running" in m]) == 1, messages


# --- normalisation: what counts as the same device ------------------------


def test_the_same_device_named_three_ways_is_one_device():
    document = learn.build([
        record("fb-aaa", hook_device="Named Enemy"),
        record("fb-bbb", hook_device="named_enemy"),
        record("fb-ccc", hook_device="named-enemy"),
    ])
    assert devices(document, "hook") == ["named-enemy"]
    assert pattern(document, "hook", "named-enemy")["n"] == 3


def test_an_objection_keeps_its_words_so_it_can_be_read():
    """A slug would make "we already have an accountant" unreadable in the
    file, and an objection has no vocabulary to slug it into."""
    document = learn.build([
        record("fb-aaa", objections=["We already have an accountant."]),
        record("fb-bbb", objections=["we already have an accountant"]),
    ])
    assert devices(document, "objection") == ["we already have an accountant"]


def test_length_bands_group_neighbouring_ads():
    document = learn.build([
        record("fb-aaa", words=20),
        record("fb-bbb", words=48),
    ])
    assert devices(document, "length") == ["words:20-49"]
    assert pattern(document, "length", "words:20-49")["description"] == (
        "20-49 words; median 34.0"
    )


def test_the_first_length_edge_separates_copy_that_fits_above_the_fold():
    document = learn.build([
        record("fb-aaa", words=0), record("fb-bbb", words=19),
        record("fb-ccc", words=20), record("fb-ddd", words=49),
    ])
    assert devices(document, "length") == ["words:0-19", "words:20-49"]
    assert pattern(document, "length", "words:0-19")["evidence"] == ["fb-aaa", "fb-bbb"]


def test_a_length_outlier_falls_into_the_open_top_band():
    document = learn.build([
        record("fb-aaa", words=200),
        record("fb-bbb", words=1400),
    ])
    assert devices(document, "length") == ["words:200+"]


def test_structure_learns_both_the_shape_and_the_sections():
    document = learn.build(PAIR)
    shape = pattern(document, "structure", "shape:hook>problem>offer>cta")
    assert shape["description"] == "shape hook > problem > offer > cta"
    section = pattern(document, "structure", "section:offer")
    assert section["description"] == 'section "offer"; median position 3.0'
    assert pattern(document, "structure", "section:hook")["description"] == (
        'section "hook"; median position 1.0'
    )


def test_a_section_position_is_where_it_sits_in_each_ad():
    document = learn.build([
        record("fb-aaa", sections=("hook", "proof", "cta")),
        record("fb-bbb", sections=("hook", "problem", "offer", "cta", "proof")),
    ])
    # Position 2 in the first ad, 5 in the second.
    assert "median position 3.5" in pattern(document, "structure", "section:proof")[
        "description"
    ]


def test_two_different_section_orders_are_two_shapes():
    other = ("hook", "cta")
    document = learn.build([
        record("fb-aaa"), record("fb-bbb"),
        record("fb-ccc", sections=other), record("fb-ddd", sections=other),
    ])
    shapes = [d for d in devices(document, "structure") if d.startswith("shape:")]
    assert sorted(shapes) == ["shape:hook>cta", "shape:hook>problem>offer>cta"]


def test_a_section_label_is_slugged_like_any_taxonomy_value():
    document = learn.build([
        record("fb-aaa", sections=("Hook", "Social Proof", "CTA")),
        record("fb-bbb", sections=("hook", "social_proof", "cta")),
    ])
    assert pattern(document, "structure", "shape:hook>social-proof>cta")["n"] == 2
    assert pattern(document, "structure", "section:social-proof")["n"] == 2


def test_cta_offer_and_proof_quote_an_example_where_there_is_text():
    document = learn.build([
        record("fb-aaa", days_running=90, cta_text="Book en demo",
               offer_type="guarantee", offer_text="Betal kun hvis det virker",
               proof_type="testimonial", proof_text="Vi sparer 4 timer om ugen"),
        record("fb-bbb", days_running=30, cta_text="Se mere",
               offer_type="guarantee", offer_text="Ingen risiko",
               proof_type="testimonial", proof_text="Anbefales"),
    ])
    assert pattern(document, "cta", "learn-more")["description"] == (
        'call to action "learn-more"; example: "Book en demo"'
    )
    assert pattern(document, "offer", "guarantee")["description"] == (
        'offer "guarantee"; example: "Betal kun hvis det virker"'
    )
    assert pattern(document, "proof", "testimonial")["description"] == (
        'proof "testimonial"; example: "Vi sparer 4 timer om ugen"'
    )


def test_an_offer_of_none_is_a_countable_device_with_no_example():
    """Two ads that make no offer is a fact about the market, and there is no
    text to quote for it."""
    document = learn.build(PAIR)
    assert pattern(document, "offer", "none")["description"] == 'offer "none"'
    assert pattern(document, "proof", "none")["description"] == 'proof "none"'


def test_the_hook_description_carries_the_median_word_count_and_an_example():
    document = learn.build([
        record("fb-aaa", days_running=90, hook_words=7, hook_text="Seven words here."),
        record("fb-bbb", days_running=30, hook_words=11, hook_text="Eleven."),
    ])
    assert pattern(document, "hook", "question")["description"] == (
        'opening device "question"; median hook 9.0 words; example: "Seven words here."'
    )


def test_a_hook_without_a_readable_word_count_still_has_a_description():
    document = learn.build([
        record("fb-aaa", hook_words="nine"), record("fb-bbb", hook_words=None),
    ])
    description = pattern(document, "hook", "question")["description"]
    assert description.startswith('opening device "question"; example: ')
    assert "median hook" not in description


# --- longevity: the archive's one money-backed vote -----------------------


def test_longevity_bands_days_running():
    document = learn.build([
        record("fb-aaa", days_running=28), record("fb-bbb", days_running=54),
        record("fb-ccc", days_running=3), record("fb-ddd", days_running=6),
    ])
    assert devices(document, "longevity") == ["days:0-6", "days:28-59"]
    assert pattern(document, "longevity", "days:28-59")["description"] == (
        "28-59 days running; median 41.0"
    )
    assert pattern(document, "longevity", "days:28-59")["evidence"] == ["fb-aaa", "fb-bbb"]


def test_the_longevity_edges_fall_where_the_scope_document_says():
    """A week is a launch; four weeks outlives a launch budget; eight weeks is
    the threshold the scope document names; 120 is evergreen."""
    document = learn.build([
        record("fb-a", days_running=7), record("fb-b", days_running=27),
        record("fb-c", days_running=60), record("fb-d", days_running=119),
        record("fb-e", days_running=120), record("fb-f", days_running=400),
    ])
    assert devices(document, "longevity") == ["days:120+", "days:60-119", "days:7-27"]


def test_longevity_is_read_for_our_own_ads_too():
    """The band is arithmetic over metrics.days_running, wherever the record
    came from; feedback writes measured_at - launched_at there."""
    document = learn.build([
        measured("fb-own-a", 1.2, days_running=10),
        measured("fb-own-b", 0.9, days_running=12),
    ])
    assert devices(document, "longevity") == ["days:7-27"]


# --- ctr: the one number only our own ads carry ----------------------------


def test_an_own_ads_ctr_becomes_a_pattern_of_its_own_kind():
    document = learn.build([measured("fb-own-a", 0.7), measured("fb-own-b", 0.8)])
    assert devices(document, "ctr") == ["ctr-pct:0.5-0.9"]
    assert pattern(document, "ctr", "ctr-pct:0.5-0.9")["evidence"] == [
        "fb-own-a", "fb-own-b",
    ]


def test_ctr_bands_are_percentage_points_with_the_contract_edges():
    document = learn.build([
        measured("fb-own-a", 0.0), measured("fb-own-b", 0.49),
        measured("fb-own-c", 0.5), measured("fb-own-d", 0.99),
        measured("fb-own-e", 1.0), measured("fb-own-f", 1.99),
        measured("fb-own-g", 2.0), measured("fb-own-h", 11.5),
    ])
    assert devices(document, "ctr") == [
        "ctr-pct:0-0.4", "ctr-pct:0.5-0.9", "ctr-pct:1.0-1.9", "ctr-pct:2.0+",
    ]
    assert pattern(document, "ctr", "ctr-pct:0-0.4")["evidence"] == ["fb-own-a", "fb-own-b"]
    assert pattern(document, "ctr", "ctr-pct:0.5-0.9")["evidence"] == ["fb-own-c", "fb-own-d"]
    assert pattern(document, "ctr", "ctr-pct:1.0-1.9")["evidence"] == ["fb-own-e", "fb-own-f"]
    assert pattern(document, "ctr", "ctr-pct:2.0+")["evidence"] == ["fb-own-g", "fb-own-h"]


def test_the_ctr_description_gives_the_band_and_the_median_inside_it():
    document = learn.build([measured("fb-own-a", 0.6), measured("fb-own-b", 0.8)])
    assert pattern(document, "ctr", "ctr-pct:0.5-0.9")["description"] == (
        "0.5-0.9% click-through; median 0.7%"
    )


def test_one_ad_that_was_clicked_a_lot_is_an_anecdote():
    """MIN_SUPPORT is the same floor for this kind as for every other one."""
    document = learn.build([
        measured("fb-own-a", 3.1), measured("fb-own-b", 0.2), measured("fb-own-c", 0.3),
    ])
    assert devices(document, "ctr") == ["ctr-pct:0-0.4"]


def test_ctr_reads_last_because_only_our_own_ads_carry_one():
    """It is what our audience did with the ad, not a thing inside it."""
    document = learn.build([measured("fb-own-a", 0.7), measured("fb-own-b", 0.8)])
    assert [p["kind"] for p in document["patterns"]][-1] == "ctr"
    assert learn.KINDS[-1] == "ctr"
    assert learn.KINDS[-2] == "longevity"


def test_ctr_is_read_wherever_the_record_carries_one_not_by_origin():
    """A rule that named an origin would be a second place for the corpus to
    define what counts."""
    document = learn.build([
        measured("fb-aaa", 1.2, origin="icp-adjacent"),
        measured("fb-bbb", 1.4, origin="icp-adjacent"),
    ])
    assert devices(document, "ctr") == ["ctr-pct:1.0-1.9"]


# --- a null is not a zero -------------------------------------------------


def test_an_ad_with_no_ctr_reading_is_in_no_ctr_pattern():
    """The criterion this kind lives or dies on. A reading nobody took, banded
    as 0.0, would be indistinguishable in the file from an ad nobody clicked -
    and two of them would be enough to support a pattern of their own."""
    document = learn.build([
        measured("fb-own-read-a", 0.7),
        measured("fb-own-read-b", 0.8),
        with_own_metrics("fb-own-null-a", own_metrics(None)),   # no impressions yet
        with_own_metrics("fb-own-null-b", own_metrics(None)),
        record("fb-none"),                                       # no own_metrics at all
    ])
    assert devices(document, "ctr") == ["ctr-pct:0.5-0.9"]
    cited = {
        rid
        for entry in document["patterns"]
        if entry["kind"] == "ctr"
        for rid in entry["evidence"]
    }
    assert cited == {"fb-own-read-a", "fb-own-read-b"}


def test_a_null_is_not_a_zero_even_where_a_zero_would_fit_the_same_band():
    """The same guard where it is hardest to see: at 0.1% and 0.3% the real
    readings already sit in the band a fabricated 0.0 would land in, so only
    the count, the evidence and the median can tell a null from a
    measurement. Zeroing the two nulls would make n 4 and the median 0.05."""
    document = learn.build([
        measured("fb-own-a", 0.1), measured("fb-own-b", 0.3),
        with_own_metrics("fb-own-null-a", own_metrics(None)),
        with_own_metrics("fb-own-null-b", own_metrics(None)),
    ])
    band = pattern(document, "ctr", "ctr-pct:0-0.4")
    assert band["n"] == 2
    assert band["evidence"] == ["fb-own-a", "fb-own-b"]
    assert band["description"] == "0-0.4% click-through; median 0.2%"


def test_a_corpus_that_carries_no_ctr_reports_nothing_to_fix():
    """Nobody can read a competitor's click-through. A line per competitor ad
    per run is not a report, it is noise."""
    messages = []
    document = learn.build(PAIR, on_skip=messages.append)
    assert devices(document, "ctr") == []
    assert messages == []


def test_a_null_reading_is_not_reported_as_something_to_fix_either():
    """An ad with no impressions in the window has no ctr; measure writing
    null there is the API working as documented."""
    messages = []
    learn.build(
        [with_own_metrics("fb-own-a", own_metrics(None)),
         with_own_metrics("fb-own-b", own_metrics(None, hook_rate=0.29))],
        on_skip=messages.append,
    )
    assert messages == []


def test_a_ctr_that_is_not_a_number_is_reported_and_left_out():
    messages = []
    document = learn.build([measured("fb-own-a", "1.2%"), measured("fb-own-b", "1.2%")],
                           on_skip=messages.append)
    assert devices(document, "ctr") == []
    assert any("fb-own-a" in m and "own_metrics.ctr" in m for m in messages), messages


def test_true_is_not_a_ctr_reading():
    """True is an int in Python, and 1.0 would band as a one-percent ad - from
    a value that is not a measurement at all."""
    messages = []
    document = learn.build([measured("fb-own-a", True), measured("fb-own-b", True)],
                           on_skip=messages.append)
    assert devices(document, "ctr") == []
    assert len(messages) == 2, messages


@pytest.mark.parametrize("reading", [float("nan"), float("inf"), float("-inf")])
def test_a_ctr_that_is_not_finite_is_refused(reading):
    """A NaN in a median silently poisons every value after it."""
    messages = []
    document = learn.build([measured("fb-own-a", reading), measured("fb-own-b", reading)],
                           on_skip=messages.append)
    assert devices(document, "ctr") == []
    assert len(messages) == 2, messages


def test_a_numeric_string_reading_is_read_rather_than_thrown_away():
    """_number() is the one coercion, so a reading that arrived as text reads
    the same way a day count that arrived as text does."""
    document = learn.build([measured("fb-own-a", "0.7"), measured("fb-own-b", "0.8")])
    assert devices(document, "ctr") == ["ctr-pct:0.5-0.9"]


def test_an_own_metrics_block_that_is_not_an_object_is_reported():
    messages = []
    learn.build([with_own_metrics("fb-own-a", [1.2]), record("fb-bbb")],
                on_skip=messages.append)
    assert any("fb-own-a" in m and "own_metrics" in m for m in messages), messages


def test_an_ad_whose_reading_is_unusable_is_still_evidence_elsewhere():
    """Only the reading is unreadable; the hook really is in that ad."""
    document = learn.build([measured("fb-own-a", "1.2%"), measured("fb-own-b", "1.2%")])
    assert pattern(document, "hook", "question")["n"] == 2


# --- per origin -----------------------------------------------------------


def test_patterns_are_derivable_for_one_origin_alone():
    """A hook that works for an accounting firm's own ads is not automatically
    one this repo is allowed to claim."""
    records = [
        record("fb-aaa", origin="competitor", hook_device="question"),
        record("fb-bbb", origin="competitor", hook_device="question"),
        record("fb-ccc", origin="icp-adjacent", hook_device="named-enemy"),
        record("fb-ddd", origin="icp-adjacent", hook_device="named-enemy"),
        measured("fb-own-eee", 0.7, hook_device="story"),
        measured("fb-own-fff", 0.8, hook_device="story"),
    ]
    competitors = learn.build(records, origin="competitor")
    assert competitors["corpus_size"] == 2
    assert devices(competitors, "hook") == ["question"]

    adjacent = learn.build(records, origin="icp-adjacent")
    assert adjacent["corpus_size"] == 2
    assert devices(adjacent, "hook") == ["named-enemy"]

    own = learn.build(records, origin="own")
    assert own["corpus_size"] == 2
    assert devices(own, "hook") == ["story"]
    assert devices(own, "ctr") == ["ctr-pct:0.5-0.9"]

    assert devices(learn.build(records), "hook") == ["named-enemy", "question", "story"]


def test_an_origin_outside_the_contract_is_refused_by_name():
    with pytest.raises(ValueError, match="partner") as excinfo:
        learn.build(PAIR, origin="partner")
    assert "competitor" in str(excinfo.value)
    assert "icp-adjacent" in str(excinfo.value)
    assert "own" in str(excinfo.value)


def test_every_corpus_origin_is_accepted():
    assert corpus.ORIGINS == ("competitor", "icp-adjacent", "own")
    for origin in corpus.ORIGINS:
        assert learn.build(PAIR, origin=origin)["schema"] == 1


# --- records this module refuses to count --------------------------------


def test_a_duplicate_id_is_refused_rather_than_counted_twice():
    with pytest.raises(ValueError, match="fb-aaa"):
        learn.build([record("fb-aaa"), record("fb-aaa")])


def test_a_record_without_an_id_cannot_be_evidence():
    nameless = record("fb-aaa")
    nameless["id"] = ""
    with pytest.raises(ValueError, match="id"):
        learn.build([nameless])


def test_something_that_is_not_a_record_is_named_by_position():
    with pytest.raises(TypeError, match="record 1"):
        learn.build([record("fb-aaa"), "fb-bbb"])


# --- the real corpus module ----------------------------------------------


def test_records_written_by_the_real_corpus_module_round_trip(tmp_path):
    """The store validates and sorts; this proves learn reads what it writes
    rather than a shape restated in the tests."""
    for entry in PAIR:
        corpus.save(entry, root=tmp_path)
    records = corpus.load_all(tmp_path)
    assert all(isinstance(r, corpus.CorpusRecord) for r in records)
    document = learn.build(records)
    assert document["corpus_size"] == 2
    assert pattern(document, "hook", "question")["evidence"] == ["fb-aaa", "fb-bbb"]


def test_corpus_records_and_their_dicts_produce_the_same_document(tmp_path):
    for entry in PAIR:
        corpus.save(entry, root=tmp_path)
    records = corpus.load_all(tmp_path)
    assert learn.dumps(learn.build(records)) == learn.dumps(learn.build(PAIR))


def test_an_own_record_written_by_the_real_corpus_module_keeps_its_ctr(tmp_path):
    """own_metrics rides under the permissive analysis block; the store must
    not strip it on the way to disk, or the ctr kind would never see one."""
    for entry in (measured("fb-own-a", 0.7), measured("fb-own-b", 0.8)):
        corpus.save(entry, root=tmp_path)
    document = learn.build(corpus.load_all(tmp_path))
    assert devices(document, "ctr") == ["ctr-pct:0.5-0.9"]


def test_find_patterns_returns_objects_a_caller_can_read():
    found = learn.find_patterns(PAIR)
    assert all(isinstance(p, learn.Pattern) for p in found)
    assert all(p.n == len(p.evidence) for p in found)
    assert [p.id for p in found] == [
        p["id"] for p in learn.build(PAIR)["patterns"]
    ]
    assert [p.to_dict() for p in found] == learn.build(PAIR)["patterns"]


# --- the file on disk -----------------------------------------------------


def test_the_written_file_has_sorted_keys_and_a_trailing_newline(tmp_path):
    text = learn.write(learn.build(PAIR), tmp_path / "patterns.json").read_text(
        encoding="utf-8"
    )
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    orders = []

    def collect(pairs):
        orders.append([k for k, _ in pairs])
        return dict(pairs)

    json.loads(text, object_pairs_hook=collect)
    assert orders
    for order in orders:
        assert order == sorted(order), order


def test_dumps_is_the_committed_json_convention():
    document = learn.build(PAIR)
    assert learn.dumps(document) == (
        json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    )


def test_a_non_ascii_quote_stays_legible_in_the_file(tmp_path):
    spoken = "Bruger du stadig timer på bogføring hver uge?"
    records = [record("fb-aaa", hook_text=spoken), record("fb-bbb", hook_text=spoken)]
    path = learn.write(learn.build(records), tmp_path / "patterns.json")
    text = path.read_text(encoding="utf-8")
    assert spoken in text
    assert "\\u00f8" not in text


def test_load_reads_back_what_write_wrote(tmp_path):
    document = learn.build(PAIR)
    assert learn.load(learn.write(document, tmp_path / "patterns.json")) == document


def test_load_names_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="patterns.json") as excinfo:
        learn.load(tmp_path / "patterns.json")
    assert "python -m engine.learn" in str(excinfo.value)


def test_load_refuses_a_schema_it_cannot_read(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps({"schema": 2, "patterns": []}), encoding="utf-8")
    with pytest.raises(learn.PatternsInvalid, match="schema"):
        learn.load(path)


def test_load_names_a_file_that_is_not_json(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text("{ truncated", encoding="utf-8")
    with pytest.raises(learn.PatternsInvalid, match="not valid JSON"):
        learn.load(path)


def test_patterns_invalid_is_a_value_error():
    assert issubclass(learn.PatternsInvalid, ValueError)


# --- the command line -----------------------------------------------------


def test_the_cli_writes_a_document_and_exits_zero(tmp_path, capsys):
    root = tmp_path / "corpus"
    for entry in PAIR:
        corpus.save(entry, root=root)
    out = tmp_path / "patterns.json"

    assert learn.main(["--corpus", str(root), "--out", str(out)]) == 0
    document = learn.load(out)
    assert document["corpus_size"] == 2
    err = capsys.readouterr().err
    assert "patterns" in err
    assert "ads" in err


def test_the_cli_reports_what_it_could_not_read(tmp_path, capsys):
    root = tmp_path / "corpus"
    corpus.save(record("fb-aaa", days_running="a while"), root=root)
    corpus.save(record("fb-bbb"), root=root)
    assert learn.main(["--corpus", str(root), "--out", str(tmp_path / "p.json")]) == 0
    err = capsys.readouterr().err
    assert "skipped: fb-aaa" in err


def test_the_cli_can_print_instead_of_writing(tmp_path, capsys):
    root = tmp_path / "corpus"
    for entry in PAIR:
        corpus.save(entry, root=root)
    assert learn.main(["--corpus", str(root), "--stdout"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["schema"] == 1
    assert "stdout" in captured.err
    assert not (tmp_path / "patterns.json").exists()


def test_the_cli_can_learn_from_one_origin(tmp_path):
    root = tmp_path / "corpus"
    corpus.save(record("fb-aaa", origin="icp-adjacent"), root=root)
    corpus.save(record("fb-bbb", origin="competitor"), root=root)
    out = tmp_path / "patterns.json"
    assert learn.main(
        ["--corpus", str(root), "--origin", "competitor", "--out", str(out)]
    ) == 0
    assert learn.load(out)["corpus_size"] == 1


def test_the_cli_refuses_an_origin_outside_the_contract(tmp_path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        learn.main(["--corpus", str(tmp_path), "--origin", "partner"])
    assert excinfo.value.code == 2
    assert "partner" in capsys.readouterr().err


def test_the_cli_names_a_corpus_that_is_not_there(tmp_path, capsys):
    assert learn.main(["--corpus", str(tmp_path / "nowhere")]) == 1
    assert "corpus" in capsys.readouterr().err


def test_the_cli_names_a_corpus_record_it_cannot_read(tmp_path, capsys):
    """A half-record stops the run by name rather than being counted around."""
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "meta-ad-fb-bad.json").write_text('{"schema": 1, "id": "fb-bad"}', encoding="utf-8")
    assert learn.main(["--corpus", str(root), "--out", str(tmp_path / "p.json")]) == 1
    err = capsys.readouterr().err
    assert "fb-bad" in err
    assert not (tmp_path / "p.json").exists()


def test_the_cli_writes_the_same_bytes_twice(tmp_path):
    root = tmp_path / "corpus"
    for entry in PAIR:
        corpus.save(entry, root=root)
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    learn.main(["--corpus", str(root), "--out", str(first)])
    learn.main(["--corpus", str(root), "--out", str(second)])
    assert first.read_bytes() == second.read_bytes()


def test_the_cli_defaults_to_the_shipped_corpus_and_the_contract_path(monkeypatch, tmp_path):
    """No flags means research/corpus/ in, research/patterns.json out - the
    weekly workflow's call. The shipped corpus is empty at this commit, so the
    document is the empty one, and the write is redirected so the test leaves
    no file in the tree."""
    monkeypatch.setattr(learn, "DEFAULT_PATH", tmp_path / "patterns.json")
    assert learn.main([]) == 0
    document = learn.load(tmp_path / "patterns.json")
    assert document["schema"] == 1
    assert document["corpus_size"] == len(corpus.load_all())
