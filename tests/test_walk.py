"""tools/walk.py: the offline walk, tested the way it claims to run.

The tool's own promise is what this file pins. It says it needs no token, no
key and no network; it says it writes only under --out; it says it refuses a
directory it did not create. A demonstration that quietly opened a socket, or
that overwrote the committed corpus the first time somebody ran it from the
repository root, would be worse than no demonstration at all.

The walk's CONTENT is not re-asserted here - tests/test_pipeline.py already
owns every seam it drives, and the tool imports that file's fixtures, so a
change to the loop fails there with a message about the seam rather than here
with a message about a demo.
"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import approval  # noqa: E402
from tools import walk as walk_tool  # noqa: E402


@pytest.fixture(autouse=True)
def restore_the_queue(monkeypatch):
    """walk() REASSIGNS approval.QUEUE, by design and for the reason its
    docstring gives. Recording it through monkeypatch restores it after each
    test, so a walk here cannot leave the rest of the suite pointed at a
    tmp_path that pytest has since deleted."""
    monkeypatch.setattr(approval, "QUEUE", approval.QUEUE)


@pytest.fixture
def no_network(monkeypatch):
    """Every socket in the process explodes - the same arming
    tests/test_discover.py uses. If the walk reaches the network anywhere,
    this is where it says so."""
    def boom(*args, **kwargs):
        raise AssertionError("tools/walk.py opened a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


def test_the_walk_completes_with_every_socket_armed(tmp_path, no_network):
    out = tmp_path / "demo"
    result = walk_tool.walk(out, walk_tool.Log(on=False))

    assert len(result["candidates"]) == 4
    assert result["verdict"].ok, result["verdict"].failures
    # The tenth stage is the one that makes it a loop rather than a line: our
    # own measured ads re-enter the corpus and mint a kind of pattern the
    # competitors cannot.
    assert result["after"]["corpus_size"] == 6
    assert any(p["kind"] == "ctr" for p in result["after"]["patterns"])


def test_the_walk_needs_no_credential(tmp_path, no_network, monkeypatch):
    """Not one of the three secrets is set. The walk must not notice.

    A walk that reads a token from the environment when one happens to be
    there would pass on the author's machine and fail on a fresh clone, which
    is the opposite of what a demonstration is for.
    """
    for name in ("META_APP_ID", "META_APP_SECRET", "META_ACCESS_TOKEN",
                 "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    walk_tool.walk(tmp_path / "demo", walk_tool.Log(on=False))


def test_the_walk_writes_only_under_out(tmp_path, no_network):
    """The committed research/ and queue/ are not touched.

    Recorded by mtime rather than by content: a write that happened to
    reproduce the same bytes is still a write into the repository, and the
    next `git status` would be the first anyone heard of it.
    """
    watched = sorted(
        path for path in (ROOT / "research").rglob("*")
        if path.is_file()
    ) + sorted(
        path for path in (ROOT / "queue").rglob("*") if path.is_file()
    )
    assert watched, "nothing to watch; this test has lost its subject"
    before = {path: path.stat().st_mtime_ns for path in watched}

    walk_tool.walk(tmp_path / "demo", walk_tool.Log(on=False))

    after = {path: path.stat().st_mtime_ns for path in watched}
    assert after == before
    assert sorted(p.name for p in (ROOT / "research" / "corpus").iterdir()) == [
        ".gitkeep"
    ], "the walk wrote into the committed corpus"


def test_the_walk_leaves_the_artifacts_a_human_can_open(tmp_path, no_network):
    out = tmp_path / "demo"
    walk_tool.walk(out, walk_tool.Log(on=False))

    expected = {
        "research/patterns.json",
        "research/concepts.json",
        "research/selection.json",
        "research/measurements.json",
        "queue/launched/payroll-bureaus.json",
    }
    written = {
        str(path.relative_to(out)) for path in out.rglob("*.json")
    }
    assert expected <= written, sorted(expected - written)

    # Six corpus records: four competitors analysed, two of our own fed back.
    corpus_files = sorted((out / "research" / "corpus").glob("*.json"))
    assert len(corpus_files) == 6

    # Every file is JSON a person can read, indented, ending in a newline.
    for path in sorted(out.rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n"), path
        json.loads(text)


def test_a_second_walk_replaces_the_first(tmp_path, no_network):
    """Re-running is the normal case, so it must not need a manual delete -
    and must not leave the previous run's files mixed in with this one's."""
    out = tmp_path / "demo"
    walk_tool.walk(out, walk_tool.Log(on=False))
    (out / "research" / "corpus" / "meta-ad-leftover.json").write_text(
        "{}\n", encoding="utf-8"
    )

    walk_tool.walk(out, walk_tool.Log(on=False))

    assert not (out / "research" / "corpus" / "meta-ad-leftover.json").exists()


def test_a_directory_the_tool_did_not_write_is_refused(tmp_path, no_network):
    """--out pointed at somebody's work is a refusal, not an rmtree.

    The tool's first act on an existing --out is to delete it. The marker file
    is the only thing standing between that and a mistyped path, so the
    refusal is tested rather than assumed.
    """
    out = tmp_path / "not-mine"
    out.mkdir()
    precious = out / "thesis.txt"
    precious.write_text("eight months of work\n", encoding="utf-8")

    with pytest.raises(walk_tool.Refused) as refusal:
        walk_tool.walk(out, walk_tool.Log(on=False))

    assert precious.read_text(encoding="utf-8") == "eight months of work\n"
    assert "--out" in str(refusal.value)


def test_refusal_is_one_line_and_exit_2(tmp_path, no_network, capsys):
    out = tmp_path / "not-mine"
    out.mkdir()

    code = walk_tool.main(["--out", str(out), "--quiet"])

    assert code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("refused: ")
    assert len(captured.err.strip().splitlines()) == 1


def test_quiet_writes_the_files_and_prints_nothing(tmp_path, no_network, capsys):
    out = tmp_path / "demo"

    code = walk_tool.main(["--out", str(out), "--quiet"])

    assert code == 0
    assert capsys.readouterr().out == ""
    assert (out / "research" / "patterns.json").exists()


def test_the_narration_names_every_stage(tmp_path, no_network, capsys):
    """Ten stages, numbered, in order. The narration is the deliverable here -
    a walk that ran silently would leave a reader with twelve JSON files and
    no idea which one to open first."""
    walk_tool.main(["--out", str(tmp_path / "demo")])

    printed = capsys.readouterr().out
    for name in ("DISCOVER", "ANALYSE", "LEARN", "CONCEPTS", "SCORE",
                 "WRITE+GATE", "APPROVE", "MEASURE", "FEEDBACK", "CLOSED"):
        assert name in printed, name
    # ...and it ends by saying which three files are the analysis.
    assert "patterns.json" in printed and "selection.json" in printed
