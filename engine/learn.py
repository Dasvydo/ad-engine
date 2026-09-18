"""python -m engine.learn [--corpus DIR] [--origin ORIGIN] [--out PATH] [--stdout]

Reusable patterns from the analysed ad corpus: what repeats, counted.

Every number in research/patterns.json is arithmetic over the corpus. Nothing
in this module calls a model and nothing it imports could reach one, which
tests/test_learn.py proves by AST-parsing this file. That is the free path -
counting costs nothing - and it is also the honest one: a pattern here is a
count of ads, not a summary of what a model thinks it just read. Asking a
model to describe its own analyses would produce confident prose with nothing
underneath it, and everything downstream needs the opposite - a hook that
traces back to named ads with a real number of days an advertiser's own money
kept them running.

## What a pattern is

One repeated device, the ids of the ads it was taken from, and how those ads
performed. A device supported by fewer than MIN_SUPPORT ads is left out
entirely: one ad is an anecdote, and the point of this step is to find what
more than one ad does.

Nine kinds, one per family of thing a record holds:

  hook       the opening device, as the analysis named it ("question")
  length     the copy's word count, banded
  structure  the section order, and each section's position in it
  cta        the call-to-action type
  offer      what the ad offers ("free-trial", "demo", "guarantee", "none")
  proof      what the ad shows for proof ("testimonial", "number", "none")
  objection  what the copy answers
  longevity  how many days the ad ran, banded
  ctr        our own ads' click-through rate, banded

Where a kind holds more than one family the device carries a prefix, so two
families inside one kind cannot collide: "shape:hook>problem>cta" and
"section:hook" under structure. The banded kinds carry one too -
"words:20-49", "days:28-59", "ctr-pct:0.5-0.9" - because a band on its own
would be a bare pair of numbers in a file that holds three different units of
them. The hook, cta, offer, proof and objection kinds are not banded at all,
so their device is the thing itself - a slug for the four that come from a
taxonomy, and the objection's own normalised wording for the one that does
not. "none" is a device like any other under offer and proof: two ads that
make no offer are a countable fact about the market, not an absence.

Patterns are derivable per origin as well as over everything: `origin=`
narrows the corpus before any counting, because a hook that works for an
accounting firm's own ads is not automatically one this repo is allowed to
claim.

## Longevity and reach, and which of them a description quotes

The Ad Library exposes no view count and no click for a stranger's ad. What
it does expose (docs/AD-RESEARCH-SCOPE.md 2.3) is how long the ad ran and how
many EU users it reached, and of those two, days running is the primary
signal: advertisers kill what does not convert, so an ad still running after
eight weeks is the one number in the archive that somebody's own money has
voted on. Reach is spend-correlated and weaker on its own - a launch can buy
reach for a week. So every pattern carries a median of each, and the ad a
description quotes is the longest-running supporter, reach breaking the tie.

## Click-through, and why a null is not a zero

analysis.own_metrics.ctr is the one measured thing in a record this repo wrote
itself: the click-through rate of an ad we launched, read off our own ad
account by engine.measure and carried into the record by engine.feedback. It
is the strongest evidence the loop will ever hold - stronger than anything it
can read about a competitor - and the ctr kind is where it is counted. The
reading is a percentage, as the Marketing API reports it (C6: 51 clicks over
4100 impressions is 1.24), so the bands are in percentage points.

Most records carry no own_metrics at all, and that absence is silent rather
than reported: a competitor's click-through is not ours to read, and a line
per unmeasurable ad per run is not a report, it is noise. A reading that is
present but unreadable IS reported, by id and by field.

Either way the ad contributes no ctr band. A null is not a zero here: an
absent reading banded as 0.0 would land in the bottom band, count toward its
support, drag its median, and be indistinguishable from an ad nobody clicked.

## Determinism

A weekly workflow commits this file, so a generator that reordered anything
would produce a diff every run saying nothing changed. Three rules prevent it:

  - Records are sorted by id on the way in, evidence is sorted, and patterns
    are ordered by (kind, device). Nothing is emitted in the order a dict or a
    set happened to yield it.
  - Ids come from that sorted order, so q03 keeps meaning the same pattern for
    as long as the pattern exists. Ordering by support instead would renumber
    the whole file whenever one new ad changed the ranking, and last week's
    concept would cite a pattern it was never derived from.
  - generated_at is the newest fetched_at in the corpus, NOT the clock. This
    file describes a corpus; regenerating it from an unchanged corpus has
    nothing new to say and should produce the same bytes.

## Defensive reads

engine.corpus validates that metrics.days_running exists, not that it is a
number - a record can carry "a while" and still be a valid schema-1 record.
So every leaf read here goes through a coercion that returns None instead of
raising, the ad still counts as evidence (the pattern really is in it), and
the unusable value is reported through `on_skip` for the operator to go and
fix. Dying in the middle of statistics.median would name neither the record
nor the field.
"""
from __future__ import annotations

import json
import math
import re
import statistics
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from engine import corpus

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "research" / "patterns.json"

SCHEMA = 1

# Two ads is the whole difference between a pattern and an anecdote. There is
# deliberately no way to lower it: a floor that can be argued down in a
# workflow argument is not a floor.
MIN_SUPPORT = 2

# Also the order patterns appear in the file: the shape of an ad as it is
# read, top to bottom, rather than alphabetical, so the document reads the way
# the copy does - and then the two kinds that are not part of the ad at all.
# Longevity is what the advertiser's money did with it; ctr is what our own
# audience did with it, and reads last because only our own ads carry one.
KINDS = (
    "hook",
    "length",
    "structure",
    "cta",
    "offer",
    "proof",
    "objection",
    "longevity",
    "ctr",
)

# An empty corpus still has to produce a valid document, and a fixed sentinel
# keeps even that byte-identical between runs.
EPOCH = "1970-01-01T00:00:00Z"

# Band edges, as lower bounds. These are a first guess, not a measurement
# (docs/AD-RESEARCH-SCOPE.md 3.5 says so and names them as the one thing here
# to revisit after the first live corpus). The word bands follow how Meta
# truncates primary text - roughly the first 125 characters, twenty-odd words,
# show before "See more" - so the first edge separates copy that fits above
# the fold from copy that does not, and the rest double.
LENGTH_EDGES = (20, 50, 100, 200)  # words:0-19, 20-49, 50-99, 100-199, 200+

# Days running, also lower bounds. A week is a launch; four weeks is past the
# point where a launch budget alone keeps an ad alive; eight weeks is the
# threshold the scope document names as the archive's one money-backed vote;
# 120 is evergreen.
LONGEVITY_EDGES = (7, 28, 60, 120)  # days:0-6, 7-27, 28-59, 60-119, 120+

# Click-through bands, in percentage points, as (exclusive ceiling, label):
# the edges are fractional, so the label is spelled out rather than derived
# from an integer edge the way the two integer bands above are. The last band
# is open. Around one percent is the commonly quoted Meta average for a link
# click; the bands split what a B2B ad to a narrow trade plausibly does either
# side of it, and are as much a first guess as the other two.
CTR_BANDS = (
    (0.5, "0-0.4"),
    (1.0, "0.5-0.9"),
    (2.0, "1.0-1.9"),
    (None, "2.0+"),
)  # ctr-pct:<label>

# How much of a quoted line a description carries. Long enough to recognise
# the hook, short enough that one rambling primary text cannot dominate the
# file.
EXAMPLE_CHARS = 90

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SPACE_RE = re.compile(r"\s+")


class PatternsInvalid(ValueError):
    """A patterns.json that this module will not read.

    Named apart from a plain ValueError because the fix is always the same -
    regenerate the file - and a consumer that catches this can say so.
    """


# --- reading the corpus defensively --------------------------------------


def _kind_of(value) -> str:
    """How an error names what it got. "missing" rather than "NoneType",
    because a None here is nearly always an absent key."""
    return "missing" if value is None else type(value).__name__


def _text(value) -> str:
    """A trimmed string, or "" for anything that is not a usable one."""
    return value.strip() if isinstance(value, str) else ""


def _slug(value: str) -> str:
    """A taxonomy label as a comparable token: "Negative Flip" -> "negative-flip".

    Used where the analysis picks from a vocabulary (hook devices, CTA, offer
    and proof types, section labels), so that the same device named three ways
    counts as one device.
    """
    return _SLUG_RE.sub("-", value.lower()).strip("-")


def _key(value: str) -> str:
    """Free text as a comparable key: case and spacing folded, edge punctuation
    dropped.

    Unlike _slug this keeps the words. An objection has no vocabulary to slug
    it into, and an operator reading patterns.json has to be able to tell which
    objection a pattern means.
    """
    return _SPACE_RE.sub(" ", value.strip().lower()).strip(" .,;:!?-")


def _number(value) -> float | None:
    """A metric or count as a float, or None when the corpus carries something
    that is not one.

    Booleans are refused on purpose: True is an int in Python, and a `words`
    field that came back as `true` would otherwise median as 1.0 - a number
    that looks plausible and means nothing. Infinities and NaN go the same way,
    because a NaN in a median silently poisons every value after it.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _band(value: float, edges: tuple[int, ...]) -> str:
    """Which band `value` falls in, as "0-19" / "20-49" / "200+", for the two
    kinds whose edges are whole numbers."""
    low = 0
    for edge in edges:
        if value < edge:
            return f"{low}-{edge - 1}"
        low = edge
    return f"{low}+"


def _ctr_band(value: float) -> str:
    """Which CTR_BANDS label `value` falls under. The last band's ceiling is
    None, so every finite value lands somewhere."""
    for ceiling, label in CTR_BANDS:
        if ceiling is None or value < ceiling:
            return label
    raise AssertionError("CTR_BANDS must end in an open band")  # pragma: no cover


def _median(values) -> float | None:
    """The median of the usable values, or None when there are none."""
    usable = [value for value in values if value is not None]
    return statistics.median(usable) if usable else None


def _median_int(values) -> int:
    """A median day count or reach. Whole, because half a day in a committed
    file is noise, and 0 when no supporting ad carries a usable value - the
    same reading engine.discover gives its NO_BASELINE sentinel."""
    median = _median(values)
    return 0 if median is None else int(median)


def _fmt(value: float) -> str:
    """One decimal place, so a median never lands in the file as
    9.333333333333334 and never changes length between runs."""
    return f"{value:.1f}"


def _quote(text: str) -> str:
    """A corpus line as a one-line quoted example, clipped to EXAMPLE_CHARS."""
    flat = _SPACE_RE.sub(" ", text.strip())
    if len(flat) > EXAMPLE_CHARS:
        flat = flat[: EXAMPLE_CHARS - 3].rstrip() + "..."
    return f'"{flat}"'


def _ignore(message: str) -> None:
    """The default `on_skip`: a caller that did not ask for the reports."""


# --- the corpus, as this module reads it ---------------------------------


@dataclass(frozen=True)
class _Row:
    """One corpus record reduced to what the counting needs.

    days_running and reach are coerced once here rather than in each family,
    so a record with an unusable metric is reported once instead of nine
    times.
    """

    id: str
    fetched_at: str
    days_running: int | None
    reach: int | None
    analysis: dict


@dataclass(frozen=True)
class _Support:
    """One ad's support for one device, held until the pattern is assembled.

    `numbers` is the family's own measurements - hook word count, band value,
    section position - and every family documents its own slots where it fills
    them in.
    """

    id: str
    days_running: int | None
    reach: int | None
    numbers: tuple = ()
    text: str = ""


def _support(row: _Row, *, numbers: tuple = (), text: str = "") -> _Support:
    """One row's support, carrying the row's metrics along for the medians."""
    return _Support(
        id=row.id,
        days_running=row.days_running,
        reach=row.reach,
        numbers=numbers,
        text=text,
    )


def _rows(records, origin: str | None, on_skip: Callable[[str], None]) -> list[_Row]:
    """Corpus records as rows, filtered by origin and sorted by id.

    Sorted here rather than trusted from the caller: load_all() already returns
    records in id order, but a caller holding a list it built itself would
    otherwise decide the order of every evidence list in the file.
    """
    if origin is not None and origin not in corpus.ORIGINS:
        raise ValueError(
            f"origin must be one of {', '.join(corpus.ORIGINS)}, got {origin!r}"
        )

    rows: list[_Row] = []
    seen: set[str] = set()
    for position, record in enumerate(records):
        data = record.to_dict() if isinstance(record, corpus.CorpusRecord) else record
        if not isinstance(data, dict):
            raise TypeError(
                f"record {position} is {_kind_of(data)}; learn reads CorpusRecords "
                f"or the dicts they came from"
            )

        rid = _text(data.get("id"))
        if not rid:
            raise ValueError(
                f"record {position} has id {data.get('id')!r}; every pattern cites "
                f"its evidence by id, so a record without one cannot be counted"
            )
        if rid in seen:
            raise ValueError(
                f"corpus id {rid!r} appears twice in this run; one ad is one "
                f"record, and counting it twice would let it support a pattern "
                f"on its own"
            )
        seen.add(rid)

        if origin is not None and data.get("origin") != origin:
            continue

        metrics = data.get("metrics")
        days = None
        reach = None
        if isinstance(metrics, dict):
            days = _number(metrics.get("days_running"))
            if days is None:
                on_skip(
                    f"{rid}: metrics.days_running is {metrics.get('days_running')!r}, "
                    f"which is not a number; the ad still counts as evidence but "
                    f"is left out of every median_days_running and of the "
                    f"longevity kind"
                )
            reach = _number(metrics.get("eu_total_reach"))
            if reach is None:
                on_skip(
                    f"{rid}: metrics.eu_total_reach is {metrics.get('eu_total_reach')!r}, "
                    f"which is not a number; the ad still counts as evidence but "
                    f"is left out of every median_reach"
                )
        else:
            on_skip(
                f"{rid}: metrics is {_kind_of(metrics)}, expected an object; the "
                f"ad is left out of every median and of the longevity kind"
            )

        analysis = data.get("analysis")
        if not isinstance(analysis, dict):
            on_skip(
                f"{rid}: analysis is {_kind_of(analysis)}, expected an object; "
                f"the ad supports no analysis pattern at all"
            )
            analysis = {}

        rows.append(
            _Row(
                id=rid,
                fetched_at=_text(data.get("fetched_at")),
                days_running=None if days is None else int(days),
                reach=None if reach is None else int(reach),
                analysis=analysis,
            )
        )

    return sorted(rows, key=lambda row: row.id)


def _obj(row: _Row, key: str, on_skip: Callable[[str], None]) -> dict | None:
    """analysis.<key> as an object, or None with a message when it is not one."""
    value = row.analysis.get(key)
    if isinstance(value, dict):
        return value
    on_skip(
        f"{row.id}: analysis.{key} is {_kind_of(value)}, expected an object; "
        f"the ad contributes no {key} pattern"
    )
    return None


def _list(row: _Row, key: str, on_skip: Callable[[str], None]) -> list | None:
    """analysis.<key> as a list, or None with a message when it is not one."""
    value = row.analysis.get(key)
    if isinstance(value, list):
        return value
    on_skip(
        f"{row.id}: analysis.{key} is {_kind_of(value)}, expected a list; "
        f"the ad contributes no {key} pattern"
    )
    return None


# --- patterns ------------------------------------------------------------


@dataclass(frozen=True)
class Pattern:
    """One pattern, contract C5. `id` is filled in once the file is ordered."""

    kind: str
    device: str
    description: str
    evidence: tuple[str, ...]
    median_days_running: int
    median_reach: int
    id: str = ""

    @property
    def n(self) -> int:
        """How many ads support this pattern.

        Derived from evidence rather than counted separately, so the two can
        never disagree: a claim traced to three ids cannot say four.
        """
        return len(self.evidence)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "device": self.device,
            "description": self.description,
            "evidence": list(self.evidence),
            "median_days_running": self.median_days_running,
            "median_reach": self.median_reach,
            "n": self.n,
        }


def _slot(supports: list[_Support], index: int) -> list:
    """One measurement column out of a family's supports."""
    return [
        support.numbers[index] if index < len(support.numbers) else None
        for support in supports
    ]


def _representative(supports: list[_Support]) -> _Support:
    """Which supporting ad a description quotes: the longest-running one,
    ties broken by reach and then by id, unknown values sorting last.

    By days running rather than by position, because "the example whose
    advertiser kept paying for it" is the useful one - longevity is the
    primary signal of the whole design (docs/AD-RESEARCH-SCOPE.md 2.3), and
    reach only the tiebreaker, since a week's launch budget can buy reach that
    nobody clicked. And by id underneath, because a rule that fell back to
    input order would put the caller's list order in the file.
    """
    return sorted(
        supports,
        key=lambda s: (
            -(s.days_running if s.days_running is not None else -1),
            -(s.reach if s.reach is not None else -1),
            s.id,
        ),
    )[0]


def _assemble(kind: str, groups: dict[str, list[_Support]], describe) -> list[Pattern]:
    """Turn one family's groups into patterns, dropping what does not repeat."""
    patterns: list[Pattern] = []
    for device in sorted(groups):
        supports = sorted(groups[device], key=lambda support: support.id)
        if len(supports) < MIN_SUPPORT:
            continue
        patterns.append(
            Pattern(
                kind=kind,
                device=device,
                description=describe(device, supports),
                evidence=tuple(support.id for support in supports),
                median_days_running=_median_int(
                    [support.days_running for support in supports]
                ),
                median_reach=_median_int([support.reach for support in supports]),
            )
        )
    return patterns


def _describe_hook(device: str, supports: list[_Support]) -> str:
    parts = [f'opening device "{device}"']
    words = _median(_slot(supports, 0))
    if words is not None:
        parts.append(f"median hook {_fmt(words)} words")
    example = _representative(supports)
    if example.text:
        parts.append(f"example: {_quote(example.text)}")
    return "; ".join(parts)


def _hook_patterns(rows, on_skip) -> list[Pattern]:
    """Slot 0 is the hook's word count."""
    groups: dict[str, list[_Support]] = {}
    for row in rows:
        hook = _obj(row, "hook", on_skip)
        if hook is None:
            continue
        device = _slug(_text(hook.get("device")))
        if not device:
            on_skip(
                f"{row.id}: analysis.hook.device is {hook.get('device')!r}, which "
                f"names no opening device; the ad contributes no hook pattern"
            )
            continue
        groups.setdefault(device, []).append(
            _support(
                row,
                numbers=(_number(hook.get("words")),),
                text=_text(hook.get("text")),
            )
        )
    return _assemble("hook", groups, _describe_hook)


def _describe_length(device: str, supports: list[_Support]) -> str:
    band = device.split(":", 1)[1]
    parts = [f"{band} words"]
    median = _median(_slot(supports, 0))
    if median is not None:
        parts.append(f"median {_fmt(median)}")
    return "; ".join(parts)


def _length_patterns(rows, on_skip) -> list[Pattern]:
    """Slot 0 is the word count itself, so the description can give the
    median inside the band as well as the band.

    Read from analysis.copy.words - the model's count over primary_text, which
    engine.analyse requires - rather than recounted here, so the corpus and
    the patterns file agree on what a word is.
    """
    groups: dict[str, list[_Support]] = {}
    for row in rows:
        copy_block = _obj(row, "copy", on_skip)
        if copy_block is None:
            continue
        value = _number(copy_block.get("words"))
        if value is None:
            on_skip(
                f"{row.id}: analysis.copy.words is {copy_block.get('words')!r}, "
                f"which is not a number; the ad contributes no length band"
            )
            continue
        device = f"words:{_band(value, LENGTH_EDGES)}"
        groups.setdefault(device, []).append(_support(row, numbers=(value,)))
    return _assemble("length", groups, _describe_length)


def _describe_shape(device: str, supports: list[_Support]) -> str:
    order = device.split(":", 1)[1].replace(">", " > ")
    return f"shape {order}"


def _describe_section(device: str, supports: list[_Support]) -> str:
    parts = [f'section "{device.split(":", 1)[1]}"']
    position = _median(_slot(supports, 0))
    if position is not None:
        parts.append(f"median position {_fmt(position)}")
    return "; ".join(parts)


def _structure_patterns(rows, on_skip) -> list[Pattern]:
    """Two families: the whole section order, and each section on its own.

    The order says what shape repeats; the per-section rows say where in the
    copy each part of that shape tends to sit, which the order alone cannot.
    A text ad's structure is an ordered list of labels with no timings, so a
    section's one slot is its position, counted from 1 the way a person reads
    the copy, among the sections that could be read: an entry that names no
    section is skipped and does not hold a place. The shape has no slot.
    """
    shapes: dict[str, list[_Support]] = {}
    sections: dict[str, list[_Support]] = {}
    for row in rows:
        blocks = _list(row, "structure", on_skip)
        if blocks is None:
            continue

        labels: list[str] = []
        counted: set[str] = set()  # membership only; never iterated
        for position, block in enumerate(blocks):
            label = _slug(_text(block))
            if not label:
                on_skip(
                    f"{row.id}: analysis.structure[{position}] is "
                    f"{block!r}, expected a section label such as \"hook\" or "
                    f"\"offer\"; that section is skipped"
                )
                continue

            labels.append(label)
            # One vote per ad per section, taken from its first appearance: an
            # ad that returns to the offer twice is still one ad that uses an
            # offer section, and its second mention is not a second ad.
            if label not in counted:
                counted.add(label)
                sections.setdefault(f"section:{label}", []).append(
                    _support(row, numbers=(float(len(labels)),))
                )

        if labels:
            shapes.setdefault("shape:" + ">".join(labels), []).append(_support(row))

    return _assemble("structure", shapes, _describe_shape) + _assemble(
        "structure", sections, _describe_section
    )


def _describe_typed(noun: str):
    """The description for a kind whose device is a taxonomy type with an
    optional line of text beside it: cta, offer and proof."""

    def describe(device: str, supports: list[_Support]) -> str:
        parts = [f'{noun} "{device}"']
        example = _representative(supports)
        if example.text:
            parts.append(f"example: {_quote(example.text)}")
        return "; ".join(parts)

    return describe


def _typed_patterns(rows, on_skip, *, key: str, kind: str, noun: str) -> list[Pattern]:
    """cta, offer and proof are the same shape in the record - {type, text} -
    and are counted the same way: the slugged type is the device, the text is
    the quoted example."""
    groups: dict[str, list[_Support]] = {}
    for row in rows:
        block = _obj(row, key, on_skip)
        if block is None:
            continue
        device = _slug(_text(block.get("type")))
        if not device:
            on_skip(
                f"{row.id}: analysis.{key}.type is {block.get('type')!r}, which "
                f"names no {noun}; the ad contributes no {kind} pattern"
            )
            continue
        groups.setdefault(device, []).append(
            _support(row, text=_text(block.get("text")))
        )
    return _assemble(kind, groups, _describe_typed(noun))


def _cta_patterns(rows, on_skip) -> list[Pattern]:
    return _typed_patterns(rows, on_skip, key="cta", kind="cta", noun="call to action")


def _offer_patterns(rows, on_skip) -> list[Pattern]:
    return _typed_patterns(rows, on_skip, key="offer", kind="offer", noun="offer")


def _proof_patterns(rows, on_skip) -> list[Pattern]:
    return _typed_patterns(rows, on_skip, key="proof", kind="proof", noun="proof")


def _describe_objection(device: str, supports: list[_Support]) -> str:
    example = _representative(supports)
    return f"objection answered: {_quote(example.text or device)}"


def _objection_patterns(rows, on_skip) -> list[Pattern]:
    groups: dict[str, list[_Support]] = {}
    for row in rows:
        items = _list(row, "objections", on_skip)
        if items is None:
            continue
        counted: set[str] = set()  # membership only; never iterated
        for position, item in enumerate(items):
            if not isinstance(item, str) or not item.strip():
                on_skip(
                    f"{row.id}: analysis.objections[{position}] is "
                    f"{_kind_of(item)}, expected a non-empty string; that "
                    f"objection is skipped"
                )
                continue
            device = _key(item)
            # One ad raising the same objection twice is still one ad.
            if not device or device in counted:
                continue
            counted.add(device)
            groups.setdefault(device, []).append(_support(row, text=_text(item)))
    return _assemble("objection", groups, _describe_objection)


def _describe_longevity(device: str, supports: list[_Support]) -> str:
    band = device.split(":", 1)[1]
    parts = [f"{band} days running"]
    median = _median(_slot(supports, 0))
    if median is not None:
        parts.append(f"median {_fmt(median)}")
    return "; ".join(parts)


def _longevity_patterns(rows, on_skip) -> list[Pattern]:
    """Slot 0 is the day count itself, so the description can give the median
    inside the band as well as the band.

    Read from the row, which coerced metrics.days_running once for every
    kind; an unusable count was reported there, so an ad without one is left
    out here without a second line about it. days_running is discover's
    arithmetic (start to stop, or start to the day of the run for an ad still
    live) and engine.feedback's for our own; both are whole days.
    """
    groups: dict[str, list[_Support]] = {}
    for row in rows:
        if row.days_running is None:
            continue
        value = float(row.days_running)
        device = f"days:{_band(value, LONGEVITY_EDGES)}"
        groups.setdefault(device, []).append(_support(row, numbers=(value,)))
    return _assemble("longevity", groups, _describe_longevity)


def _describe_ctr(device: str, supports: list[_Support]) -> str:
    band = device.split(":", 1)[1]
    parts = [f"{band}% click-through"]
    median = _median(_slot(supports, 0))
    if median is not None:
        parts.append(f"median {_fmt(median)}%")
    return "; ".join(parts)


def _ctr_patterns(rows, on_skip) -> list[Pattern]:
    """Slot 0 is the percentage itself, so the description can give the median
    inside the band as well as the band.

    Read from analysis.own_metrics, which engine.feedback carries in from the
    measurement - so in practice this counts our own launched ads, the only
    ads whose click-through anybody can read. It is deliberately not
    restricted to origin "own": a record from anywhere that carries a real
    reading is real evidence, and a rule here that named an origin would be a
    second place for the corpus to define what counts.
    """
    groups: dict[str, list[_Support]] = {}
    for row in rows:
        block = row.analysis.get("own_metrics")
        # Absent is the normal state of the corpus - a competitor's clicks are
        # not ours to read - so it is silent. _obj() would report it, and a
        # line per competitor ad per run would bury the reports that mean
        # something. Present but not an object is somebody's edit, and is not.
        if block is None:
            continue
        if not isinstance(block, dict):
            on_skip(
                f"{row.id}: analysis.own_metrics is {_kind_of(block)}, expected "
                f"an object; the ad contributes no ctr pattern"
            )
            continue

        reading = block.get("ctr")
        # A NULL IS NOT A ZERO. The Marketing API reports no ctr for an ad with
        # no impressions in the window, and engine.measure writes absent as
        # null, never 0 - so a null here means nobody could read this ad's
        # click-through, a fact about the reading, not a defect for an
        # operator to go and fix. What it must never become is 0.0, which
        # would band at the bottom and count as an ad nobody clicked. Left out
        # of the groups entirely, it cannot do either.
        if reading is None:
            continue
        value = _number(reading)
        if value is None:
            on_skip(
                f"{row.id}: analysis.own_metrics.ctr is {reading!r}, which is "
                f"not a number; the ad contributes no ctr band"
            )
            continue

        device = f"ctr-pct:{_ctr_band(value)}"
        groups.setdefault(device, []).append(_support(row, numbers=(value,)))
    return _assemble("ctr", groups, _describe_ctr)


_FAMILIES = (
    _hook_patterns,
    _length_patterns,
    _structure_patterns,
    _cta_patterns,
    _offer_patterns,
    _proof_patterns,
    _objection_patterns,
    _longevity_patterns,
    _ctr_patterns,
)


def _patterns(rows: list[_Row], on_skip: Callable[[str], None]) -> list[Pattern]:
    """Every family, ordered, with ids assigned."""
    found: list[Pattern] = []
    for family in _FAMILIES:
        found.extend(family(rows, on_skip))

    ordered = sorted(found, key=lambda p: (KINDS.index(p.kind), p.device))

    # Two digits normally, wider once there are more patterns than that holds:
    # "q100" sorts before "q99" as text, which would quietly break any consumer
    # that sorts ids rather than trusting the file's order. The prefix is q so
    # that a concept can never cite one of reel-engine's p-ids by accident.
    width = max(2, len(str(len(ordered))))
    return [
        replace(pattern, id=f"q{number:0{width}d}")
        for number, pattern in enumerate(ordered, start=1)
    ]


def _generated_at(rows: list[_Row]) -> str:
    """The newest fetched_at in the corpus this document describes.

    RFC3339 with a Z sorts correctly as text, so this needs no date parsing -
    and a clock reading here would rewrite the file on every weekly run whether
    or not the corpus had changed.
    """
    stamps = [row.fetched_at for row in rows if row.fetched_at]
    return max(stamps) if stamps else EPOCH


# --- the public surface --------------------------------------------------


def find_patterns(
    records,
    *,
    origin: str | None = None,
    on_skip: Callable[[str], None] | None = None,
) -> list[Pattern]:
    """Every pattern in `records` that at least MIN_SUPPORT ads support.

    `records` are CorpusRecords or the dicts they came from. `origin` narrows
    the corpus to "competitor", "icp-adjacent" or "own" before anything is
    counted. `on_skip` is called with a one-line message for each corpus value
    that could not be used; the default discards them.
    """
    report = on_skip or _ignore
    return _patterns(_rows(records, origin, report), report)


def build(
    records,
    *,
    origin: str | None = None,
    generated_at: str | None = None,
    on_skip: Callable[[str], None] | None = None,
) -> dict:
    """The whole document, contract C5. The only place its shape is written.

    `generated_at` defaults to the newest fetched_at in the corpus. Pass one
    only where a caller genuinely wants a different stamp; a clock reading puts
    a diff in every weekly commit that says nothing changed.
    """
    report = on_skip or _ignore
    rows = _rows(records, origin, report)
    return {
        "schema": SCHEMA,
        "generated_at": generated_at or _generated_at(rows),
        "corpus_size": len(rows),
        "patterns": [pattern.to_dict() for pattern in _patterns(rows, report)],
    }


def dumps(document: dict) -> str:
    """The document as it goes to disk.

    sorted keys, two-space indent, trailing newline, non-ASCII left legible -
    the same format as engine/corpus.py writes, for the same reason: a
    committed file has to diff as the fields that actually changed.
    """
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write(document: dict, path: Path | str | None = None) -> Path:
    """Write the document and return its path."""
    path = Path(path) if path else DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(document), encoding="utf-8")
    return path


def load(path: Path | str | None = None) -> dict:
    """Read a patterns document. What the concept and score steps call."""
    path = Path(path) if path else DEFAULT_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"no patterns file at {path}; run python -m engine.learn to write one "
            f"from research/corpus/"
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PatternsInvalid(f"{path} is not valid JSON: {exc}") from exc

    schema = document.get("schema") if isinstance(document, dict) else None
    if schema != SCHEMA:
        raise PatternsInvalid(
            f"{path} has schema {schema!r}; this module reads schema {SCHEMA} "
            f"only. Regenerate it with python -m engine.learn rather than "
            f"reading fields that may have moved."
        )
    return document


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m engine.learn",
        description="Patterns from the analysed ad corpus. Counts only, no model.",
    )
    parser.add_argument("--corpus", default=None,
                        help=f"corpus directory (default {corpus.DEFAULT_ROOT})")
    parser.add_argument("--origin", default=None, choices=list(corpus.ORIGINS),
                        help="learn from ads of this origin only")
    parser.add_argument("--out", default=None,
                        help=f"write the document here (default {DEFAULT_PATH})")
    parser.add_argument("--stdout", action="store_true",
                        help="print the document instead of writing it")
    args = parser.parse_args(argv)

    try:
        records = corpus.load_all(Path(args.corpus) if args.corpus else None)
    except (FileNotFoundError, corpus.CorpusInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    skipped: list[str] = []
    document = build(records, origin=args.origin, on_skip=skipped.append)
    for message in skipped:
        print(f"skipped: {message}", file=sys.stderr)

    if args.stdout:
        sys.stdout.write(dumps(document))
        destination = "stdout"
    else:
        destination = str(write(document, args.out))

    print(
        f"{len(document['patterns'])} patterns supported by {MIN_SUPPORT}+ of "
        f"{document['corpus_size']} ads -> {destination}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
