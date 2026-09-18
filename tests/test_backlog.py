"""engine/backlog.py (a verbatim copy of reel-engine's) and tools/sync_backlog.py.

The parser tests are reel-engine's own, carried across unchanged: the module
is a byte-for-byte copy, so its tests should be too. The sync tests are new.
Every test is offline; the two that read the sibling checkout skip, never
fail, when it is absent.
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

from engine.backlog import DEFAULT_PATH, ROOT, Segment, load, next_unused
from tools import sync_backlog
from tools.sync_backlog import BEGIN, END, DEFAULT_SOURCE, SyncError, main, sync

SAMPLE = """# Segment backlog

Ranked. Edit by hand. One table row per segment.

| rank | id | trade | questions | note |
|---|---|---|---|---|
| 1 | insurance-brokers | Insurance brokers | certificate, renewal, cover | worked example |
| 2 | freight-forwarders | Freight forwarders | docs, eta, quote | shipped |
| 3 | letting-agents | Letting agents | epc, deposit, viewing | untested |
"""

SIBLING_MODULE = ROOT.parent / "reel-engine" / "engine" / "backlog.py"
needs_sibling = pytest.mark.skipif(
    not DEFAULT_SOURCE.is_file(), reason="../reel-engine is not checked out"
)


@pytest.fixture
def backlog(tmp_path):
    p = tmp_path / "backlog.md"
    p.write_text(SAMPLE, encoding="utf-8")
    return p


# --- the parser: reel-engine/tests/test_backlog.py, unchanged --------------


def test_load_parses_every_row(backlog):
    assert len(load(backlog)) == 3


def test_load_returns_rank_ascending(backlog):
    assert [s.rank for s in load(backlog)] == [1, 2, 3]


def test_load_sorts_by_rank_whatever_the_file_order(tmp_path):
    p = tmp_path / "shuffled.md"
    p.write_text(
        SAMPLE.replace("| 1 | insurance", "| 3 | insurance")
        .replace("| 3 | letting", "| 1 | letting"),
        encoding="utf-8",
    )
    assert [s.id for s in load(p)] == [
        "letting-agents", "freight-forwarders", "insurance-brokers",
    ]


def test_questions_is_a_three_tuple(backlog):
    assert load(backlog)[0].questions == ("certificate", "renewal", "cover")


def test_a_segment_without_exactly_three_questions_is_rejected(tmp_path):
    p = tmp_path / "bad.md"
    p.write_text(
        SAMPLE.replace("certificate, renewal, cover", "certificate, renewal"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exactly 3"):
        load(p)


def test_next_unused_skips_used_ids(backlog):
    segments = load(backlog)
    assert next_unused(segments, {"insurance-brokers"}).id == "freight-forwarders"


def test_next_unused_raises_when_everything_is_used(backlog):
    segments = load(backlog)
    with pytest.raises(LookupError):
        next_unused(segments, {s.id for s in segments})


def test_typo_in_rank_raises_with_line_text(tmp_path):
    p = tmp_path / "bad.md"
    p.write_text(
        SAMPLE.replace("| 1 |", "| 1a |"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="malformed backlog row") as excinfo:
        load(p)
    assert "| 1a |" in str(excinfo.value)


def test_wrong_cell_count_raises_with_line_text(tmp_path):
    p = tmp_path / "bad.md"
    p.write_text(
        SAMPLE.replace("insurance-brokers", "insurance-brokers | extra"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="malformed backlog row") as excinfo:
        load(p)
    assert "insurance-brokers | extra" in str(excinfo.value)


def test_duplicate_segment_ids_are_rejected(tmp_path):
    """A repeated id makes used_ids() lie in both directions.

    One job would mark both rows used - silently dropping a segment that was
    never written - while next_unused() would keep returning whichever row
    sorted first, re-picking a slot already spoken for.
    """
    p = tmp_path / "dupe.md"
    p.write_text(
        SAMPLE
        + "| 4 | letting-agents | Letting agents, again | epc, deposit, viewing | oops |\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate segment ids") as excinfo:
        load(p)
    assert "letting-agents" in str(excinfo.value)


def test_a_duplicate_is_named_once_even_when_it_repeats_three_times(tmp_path):
    """The report is built from a set, so the id must appear once, not per row."""
    extra = "| {rank} | letting-agents | Letting agents | epc, deposit, viewing | oops |\n"
    p = tmp_path / "dupe3.md"
    p.write_text(SAMPLE + extra.format(rank=4) + extra.format(rank=5), encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        load(p)
    assert str(excinfo.value).count("letting-agents") == 1


def test_a_missing_backlog_is_a_named_file_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="no backlog at"):
        load(tmp_path / "absent.md")


def test_a_file_with_no_rows_is_refused(tmp_path):
    p = tmp_path / "prose.md"
    p.write_text("# Nothing but prose\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no segment rows"):
        load(p)


# --- the committed copy ------------------------------------------------------


def test_the_committed_backlog_is_the_five_ranked_segments():
    """The table in this repository is reel-engine's table as of the copy."""
    segments = load(DEFAULT_PATH)
    assert [s.id for s in segments] == [
        "accountants", "payroll-bureaus", "bookkeepers", "admin-firms", "audit-firms",
    ]
    assert [s.rank for s in segments] == [1, 2, 3, 4, 5]
    assert segments[1] == Segment(
        2, "payroll-bureaus", "Payroll bureaus", ("payslip", "holiday", "tax-code"),
        "strongest lookup profile of the set - all three are a record fetch, "
        "none is an opinion",
    )


def test_the_committed_backlog_carries_the_markers_and_the_warning():
    text = DEFAULT_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines.count(BEGIN) == 1 and lines.count(END) == 1
    assert lines.index(BEGIN) < lines.index(END)
    assert "Every pipe-delimited row in this file is parsed as data" in text
    assert "copy of `reel-engine/queue/backlog.md`" in text
    assert "token" in text  # the header says WHY it is a copy
    # the tool's own definition of the table: every row sits inside the block
    for i, line in enumerate(lines):
        if sync_backlog.is_row(line):
            assert lines.index(BEGIN) < i < lines.index(END), line


def test_default_source_is_the_sibling_checkout():
    assert DEFAULT_SOURCE.resolve() == (
        ROOT.parent / "reel-engine" / "queue" / "backlog.md"
    ).resolve()
    assert sync_backlog.LOCAL == DEFAULT_PATH == ROOT / "queue" / "backlog.md"


@needs_sibling
def test_the_committed_table_matches_the_sibling_exactly(capsys):
    """Run the real check against the real sibling: no drift as of this commit."""
    assert main(["--check"]) == 0
    assert "in sync" in capsys.readouterr().out
    assert load(DEFAULT_PATH) == load(DEFAULT_SOURCE)


@needs_sibling
def test_the_module_is_a_verbatim_copy_of_reel_engines():
    """CONTRACTS.md: 'a verbatim copy'. Byte for byte, or the contract is broken."""
    ours = (ROOT / "engine" / "backlog.py").read_bytes()
    assert ours == SIBLING_MODULE.read_bytes()


# --- tools/sync_backlog.py ---------------------------------------------------

LOCAL_TEMPLATE = """# Segment backlog (a copy)

Prose above the block, with a pipe in `code | span` that is not a row.

<!-- backlog:begin -->
| rank | id | trade | questions | note |
|---|---|---|---|---|
| 1 | insurance-brokers | Insurance brokers | certificate, renewal, cover | stale |
<!-- backlog:end -->

Prose below the block. Also untouched.
"""

SOURCE_TEXT = """# Segment backlog

Ranked, hand-edited.

> Every pipe-delimited row in this file is parsed as data.

## ICP lock

| rank | id | trade | questions | note |
|---|---|---|---|---|
| 1 | accountants | Accountants | deadline, receipts, mileage | reframed |
| 2 | payroll-bureaus | Payroll bureaus | payslip, holiday, tax-code | strongest |

## Parked

- **letting-agents** - prose, not a row.
"""

SOURCE_ROWS = [
    "| rank | id | trade | questions | note |",
    "|---|---|---|---|---|",
    "| 1 | accountants | Accountants | deadline, receipts, mileage | reframed |",
    "| 2 | payroll-bureaus | Payroll bureaus | payslip, holiday, tax-code | strongest |",
]


@pytest.fixture
def local(tmp_path):
    p = tmp_path / "queue" / "backlog.md"
    p.parent.mkdir()
    p.write_text(LOCAL_TEMPLATE, encoding="utf-8")
    return p


@pytest.fixture
def source(tmp_path):
    p = tmp_path / "reel-engine" / "queue" / "backlog.md"
    p.parent.mkdir(parents=True)
    p.write_text(SOURCE_TEXT, encoding="utf-8")
    return p


def _block(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[lines.index(BEGIN) + 1:lines.index(END)]


def test_source_rows_is_exactly_what_the_parser_would_read(source):
    assert sync_backlog.source_rows(source) == SOURCE_ROWS


def test_sync_replaces_the_block_and_nothing_else(local, source):
    out = io.StringIO()
    assert main(["--source", str(source)], target=local, out=out) == 0
    assert "synced 2 segments (4 table lines)" in out.getvalue()

    text = local.read_text(encoding="utf-8")
    head, _, rest = LOCAL_TEMPLATE.partition(BEGIN + "\n")
    _, _, tail = rest.partition(END + "\n")
    assert text == head + BEGIN + "\n" + "\n".join(SOURCE_ROWS) + "\n" + END + "\n" + tail
    assert _block(local) == SOURCE_ROWS
    assert text.endswith("\n")
    # and the result is a backlog engine/backlog.py reads as the source
    assert load(local) == load(source)


def test_sync_is_idempotent_and_writes_nothing_when_in_sync(local, source):
    assert main(["--source", str(source)], target=local, out=io.StringIO()) == 0
    before = local.read_bytes()
    stamp = local.stat().st_mtime_ns
    out = io.StringIO()
    assert main(["--source", str(source)], target=local, out=out) == 0
    assert "in sync" in out.getvalue() and "nothing written" in out.getvalue()
    assert local.read_bytes() == before
    assert local.stat().st_mtime_ns == stamp


def test_check_detects_drift_prints_a_diff_and_writes_nothing(local, source):
    before = local.read_bytes()
    out = io.StringIO()
    assert main(["--source", str(source), "--check"], target=local, out=out) == 1
    printed = out.getvalue()
    assert "-| 1 | insurance-brokers |" in printed
    assert "+| 1 | accountants |" in printed
    assert "+| 2 | payroll-bureaus |" in printed
    assert "python tools/sync_backlog.py" in printed  # the fix, by name
    assert local.read_bytes() == before


def test_check_exits_zero_when_in_sync(local, source):
    assert sync(source, local, out=io.StringIO()) == 0
    out = io.StringIO()
    assert main(["--source", str(source), "--check"], target=local, out=out) == 0
    assert "in sync" in out.getvalue()


def test_a_changed_note_is_drift_too(local, source):
    """The block is compared verbatim: a note edited on one side is drift."""
    sync(source, local, out=io.StringIO())
    source.write_text(SOURCE_TEXT.replace("| reframed |", "| reworded |"), encoding="utf-8")
    out = io.StringIO()
    assert main(["--source", str(source), "--check"], target=local, out=out) == 1
    assert "+| 1 | accountants | Accountants | deadline, receipts, mileage | reworded |" \
        in out.getvalue()


def test_missing_source_refuses_by_name(local, tmp_path):
    absent = tmp_path / "elsewhere" / "backlog.md"
    before = local.read_bytes()
    err = io.StringIO()
    code = main(["--source", str(absent)], target=local, out=io.StringIO(), err=err)
    assert code == 2
    message = err.getvalue()
    assert message.startswith("refused: no reel-engine backlog at ")
    assert str(absent) in message
    assert "--source" in message and "../reel-engine" in message
    assert local.read_bytes() == before


def test_missing_source_under_check_is_also_a_refusal_not_drift(local, tmp_path):
    err = io.StringIO()
    code = main(["--source", str(tmp_path / "nope.md"), "--check"],
                target=local, out=io.StringIO(), err=err)
    assert code == 2
    assert "nope.md" in err.getvalue()


def test_missing_source_from_the_command_line_is_one_line_not_a_traceback(tmp_path):
    """The process-level promise: exit 2 and one line on stderr, nothing written.

    Runs the script the way the cron would, with --check so the real
    queue/backlog.md is only ever read. Offline: a path that does not exist.
    """
    absent = tmp_path / "missing" / "backlog.md"
    before = DEFAULT_PATH.read_bytes()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "sync_backlog.py"),
         "--source", str(absent), "--check"],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    assert proc.stderr.strip().startswith("refused: no reel-engine backlog at")
    assert proc.stderr.count("\n") == 1
    assert DEFAULT_PATH.read_bytes() == before


def test_a_malformed_source_is_refused_before_anything_is_written(local, source):
    source.write_text(
        SOURCE_TEXT.replace("deadline, receipts, mileage", "deadline, receipts"),
        encoding="utf-8",
    )
    before = local.read_bytes()
    err = io.StringIO()
    assert main(["--source", str(source)], target=local, out=io.StringIO(), err=err) == 2
    message = err.getvalue()
    assert "engine/backlog.py can read" in message
    assert "accountants" in message and "exactly 3" in message  # the parser's own words
    assert "nothing was written" in message
    assert local.read_bytes() == before


def test_a_source_with_a_duplicate_id_is_refused(local, source):
    source.write_text(
        SOURCE_TEXT + "| 3 | accountants | Accountants | a, b, c | again |\n",
        encoding="utf-8",
    )
    with pytest.raises(SyncError, match="duplicate segment ids"):
        sync(source, local, out=io.StringIO())


def test_a_local_file_without_markers_is_refused(tmp_path, source):
    bare = tmp_path / "bare.md"
    bare.write_text(SAMPLE, encoding="utf-8")
    before = bare.read_bytes()
    with pytest.raises(SyncError) as excinfo:
        sync(source, bare, out=io.StringIO())
    assert BEGIN in str(excinfo.value) and END in str(excinfo.value)
    assert "found 0 and 0" in str(excinfo.value)
    assert bare.read_bytes() == before


def test_two_begin_markers_are_refused(local, source):
    local.write_text(LOCAL_TEMPLATE.replace(BEGIN, BEGIN + "\n" + BEGIN), encoding="utf-8")
    with pytest.raises(SyncError, match="found 2 and 1"):
        sync(source, local, out=io.StringIO())


def test_end_before_begin_is_refused(local, source):
    swapped = LOCAL_TEMPLATE.replace(BEGIN, "@@").replace(END, BEGIN).replace("@@", END)
    local.write_text(swapped, encoding="utf-8")
    with pytest.raises(SyncError, match="before"):
        sync(source, local, out=io.StringIO())


def test_a_row_outside_the_markers_is_refused_by_line(local, source):
    """The parser reads every pipe row anywhere, so a stray one outside the
    block would make the local table differ from the source however the block
    is rewritten. Named by line number, in both modes, nothing written."""
    text = LOCAL_TEMPLATE.replace(
        "Prose below the block.",
        "| 9 | stray | Stray | a, b, c | outside |\nProse below the block.",
    )
    local.write_text(text, encoding="utf-8")
    before = local.read_bytes()
    stray_line = text.splitlines().index("| 9 | stray | Stray | a, b, c | outside |") + 1
    for flags in ([], ["--check"]):
        err = io.StringIO()
        code = main(["--source", str(source), *flags], target=local,
                    out=io.StringIO(), err=err)
        assert code == 2
        assert f"outside the markers at line {stray_line}" in err.getvalue()
    assert local.read_bytes() == before


def test_a_missing_local_file_is_refused_by_name(tmp_path, source):
    absent = tmp_path / "gone" / "backlog.md"
    with pytest.raises(SyncError, match="no local backlog at"):
        sync(source, absent, out=io.StringIO())


def test_source_rows_are_copied_verbatim_including_trailing_spaces(local, tmp_path):
    """A row is matched on its stripped form but copied as written."""
    src = tmp_path / "spaced.md"
    src.write_text(
        "| rank | id | trade | questions | note |  \n"
        "|---|---|---|---|---|\n"
        "| 1 | accountants | Accountants | a, b, c | note |\n",
        encoding="utf-8",
    )
    assert sync(src, local, out=io.StringIO()) == 0
    assert _block(local)[0] == "| rank | id | trade | questions | note |  "


def test_the_cli_surface_is_source_and_check_only():
    out = io.StringIO()
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"], out=out)
    assert excinfo.value.code == 0
