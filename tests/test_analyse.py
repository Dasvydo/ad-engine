"""Analysis: a batch of copy is one call, a creative is one call, and a record
the corpus accepts as it stands.

Five properties are worth a test here; the rest is bookkeeping.

**One call per batch, one call per creative.** Twelve text ads cost one call,
twelve plus a hand-saved creative cost two, and nothing splits one reading
into a second question. The `calls` count on the run is what the cost ledger
reads, so it is pinned separately from len(records).

**The batch is complete or there is no batch.** A reply short an id,
truncated, or not JSON raises rather than returning the ads that happened to
come first - a half-batch would be counted as evidence by learn/ and score/
forever afterwards. A per-ad refusal is the one thing that is allowed to
fail alone.

**Nothing is fetched.** No snapshot page, no creative, no socket. Checked by
parsing the module, by exploding every socket in the process and running a
whole batch through, and by pinning the media kinds this module emits to the
ones engine/model.py can attach.

**The creative path is manual-seed only.** A file the operator saved by hand
is attached to the call as a `media` entry and the record says so under
analysis.creative; a file the transport refuses (21 MiB) is a skip that
names the fix, not a crash that costs the batch its analysis.

**The record is the corpus's.** It validates, saves and loads back
unchanged, its facts are the candidate's rather than the reply's, and its
provenance lives under `analysis` where the schema leaves room.

Every test is offline: the model client is tests/stubs.StubClient, or a real
engine.model._Messages over a spy SDK where the file has to reach the seam.
No test needs a key.
"""
import ast
import copy
import json
import os
import re
import socket
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine import analyse, corpus, model
from engine.analyse import (
    AnalysisError,
    AnalysisRun,
    SkippedCandidate,
    analyse_all,
    analyse_batch,
    analyse_media,
    local_media,
)
from tests.stubs import StubClient, json_reply, text_reply

ROOT = Path(__file__).resolve().parents[1]
ANALYSE_SRC = Path(analyse.__file__).read_text(encoding="utf-8")
NOW = datetime(2026, 9, 22, 6, 4, 11, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures: a C2 candidate as engine.discover.candidate() makes it, and the
# per-ad analysis a well-behaved model answers with.
# ---------------------------------------------------------------------------


def candidate(**overrides) -> dict:
    """A fresh meta-ad candidate (contract C2). Deep-copied so a test that
    reaches into metrics/ or copy/ cannot leak its edit into the next."""
    row = {
        "id": "fb-961046237012883",
        "platform": "meta-ad",
        "url": "https://www.facebook.com/ads/library/?id=961046237012883",
        "channel": "Balance - Your AI Powered Accountants",
        "origin": "icp-adjacent",
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
        "copy": {
            "primary_text": "Bruger du stadig timer på bogføring hver uge? "
                            "Vi gør dit regnskab bedre og billigere.",
            "headline": "Se om vi kan gøre dit regnskab bedre",
            "description": "AI-drevet bogholderi til små virksomheder",
            "link_caption": "balance.dk",
        },
        "outlier_ratio": 2.4,
    }
    row = copy.deepcopy(row)
    row.update(overrides)
    return row


def candidates(n: int, prefix: str = "fb-") -> list[dict]:
    return [candidate(id="%s%d" % (prefix, i)) for i in range(1, n + 1)]


ANALYSIS = {
    "copy": {"words": 16},
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


def analysis(**overrides) -> dict:
    fresh = copy.deepcopy(ANALYSIS)
    fresh.update(overrides)
    return fresh


def envelope(ids, per_ad=None) -> dict:
    """The reply shape the prompt asks for: {"ads": {"<id>": {...}}}.
    `per_ad` overrides the analysis for named ids."""
    per_ad = per_ad or {}
    return {"ads": {cid: per_ad.get(cid, analysis()) for cid in ids}}


def reply_for(ids, per_ad=None, **kw):
    return json_reply(envelope(ids, per_ad), **kw)


def save_media(root: Path, cid: str, suffix: str = ".mp4", size: int = 16) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / (cid + suffix)
    path.write_bytes(b"\x00" * size)
    return path


def ids_in_prompt(client: StubClient, index: int = 0) -> list[str]:
    """Every id the ADS block of call `index` lists, in order."""
    sent = client.sent(index)
    block = sent[sent.index("ADS\n") + 4:sent.index("\nReturn ONLY")]
    return [ad["id"] for ad in json.loads(block)]


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    """No test here has a key, and none may need one."""
    for name in model.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def no_sockets(monkeypatch):
    def exploding(*args, **kwargs):
        raise AssertionError("the analysis path opened a socket")

    monkeypatch.setattr(socket, "socket", exploding)
    monkeypatch.setattr(socket, "create_connection", exploding)


# ---------------------------------------------------------------------------
# The constants are the contract's, and the fixture is the schema's shape.
# ---------------------------------------------------------------------------


def test_the_model_is_the_writer_not_the_judge():
    assert analyse.MODEL_ANALYSE == model.MODEL_WRITE
    assert analyse.MODEL_ANALYSE != model.MODEL_FLASH


def test_the_contract_constants():
    assert analyse.MAX_TOKENS_ANALYSE == 16000
    assert analyse.BATCH_SIZE == 12
    assert analyse.MEDIA_ROOT == ROOT / "research" / "media"
    assert analyse.TEXT_ONLY == "text-only"
    assert analyse.LOCAL_FILE == "local-file"
    assert analyse.HOOK_DEVICES == (
        "question", "negative-flip", "cost-of-inaction", "named-enemy", "before-after",
        "credential", "social-proof", "curiosity-gap", "direct-offer", "how-to", "story",
    )
    assert analyse.STRUCTURE_LABELS == (
        "hook", "problem", "agitate", "demo", "proof", "offer", "guarantee", "cta")
    assert analyse.OFFER_TYPES == (
        "none", "free-trial", "demo", "guarantee", "price", "discount", "lead-magnet")
    assert analyse.PROOF_TYPES == ("none", "testimonial", "number", "logo", "case-study", "award")
    assert analyse.CTA_TYPES == (
        "learn-more", "sign-up", "book-demo", "message", "download", "shop", "none")
    assert issubclass(AnalysisError, ValueError)
    assert issubclass(SkippedCandidate, RuntimeError)


def test_the_stub_analysis_is_exactly_what_the_corpus_asks_the_model_for():
    """The fixture is the contract's shape, not a hand-kept copy of it. A
    corpus that grows an analysis field must break this test, not pass it
    while the prompt quietly stops asking."""
    assert set(ANALYSIS) == set(analyse.MODEL_KEYS)
    assert set(analyse.MODEL_KEYS) | {"creative"} == set(corpus.REQUIRED_NESTED["analysis"])
    assert "creative" not in analyse.MODEL_KEYS


def test_the_suffixes_looked_for_are_the_ones_the_transport_can_attach():
    """A suffix found here that engine/model.py refuses would be a skip on
    every run; a suffix it accepts that is never looked for would be a file
    the operator saved for nothing."""
    assert analyse.MEDIA_SUFFIXES == tuple(model.MIME_BY_SUFFIX)


# ---------------------------------------------------------------------------
# One call per batch. Two ads, one call, two records.
# ---------------------------------------------------------------------------


def test_a_two_ad_batch_is_one_call_and_two_records():
    rows = candidates(2)
    client = StubClient(reply_for(["fb-1", "fb-2"]))
    run = analyse_batch(rows, client=client, now=NOW)
    assert isinstance(run, AnalysisRun)
    assert [r["id"] for r in run.records] == ["fb-1", "fb-2"]
    assert run.skipped == []
    assert run.calls == 1
    assert len(client.calls) == 1
    assert client.remaining == 0


def test_the_batch_call_is_the_pinned_writer_model_with_room_for_twelve():
    client = StubClient(reply_for(["fb-1"]))
    analyse_batch(candidates(1), client=client, now=NOW)
    assert client.calls[0] == {
        "model": analyse.MODEL_ANALYSE,
        "max_tokens": analyse.MAX_TOKENS_ANALYSE,
        "messages": client.calls[0]["messages"],
    }
    assert client.calls[0]["messages"][0]["role"] == "user"
    assert "media" not in client.calls[0]["messages"][0]


def test_every_ad_in_the_batch_is_listed_by_id_with_its_copy_and_metrics():
    rows = candidates(3)
    rows[1]["copy"]["headline"] = "Payroll, closed by Thursday"
    client = StubClient(reply_for(["fb-1", "fb-2", "fb-3"]))
    analyse_batch(rows, client=client, now=NOW)
    assert ids_in_prompt(client) == ["fb-1", "fb-2", "fb-3"]
    sent = client.sent()
    assert "Payroll, closed by Thursday" in sent
    assert "Bruger du stadig timer" in sent          # non-ASCII copy, unescaped
    assert '"days_running": 41' in sent
    assert '"variants": 3' in sent


def test_twelve_text_ads_plus_one_media_candidate_is_two_calls(tmp_path):
    rows = candidates(12) + [candidate(id="fb-clip")]
    save_media(tmp_path, "fb-clip")
    client = StubClient([
        reply_for(["fb-clip"]),                              # the creative, first
        reply_for(["fb-%d" % i for i in range(1, 13)]),      # then the batch
    ])
    run = analyse_all(rows, client=client, media_root=tmp_path, now=NOW)
    assert len(run.records) == 13
    assert run.skipped == []
    assert run.calls == 2
    assert len(client.calls) == 2
    assert client.media(0) == [{"kind": "local-file", "ref": str(tmp_path / "fb-clip.mp4")}]
    assert client.media(1) == []
    assert ids_in_prompt(client, 1) == ["fb-%d" % i for i in range(1, 13)]
    assert "fb-clip" not in ids_in_prompt(client, 1)


def test_records_come_back_in_the_order_the_candidates_were_given(tmp_path):
    rows = [candidate(id="fb-a"), candidate(id="fb-clip"), candidate(id="fb-b")]
    save_media(tmp_path, "fb-clip", ".jpg")
    client = StubClient([reply_for(["fb-clip"]), reply_for(["fb-a", "fb-b"])])
    run = analyse_all(rows, client=client, media_root=tmp_path, now=NOW)
    assert [r["id"] for r in run.records] == ["fb-a", "fb-clip", "fb-b"]


def test_batch_size_splits_the_text_ads_and_is_refused_below_one():
    rows = candidates(12)
    client = StubClient([
        reply_for(["fb-1", "fb-2", "fb-3", "fb-4", "fb-5"]),
        reply_for(["fb-6", "fb-7", "fb-8", "fb-9", "fb-10"]),
        reply_for(["fb-11", "fb-12"]),
    ])
    run = analyse_all(rows, client=client, batch_size=5, now=NOW)
    assert len(run.records) == 12
    assert run.calls == 3
    assert ids_in_prompt(client, 2) == ["fb-11", "fb-12"]

    with pytest.raises(ValueError, match="batch_size"):
        analyse_all(rows, client=StubClient(), batch_size=0)


def test_an_empty_batch_costs_no_call_and_an_empty_run_needs_no_key():
    client = StubClient()
    assert analyse_batch([], client=client) == AnalysisRun()
    assert client.calls == []
    # No client passed, no key set: an empty run must not demand one.
    assert analyse_all([]) == AnalysisRun([], [], 0)


def test_a_run_with_work_and_no_client_asks_for_the_key_before_any_socket(no_sockets):
    with pytest.raises(model.ConfigError, match="GEMINI_API_KEY"):
        analyse_all(candidates(1))


def test_a_run_builds_one_client_for_the_whole_run(monkeypatch, tmp_path):
    built = []

    def one_client():
        built.append(1)
        return StubClient([reply_for(["fb-clip"]), reply_for(["fb-1", "fb-2"])])

    monkeypatch.setattr(model, "client", one_client)
    save_media(tmp_path, "fb-clip")
    run = analyse_all(candidates(2) + [candidate(id="fb-clip")], media_root=tmp_path, now=NOW)
    assert len(run.records) == 3
    assert built == [1]


# ---------------------------------------------------------------------------
# The batch is complete or there is no batch.
# ---------------------------------------------------------------------------


def test_a_batch_reply_missing_an_id_raises_and_returns_nothing():
    rows = candidates(3)
    client = StubClient(reply_for(["fb-1", "fb-3"]))       # fb-2 is not answered
    with pytest.raises(AnalysisError) as caught:
        analyse_batch(rows, client=client, now=NOW)
    message = str(caught.value)
    assert "fb-2" in message                                # which id is missing
    assert "'fb-1', 'fb-3'" in message                      # what it did answer
    assert "short 1 of 3" in message
    assert "nothing is returned" in message
    assert "batch_size" in message                          # the fix


def test_a_batch_reply_short_an_id_stops_analyse_all_too():
    """A skip is about one ad; an incomplete reply is the prompt or the model
    being wrong for the batch, and finishing the run would write a corpus
    nobody can trust. Nothing from that batch is kept."""
    with pytest.raises(AnalysisError, match="fb-2"):
        analyse_all(candidates(2), client=StubClient(reply_for(["fb-1"])), now=NOW)


def test_a_truncated_batch_raises_rather_than_returning_the_first_ads():
    client = StubClient(reply_for(["fb-1", "fb-2"], stop_reason="max_tokens"))
    with pytest.raises(AnalysisError, match="truncated at max_tokens"):
        analyse_batch(candidates(2), client=client, now=NOW)


def test_a_truncated_media_reply_raises_too(tmp_path):
    save_media(tmp_path, "fb-clip")
    client = StubClient(reply_for(["fb-clip"], stop_reason="max_tokens"))
    with pytest.raises(AnalysisError, match="truncated"):
        analyse_media(candidate(id="fb-clip"), client=client, media_root=tmp_path, now=NOW)


def test_an_unparseable_reply_raises():
    client = StubClient(text_reply("I read them. They were fine."))
    with pytest.raises(AnalysisError, match="could not parse"):
        analyse_batch(candidates(1), client=client, now=NOW)


def test_a_reply_without_the_ads_envelope_raises_and_names_what_it_had():
    """The model answered with ONE analysis where the prompt asked for the
    envelope. Its keys are named so the failure reads as what it is."""
    client = StubClient(json_reply(analysis()))
    with pytest.raises(AnalysisError, match="no 'ads' object") as caught:
        analyse_batch(candidates(1), client=client, now=NOW)
    assert "'hook'" in str(caught.value)


def test_a_per_ad_entry_that_is_not_an_object_raises():
    client = StubClient(json_reply({"ads": {"fb-1": analysis(), "fb-2": "looks fine"}}))
    with pytest.raises(AnalysisError, match="fb-2"):
        analyse_batch(candidates(2), client=client, now=NOW)


def test_a_missing_nested_key_is_named_by_the_corpus_and_stops_the_batch():
    short = analysis()
    del short["hook"]["words"]
    client = StubClient(reply_for(["fb-1", "fb-2"], {"fb-2": short}))
    with pytest.raises(corpus.CorpusInvalid, match=r"'fb-2'.*analysis\.hook\.words"):
        analyse_batch(candidates(2), client=client, now=NOW)


def test_a_code_fenced_reply_is_still_read():
    text = "Here you go:\n```json\n%s\n```\n" % json.dumps(envelope(["fb-1"]))
    run = analyse_batch(candidates(1), client=StubClient(text_reply(text)), now=NOW)
    assert run.records[0]["analysis"]["hook"]["device"] == "question"


def test_an_id_the_model_volunteered_is_ignored():
    client = StubClient(json_reply({"ads": {"fb-1": analysis(), "fb-99": analysis()}}))
    run = analyse_batch(candidates(1), client=client, now=NOW)
    assert [r["id"] for r in run.records] == ["fb-1"]


# ---------------------------------------------------------------------------
# A refusal is per ad. The rest of the batch survives.
# ---------------------------------------------------------------------------


def test_a_per_ad_refusal_skips_that_id_and_the_rest_of_the_batch_survives():
    rows = candidates(3)
    client = StubClient(reply_for(
        ["fb-1", "fb-2", "fb-3"], {"fb-2": {"refuse": "the copy is empty"}}
    ))
    run = analyse_batch(rows, client=client, now=NOW)
    assert [r["id"] for r in run.records] == ["fb-1", "fb-3"]
    assert len(run.skipped) == 1
    assert run.skipped[0].startswith("fb-2: skipped")
    assert "the copy is empty" in run.skipped[0]
    assert run.calls == 1


def test_a_media_refusal_is_a_skip_that_still_cost_its_call(tmp_path):
    save_media(tmp_path, "fb-clip")
    client = StubClient(reply_for(["fb-clip"], {"fb-clip": {"refuse": "the file is blank"}}))
    with pytest.raises(SkippedCandidate, match="the file is blank") as caught:
        analyse_media(candidate(id="fb-clip"), client=client, media_root=tmp_path, now=NOW)
    assert caught.value.candidate_id == "fb-clip"
    assert caught.value.cost == 1

    client = StubClient(reply_for(["fb-clip"], {"fb-clip": {"refuse": "the file is blank"}}))
    run = analyse_all([candidate(id="fb-clip")], client=client, media_root=tmp_path, now=NOW)
    assert run.records == []
    assert "fb-clip" in run.skipped[0] and "blank" in run.skipped[0]
    assert run.calls == 1


def test_a_label_outside_the_vocabulary_is_a_skip_naming_the_label_not_a_record():
    """Labels are counted across ads. One outside the list would never match
    another, so it is refused for that ad; refusing the batch would throw
    away the other analyses over one word."""
    odd = analysis(hook={"words": 7, "text": "x", "device": "humour"})
    client = StubClient(reply_for(["fb-1", "fb-2"], {"fb-1": odd}))
    run = analyse_batch(candidates(2), client=client, now=NOW)
    assert [r["id"] for r in run.records] == ["fb-2"]
    assert len(run.skipped) == 1
    line = run.skipped[0]
    assert line.startswith("fb-1: skipped")
    assert "hook.device 'humour'" in line
    assert "question" in line and "story" in line          # the allowed list
    assert "engine/analyse.py" in line                     # where to widen it


def test_a_structure_label_outside_the_list_is_refused_the_same_way():
    odd = analysis(structure=["hook", "testimonial-montage", "cta"])
    run = analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"], {"fb-1": odd})), now=NOW)
    assert run.records == []
    assert "structure[1] 'testimonial-montage'" in run.skipped[0]


def test_a_label_that_is_not_a_string_is_off_vocabulary():
    odd = analysis(cta={"type": None, "text": ""})
    run = analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"], {"fb-1": odd})), now=NOW)
    assert run.records == []
    assert "cta.type None" in run.skipped[0]


def test_case_and_separators_are_folded_but_meaning_is_not_guessed():
    folded = analysis(
        hook={"words": 7, "text": "x", "device": "Negative_Flip"},
        structure=["Hook", "problem ", "CTA"],
        offer={"type": "Free Trial", "text": "14 dage gratis"},
    )
    run = analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"], {"fb-1": folded})), now=NOW)
    got = run.records[0]["analysis"]
    assert got["hook"]["device"] == "negative-flip"
    assert got["structure"] == ["hook", "problem", "cta"]
    assert got["offer"]["type"] == "free-trial"


# ---------------------------------------------------------------------------
# The creative path: the file is attached, and the record says so.
# ---------------------------------------------------------------------------


def test_a_media_candidate_attaches_the_file_and_the_record_says_so(tmp_path):
    saved = save_media(tmp_path, "fb-clip", ".mov")
    client = StubClient(reply_for(["fb-clip"]))
    record = analyse_media(candidate(id="fb-clip"), client=client, media_root=tmp_path, now=NOW)
    assert len(client.calls) == 1
    message = client.calls[0]["messages"][0]
    assert message["media"] == {"kind": "local-file", "ref": str(saved)}
    assert "fb-clip.mov" in message["content"]
    assert record["analysis"]["creative"] == {"kind": "local-file", "ref": str(saved)}
    corpus.validate(record)


def test_the_media_prompt_asks_for_the_first_two_seconds_folded_into_hook_and_structure(tmp_path):
    save_media(tmp_path, "fb-clip")
    client = StubClient(reply_for(["fb-clip"]))
    analyse_media(candidate(id="fb-clip"), client=client, media_root=tmp_path, now=NOW)
    sent = client.sent()
    assert "first two\nseconds" in sent or "first two seconds" in sent
    assert "hook.text" in sent and "structure begins" in sent
    assert "saved by hand" in sent
    assert '"fb-clip": {"refuse"' in sent                     # the envelope, one id
    assert ids_in_prompt(client) == ["fb-clip"]


def test_a_text_candidate_is_stamped_text_only_and_carries_no_media():
    client = StubClient(reply_for(["fb-1"]))
    run = analyse_batch(candidates(1), client=client, now=NOW)
    assert run.records[0]["analysis"]["creative"] == {"kind": "text-only"}
    assert client.media(0) == []


def test_analyse_media_with_no_file_is_a_skip_that_names_where_to_put_it(tmp_path):
    client = StubClient()
    with pytest.raises(SkippedCandidate) as caught:
        analyse_media(candidate(id="fb-none"), client=client, media_root=tmp_path)
    message = str(caught.value)
    assert "fb-none" in message
    assert str(tmp_path / "fb-none.mp4") in message
    assert "snapshot" in message and "by hand" in message
    assert "Nothing here downloads" in message
    assert "analyse_all" in message                          # the text path exists
    assert client.calls == []


def test_a_file_in_the_repository_is_named_relative_to_it_and_one_outside_as_is(tmp_path):
    inside = ROOT / "research" / "media" / "fb-1.mp4"        # need not exist
    assert analyse._provenance_ref(inside) == "research/media/fb-1.mp4"
    outside = tmp_path / "fb-1.mp4"
    assert analyse._provenance_ref(outside) == str(outside)


def test_local_media_finds_a_file_by_id_alone_with_the_clip_winning(tmp_path):
    assert local_media(candidate(id="fb-1"), media_root=tmp_path) is None   # no directory yet
    save_media(tmp_path, "fb-1", ".png")
    assert local_media(candidate(id="fb-1"), media_root=tmp_path).name == "fb-1.png"
    save_media(tmp_path, "fb-1", ".webm")
    assert local_media(candidate(id="fb-1"), media_root=tmp_path).name == "fb-1.webm"
    save_media(tmp_path, "fb-1", ".mp4")
    assert local_media(candidate(id="fb-1"), media_root=tmp_path).name == "fb-1.mp4"
    assert local_media(candidate(id="fb-nothing"), media_root=tmp_path) is None
    assert local_media(candidate(id="fb-"), media_root=tmp_path) is None     # prefix, not match


def test_local_media_ignores_a_suffix_it_cannot_send_and_reads_case_loosely(tmp_path):
    save_media(tmp_path, "fb-1", ".gif")
    assert local_media(candidate(id="fb-1"), media_root=tmp_path) is None
    save_media(tmp_path, "fb-1", ".MOV")
    assert local_media(candidate(id="fb-1"), media_root=tmp_path).name == "fb-1.MOV"
    (tmp_path / "fb-12.mp4").write_bytes(b"x")               # a different ad
    assert local_media(candidate(id="fb-1"), media_root=tmp_path).name == "fb-1.MOV"


# ---------------------------------------------------------------------------
# The seam onto engine/model.py: the file really reaches the transport, and
# a file the transport refuses is a skip, not a crash.
# ---------------------------------------------------------------------------


class _SpyModels:
    """Google's models.generate_content, without the network: records what it
    was handed and answers with one fixed text."""

    def __init__(self, text: str):
        self._text = text
        self.contents = []

    def generate_content(self, *, model, contents, config):
        self.contents.append(contents)
        return types.SimpleNamespace(text=self._text, candidates=[])


def real_client(text: str):
    """A genuine GeminiClient whose only fake part is the SDK underneath it,
    so engine.model._media_part really runs on the file."""
    inner = types.SimpleNamespace(models=_SpyModels(text))
    client = model.GeminiClient.__new__(model.GeminiClient)
    client._client = inner
    client.messages = model._Messages(inner)
    return client, inner.models


def test_a_21_mib_file_is_a_skip_that_names_the_fix_not_a_crash(tmp_path, no_sockets):
    """The transport refuses a file over its inline ceiling with a plain
    ValueError before any socket. That is one operator's problem; the text
    ad in the same run is still analysed, and the ledger does not count a
    call that never reached the wire."""
    big = tmp_path / "fb-big.mp4"
    big.touch()
    os.truncate(big, model.INLINE_LIMIT + 1024 * 1024)         # 21 MiB, sparse
    assert big.stat().st_size == 21 * 1024 * 1024

    client, spy = real_client(json.dumps(envelope(["fb-ok"])))
    run = analyse_all(
        [candidate(id="fb-big"), candidate(id="fb-ok")],
        client=client, media_root=tmp_path, now=NOW,
    )
    assert [r["id"] for r in run.records] == ["fb-ok"], (
        "the readable ad was not analysed; the oversized file killed the run"
    )
    assert len(run.skipped) == 1
    assert run.skipped[0].startswith("fb-big: skipped")
    assert "fb-big.mp4" in run.skipped[0]
    assert "File API" in run.skipped[0]
    assert run.calls == 1
    assert len(spy.contents) == 1
    assert isinstance(spy.contents[0], str)                    # the text batch, no part


def test_an_oversized_file_through_analyse_media_is_a_skip_costing_nothing(tmp_path):
    big = tmp_path / "fb-big.mp4"
    big.touch()
    os.truncate(big, model.INLINE_LIMIT + 1)
    client, spy = real_client("{}")
    with pytest.raises(SkippedCandidate, match="could not be attached") as caught:
        analyse_media(candidate(id="fb-big"), client=client, media_root=tmp_path, now=NOW)
    assert caught.value.cost == 0
    assert spy.contents == []


def test_a_saved_file_really_reaches_the_wire_as_an_inline_part(tmp_path):
    save_media(tmp_path, "fb-clip", ".webm")
    client, spy = real_client(json.dumps(envelope(["fb-clip"])))
    record = analyse_media(candidate(id="fb-clip"), client=client, media_root=tmp_path, now=NOW)
    assert record["analysis"]["creative"]["kind"] == "local-file"
    contents = spy.contents[0]
    assert not isinstance(contents, str)
    assert contents[1].inline_data.mime_type == "video/webm"


def _kinds_in(path) -> set:
    known = {"youtube-url", "local-file", "file-uri"}
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value in known
    }


def test_every_media_kind_this_module_emits_is_one_the_transport_handles():
    """Pins the two sides of the seam. engine/model.py raises on a kind it
    does not know rather than sending a bare prompt, so a divergence fails
    loudly - but in a weekly job, after the quota is spent. This catches it
    here."""
    emitted = _kinds_in(analyse.__file__)
    handled = _kinds_in(model.__file__)
    assert emitted == {"local-file"}
    assert emitted <= handled


# ---------------------------------------------------------------------------
# Nothing is fetched. No snapshot, no creative, no socket.
# ---------------------------------------------------------------------------


def _imports(source: str) -> set:
    tree = ast.parse(source)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
    return found


def test_nothing_in_this_module_can_fetch_anything():
    """Parsed rather than reviewed. A transport imported here would turn a
    reading of copy into a scraper, which docs/AD-RESEARCH-SCOPE.md rules out
    and which the Ad Library's terms rule out first."""
    forbidden = (
        "subprocess", "urllib", "http", "requests", "httpx", "aiohttp",
        "socket", "ssl", "google", "yt_dlp", "ffmpeg", "selenium", "playwright",
    )
    imported = _imports(ANALYSE_SRC)
    leaked = sorted(
        name for name in imported for bad in forbidden
        if name == bad or name.startswith(bad + ".")
    )
    assert leaked == [], f"engine/analyse.py imports {leaked}"
    assert "ads/library" not in ANALYSE_SRC.replace("facebook.com/ads/library/?id=", "")
    assert "snapshot_url" not in ANALYSE_SRC


def test_the_whole_path_opens_no_socket(no_sockets, tmp_path):
    """Not "does not download": opens nothing at all. Every socket in the
    process explodes, and a run with a batch and a creative completes."""
    save_media(tmp_path, "fb-clip")
    client = StubClient([reply_for(["fb-clip"]), reply_for(["fb-1", "fb-2"])])
    run = analyse_all(candidates(2) + [candidate(id="fb-clip")],
                      client=client, media_root=tmp_path, now=NOW)
    assert len(run.records) == 3


def test_every_call_goes_through_engine_model_call_model(monkeypatch):
    assert "messages.create" not in ANALYSE_SRC
    seen = []
    real = model.call_model

    def spy(client, **kw):
        seen.append(kw)
        return real(client, **kw)

    monkeypatch.setattr(model, "call_model", spy)
    analyse_batch(candidates(2), client=StubClient(reply_for(["fb-1", "fb-2"])), now=NOW)
    assert len(seen) == 1
    assert set(seen[0]) == {"model", "max_tokens", "messages"}


def test_a_provider_fault_raised_by_the_client_propagates_as_itself():
    """A CapacityError is the operator's to read, not this module's to hide
    in a skip line: the sibling's fanout catches ConfigError by name."""
    client = StubClient(model.CapacityError("Gemini is out of capacity right now"))
    with pytest.raises(model.CapacityError):
        analyse_all(candidates(1), client=client, now=NOW)


# ---------------------------------------------------------------------------
# The record the corpus accepts, unmodified.
# ---------------------------------------------------------------------------


def test_the_record_validates_saves_and_loads_back_unchanged(tmp_path):
    run = analyse_batch([candidate()], client=StubClient(reply_for(["fb-961046237012883"])), now=NOW)
    record = run.records[0]
    corpus.validate(record)
    assert corpus.CorpusRecord.from_dict(record).id == "fb-961046237012883"
    path = corpus.save(record, root=tmp_path)
    assert path.name == "meta-ad-fb-961046237012883.json"
    assert corpus.load(path).to_dict() == record
    assert path.read_text(encoding="utf-8").endswith("}\n")


def test_the_record_carries_exactly_the_schemas_top_level_keys():
    run = analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"])), now=NOW)
    assert set(run.records[0]) == set(corpus.REQUIRED_KEYS)


def test_the_record_is_the_c1_example_from_this_candidate():
    """The C1 record in docs/CONTRACTS.md, assembled from the C2 candidate
    beside it and the model's analysis - field for field."""
    run = analyse_batch([candidate()], client=StubClient(reply_for(["fb-961046237012883"])), now=NOW)
    record = run.records[0]
    assert record["schema"] == 1
    assert record["id"] == "fb-961046237012883"
    assert record["platform"] == "meta-ad"
    assert record["url"] == "https://www.facebook.com/ads/library/?id=961046237012883"
    assert record["channel"] == "Balance - Your AI Powered Accountants"
    assert record["origin"] == "icp-adjacent"
    assert record["fetched_at"] == "2026-09-22T06:04:11Z"
    assert record["metrics"] == candidate()["metrics"]
    assert record["model"] == "gemini-3.6-flash"
    got = record["analysis"]
    assert got["copy"] == dict(candidate()["copy"], words=16)
    assert got["hook"] == ANALYSIS["hook"]
    assert got["structure"] == ["hook", "problem", "offer", "cta"]
    assert got["offer"] == {"type": "none", "text": ""}
    assert got["proof"] == {"type": "none", "text": ""}
    assert got["cta"] == {"type": "learn-more", "text": "Se om vi kan gøre dit regnskab bedre"}
    assert got["objections"] == ["we already have an accountant"]
    assert got["creative"] == {"kind": "text-only"}
    assert got["outlier_ratio"] == 2.4
    assert set(got) == set(corpus.REQUIRED_NESTED["analysis"]) | {"outlier_ratio"}


def test_copy_is_the_candidates_copy_plus_the_models_word_count():
    """The model counts; it does not get to restate the copy. A reply that
    echoes different text is ignored, and one that forgets the count is
    named by the corpus."""
    echo = analysis(copy={"words": 3, "primary_text": "something else entirely"})
    run = analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"], {"fb-1": echo})), now=NOW)
    assert run.records[0]["analysis"]["copy"]["primary_text"].startswith("Bruger du")
    assert run.records[0]["analysis"]["copy"]["words"] == 3

    forgot = analysis(copy={})
    with pytest.raises(corpus.CorpusInvalid, match=r"analysis\.copy\.words"):
        analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"], {"fb-1": forgot})), now=NOW)


def test_the_candidates_facts_win_over_anything_the_model_says():
    spoofed = analysis()
    spoofed.update({
        "id": "fb-not-this", "url": "https://example.invalid/", "model": "other",
        "creative": {"kind": "local-file", "ref": "/nowhere"}, "outlier_ratio": 99,
        "metrics": {"eu_total_reach": 1},
    })
    client = StubClient(reply_for(["fb-1"], {"fb-1": spoofed}))
    record = analyse_batch(candidates(1), client=client, now=NOW).records[0]
    assert record["id"] == "fb-1"
    assert record["url"] == candidate()["url"]
    assert record["model"] == analyse.MODEL_ANALYSE == client.calls[0]["model"]
    assert record["metrics"] == candidate()["metrics"]
    assert record["analysis"]["creative"] == {"kind": "text-only"}
    assert record["analysis"]["outlier_ratio"] == 2.4
    assert "id" not in record["analysis"] and "metrics" not in record["analysis"]


def test_provenance_rides_inside_analysis_where_the_schema_allows_it():
    record = analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"])), now=NOW).records[0]
    assert "outlier_ratio" not in record
    assert record["analysis"]["outlier_ratio"] == 2.4
    assert "creative" not in record


def test_fetched_at_is_pinned_by_now_and_is_utc_to_the_second():
    east = datetime(2026, 9, 22, 8, 4, 11, tzinfo=timezone(timedelta(hours=2)))
    run = analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"])), now=east)
    assert run.records[0]["fetched_at"] == "2026-09-22T06:04:11Z"

    naive = datetime(2026, 9, 22, 6, 4, 11)                   # read as UTC
    run = analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"])), now=naive)
    assert run.records[0]["fetched_at"] == "2026-09-22T06:04:11Z"

    run = analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"])), now="2026-09-22T06:04:11Z")
    assert run.records[0]["fetched_at"] == "2026-09-22T06:04:11Z"

    run = analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"])))
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", run.records[0]["fetched_at"])


def test_the_analysis_is_read_past_the_thinking_block():
    """The JSON is not content[0]; a thinking block is (tests/stubs.py leads
    every reply with one)."""
    run = analyse_batch(candidates(1), client=StubClient(reply_for(["fb-1"])), now=NOW)
    assert run.records[0]["analysis"]["hook"]["text"]


# ---------------------------------------------------------------------------
# The candidate is refused before any call when it is not a meta-ad C2.
# ---------------------------------------------------------------------------


def test_an_unknown_platform_is_refused_naming_meta_ad_before_any_call(tmp_path):
    client = StubClient(reply_for(["fb-1"]))
    for call in (
        lambda: analyse_batch([candidate(id="fb-1", platform="youtube")], client=client),
        lambda: analyse_media([candidate(id="fb-1", platform="instagram")][0], client=client, media_root=tmp_path),
        lambda: analyse_all([candidate(id="fb-1"), candidate(id="fb-2", platform="tiktok")], client=client),
    ):
        with pytest.raises(ValueError, match="meta-ad only") as caught:
            call()
        assert "platform" in str(caught.value)
    assert client.calls == []


def test_a_candidate_missing_a_c2_key_is_refused_naming_it():
    row = candidate()
    del row["copy"]
    with pytest.raises(ValueError, match="'copy'.*contract C2"):
        analyse_batch([row], client=StubClient())
    with pytest.raises(ValueError, match="blank id"):
        analyse_all([candidate(id="")], client=StubClient())


def test_a_duplicate_id_is_refused_before_any_call():
    client = StubClient()
    with pytest.raises(ValueError, match="'fb-1' appears twice"):
        analyse_all([candidate(id="fb-1"), candidate(id="fb-1")], client=client)
    assert client.calls == []


# ---------------------------------------------------------------------------
# The prompt asks for what the schema requires, in the closed vocabularies.
# ---------------------------------------------------------------------------


def test_the_prompt_asks_for_every_key_the_corpus_requires_of_the_model():
    client = StubClient(reply_for(["fb-1"]))
    analyse_batch(candidates(1), client=client, now=NOW)
    sent = client.sent()
    for dotted, keys in corpus.REQUIRED_NESTED.items():
        if not dotted.startswith("analysis") or dotted == "analysis.creative":
            continue
        for key in keys:
            if key == "creative":
                continue                                        # stamped, not asked
            assert key in sent, f"{dotted}.{key} is not asked for"
    assert "exactly these keys: " + ", ".join(analyse.MODEL_KEYS) in sent


def test_the_prompt_renders_every_vocabulary_and_says_to_reuse_a_label():
    client = StubClient(reply_for(["fb-1"]))
    analyse_batch(candidates(1), client=client, now=NOW)
    sent = client.sent()
    for vocabulary in (analyse.HOOK_DEVICES, analyse.STRUCTURE_LABELS, analyse.OFFER_TYPES,
                       analyse.PROOF_TYPES, analyse.CTA_TYPES):
        assert ", ".join(vocabulary) in sent
    assert "never invent a\nsynonym" in sent or "never invent a synonym" in sent
    assert "counted across ads" in sent
    assert "halve its evidence" in sent


def test_the_prompt_asks_for_what_a_copywriter_reuses_and_gives_a_way_to_refuse():
    client = StubClient(reply_for(["fb-1"]))
    analyse_batch(candidates(1), client=client, now=NOW)
    sent = client.sent()
    for phrase in (
        "count of whitespace-separated words",
        "verbatim",
        "exact ask",
        "objection",
        "in the order they appear",
        "Do not guess",
        '{"refuse": "one sentence saying why"}',
        "Never leave an id out",
        '{"ads": {"<id>": {...}, ...}}',
    ):
        assert phrase in sent, phrase
