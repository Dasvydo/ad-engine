"""The corpus store: does a C1 record survive the disk, and does a bad one stop.

`record(**overrides)` at module level builds a complete, valid C1 record; other
test files copy it rather than import it, so each suite pins its own contract.
"""
import ast
import copy
import json
import re
from pathlib import Path

import pytest

from engine import corpus

# The C1 example from docs/CONTRACTS.md, verbatim in shape. The Danish text is
# the kind of thing the Ad Library actually returns for a DK reach query.
RECORD = {
    "schema": 1,
    "id": "fb-961046237012883",
    "platform": "meta-ad",
    "url": "https://www.facebook.com/ads/library/?id=961046237012883",
    "channel": "Balance - Your AI Powered Accountants",
    "origin": "icp-adjacent",
    "fetched_at": "2026-09-22T06:04:11Z",
    "metrics": {
        "eu_total_reach": 12000,
        "days_running": 41,
        "active": True,
        "variants": 3,
        "page_id": "1007614045762121",
        "publisher_platforms": ["facebook", "instagram"],
        "languages": ["da"],
        "countries": ["DK"],
    },
    "analysis": {
        "copy": {
            "primary_text": "Bruger du stadig timer på bogføring hver uge? "
                            "Vi gør dit regnskab bedre og billigere.",
            "headline": "Se om vi kan gøre dit regnskab bedre",
            "description": "AI-drevet bogholderi til små virksomheder",
            "link_caption": "balance.dk",
            "words": 16,
        },
        "hook": {
            "words": 9,
            "text": "Bruger du stadig timer på bogføring hver uge?",
            "device": "question",
        },
        "structure": ["hook", "problem", "offer", "cta"],
        "offer": {"type": "none", "text": ""},
        "proof": {"type": "none", "text": ""},
        "cta": {"type": "learn-more", "text": "Se om vi kan gøre dit regnskab bedre"},
        "objections": ["we already have an accountant"],
        "creative": {"kind": "text-only"},
        "outlier_ratio": 2.4,
    },
    "model": "gemini-3.6-flash",
}


def record(**overrides) -> dict:
    """A fresh valid C1 record. Deep-copied so a test that reaches into
    metrics/ or analysis/ cannot leak its edit into the next test."""
    fresh = copy.deepcopy(RECORD)
    fresh.update(overrides)
    return fresh


# --- round trip and on-disk shape ----------------------------------------


def test_a_saved_record_loads_back_as_an_equal_dict(tmp_path):
    path = corpus.save(record(), root=tmp_path)
    assert corpus.load(path).to_dict() == RECORD


def test_the_dataclass_round_trips_without_touching_the_disk():
    assert corpus.CorpusRecord.from_dict(record()).to_dict() == RECORD


def test_a_complete_c1_record_round_trips_byte_identically(tmp_path):
    """save -> load -> save must not move a byte: a load/save cycle that
    rewrote the file would put noise in every commit the research cron makes."""
    first = corpus.save(record(), root=tmp_path)
    before = first.read_bytes()
    after = corpus.save(corpus.load(first), root=tmp_path).read_bytes()
    assert after == before
    # And the bytes are exactly the committed-JSON convention, nothing else.
    expected = json.dumps(RECORD, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    assert before.decode("utf-8") == expected


def test_the_saved_file_has_sorted_keys_at_every_level_and_a_trailing_newline(tmp_path):
    """Both are what keep a re-analysis readable as a diff. Checked at every
    nesting level, not just the top: analysis/ is where the fields change."""
    text = corpus.save(record(), root=tmp_path).read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")

    orders = []

    def collect(pairs):
        orders.append([k for k, _ in pairs])
        return dict(pairs)

    json.loads(text, object_pairs_hook=collect)
    assert orders, "no objects parsed"
    for order in orders:
        assert order == sorted(order), order


def test_the_filename_is_the_platform_and_the_id(tmp_path):
    assert corpus.save(record(), root=tmp_path).name == "meta-ad-fb-961046237012883.json"
    assert corpus.path_for(record(), tmp_path) == tmp_path / "meta-ad-fb-961046237012883.json"


def test_path_for_defaults_to_the_shipped_corpus_directory():
    assert corpus.path_for(record()).parent == corpus.DEFAULT_ROOT


def test_non_ascii_copy_survives_and_stays_legible_in_the_file(tmp_path):
    """Escaped as \\uXXXX the text round-trips too, but nobody can review it.
    Danish and Lithuanian copy is most of what this corpus holds."""
    native = record()
    native["analysis"]["copy"]["headline"] = "Apskaita, kurią supranti"
    path = corpus.save(native, root=tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "Apskaita, kurią supranti" in text
    assert "gøre dit regnskab" in text
    assert "\\u00f8" not in text
    assert corpus.load(path).to_dict() == native


# --- validation ----------------------------------------------------------


# C1 is a contract five other modules read (analyse, learn, score, feedback,
# fanout), so the key list is pinned here literally rather than imported. The
# parametrised tests below iterate the module's own REQUIRED_KEYS and
# REQUIRED_NESTED, which proves every key it knows about is enforced - but
# would stay green if a key were dropped from those constants, taking the
# contract with it. This test is the one that notices.
C1_TOP_LEVEL = [
    "analysis", "channel", "fetched_at", "id", "metrics", "model",
    "origin", "platform", "schema", "url",
]
C1_NESTED = {
    "metrics": ["active", "days_running", "eu_total_reach", "page_id", "variants"],
    "analysis": ["copy", "creative", "cta", "hook", "objections", "offer",
                 "proof", "structure"],
    "analysis.copy": ["description", "headline", "link_caption", "primary_text", "words"],
    "analysis.hook": ["device", "text", "words"],
    "analysis.offer": ["text", "type"],
    "analysis.proof": ["text", "type"],
    "analysis.cta": ["text", "type"],
    "analysis.creative": ["kind"],
}
C1_LISTS = ["analysis.objections", "analysis.structure"]


def test_the_enforced_key_set_is_still_the_contract():
    assert sorted(corpus.REQUIRED_KEYS) == sorted(C1_TOP_LEVEL)
    assert sorted(corpus.REQUIRED_NESTED) == sorted(C1_NESTED)
    for parent, keys in C1_NESTED.items():
        assert sorted(corpus.REQUIRED_NESTED[parent]) == sorted(keys), parent
    assert sorted(corpus.REQUIRED_LISTS) == C1_LISTS


def test_the_enums_are_still_the_contract():
    assert corpus.SCHEMA == 1
    assert corpus.PLATFORMS == ("meta-ad",)
    assert corpus.ORIGINS == ("competitor", "icp-adjacent", "own")
    assert corpus.DEFAULT_ROOT == corpus.ROOT / "research" / "corpus"


def test_nested_parents_are_declared_before_their_children():
    """validate() resolves "analysis.copy" only after "analysis" has been
    proved an object holding "copy"; the dict order is what guarantees that."""
    seen = []
    for dotted, keys in corpus.REQUIRED_NESTED.items():
        parent, _, child = dotted.rpartition(".")
        if parent:
            assert parent in seen, f"{dotted} listed before {parent}"
            assert child in corpus.REQUIRED_NESTED[parent], f"{parent} does not require {child}"
        seen.append(dotted)
    for dotted in corpus.REQUIRED_LISTS:
        parent, _, child = dotted.rpartition(".")
        assert child in corpus.REQUIRED_NESTED[parent], f"{parent} does not require {child}"


def test_a_complete_record_validates():
    assert corpus.validate(record()) is None


def test_a_record_that_is_not_an_object_is_refused():
    with pytest.raises(corpus.CorpusInvalid, match="not a JSON object"):
        corpus.validate([record()])


@pytest.mark.parametrize("key", corpus.REQUIRED_KEYS)
def test_a_missing_top_level_key_is_named(tmp_path, key):
    short = record()
    del short[key]
    with pytest.raises(corpus.CorpusInvalid, match=re.escape(repr(key))):
        corpus.save(short, root=tmp_path)


NESTED_KEYS = [
    (parent, key)
    for parent, keys in corpus.REQUIRED_NESTED.items()
    for key in keys
]


@pytest.mark.parametrize("parent,key", NESTED_KEYS)
def test_a_missing_nested_key_is_named_with_its_dotted_path(tmp_path, parent, key):
    """"page_id" alone would leave the operator searching; "metrics.page_id"
    does not."""
    short = record()
    target = short
    for part in parent.split("."):
        target = target[part]
    del target[key]
    with pytest.raises(corpus.CorpusInvalid, match=re.escape(repr(f"{parent}.{key}"))):
        corpus.save(short, root=tmp_path)


@pytest.mark.parametrize("dotted", corpus.REQUIRED_NESTED)
def test_a_nested_block_that_is_not_an_object_is_refused(tmp_path, dotted):
    wrong = record()
    parent, _, child = dotted.rpartition(".")
    holder = wrong
    for part in parent.split(".") if parent else []:
        holder = holder[part]
    holder[child] = "flattened"
    with pytest.raises(corpus.CorpusInvalid, match=re.escape(repr(dotted))) as excinfo:
        corpus.save(wrong, root=tmp_path)
    assert "must be a JSON object" in str(excinfo.value)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("dotted", corpus.REQUIRED_LISTS)
def test_a_list_field_that_is_not_a_list_is_refused(tmp_path, dotted):
    """One object where the contract asks for a list of them validates key by
    key and then makes learn/ count one objection as none."""
    flat = record()
    parent, _, child = dotted.rpartition(".")
    holder = flat
    for part in parent.split("."):
        holder = holder[part]
    holder[child] = {"0": "hook"}
    with pytest.raises(corpus.CorpusInvalid, match=re.escape(repr(dotted))) as excinfo:
        corpus.save(flat, root=tmp_path)
    assert "must be a list" in str(excinfo.value)


def test_an_empty_list_is_still_a_list():
    """An ad that answers no objection has [] there, not a missing key: absent
    and empty mean different things to learn/."""
    quiet = record()
    quiet["analysis"]["objections"] = []
    assert corpus.validate(quiet) is None


def test_a_wrong_schema_is_refused_and_names_the_fix(tmp_path):
    with pytest.raises(corpus.CorpusInvalid, match="schema") as excinfo:
        corpus.save(record(schema=2), root=tmp_path)
    assert "2" in str(excinfo.value)
    assert "engine/corpus.py" in str(excinfo.value)


def test_a_platform_outside_the_set_is_refused_and_named(tmp_path):
    """The reel platforms belong to the sibling's corpus; a youtube record
    here was saved to the wrong repository."""
    with pytest.raises(corpus.CorpusInvalid, match="youtube") as excinfo:
        corpus.save(record(platform="youtube"), root=tmp_path)
    assert "meta-ad" in str(excinfo.value)
    with pytest.raises(corpus.CorpusInvalid, match="instagram"):
        corpus.save(record(platform="instagram"), root=tmp_path)


def test_an_origin_outside_the_set_is_refused_and_named(tmp_path):
    with pytest.raises(corpus.CorpusInvalid, match="partner") as excinfo:
        corpus.save(record(origin="partner"), root=tmp_path)
    for allowed in ("competitor", "icp-adjacent", "own"):
        assert allowed in str(excinfo.value)


@pytest.mark.parametrize("origin", corpus.ORIGINS)
def test_every_contract_origin_validates(origin):
    assert corpus.validate(record(origin=origin)) is None


def test_nothing_is_written_when_the_record_is_invalid(tmp_path):
    """A half-accepted record on disk is worse than a refused one: it reads back
    clean next week and nobody remembers the save that complained."""
    with pytest.raises(corpus.CorpusInvalid):
        corpus.save(record(origin="partner"), root=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_an_unexpected_top_level_key_is_refused(tmp_path):
    """The top level IS the contract; a field the prompt learns belongs under
    analysis, where the shape is permissive."""
    with pytest.raises(corpus.CorpusInvalid, match="notes") as excinfo:
        corpus.save(record(notes="added by hand"), root=tmp_path)
    assert "schema 1 defines exactly" in str(excinfo.value)


def test_page_id_belongs_under_metrics_not_at_the_top_level(tmp_path):
    with pytest.raises(corpus.CorpusInvalid, match="page_id"):
        corpus.save(record(page_id="1007614045762121"), root=tmp_path)


def test_an_id_that_would_escape_the_corpus_directory_is_refused(tmp_path):
    """The id is half the filename, so a slash in it writes outside the corpus."""
    with pytest.raises(corpus.CorpusInvalid, match="id"):
        corpus.save(record(id="../../etc/passwd"), root=tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad", ["", "fb 961", "fb:961", 961046237012883, None])
def test_a_blank_or_unfilable_id_is_refused(tmp_path, bad):
    """Refuse rather than guess: a blank id would name the file `meta-ad-.json`
    and an int id (the archive's digits, unprefixed and unstringed) would
    sort differently from every other record."""
    with pytest.raises(corpus.CorpusInvalid, match="id"):
        corpus.save(record(id=bad), root=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_analysis_is_permissive_so_an_own_record_validates():
    """feedback writes `own_metrics` and `derived_from` under analysis, and
    `model: "none (authored)"`; none of that needs a schema bump."""
    own = record(id="fb-own-payroll-bureaus-1234", origin="own", model="none (authored)")
    own["analysis"]["own_metrics"] = {"ctr": 1.24, "hook_rate": 0.293, "hold_rate": None}
    own["analysis"]["derived_from"] = {"note": "copy read off the job file; ctr from measure"}
    own["analysis"]["creative"] = {"kind": "authored"}
    assert corpus.validate(own) is None


def test_metrics_is_permissive_so_the_archive_lists_ride_along():
    bare = record()
    for extra in ("publisher_platforms", "languages", "countries"):
        del bare["metrics"][extra]
    assert corpus.validate(bare) is None
    bare["metrics"]["media_type"] = "VIDEO"
    assert corpus.validate(bare) is None


def test_a_local_file_creative_validates_with_its_ref():
    """The media path stamps `creative: {"kind": "local-file", "ref": ...}`;
    only `kind` is fixed, the ref rides along."""
    watched = record()
    watched["analysis"]["creative"] = {"kind": "local-file", "ref": "research/media/fb-961046237012883.mp4"}
    assert corpus.validate(watched) is None


# --- validation on the way in, not just on the way out -------------------


def _write_raw(path: Path, data: dict) -> Path:
    """Write without going through save(), to prove load() validates too."""
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_refuses_a_platform_outside_the_set(tmp_path):
    path = _write_raw(tmp_path / "youtube-fb-1.json", record(platform="youtube"))
    with pytest.raises(corpus.CorpusInvalid, match="youtube"):
        corpus.load(path)


def test_load_refuses_a_record_missing_a_required_key(tmp_path):
    short = record()
    del short["channel"]
    path = _write_raw(tmp_path / "meta-ad-fb-961046237012883.json", short)
    with pytest.raises(corpus.CorpusInvalid, match="channel"):
        corpus.load(path)


def test_load_refuses_a_record_missing_a_nested_key_by_dotted_path(tmp_path):
    short = record()
    del short["metrics"]["page_id"]
    path = _write_raw(tmp_path / "meta-ad-fb-961046237012883.json", short)
    with pytest.raises(corpus.CorpusInvalid, match=re.escape("'metrics.page_id'")):
        corpus.load(path)


def test_an_unknown_schema_version_raises_rather_than_guessing(tmp_path):
    """Reading schema 2 with schema 1's expectations mis-reads every field it
    thinks it recognises, silently."""
    path = _write_raw(tmp_path / "meta-ad-fb-961046237012883.json", record(schema=2))
    with pytest.raises(corpus.CorpusInvalid, match="schema") as excinfo:
        corpus.load(path)
    assert "2" in str(excinfo.value)


def test_load_names_the_file_when_it_is_not_json(tmp_path):
    path = tmp_path / "meta-ad-fb-961046237012883.json"
    path.write_text("{ truncated", encoding="utf-8")
    with pytest.raises(corpus.CorpusInvalid, match="not valid JSON") as excinfo:
        corpus.load(path)
    assert path.name in str(excinfo.value)


def test_load_names_the_path_that_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="gone.json"):
        corpus.load(tmp_path / "gone.json")


def test_an_error_names_the_file_as_well_as_the_id(tmp_path):
    """Two hundred near-identical files; the message has to say which one."""
    path = _write_raw(tmp_path / "meta-ad-fb-961046237012883.json", record(origin="partner"))
    with pytest.raises(corpus.CorpusInvalid) as excinfo:
        corpus.load(path)
    assert "fb-961046237012883" in str(excinfo.value)
    assert str(path) in str(excinfo.value)


def test_an_error_on_a_record_with_no_id_still_names_the_file(tmp_path):
    short = record()
    del short["id"]
    path = _write_raw(tmp_path / "hand-written.json", short)
    with pytest.raises(corpus.CorpusInvalid) as excinfo:
        corpus.load(path)
    assert "no usable id" in str(excinfo.value)
    assert str(path) in str(excinfo.value)


# --- the corpus as a whole -----------------------------------------------


def test_load_all_returns_every_record_ordered_by_id(tmp_path):
    """Ordered by id, not by filename: these disagree on purpose here (one
    sits in a subdirectory), so downstream counting reads the same corpus
    however the files got named."""
    corpus.save(record(id="fb-999"), root=tmp_path)
    corpus.save(record(id="fb-111"), root=tmp_path)
    corpus.save(record(id="fb-555"), root=tmp_path / "2026-w39")
    assert [r.id for r in corpus.load_all(tmp_path)] == ["fb-111", "fb-555", "fb-999"]


def test_load_all_returns_records_not_raw_dicts(tmp_path):
    corpus.save(record(), root=tmp_path)
    loaded = corpus.load_all(tmp_path)
    assert all(isinstance(r, corpus.CorpusRecord) for r in loaded)
    assert [r.to_dict() for r in loaded] == [RECORD]


def test_a_duplicate_id_raises_naming_both_files(tmp_path):
    """Two files for one ad would have learn/ median the same evidence twice
    and let a single ad carry a pattern on its own. Both paths are named so
    the operator knows which to delete."""
    kept = corpus.save(record(), root=tmp_path)
    stray = _write_raw(tmp_path / "hand-copied.json", record(channel="Someone Else"))
    with pytest.raises(corpus.CorpusInvalid, match="duplicate") as excinfo:
        corpus.load_all(tmp_path)
    message = str(excinfo.value)
    assert "fb-961046237012883" in message
    assert str(kept) in message
    assert str(stray) in message


def test_load_all_refuses_the_whole_corpus_when_one_file_is_bad(tmp_path):
    """A skip here would make the corpus a different size on every run."""
    corpus.save(record(id="fb-1"), root=tmp_path)
    _write_raw(tmp_path / "meta-ad-fb-2.json", record(id="fb-2", origin="partner"))
    with pytest.raises(corpus.CorpusInvalid, match="partner"):
        corpus.load_all(tmp_path)


def test_an_empty_corpus_is_an_empty_list_not_an_error(tmp_path):
    assert corpus.load_all(tmp_path) == []


def test_a_missing_corpus_directory_is_named(tmp_path):
    with pytest.raises(FileNotFoundError, match="corpus") as excinfo:
        corpus.load_all(tmp_path / "nowhere")
    assert ".gitkeep" in str(excinfo.value)


def test_the_shipped_corpus_directory_exists_and_loads():
    """research/corpus/.gitkeep is what keeps the directory in a fresh clone."""
    assert (corpus.DEFAULT_ROOT / ".gitkeep").exists()
    assert isinstance(corpus.load_all(), list)


# --- the reason this module is safe to import anywhere -------------------


FORBIDDEN = (
    "engine.model",
    "engine.discover",
    "engine.analyse",
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


def test_the_corpus_module_reaches_no_model_and_no_network():
    """analyse, learn, score and feedback all import this, and their tests
    must stay offline. A model client or an HTTP library pulled in here would
    make the whole chain need an API key to import."""
    tree = ast.parse(Path(corpus.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    leaked = sorted(
        name
        for name in imported
        for bad in FORBIDDEN
        if name == bad or name.startswith(bad + ".")
    )
    assert leaked == [], f"engine/corpus.py imports {leaked}"
