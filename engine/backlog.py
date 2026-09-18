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
        match = ROW_RE.match(line.strip())
        if not match:
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
