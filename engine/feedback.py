"""python -m engine.feedback [--dry-run] [--measurements PATH] [--corpus DIR] [--seeds PATH]

Our own launched ads, fed back into the corpus as records like any other.

This is the step that closes the loop. Once an ad we launched is a corpus
record with origin "own", engine.learn counts it exactly as it counts a
stranger's ad - find_patterns(records, origin="own") needs no change to read
it - and it carries the one number nothing else in this loop can read: a real
click-through rate, from our own ad account, under analysis.own_metrics. The
ctr kind in engine.learn is fed by these records and by nothing else, and a
hook that repeats in three long-running competitor ads AND in our own
best-clicked ad is the strongest citation this system can write.

## Why nothing here calls a model

engine.analyse pays a model to read a competitor's copy because nothing else
can say what is in it. We wrote this copy. The primary text, the headline, the
description, the button and the offer are in queue/launched/<segment>.json
verbatim - the same file the gate passed and a human tapped `go` on twice.
Asking a model to describe an ad we authored would be paying to rediscover our
own job file, and the answer would be less exact than the file it was guessing
at. So this module reads three files and counts words. Nothing it imports can
reach a model or the network, which tests/test_feedback.py proves by
AST-parsing it - and tests/test_learn.py proves again from the other end of
the ctr path, so neither end of that path can quietly grow a client.

## Why the measurement and the seeds are read here, not imported

engine.measure writes research/measurements.json and engine.discover loads
research/seeds.yaml, and both of them import urllib for their transports.
Importing either to read one file would put a socket-capable module in this
one's import closure, which is exactly what the AST tests forbid. So the C6
document is read by this module against a schema number it pins itself, and
the `own:` block is read by this module with the same three field names
engine.discover gives it - a discover.Own passes through record_for()
unchanged, and so does the Own defined below.

## What is exact here, and what is deliberately not

Exact, read straight off the files:

  - the copy, verbatim, and its word count;
  - the button type and the offer id, which are enums the writer stamped and
    the gate checked;
  - impressions, reach, click-through, hook rate and hold rate, which come
    from the measurement row engine.measure wrote off the Marketing API
    insights edge and are copied through untouched, nulls included. A metric
    the API did not report stays null; it is never 0. engine.learn bands the
    click-through, and a fabricated 0.0 there would read as an ad nobody
    clicked.

Derived, and said so in the record itself - analysis.derived_from.note - rather
than dressed up as analysis:

  - analysis.hook is the first sentence of primary_text.en, counted. A model
    reading a competitor's ad decides where the hook ends; here a sentence
    boundary decides, which is exact and slightly dumber.
  - analysis.hook.device is "authored". Which rhetorical device our hook "is"
    is a judgement a model makes about someone else's copy, and a guessed one
    would travel into next week's concept as evidence. "authored" groups our
    own ads together in patterns.json and can never be mistaken for a device
    read off a competitor's ad.
  - analysis.structure is inferred from the offer id alone: hook > offer > cta
    when the job makes an offer, hook > cta when it does not. Nobody here has
    marked where a problem or a proof sits in the copy, so no such section is
    claimed.
  - analysis.offer.text and analysis.cta.text are empty. The offer's wording
    is somewhere in the primary text and the button's label is Meta's, and
    picking the sentence that "is" the offer would be a judgement.
  - analysis.proof is none and analysis.objections is empty. Whether a line
    counts as proof, and which objection it answers, is written down nowhere
    this module can read.
  - metrics.days_running is measured_at minus launched_at in whole days: the
    window the numbers cover, not how long the ad has been live today.
  - metrics.variants is the number of ad ids pinned in the job.

## An ad with no impressions is not a record

engine.learn bands analysis.own_metrics.ctr and medians metrics.eu_total_reach
over the ads supporting a pattern. A row with no impressions - the ad is
paused, or the window is empty, or the measurement ran an hour after launch -
has a click-through that means nothing and a reach of nothing, and a record
written from it would say so in no field a reader would look at. So it is
skipped by name, and stays skipped until a measurement carries real
impressions.
"""
from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from engine import approval, corpus

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MEASUREMENTS = ROOT / "research" / "measurements.json"
DEFAULT_SEEDS = ROOT / "research" / "seeds.yaml"

# C6: the measurements document this module reads. Written by the measure
# step; deliberately not imported (see the module docstring), so the schema
# number and the key holding the rows are pinned here.
MEASUREMENTS_SCHEMA = 1
ROWS_KEY = "rows"

ORIGIN = "own"

# The only platform this corpus holds. Spelled out so the record says what it
# is; a test pins that it is corpus.PLATFORMS[0].
PLATFORM = "meta-ad"

# C1's `model` records what produced the analysis. Nothing did: every field
# below is read off the job we wrote and the row engine.measure read. Naming a
# model here - even the one the copy came from - would make a record that was
# never analysed indistinguishable from one that was.
MODEL = "none (authored)"

# The record id, and so the filename, is `fb-own-<segment>-<ad id>`. The
# "fb-own-" prefix keeps ours clear of engine.discover's `fb-<library id>` ids
# for ads we did not write, and the ad id keeps two ads launched from one
# job as two records - corpus.load_all refuses two records with one id.
ID_PREFIX = "fb-own-"

# What the hook's device and the creative's kind say: whose slot this is, not
# what a model would call the move it makes. Both slug to themselves in
# engine.learn.
HOOK_DEVICE = "authored"
CREATIVE_KIND = "authored"

# Where the numbers came from, which is what `url` means for every other
# record too: a competitor's record points at the Ad Library page the archive
# was read from, and ours points at the Marketing API insights edge
# engine.measure reads (docs/CONTRACTS.md: "the Marketing API insights edge is
# the only read for our own"). Unversioned, as measure's GRAPH constant is;
# META_GRAPH_VERSION inserts a version at call time and is not a fact about
# the ad. Not the Ad Library page: whether the Ads Manager ad id is also the
# Library id is unverified, and a link nobody checked is a small lie in a
# committed file.
INSIGHTS_URL = "https://graph.facebook.com/{ad_id}/insights"

# The C1 structure vocabulary this module is willing to claim. `offer` is
# claimed only when the job names one; nothing here has read where a problem
# or a proof sits in the copy, so neither is ever claimed.
STRUCTURE_WITH_OFFER = ("hook", "offer", "cta")
STRUCTURE_WITHOUT_OFFER = ("hook", "cta")
NO_OFFER = "none"

# analysis.own_metrics, exactly the three keys the contract names, in the order
# they are read: ctr from the row's metrics, the two rates from its derived
# block. Copied through as they are, nulls included, and never widened here: a
# whitelist that grew would be a second definition of C6.
OWN_METRIC_KEYS = ("ctr", "hook_rate", "hold_rate")

# Stamped into every record so the file says what it is without anyone having
# to find this module first. It names every field that was derived rather
# than read, because that is the list a reader needs.
DERIVED_NOTE = (
    "Authored, not analysed: read off the launched job we wrote and the "
    "measurement row engine.measure read, with no model call. Exact - the "
    "copy (words counted here), the cta and offer enums, and own_metrics "
    "copied through with its nulls. Derived - hook is the first sentence of "
    "primary_text.en with device 'authored'; structure is inferred from the "
    "offer id alone; offer.text and cta.text are left empty rather than "
    "picked; proof is none and objections are empty because neither is "
    "written down; link_caption is the job's destination; days_running is "
    "measured_at minus launched_at in whole days; variants is the number of "
    "pinned ad ids; page_id is research/seeds.yaml's own block. See "
    "engine/feedback.py."
)

_WHITESPACE_RE = re.compile(r"\s+")
_LINE_BREAK_RE = re.compile(r"\r?\n")
# A sentence ends at terminal punctuation followed by whitespace or the end of
# the text, so "3.5 hours" and "doviloop.dev" do not end one. "e.g." does; our
# copy has no abbreviations, and a copy that grew some would need a real
# splitter rather than a wider regex.
_SENTENCE_END_RE = re.compile(r"[.!?]+(?=\s|$)")
# A Facebook page id is a decimal string in every API reference and every
# Ad Library URL; the same reading engine.discover gives the seeds.
_DIGITS_RE = re.compile(r"^[0-9]+$")


class SkippedAd(RuntimeError):
    """This launched ad produced no record, and the message says why.

    Not a bug and not a failed run. The usual cause is an ad nobody has
    measured with real impressions yet, which is fixed by measuring it next
    week rather than by running this again today - so the run collects these
    and carries on, the way engine.analyse treats a creative nobody saved.
    `segment` and `ad_id` are carried separately so a caller can group skips
    without parsing the sentence.
    """

    def __init__(self, message: str, *, segment: str = "", ad_id: str = ""):
        super().__init__(message)
        self.segment = segment
        self.ad_id = ad_id


class MeasurementsInvalid(ValueError):
    """research/measurements.json is not a document this module can read.

    Separate from SkippedAd because the fix is different: one ad being
    unmeasured is normal, and the whole file being unreadable stops the step.
    """


class SeedsInvalid(ValueError):
    """The own: block of research/seeds.yaml is not one this module can read.

    Only the own block is checked here. engine.discover validates the rest of
    the file, and a second validator for pages and queries would be a second
    place for the two to disagree.
    """


@dataclass(frozen=True)
class Own:
    """OUR page and ad account, as research/seeds.yaml's own: block holds it.

    The same three field names as engine.discover.Own, on purpose: record_for
    reads `page_id` and `page_name` off whichever of the two it is handed, so
    a caller holding a discover.Seeds passes `seeds.own` straight through.
    Defined here rather than imported because engine.discover carries a
    transport, and this module's import closure must not (module docstring).
    Ships blank: page_id "" and channel "own" until somebody fills it in.
    """

    page_id: str | None = None
    page_name: str | None = None
    ad_account_id: str | None = None


@dataclass(frozen=True)
class FeedbackRun:
    """What one pass produced.

    `written` is the corpus path of every record, in the order they were
    handled; on a dry run it is where each one WOULD have gone and nothing
    was touched. `records` holds the same records in the same order, so a
    caller can read what was written without opening the files. `skipped` is
    one line per ad, job or row that made no record, each naming why.
    """

    written: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)


# --- reading what we wrote -----------------------------------------------


def _plain(raw) -> str:
    """A field as words: whitespace collapsed, anything that is not a string
    read as empty."""
    if not isinstance(raw, str):
        return ""
    return _WHITESPACE_RE.sub(" ", raw).strip()


def first_sentence(text) -> str:
    """The hook: the first sentence of the primary text, as written.

    The text up to and including the first terminal punctuation run that is
    followed by whitespace or the end, or up to the first line break,
    whichever comes first - an author who broke the line meant the first line
    to stand on its own. No punctuation and no break means the whole text is
    one sentence. Whitespace is collapsed; the punctuation is kept because it
    is part of what was written.
    """
    if not isinstance(text, str):
        return ""
    first_line = _LINE_BREAK_RE.split(text.strip(), maxsplit=1)[0]
    match = _SENTENCE_END_RE.search(first_line)
    sentence = first_line[: match.end()] if match else first_line
    return _plain(sentence)


def _skip(segment: str, ad_id: str, why: str) -> SkippedAd:
    return SkippedAd(
        "%s ad %s: skipped - %s" % (segment or "?", ad_id or "?", why),
        segment=segment,
        ad_id=ad_id,
    )


def _english(job: dict, key: str, *, segment: str, ad_id: str) -> str:
    """The `en` text of one of the job's {en, da, lt} maps, verbatim.

    A launched job passed the gate, which requires each of the three copy
    fields to be a map with a non-empty `en`; a job short of one is not the
    job that shipped, and a record written from it would misdescribe the ad.
    A bare string is refused rather than read as English: which language it
    is in is exactly the thing nobody wrote down.
    """
    value = job.get(key)
    if not isinstance(value, dict):
        raise _skip(
            segment,
            ad_id,
            "the job's %s is %s, expected a {en, da, lt} map. The gate would "
            "not have passed this file; restore the launched job rather than "
            "writing a record from it." % (key, type(value).__name__),
        )
    text = value.get("en")
    if not isinstance(text, str) or not text.strip():
        raise _skip(
            segment,
            ad_id,
            "the job's %s.en is %r, and the record's copy is the English we "
            "wrote. Restore it rather than writing a record with the copy "
            "missing." % (key, text),
        )
    return text


def _enum(job: dict, key: str, *, segment: str, ad_id: str) -> str:
    """A one-word field the writer stamped (cta, offer), stripped."""
    value = _plain(job.get(key))
    if not value:
        raise _skip(
            segment,
            ad_id,
            "the job names no %s (%r); the gate requires one, so this is not "
            "the job that shipped." % (key, job.get(key)),
        )
    return value


def _timestamp(value, *, what: str, segment: str, ad_id: str) -> datetime:
    """An ISO-8601 stamp as an aware UTC datetime. A bare date is midnight
    UTC; a naive stamp is read as UTC, which is what every writer here
    stamps."""
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise _skip(
            segment,
            ad_id,
            "%s is %r; days_running is measured_at minus launched_at, and a "
            "window with one end missing has no length." % (what, value),
        )
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise _skip(
            segment,
            ad_id,
            "%s %r is not an ISO-8601 timestamp (expected the form "
            "%s)." % (what, value, approval.TIMESTAMP_FORMAT.replace("%", "")),
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# --- reading what the ad did ----------------------------------------------


def _whole(value) -> int | None:
    """A count as a whole number, or None when `value` is not one.

    bool is refused because True is an int in Python and is not one
    impression. Infinity and NaN are refused because int(inf) raises and a
    NaN that reached a median would poison every value after it. A fraction
    is refused because a count is a whole number, and a fraction means
    whatever produced it was dividing something.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and (not math.isfinite(value) or value != int(value)):
        return None
    return int(value)


def _impressions(metrics: dict, *, segment: str, ad_id: str) -> int:
    """The impression count, which must be a real one.

    Zero and null are refused, not stored: an ad with no impressions has a
    click-through that means nothing and a reach of nothing, and a record
    written from it would band in engine.learn as an ad nobody clicked.
    """
    value = metrics.get("impressions")
    count = _whole(value)
    if count is None:
        raise _skip(
            segment,
            ad_id,
            "metrics.impressions is %r, which is not a whole number of "
            "impressions. %s"
            % (
                value,
                "Measure it again once it has served: a record with no "
                "impressions would band in engine.learn as an ad nobody "
                "clicked."
                if value is None
                else "Fix the measurement rather than writing a record the "
                "medians cannot read.",
            ),
        )
    if count <= 0:
        raise _skip(
            segment,
            ad_id,
            "metrics.impressions is %d, so this ad has not really been "
            "measured yet. Measure it again once it has served: a record "
            "with no impressions would band in engine.learn as an ad nobody "
            "clicked." % count,
        )
    return count


def _reach(metrics: dict, *, segment: str, ad_id: str) -> int | None:
    """The reach as a whole number, or null when the API reported none.

    Null rather than 0 for an absent reach, the rule every measured number
    in this repository follows (engine.measure writes absent as null, never
    0): engine.learn medians eu_total_reach across the ads supporting a
    pattern, reports a null by id and leaves it out, whereas a 0 would count
    as an ad nobody saw. Junk - a string, a bool, a fraction - is refused
    rather than carried, because engine.corpus does not type-check inside
    metrics and "3.3k" would reach the medians silently.
    """
    value = metrics.get("reach")
    if value is None:
        return None
    count = _whole(value)
    if count is None:
        raise _skip(
            segment,
            ad_id,
            "metrics.reach is %r, which is not a whole number; fix the "
            "measurement rather than writing a record the medians cannot "
            "read." % (value,),
        )
    return count


def _own_field(own, name: str) -> str:
    """`page_id` or `page_name` off an Own - ours, engine.discover's, a
    mapping, or None - as stripped text, "" when blank."""
    if own is None:
        return ""
    value = own.get(name) if isinstance(own, dict) else getattr(own, name, None)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    return str(value).strip()


# --- the corpus record ---------------------------------------------------


def record_for(job: dict, row: dict, *, own, now=None) -> dict:
    """One launched job plus one measurement row -> one C1 record.

    `job` is queue/launched/<segment>.json, which IS the copy that went out:
    it passed the gate, a human tapped `go` on it twice, and approval.launch
    pinned the ad ids into it. `row` is one entry of research/measurements.json
    (C6); it names the segment and the ad id, so nothing has to be passed
    twice. `own` is the own: block of research/seeds.yaml - engine.discover's
    Own, this module's Own, or None for a blank block, which gives page_id ""
    and channel "own".

    `now` is accepted because the contract fixes the signature and a caller
    may hand it through; nothing here reads the clock. Every stamp in the
    record is the row's or the job's, so re-running this step over unchanged
    inputs rewrites the same bytes, and a test pins that `now` changes
    nothing.

    Raises SkippedAd - naming the segment and the ad id - rather than
    returning a record that would mislead: no real impressions, a row for an
    ad the job does not pin, a job short of the copy its gate required, a
    window with a missing end. The returned record is validated by
    engine.corpus before it is handed back.
    """
    del now  # accepted for the signature; nothing here depends on the clock

    segment = _plain(job.get("segment"))
    ad_id = _plain(row.get("ad_id"))
    if not segment:
        raise _skip(
            segment,
            ad_id,
            "the job names no segment (%r); the segment is the queue "
            "filename and half the record's id." % (job.get("segment"),),
        )
    if not ad_id:
        raise _skip(
            segment,
            ad_id,
            "the row names no ad id (%r); every record of our own is one "
            "measured ad, and the ad id is half its id." % (row.get("ad_id"),),
        )

    row_segment = _plain(row.get("segment"))
    if row_segment != segment:
        raise _skip(
            segment,
            ad_id,
            "the row says segment %r and the job says %r. A row is matched "
            "to a job by segment, so one of the two is misfiled; look at "
            "research/measurements.json and queue/launched/." % (row_segment, segment),
        )

    ads = job.get(approval.ADS)
    if not isinstance(ads, dict) or ad_id not in ads:
        pinned = ", ".join(sorted(ads)) if isinstance(ads, dict) and ads else "none"
        raise _skip(
            segment,
            ad_id,
            "the job pins ad ids %s, not this one. Either the row measures "
            "an ad that was not launched from this job or the job is short "
            "an id; fix whichever is wrong rather than crediting this copy "
            "with numbers it may not have earned." % pinned,
        )
    pinned_ids = ads[ad_id] if isinstance(ads[ad_id], dict) else {}

    record_id = "%s%s-%s" % (ID_PREFIX, segment, ad_id)
    if not corpus.ID_RE.match(record_id):
        raise _skip(
            segment,
            ad_id,
            "%r cannot be half a filename; the segment and the ad id must "
            "be letters, digits, dot, underscore, tilde or hyphen." % record_id,
        )

    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        raise _skip(
            segment,
            ad_id,
            "the row has no metrics object (%r), so there is nothing to learn "
            "from this ad yet." % (metrics,),
        )
    derived = row.get("derived")
    if not isinstance(derived, dict):
        derived = {}

    # Proved real, not stored: the record carries the rates the impressions
    # were divided into, and a count that reached the corpus would be a
    # second copy of a number research/measurements.json already holds.
    _impressions(metrics, segment=segment, ad_id=ad_id)
    reach = _reach(metrics, segment=segment, ad_id=ad_id)

    measured_at = row.get("measured_at")
    measured = _timestamp(measured_at, what="the row's measured_at",
                          segment=segment, ad_id=ad_id)
    launched = _timestamp(job.get(approval.LAUNCHED_AT),
                          what="the job's launched_at",
                          segment=segment, ad_id=ad_id)
    window = measured - launched
    if window.total_seconds() < 0:
        raise _skip(
            segment,
            ad_id,
            "measured_at %r is before launched_at %r; one of the two stamps "
            "is wrong, and a negative window is not a number of days."
            % (measured_at, job.get(approval.LAUNCHED_AT)),
        )
    # Whole days, floored: the window the numbers cover. Not how long the ad
    # has been live today - that would need the clock, and the record has to
    # rewrite the same bytes from the same row.
    days_running = int(window.total_seconds() // 86400)

    primary_text = _english(job, "primary_text", segment=segment, ad_id=ad_id)
    headline = _english(job, "headline", segment=segment, ad_id=ad_id)
    description = _english(job, "description", segment=segment, ad_id=ad_id)
    cta = _enum(job, "cta", segment=segment, ad_id=ad_id)
    offer = _enum(job, "offer", segment=segment, ad_id=ad_id)
    hook_text = first_sentence(primary_text)

    creative_source = job.get("creative_source")
    creative_kind = (
        _plain(creative_source.get("kind")) if isinstance(creative_source, dict) else ""
    )

    record = {
        "schema": corpus.SCHEMA,
        "id": record_id,
        "platform": PLATFORM,
        "url": INSIGHTS_URL.format(ad_id=ad_id),
        # The page the ad went out as, which is the nearest thing our own
        # record has to a competitor record's channel; "own" until the seeds
        # name it, so the record still says whose it is.
        "channel": _own_field(own, "page_name") or ORIGIN,
        "origin": ORIGIN,
        # When the numbers were read, which is what fetched_at means for every
        # other record too - and it comes from the row rather than from the
        # clock, so re-running this step over an unchanged measurement
        # rewrites the same bytes. Verbatim, as measure stamped it.
        "fetched_at": measured_at.strip(),
        "metrics": {
            "eu_total_reach": reach,
            "days_running": days_running,
            # A launched job is live by definition here: nothing in this
            # repository reads an ad's status back, and a paused ad shows up
            # as a row with no impressions, which is skipped above.
            "active": True,
            "variants": len(ads),
            "page_id": _own_field(own, "page_id"),
        },
        "analysis": {
            "copy": {
                "primary_text": primary_text,
                "headline": headline,
                "description": description,
                # What we wrote, not the caption Ads Manager rendered: Meta
                # shows a display link of its own choosing, and nothing here
                # has looked at the rendered ad.
                "link_caption": _plain(job.get("destination")),
                # Counted here, over whitespace, the same definition
                # engine.analyse asks the model for.
                "words": len(primary_text.split()),
            },
            "hook": {
                "words": len(hook_text.split()),
                "text": hook_text,
                "device": HOOK_DEVICE,
            },
            "structure": list(
                STRUCTURE_WITHOUT_OFFER if offer == NO_OFFER else STRUCTURE_WITH_OFFER
            ),
            # The offer id the writer stamped and the gate verified against
            # claims/evidence.json. Its wording is somewhere in the primary
            # text; which sentence "is" the offer would be a judgement.
            "offer": {"type": offer, "text": ""},
            "proof": {"type": "none", "text": ""},
            "cta": {
                # C1's cta vocabulary is lowercase-hyphen ("learn-more"); the
                # job carries Meta's button enum ("LEARN_MORE"). One is the
                # other's spelling, so folding it is not a guess. The label
                # the button showed is Meta's, in the viewer's language, so
                # there is no text of ours to quote.
                "type": cta.lower().replace("_", "-"),
                "text": "",
            },
            # Empty unless someone writes them down: see the module docstring.
            "objections": [],
            "creative": {"kind": CREATIVE_KIND},
            # Copied through as they are, nulls included. engine.learn already
            # refuses a leaf that is not a finite number and reports it by
            # name, and a second coercion here would be a second place for
            # the two to disagree. Deep-copied so the record never aliases
            # the row it came from.
            "own_metrics": {
                "ctr": copy.deepcopy(metrics.get("ctr")),
                "hook_rate": copy.deepcopy(derived.get("hook_rate")),
                "hold_rate": copy.deepcopy(derived.get("hold_rate")),
            },
            # Stamped after everything else, inside `analysis` because
            # engine.corpus closes the top level to exactly its schema. This
            # is the record saying what it is, in the file, to whoever opens
            # it - and where it came from: which job, which concept, which
            # patterns that concept cited.
            "derived_from": {
                "kind": CREATIVE_KIND,
                "segment": segment,
                "ad_id": ad_id,
                "campaign_id": pinned_ids.get("campaign_id"),
                "adset_id": pinned_ids.get("adset_id"),
                "concept_id": _plain(job.get("concept_id")),
                "pattern_ids": [
                    p for p in (_plain(item) for item in (job.get("pattern_ids") or []))
                    if p
                ],
                "placement": _plain(job.get("placement")),
                "creative_kind": creative_kind,
                "launched_at": _plain(job.get(approval.LAUNCHED_AT)),
                "note": DERIVED_NOTE,
            },
        },
        "model": MODEL,
    }

    # engine.corpus is the single definition of a complete record and its
    # message already names the offending key the way the file lays it out,
    # so it is raised as it is rather than rephrased.
    corpus.validate(record)
    return record


# --- the measurements file (C6) ------------------------------------------


def load_measurements(path: Path | str | None = None) -> list[dict]:
    """The rows in research/measurements.json, as written by the measure step.

    Only the rows: every one carries its own segment, ad id and measured_at,
    so nothing downstream needs the envelope.
    """
    path = Path(path) if path else DEFAULT_MEASUREMENTS
    if not path.exists():
        raise FileNotFoundError(
            "no measurements at %s; run `python -m engine.measure` first - "
            "until an ad has real numbers there is nothing for the corpus to "
            "learn from it." % path
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MeasurementsInvalid("%s is not valid JSON: %s" % (path, exc)) from exc

    if not isinstance(document, dict):
        raise MeasurementsInvalid(
            "%s holds a %s; C6 is an object with schema, generated_at and %s."
            % (path, type(document).__name__, ROWS_KEY)
        )
    schema = document.get("schema")
    if schema != MEASUREMENTS_SCHEMA:
        raise MeasurementsInvalid(
            "%s has schema %r; this module reads schema %d only. Re-run the "
            "measure step rather than reading fields that may have moved."
            % (path, schema, MEASUREMENTS_SCHEMA)
        )
    rows = document.get(ROWS_KEY)
    if not isinstance(rows, list):
        raise MeasurementsInvalid(
            "%s has %s %r; C6 says a list, and one row read as a whole file "
            "would feed the corpus a record nobody measured."
            % (path, ROWS_KEY, type(rows).__name__ if rows is not None else None)
        )
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            raise MeasurementsInvalid(
                "%s %s[%d] is a %s; every row is an object."
                % (path, ROWS_KEY, position, type(row).__name__)
            )
    return rows


def _by_segment(rows: list[dict]) -> tuple[dict[str, list[dict]], list[str]]:
    """Rows grouped by the job they measure, each group in a fixed order, plus
    a line for every row that names no segment.

    Sorted by ad id rather than by file order so that a run over an unchanged
    measurements file writes the same records in the same order.
    """
    grouped: dict[str, list[dict]] = {}
    orphans: list[str] = []
    for position, row in enumerate(rows):
        segment = _plain(row.get("segment"))
        if not segment:
            orphans.append(
                "%s[%d]: skipped - the row names no segment (%r), so it cannot "
                "be matched to a launched job."
                % (ROWS_KEY, position, row.get("segment"))
            )
            continue
        grouped.setdefault(segment, []).append(row)
    for group in grouped.values():
        group.sort(key=lambda row: _plain(row.get("ad_id")))
    return grouped, orphans


# --- the seeds file's own block ------------------------------------------


def _seed_text(value, *, path: Path, key: str) -> str | None:
    """One own: field as stripped text, or None when blank.

    YAML reads an unquoted page id as an int, so ints are accepted and
    spelled back out; anything else that is not a string is somebody's edit.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise SeedsInvalid(
            "%s: own.%s is a %s, expected a quoted string (or blank)"
            % (path, key, type(value).__name__)
        )
    text = str(value).strip()
    return text or None


def load_own(seeds_path: Path | str | None = None) -> Own:
    """The own: block of research/seeds.yaml, or a blank Own when it is blank.

    Only that block is read. Blank is the shipped state and is not an error
    here - the record then carries page_id "" and channel "own", which is
    true - whereas engine.measure refuses a blank block because it would
    have to guess whose account to read.
    """
    path = Path(seeds_path) if seeds_path else DEFAULT_SEEDS
    if not path.exists():
        raise FileNotFoundError(
            "no seeds file at %s; research/seeds.yaml ships with a blank own: "
            "block, so a missing file means a bad checkout rather than nothing "
            "to read." % path
        )
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SeedsInvalid("%s is not YAML this module can read: %s" % (path, exc)) from exc
    if document is None:
        return Own()
    if not isinstance(document, dict):
        raise SeedsInvalid(
            "%s holds a %s at the top level, expected a mapping with an own: block"
            % (path, type(document).__name__)
        )
    block = document.get("own")
    if block is None:
        return Own()
    if not isinstance(block, dict):
        raise SeedsInvalid(
            "%s: own is a %s, expected a mapping with page_id, page_name and "
            "ad_account_id (each may be blank)" % (path, type(block).__name__)
        )
    page_id = _seed_text(block.get("page_id"), path=path, key="page_id")
    if page_id is not None and not _DIGITS_RE.match(page_id):
        raise SeedsInvalid(
            "%s: own.page_id %r is not a Facebook page id (all digits). It is "
            "NOT the page name: read the number out of the Ad Library URL for "
            "the page, and quote it." % (path, page_id)
        )
    return Own(
        page_id=page_id,
        page_name=_seed_text(block.get("page_name"), path=path, key="page_name"),
        ad_account_id=_seed_text(
            block.get("ad_account_id"), path=path, key="ad_account_id"
        ),
    )


# --- the whole launched queue --------------------------------------------


def feed_back(
    *,
    corpus_root: Path | str | None = None,
    measurements_path: Path | str | None = None,
    seeds_path: Path | str | None = None,
    now=None,
    dry_run: bool = False,
) -> FeedbackRun:
    """Every launched ad that has real numbers, as corpus records on disk.

    Reads research/measurements.json, queue/launched/ (through engine.approval,
    so a `<segment>.reel.json` sidecar is never mistaken for a job) and the
    own: block of research/seeds.yaml; writes one record per measured ad with
    engine.corpus.save. One ad producing no record never costs the others
    theirs - the reason is collected and the run carries on - because the
    ordinary case is an ad that went live this week and has not served yet.

    `dry_run` lists where each record would go and touches nothing. `now` is
    handed through to record_for, which does not read it.
    """
    rows = load_measurements(measurements_path)
    own = load_own(seeds_path)
    grouped, skipped = _by_segment(rows)

    written: list[Path] = []
    records: list[dict] = []
    seen: set[str] = set()

    for job in approval.jobs_in("launched"):
        segment = job.segment_id
        seen.add(segment)
        measured = grouped.get(segment)
        if not measured:
            skipped.append(
                "%s: skipped - launched but not measured yet, so there is "
                "nothing it can teach. It becomes a record the week its row "
                "has real impressions." % segment
            )
            continue
        try:
            document = approval.load_job(job)
        except ValueError as exc:
            skipped.append("%s: skipped - %s" % (segment, exc))
            continue
        for row in measured:
            try:
                record = record_for(document, row, own=own, now=now)
                path = (
                    corpus.path_for(record, corpus_root)
                    if dry_run
                    else corpus.save(record, corpus_root)
                )
            except SkippedAd as exc:
                skipped.append(str(exc))
                continue
            except corpus.CorpusInvalid as exc:
                # record_for validated already, so this is the store refusing
                # a record it was handed - reported by name, never half
                # written, and never the end of the run.
                skipped.append(
                    "%s ad %s: skipped - the corpus refused the record: %s"
                    % (segment, _plain(row.get("ad_id")), exc)
                )
                continue
            written.append(path)
            records.append(record)

    # A measurement whose job is not in queue/launched/ is reported rather
    # than dropped: the numbers exist, so either the job was moved or the
    # segment is misspelled, and both are things to go and look at.
    for segment in sorted(set(grouped) - seen):
        skipped.append(
            "%s: skipped - measured, but there is no queue/launched/%s.json to "
            "read the copy from. Either the job moved or the segment is "
            "misspelled." % (segment, segment)
        )

    return FeedbackRun(written=written, skipped=skipped, records=records)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m engine.feedback",
        description=(
            "Our own launched, measured ads as corpus records. Reads three "
            "files and counts words; calls no model and opens no socket."
        ),
    )
    parser.add_argument("--measurements", default=None,
                        help="C6 measurements (default %s)" % DEFAULT_MEASUREMENTS)
    parser.add_argument("--corpus", default=None,
                        help="corpus directory (default %s)" % corpus.DEFAULT_ROOT)
    parser.add_argument("--seeds", default=None,
                        help="seeds file whose own: block names our page "
                             "(default %s)" % DEFAULT_SEEDS)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be written, and write nothing")
    args = parser.parse_args(argv)

    try:
        run = feed_back(
            corpus_root=args.corpus,
            measurements_path=args.measurements,
            seeds_path=args.seeds,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, MeasurementsInvalid, SeedsInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for message in run.skipped:
        print("skipped: %s" % message, file=sys.stderr)
    for path in run.written:
        print("%s %s" % ("would write" if args.dry_run else "wrote", path))
    print(
        "%d record(s) %s, %d skipped"
        % (len(run.written), "to write" if args.dry_run else "written", len(run.skipped)),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
