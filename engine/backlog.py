"""The segment backlog: a ranked markdown table, read as data.

A backlog of ~100 hand-curated segments changing monthly is a file, not a
database. Its directory is its status and git history is its audit log.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "queue" / "backlog.md"

# A table row: leading pipe, five cells, trailing pipe. Separator rows (---)
# and the header are filtered out by the rank cell failing to be an integer.
ROW_RE = re.compile(r"^\|(.+)\|$")

# A row anchored at one end only. Checked so it can be REFUSED rather than
# skipped - see load(). The leading-pipe case needs a trailing non-pipe and
# vice versa, so a well-formed row never matches this.
HALF_PIPED_RE = re.compile(r"^\|.*[^|]$|^[^|].*\|$")


@dataclass(frozen=True)
class Segment:
    rank: int
    id: str
    trade: str
    questions: tuple[str, str, str]
    note: str


def load(path: Path | None = None) -> list[Segment]:
    path = Path(path) if path else DEFAULT_PATH
    if not path.exists():
        raise FileNotFoundError(f"no backlog at {path}")

    segments: list[Segment] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        match = ROW_RE.match(stripped)
        if not match:
            # A row anchored at ONE end is a typo in a table, not prose, and
            # dropping it silently shrinks the backlog with nothing said.
            # MEASURED 2026-09-19: delete the trailing pipe from rank 1 and
            # load() returns four segments instead of five, next_unused()
            # hands out rank 2, and no error is raised anywhere. The file's
            # own banner promises "a malformed one raises", so it must.
            #
            # Prose is unaffected: a sentence does not begin or end with a
            # pipe. A fenced code block CAN, which is why the refusal names
            # the line and says how to neutralise it.
            if HALF_PIPED_RE.match(stripped):
                raise ValueError(
                    f"malformed backlog row: {line!r} (a table row needs a "
                    f"pipe at BOTH ends; this one has exactly one, so it "
                    f"would be skipped silently and the backlog would be one "
                    f"segment shorter than it looks). Add the missing pipe, "
                    f"or if this line is not a table row, indent it or move "
                    f"it out of the file - every pipe-delimited row here is "
                    f"parsed as data, anywhere in the file."
                )
            continue
        cells = [c.strip() for c in match.group(1).split("|")]

        # Check if this is a header row (first cell is "rank")
        if cells and cells[0] == "rank":
            continue

        # Check if this is a separator row (all dashes/colons)
        if cells and all(c.replace("-", "").replace(":", "") == "" for c in cells):
            continue

        # At this point, if it has the pipe structure, it must be a valid data row
        if len(cells) != 5:
            raise ValueError(
                f"malformed backlog row: {line!r} (expected 5 cells, got {len(cells)})"
            )

        try:
            rank = int(cells[0])
        except ValueError:
            raise ValueError(
                f"malformed backlog row: {line!r} (rank must be an integer, got {cells[0]!r})"
            )

        # The id is how every other file names this segment: a queue job is
        # queue/<stage>/<id>.json, a concept cites it, an approval issue
        # carries it in its marker. A blank one was constructed into a Segment
        # and handed straight to next_unused() as the top-ranked candidate,
        # which then proposes a reel whose job file is named ".json".
        if not cells[1]:
            raise ValueError(
                f"malformed backlog row: {line!r} (the id cell is empty, and "
                f"the id is what names this segment's job file, its concept "
                f"and its approval issue). Give it a short slug."
            )

        questions = tuple(q.strip() for q in cells[3].split(",") if q.strip())
        if len(questions) != 3:
            raise ValueError(
                f"segment {cells[1]!r} lists {len(questions)} questions; "
                f"the template requires exactly 3 recurring tags"
            )
        segments.append(Segment(rank, cells[1], cells[2], questions, cells[4]))

    if not segments:
        raise ValueError(f"{path} has no segment rows")

    ids = [s.id for s in segments]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate segment ids: {', '.join(sorted(duplicates))}")

    return sorted(segments, key=lambda s: s.rank)


def next_unused(segments: list[Segment], used: set[str]) -> Segment:
    for segment in segments:
        if segment.id not in used:
            return segment
    raise LookupError(
        f"every segment in the backlog is used ({len(segments)} total); "
        f"add a row to queue/backlog.md"
    )
