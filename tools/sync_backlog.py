"""python tools/sync_backlog.py [--source PATH] [--check]

Copy reel-engine's segment table into this repository's `queue/backlog.md`.

THE DESIGN DECISION, and why this file exists at all: the ICP is one ranked
list and `reel-engine` owns it, so the honest thing would be to read
`../reel-engine/queue/backlog.md` straight from the sibling checkout - which is
what `docs/AD-RESEARCH-SCOPE.md` section 3.6 first proposed. But the research
cron runs unattended, and a sibling checkout inside GitHub Actions costs a
second repository's token (`REEL_ENGINE_TOKEN`) just to read one markdown
table. A free, read-only sweep should not be able to fail on a credential it
has no other use for. So the table is COPIED, the copy is committed, and this
tool is what keeps the copy honest: `--check` in CI turns drift into a red run
with a diff, and a plain run rewrites the copy in one command.

What is copied is exactly what `engine/backlog.py` would read: every
pipe-delimited row of the source, anywhere in the file, in order - the header
row, the separator and the data rows. That is not a coincidence; it is the
parser's own definition of "the table" (`backlog.ROW_RE`), reused here so the
two can never disagree about what a row is. The rows land verbatim between the
`<!-- backlog:begin -->` and `<!-- backlog:end -->` markers of the local file.
Nothing outside the markers is touched: the local prose above the table is
this repository's own, and says why the copy exists.

Refuse rather than guess, and name the fix:

- a source that is not there is a one-line refusal naming the path and
  `--source`, not a traceback from `read_text`;
- a source table `engine/backlog.py` cannot parse is refused BEFORE anything
  is written, with the parser's own message naming the row - this tool never
  commits a table the engine would then choke on;
- a source row that lost one of its two pipes is refused by line HERE, because
  the parser does not refuse it: it skips the line and the table arrives a
  segment short with nothing raised. This is a stopgap on the inbound path,
  not the fix; the fix is a guard in `engine/backlog.py`, which cannot land on
  this side alone because that file is a byte-for-byte copy of the sibling's;
- a local file with no markers, two of them, or the end before the begin, is
  refused with the marker names;
- a pipe-delimited row OUTSIDE the markers is refused by line, because the
  parser reads every such row as data and no rewrite of the block would make
  the local table equal the source.

Exit codes: 0 in sync (or just synced), 1 drift found under `--check` (a
diff is printed, nothing is written), 2 refused (nothing is written).
"""
from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import backlog  # noqa: E402

# The sibling checkout, exactly where README.md already expects
# `../outreach-engine` and where build.yml checks out `Dasvydo/reel-engine`.
DEFAULT_SOURCE = ROOT / ".." / "reel-engine" / "queue" / "backlog.md"
LOCAL = backlog.DEFAULT_PATH

BEGIN = "<!-- backlog:begin -->"
END = "<!-- backlog:end -->"


class SyncError(RuntimeError):
    """Operator's to fix; printed as one line and exit 2, never a traceback."""


def _display(path: Path) -> str:
    """The path as a human would type it: relative to ROOT when it is nearby.

    `../reel-engine/queue/backlog.md` and `queue/backlog.md` read better in a
    message than two absolute paths that differ in one directory; a path
    somewhere else entirely (a tmp copy) is shown in full.
    """
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(ROOT.parent)
    except ValueError:
        return str(path)
    return os.path.relpath(resolved, ROOT)


def is_row(line: str) -> bool:
    """A row is whatever `engine/backlog.py` would parse as one."""
    return bool(backlog.ROW_RE.match(line.strip()))


def half_piped(line: str) -> bool:
    """A line one pipe short of a row: anchored at one end, not both.

    MEASURED, on a four-row table with the rank-2 row's trailing pipe removed:
    `backlog.load` returned three segments and raised nothing - `ROW_RE` fails,
    the parser's loop skips the line, and the backlog silently shrinks. Every
    other one-character corruption of a row (a cell added, a cell dropped, a
    non-integer rank) raises by name. Dropping one `|` is the single realistic
    hand-edit that does not, which is why this tool looks for it by hand.

    Prose is untouched: a sentence carrying a `code | span` is anchored at
    neither end, and four pipes are required before a line is even considered.
    """
    stripped = line.strip()
    if is_row(stripped) or stripped.count("|") < 4:
        return False
    return stripped.startswith("|") or stripped.endswith("|")


def source_rows(source: Path) -> list[str]:
    """Every table line of the source, verbatim and in order.

    Validated through `backlog.load` first: a malformed row, a missing table
    or a duplicate id is refused here, with the parser's own message, rather
    than being copied into this repository and discovered by the next cron.
    A row that lost one of its two pipes is refused first and separately,
    because `backlog.load` is precisely the check that stays quiet about it.
    """
    source = Path(source)
    if not source.is_file():
        raise SyncError(
            f"no reel-engine backlog at {_display(source)}; clone "
            f"Dasvydo/reel-engine beside this checkout (../reel-engine) or "
            f"point --source at its queue/backlog.md"
        )
    lines = source.read_text(encoding="utf-8").splitlines()
    half = [str(i + 1) for i, line in enumerate(lines) if half_piped(line)]
    if half:
        raise SyncError(
            f"{_display(source)} has a row with only one of its two pipes at "
            f"line {', '.join(half)}; engine/backlog.py skips such a line "
            f"instead of raising, so the table would arrive here a segment "
            f"short - restore the missing | in reel-engine"
        )
    try:
        backlog.load(source)
    except ValueError as exc:
        raise SyncError(
            f"{_display(source)} is not a table engine/backlog.py can read "
            f"({exc}); fix the row in reel-engine, nothing was written here"
        ) from exc
    return [line for line in lines if is_row(line)]


def locate_block(lines: list[str], *, name: str) -> tuple[int, int]:
    """Indices of the begin and end marker lines, or a refusal naming them."""
    begins = [i for i, line in enumerate(lines) if line.strip() == BEGIN]
    ends = [i for i, line in enumerate(lines) if line.strip() == END]
    if len(begins) != 1 or len(ends) != 1:
        raise SyncError(
            f"{name} must contain exactly one {BEGIN} and one {END} marker "
            f"(found {len(begins)} and {len(ends)}); put them on their own "
            f"lines around the table"
        )
    begin, end = begins[0], ends[0]
    if end < begin:
        raise SyncError(
            f"{name} has {END} (line {end + 1}) before {BEGIN} "
            f"(line {begin + 1}); swap them"
        )
    strays = [i for i, line in enumerate(lines)
              if is_row(line) and not begin < i < end]
    if strays:
        where = ", ".join(str(i + 1) for i in strays)
        raise SyncError(
            f"{name} has a pipe-delimited row outside the markers at line "
            f"{where}; engine/backlog.py parses every such row as data, so "
            f"rewrite it as prose or move it inside the markers"
        )
    return begin, end


def sync(source: Path, target: Path, *, check: bool = False, out=None) -> int:
    """Make the block in `target` equal the table in `source`.

    Returns the exit code documented in the module docstring. Raises
    SyncError for anything that stops the comparison being made at all.
    """
    out = out if out is not None else sys.stdout
    source, target = Path(source), Path(target)
    rows = source_rows(source)

    if not target.is_file():
        raise SyncError(
            f"no local backlog at {_display(target)}; restore it from git "
            f"(it is committed) before syncing"
        )
    # newline="" keeps the target's own line endings; `read_text` would
    # collapse CRLF to LF on the way in and the rejoin would write LF back
    # over the whole file, prose included.
    with target.open(encoding="utf-8", newline="") as handle:
        text = handle.read()
    lines = text.splitlines()
    kept = text.splitlines(keepends=True)
    begin, end = locate_block(lines, name=_display(target))
    current = lines[begin + 1:end]

    # Counted by the parser, not by arithmetic on the layout. MEASURED: a
    # source with no header and no separator (both optional to
    # `engine/backlog.py`, which filters them by content) reported "3
    # segments" and wrote 5; a source carrying a second table reported 9 and
    # wrote 7; a single row with no header reported -1.
    segments = len(backlog.load(source))
    if current == rows:
        print(f"{_display(target)} is in sync with {_display(source)} "
              f"({segments} segments); nothing written", file=out)
        return 0

    if check:
        diff = difflib.unified_diff(
            current, rows,
            fromfile=_display(target), tofile=_display(source), lineterm="",
        )
        for line in diff:
            print(line, file=out)
        print(f"{_display(target)} drifts from {_display(source)}; run "
              f"python tools/sync_backlog.py to rewrite the block "
              f"(nothing written)", file=out)
        return 1

    # Spliced on the lines as they arrived, endings included, so every byte
    # outside the block survives the write. MEASURED: the old
    # splitlines/"\n".join round-trip rewrote 11 of 12 line endings in a CRLF
    # copy of this file, 3 of them in the prose the docstring promises not to
    # touch. The inserted rows take the begin marker's own ending, so they
    # match the block they are joining rather than a guess about the file.
    eol = kept[begin][len(lines[begin]):] or "\n"
    new_text = ("".join(kept[:begin + 1])
                + "".join(row + eol for row in rows)
                + "".join(kept[end:]))
    with target.open("w", encoding="utf-8", newline="") as handle:
        handle.write(new_text)
    print(f"synced {segments} segments ({len(rows)} table lines) from "
          f"{_display(source)} into {_display(target)}", file=out)
    return 0


def main(argv: list[str] | None = None, *, target: Path | None = None,
         out=None, err=None) -> int:
    """The CLI. `target`, `out` and `err` are injection points for tests;
    the command line itself is exactly `[--source PATH] [--check]`."""
    parser = argparse.ArgumentParser(
        prog="python tools/sync_backlog.py",
        description="Copy reel-engine's segment table into queue/backlog.md.",
    )
    parser.add_argument(
        "--source", type=Path, default=DEFAULT_SOURCE, metavar="PATH",
        help="reel-engine's queue/backlog.md "
             "(default: ../reel-engine/queue/backlog.md beside this checkout)",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="exit 1 and print a diff when the two tables differ; write nothing",
    )
    args = parser.parse_args(argv)
    err = err if err is not None else sys.stderr
    try:
        return sync(args.source, target or LOCAL, check=args.check, out=out)
    except SyncError as exc:
        if out is None:
            sys.stdout.flush()
        print(f"refused: {exc}", file=err)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
