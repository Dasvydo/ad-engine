"""Concept records -> a scorecard for every one of them, and the best three ads.

Five dimensions decide a concept, and the split between them is the design
decision. FOUR are MEASURED and cost nothing: pattern evidence, claims
survivability, ICP fit and novelty are all read off files already in the tree.
ONE is JUDGED, and the whole fan-out's judgement is bought with a SINGLE model
call that scores every concept at once - one call per run, never one per
concept, because the free tier's daily quota is the budget and N calls buy the
same answer N times over.

That split is engine/gate.py's, deliberately: structural() costs nothing and
runs first, editorial() makes the one model call, run() joins them, and the
result carries the verdict plus the reasons behind it. This module is that
module's sibling for concepts, ported from reel-engine/engine/score.py with the
substitutions docs/CONTRACTS.md names. It reuses engine/gate.py's claims
policy rather than restating it - the same regex, the same attestation file,
the same evidence keys - so a hook attested for the gate is attested here.

Three properties are load-bearing:

  - A concept that fails claims survivability CANNOT be selected, whatever else
    it scores. gate.structural() refuses an unattested number in a spoken
    field, so such a concept is going to die at the gate; selecting it spends
    a write call, a gate call and a render on an ad that cannot ship.
  - Every concept gets a scorecard, not just the winners. A selection nobody can
    audit is an oracle, and an oracle cannot be argued with when it is wrong.
  - Three winners must name three SEGMENTS wherever three exist, and then three
    PLACEMENTS wherever the segments run out. A job is filed at
    queue/proposed/<segment>.json, so two winners on one segment are one ad and
    a refusal - and icp_fit is a pure function of the segment, identical for
    every concept naming it, so ranking on the total alone quietly favours
    whichever segment scores best until the whole top N lands on it. The
    placement pass is the ads-only half: when the eligible concepts name fewer
    segments than there are slots, the remaining slots prefer a different
    placement, so three winners are three ads and not three videos for one
    trade (docs/AD-RESEARCH-SCOPE.md 3.7).

What the ads twin measures differently from the reel one:

  - Pattern evidence reads `median_days_running`, not `median_views`. The Ad
    Library exposes no view count; what it exposes is how long an advertiser's
    own money kept an ad running, which docs/AD-RESEARCH-SCOPE.md 2.3 names as
    the primary signal. Weighed on a log scale to DAYS_FULL, as views were.
  - Novelty compares against the live queue AND creative/*.json: the two
    hand-written arms already carry an angle each, and a concept that re-argues
    "more clients, same team" is not a new ad. creative/example-job.json is the
    writer's worked example, not an ad we run, and is excluded by name.

Nothing here selects on a number it did not check. A patterns file is written by
a counting step and a concept record by a model, so every leaf this module does
arithmetic on is coerced first and named in the scorecard when it cannot be: a
selection run must not die halfway through on a TypeError, and it must not
quietly read junk as zero either.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Mapping

from engine import gate, learn, model
from engine.backlog import Segment
from engine.backlog import load as load_backlog

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATTERNS = learn.DEFAULT_PATH
DEFAULT_QUEUE = ROOT / "queue"
DEFAULT_CREATIVE = ROOT / "creative"

PATTERNS_SCHEMA = learn.SCHEMA

# A job in any of these three directories is live work, so its angle is taken.
# queue/rejected/ is deliberately absent: queue/backlog.md is explicit that a
# parked draft never passed the gate, so neither its segment nor its angle is
# spoken for. The same three stages engine/approval.py calls LIVE_STAGES.
LIVE_STAGES = ("proposed", "built", "launched")

# engine/approval.py writes a reel-engine selection beside a job as
# <segment>.reel.json. It carries the concept that produced the job, not ad
# copy, and its stem is not a segment id - so it is not a job for novelty
# either. Same suffix as approval.REEL_SELECTION_SUFFIX; pinned by a test.
REEL_SELECTION_SUFFIX = ".reel.json"

# The hand-written arms in creative/ each argue an angle, and the writer's
# worked example argues one too - but the example is a teaching file for a
# trade outside the backlog, not an ad we run, so it holds no angle here.
EXAMPLE_JOB = "example-job.json"

# The lines in which an ad argues its own case. `description` is the trade
# line ("Built for accounting, admin and broker firms") and the same words on
# every ad, so it carries no angle and is not compared. Only `en`: da and lt
# are either the placeholder or a native's proofread of the same argument.
JOB_ANGLE_KEYS = ("headline", "primary_text")
JOB_LANGUAGE = "en"

DIMENSIONS = (
    "pattern_evidence",
    "claims_survivability",
    "icp_fit",
    "novelty",
    "editorial",
)

# The four that cost nothing, and the one that costs the run's only model call.
MEASURED = DIMENSIONS[:4]
JUDGED = DIMENSIONS[4]

# Measurement outranks judgement wherever a measurement exists - the repo's
# stated preference (docs/AD-RESEARCH-SCOPE.md 1.2, rule 2), applied to
# selection. The four measured dimensions carry 0.80 of the total between
# them; the model's taste carries 0.20 and cannot outvote the evidence on its
# own. Unchanged from reel-engine, per docs/CONTRACTS.md.
#
# claims survivability is weighted lightest of the five because it is a gate,
# not a gradient: it is worth 1.00 or 0.00, and a 0.00 is expressed as
# exclusion rather than as arithmetic. Its weight only keeps a failed concept's
# printed total honest next to the others.
WEIGHTS = {
    "pattern_evidence": 0.30,
    "claims_survivability": 0.10,
    "icp_fit": 0.25,
    "novelty": 0.15,
    "editorial": 0.20,
}

TOP_N = 3

# A pattern seen in a single ad is a coincidence. engine/corpus.py refuses a
# duplicate id for exactly this reason, so n saturates at three: three
# independent ads is where a device stops being one page's habit.
EVIDENCE_FULL_N = 3

# Days running are weighed on a log scale because longevity is multiplicative
# in what it says: the step from a week to a month says as much about an
# advertiser's conviction as the step from a month to four months. 120 days is
# the ceiling: it is the lower edge of engine/learn.py's top longevity band
# (LONGEVITY_EDGES ends at 120), so a pattern whose median supporter ran four
# months earns full marks, and past it a pattern is not more true, only older.
# ASSUMED from that band edge, not measured against a live corpus - the same
# first guess the band edges themselves are (docs/AD-RESEARCH-SCOPE.md 3.5).
DAYS_FULL = 120

# A live job on the same segment floors the similarity even when the wording
# shares nothing: the segment already has an ad, so a second one is at best a
# second angle on an audience that has already heard from us this month.
SAME_SEGMENT_SIMILARITY = 0.5

# Words that carry no angle. Small and hand-written rather than a dependency -
# the comparison only has to separate "the same argument again" from "a
# different argument", not to do linguistics.
STOPWORDS = frozenset("""
about after again all already also and any are because been before
but can did doing does dont down each even ever every for from get gets
had has have her his how into its just like made make more most much must
never new not now off one only other our out over own put same she should
still such than that the their them then there these they this those
through too under until very was way well were what when where which while
who why will with without would you your yours
""".split())

WORD_RE = re.compile(r"[a-z][a-z'-]*")

# A recurring tag is a LOOKUP when it names a record somebody can fetch -
# "payslip", "tax-code", "deadline". It is a JUDGEMENT CALL when answering it
# means weighing a situation, and queue/backlog.md records what that costs: the
# `allowance` tag was rejected by the editorial gate twice, because "can I claim
# the laptop?" needs a business-use percentage rather than a record.
#
# This vocabulary is the cheap half of that test, and it is a measurement, not
# an opinion: it reads the segment's own three tags out of queue/backlog.md. The
# editorial dimension still reads the concept afterwards.
JUDGEMENT_WORDS = frozenset("""
advice advise advisable allowance appropriate assessment best claimable
correct eligibility eligible estimate fair guess judgement opinion
recommend recommendation reasonable review risk should suitable whether worth
""".split())

# A tag longer than this is a question being asked, not a record being named.
LOOKUP_MAX_WORDS = 2

MODEL_SCORE = model.MODEL_WRITE

# One call carries the whole week's fan-out, and a thinking-capable model spends
# its budget on thinking before it writes a single visible token - the gate
# measured 4096 as too tight for a second pass (engine/gate.py, MAX_TOKENS_GATE,
# measured in reel-engine). Losing this call loses the run, and only the tokens
# actually used are billed, so the ceiling is set where the gate set it rather
# than trimmed to the visible answer.
MAX_TOKENS_SCORE = 16000

RUBRIC = """You are the editorial scorer on an ad engine. Below is a list of
concepts for Meta ads - Reels, feed and static placements - each aimed at one
trade. Score EVERY one of them and return JSON only.

Score ONE thing: how well the hook and the angle would land as the first line
of an ad read by someone in that trade - the line above the fold, before the
image or the video has said anything. Everything else about these concepts is
already measured from files - do NOT score evidence, novelty, originality of
segment, placement, the offer, or whether a number is allowed. Do not reward a
concept for being safe.

A strong concept, 0.8 to 1.0:
  - the hook names a specific, recognisable moment in that trade's week - a
    request that lands, a deadline that recurs, a document asked for again
  - the angle argues something: answering the same client question again and
    again is repetition, not work
  - what it offers can be described rather than promised

A weak concept, 0.0 to 0.3:
  - the hook is a generic complaint about email, busyness or admin that would
    fit any trade equally
  - the angle is a feature list, or a latency or accuracy promise nothing can
    guarantee
  - the hook and the angle are arguing two different things

Return exactly this JSON and nothing that contradicts it:
{"scores": [{"id": "a01", "score": 0.0, "reason": "one sentence"}]}

Every id below must appear exactly once in your answer.

CONCEPTS:
"""


class PatternsInvalid(learn.PatternsInvalid):
    """research/patterns.json is not a readable schema-1 patterns file.

    A subclass of engine/learn.py's, so a caller catching either catches both.
    Named apart from a plain ValueError because the fix is the learn step, not
    the scorer: the message always says which file and which key.
    """


@dataclass(frozen=True)
class Judgement:
    """One concept's editorial score, as the model returned it."""

    score: float
    reason: str


@dataclass(frozen=True)
class Job:
    """A live job in queue/, or a creative/ arm, reduced to what novelty reads.

    `segment` is the filename stem for a queue job - engine/propose.py writes
    <segment>.json and that is the only place a job records which segment it
    belongs to - and None for a creative/ file, whose id is a framing
    ("capacity", "hours") and not a segment. None never matches a concept's
    segment, so the same-segment floor cannot fire on a creative arm.
    """

    stage: str
    segment: str | None
    path: str
    words: frozenset[str]


@dataclass(frozen=True)
class Context:
    """Everything the four measured dimensions read, loaded once per run.

    Held as data rather than re-read per concept so that scoring twelve
    concepts opens the backlog once and the attestation file once, and so a
    test can hand over a context built entirely in a tmp_path with no repo
    state behind it. `evidence` is the SET OF ATTESTATION KEYS -
    gate.evidence_key("hook", hook) is either in it or not.
    """

    patterns: dict[str, dict]
    segments: dict[str, Segment]
    jobs: tuple[Job, ...]
    evidence: frozenset[str]


@dataclass(frozen=True)
class Scorecard:
    """One concept's five scores, why each is what it is, and its fate.

    `total` is a property rather than a stored field so it cannot fall out of
    step with `scores`: the measured dimensions are filled in first and the
    editorial one afterwards, and a stored total would have been computed
    before the model answered. `placement` is carried because the spread
    reads it; it is not a score.
    """

    id: str
    segment: str
    scores: dict[str, float]
    placement: str = ""
    reasons: list[str] = field(default_factory=list)
    eligible: bool = True
    selected: bool = False
    verdict: str = ""

    @property
    def total(self) -> float:
        return round(
            sum(WEIGHTS[d] * float(self.scores.get(d, 0.0)) for d in DIMENSIONS), 4
        )

    def as_dict(self) -> dict:
        """The scorecard as JSON, for whatever writes the audit trail."""
        return {
            "id": self.id,
            "segment": self.segment,
            "placement": self.placement,
            "scores": {d: round(float(self.scores.get(d, 0.0)), 4) for d in DIMENSIONS},
            "total": self.total,
            "eligible": self.eligible,
            "selected": self.selected,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class Selection:
    """The winners, the scorecard for every concept, and what it cost.

    `scorecards` covers every concept that was scored, best first, with the
    excluded ones last. `model_calls` is 1 for a normal run and 0 when there
    was nothing to score - the number the cost ledger cares about.
    """

    selected: list[dict]
    scorecards: list[Scorecard]
    model_calls: int

    def as_dict(self) -> dict:
        return {
            "selected": [c.get("id") for c in self.selected],
            "model_calls": self.model_calls,
            "scorecards": [card.as_dict() for card in self.scorecards],
        }


def _number(value, what: str, notes: list[str]) -> float:
    """A leaf out of a generated file, as a float or as 0.0 plus a note.

    engine/learn.py writes `n` and `median_days_running` as ints, but nothing
    type-checks a patterns file on the way back in, so a string, a null or a
    list reaches this module intact. Both failure modes have to be avoided at
    once: a TypeError halfway through loses every scorecard computed before
    it, and silently reading junk as zero loses the reason it was zero. bool
    is refused on purpose - True is not one day.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        notes.append("%s is %r, not a number; counted as 0" % (what, value))
        return 0.0
    if not math.isfinite(value):
        notes.append("%s is %r, which is not a usable number; counted as 0" % (what, value))
        return 0.0
    return float(value)


def _words(text) -> frozenset[str]:
    """The content words of a line, lowercased, for comparing two arguments."""
    found = WORD_RE.findall(str(text).replace("**", "").lower())
    return frozenset(w for w in found if len(w) > 2 and w not in STOPWORDS)


def _overlap(a: frozenset[str], b: frozenset[str]) -> float:
    """How much of the smaller phrasing the larger one already contains.

    The overlap coefficient, not Jaccard: a hook is a dozen words and a
    primary text is three paragraphs, so Jaccard would score a word-for-word
    copy of the hook at about 0.2 and call it novel. Containment answers the
    question actually being asked - has this been said already.
    """
    if not a or not b:
        return 0.0
    return len(a & b) / float(min(len(a), len(b)))


def load_patterns(path: Path | None = None) -> dict[str, dict]:
    """research/patterns.json, as {pattern id: pattern record}.

    Absence is an error rather than an empty dict: scoring pattern evidence
    against no patterns gives every concept the same zero, which looks like a
    ranking and is not one. engine/learn.py's own loader reads the file and
    checks the schema (its FileNotFoundError names the command to run); this
    only adds the by-id view a concept's citations are resolved against.
    """
    path = Path(path) if path else DEFAULT_PATTERNS
    data = learn.load(path)

    patterns = data.get("patterns")
    if not isinstance(patterns, list):
        raise PatternsInvalid(
            "%s key 'patterns' must be a list; got %s"
            % (path, type(patterns).__name__)
        )

    by_id = {}
    for entry in patterns:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise PatternsInvalid(
                "%s contains a pattern with no string id: %r; a concept cites "
                "patterns by id, so an unidentified one can never be scored"
                % (path, entry)
            )
        if entry["id"] in by_id:
            # Last-wins would score a concept against whichever copy happened
            # to come second. engine/concepts.py refuses the same file for the
            # same reason: a concept traceable to two pieces of evidence is
            # traceable to neither.
            raise PatternsInvalid(
                "%s repeats pattern id %r; one pattern is one id, so re-id or "
                "drop whichever is wrong" % (path, entry["id"])
            )
        by_id[entry["id"]] = entry
    return by_id


def _angle_words(content: dict) -> frozenset[str]:
    """The words of headline.en and primary_text.en, however the file spells
    them: a {en, da, lt} map (C3, creative/*.json) or a bare string (an older
    hand-written arm). A view, not a validator - the gate ran already."""
    words: frozenset[str] = frozenset()
    for key in JOB_ANGLE_KEYS:
        value = content.get(key, "")
        if isinstance(value, dict):
            value = value.get(JOB_LANGUAGE, "")
        if isinstance(value, str):
            words |= _words(value)
    return words


def _read_job(path: Path) -> dict | None:
    """The JSON object in a job file, or None for anything that is not one.

    A malformed or unreadable file is skipped rather than raised on: it is
    somebody else's half-written state, and refusing to score this week's
    concepts because last month's job file has a stray comma in it would be
    the wrong trade.
    """
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return content if isinstance(content, dict) else None


def _queue_jobs(queue_root: Path) -> list[Job]:
    jobs = []
    for stage in LIVE_STAGES:
        stage_dir = queue_root / stage
        if not stage_dir.is_dir():
            continue
        for path in sorted(stage_dir.glob("*.json")):
            if path.name.endswith(REEL_SELECTION_SUFFIX):
                continue
            content = _read_job(path)
            if content is None:
                continue
            jobs.append(Job(
                stage=stage,
                segment=path.stem,
                path="queue/%s/%s" % (stage, path.name),
                words=_angle_words(content),
            ))
    return jobs


def _creative_jobs(creative_root: Path) -> list[Job]:
    jobs = []
    if not creative_root.is_dir():
        return jobs
    for path in sorted(creative_root.glob("*.json")):
        if path.name == EXAMPLE_JOB:
            continue
        content = _read_job(path)
        if content is None:
            continue
        jobs.append(Job(
            stage="creative",
            segment=None,
            path="creative/%s" % path.name,
            words=_angle_words(content),
        ))
    return jobs


def load_jobs(
    queue_root: Path | None = None, creative_root: Path | None = None
) -> tuple[Job, ...]:
    """Every live job under queue/ and every arm under creative/, reduced to
    segment plus angle words. Queue jobs first, in stage then filename order;
    creative arms after, in filename order, minus the worked example."""
    queue_root = Path(queue_root) if queue_root else DEFAULT_QUEUE
    creative_root = Path(creative_root) if creative_root else DEFAULT_CREATIVE
    return tuple(_queue_jobs(queue_root) + _creative_jobs(creative_root))


def load_context(
    *,
    patterns_path: Path | None = None,
    backlog_path: Path | None = None,
    queue_root: Path | None = None,
    creative_root: Path | None = None,
    evidence: Mapping | Iterable[str] | None = None,
) -> Context:
    """Read the four measured dimensions' inputs. No model, no network.

    `evidence` is the attestation table (gate.load_attestations()'s mapping)
    or just its keys; None reads claims/evidence.json once. Either way the
    context keeps the key set, which is all _claims_survivability asks.
    """
    segments = {s.id: s for s in load_backlog(backlog_path)}
    entries = gate.load_attestations() if evidence is None else evidence
    return Context(
        patterns=load_patterns(patterns_path),
        segments=segments,
        jobs=load_jobs(queue_root, creative_root),
        evidence=frozenset(entries),
    )


def _pattern_ids(concept: Mapping) -> list[str]:
    """The cited pattern ids, however the concept writer phrased them.

    A single id arriving as a bare string rather than a list is the same defect
    class engine/gate.py handles for the model's "failures" field, and iterating
    that string would cite one pattern per letter.
    """
    cited = concept.get("pattern_ids")
    if cited is None:
        return []
    if isinstance(cited, str):
        return [cited]
    if not isinstance(cited, (list, tuple)):
        return []
    return [c for c in cited if isinstance(c, str)]


def _days_score(days: float) -> float:
    """Longevity on a log scale, 0.0 at no days and 1.0 at DAYS_FULL.

    log1p rather than log so that 0 - engine/learn.py's sentinel for "no
    supporting ad carried a usable value" - is a plain zero, not a domain
    error, and so that the curve is the reel scorer's over views.
    """
    clipped = min(max(days, 0.0), float(DAYS_FULL))
    return math.log1p(clipped) / math.log1p(float(DAYS_FULL))


def _pattern_evidence(concept: Mapping, context: Context) -> tuple[float, str]:
    """How well-supported are the patterns this concept leans on.

    Per pattern: half the score from `n` (how many ads showed the device) and
    half from `median_days_running` (how long an advertiser's money kept them
    running when they did). Averaged over the cited patterns rather than
    maxed, because a hook resting on a strong pattern and a weak one really is
    resting on both.
    """
    cited = _pattern_ids(concept)
    if not cited:
        return 0.0, "cites no pattern, so the hook traces to no measured ad"

    notes = []
    scores = []
    for pattern_id in cited:
        pattern = context.patterns.get(pattern_id)
        if pattern is None:
            notes.append("%s is not in the patterns file" % pattern_id)
            scores.append(0.0)
            continue
        n = _number(pattern.get("n"), "%s n" % pattern_id, notes)
        days = _number(
            pattern.get("median_days_running"),
            "%s median_days_running" % pattern_id,
            notes,
        )
        n_score = min(max(n, 0.0), EVIDENCE_FULL_N) / float(EVIDENCE_FULL_N)
        scores.append(0.5 * n_score + 0.5 * _days_score(days))
        notes.append("%s n=%g median_days_running=%g" % (pattern_id, n, days))

    return sum(scores) / float(len(scores)), "; ".join(notes)


def _claims_survivability(concept: Mapping, context: Context) -> tuple[float, str]:
    """Would this concept's hook survive engine/gate.py's number policy.

    Binary on purpose, because the policy it mirrors is binary: structural()
    refuses outright a number in a spoken field that claims/evidence.json does
    not attest. A concept that needs one is a write call already spent.

    Same field name, same hashing, same file as the gate and as reel-engine's
    build: gate.unattested_numbers("hook", hook) against the context's key
    set, so a hook attested for the reel build is attested here, and an
    operator who can attest one can attest the other.
    """
    if concept.get("needs_numbers"):
        return 0.0, (
            "needs_numbers is set, and engine/gate.py refuses a number in a "
            "spoken field unless claims/evidence.json attests it"
        )

    hook = concept.get("hook", "")
    found = gate.NUM_RE.findall(gate.spoken(hook))
    if not found:
        return 1.0, "no number in the hook, and needs_numbers is not set"

    key = gate.evidence_key("hook", hook)
    unattested = gate.unattested_numbers("hook", hook, attestations=context.evidence)
    if not unattested:
        return 1.0, "the hook's number is attested in claims/evidence.json (%s)" % key[:12]

    return 0.0, (
        "the hook contains %s with no attestation in claims/evidence.json.\n"
        "    text: %s\n"
        "    add:  %r: {\"kind\": \"measured|architectural|illustrative\", "
        "\"field\": \"hook\", \"text\": %r, \"source\": \"...\", \"asOf\": \"YYYY-MM-DD\"}"
        % (", ".join(repr(f) for f in unattested), gate.spoken(hook), key, gate.spoken(hook))
    )


def _is_lookup(question: str) -> bool:
    """Is this recurring tag a record to fetch, or a situation to weigh."""
    words = WORD_RE.findall(str(question).lower())
    if not words or len(words) > LOOKUP_MAX_WORDS:
        return False
    return not any(w in JUDGEMENT_WORDS for w in words)


def _icp_fit(concept: Mapping, context: Context) -> tuple[float, str]:
    """Is this segment one we sell to, and can its questions be answered.

    Two facts, both on disk. A segment absent from queue/backlog.md is outside
    the locked ICP (or parked, which backlog.md writes as prose precisely so the
    parser cannot return it), and nothing downstream would pick it up anyway.
    Present, the score is the share of its three tags that read as lookups -
    queue/backlog.md's own rule, and gate G3's.
    """
    segment_id = concept.get("segment")
    segment = context.segments.get(segment_id) if isinstance(segment_id, str) else None
    if segment is None:
        return 0.0, (
            "segment %r is not a row in queue/backlog.md, so it is off-ICP, "
            "parked, or misspelled" % (segment_id,)
        )

    judgement = [q for q in segment.questions if not _is_lookup(q)]
    lookups = len(segment.questions) - len(judgement)
    fit = lookups / float(len(segment.questions))
    if judgement:
        return fit, "backlog rank %d; %s read as judgement calls, not lookups" % (
            segment.rank,
            ", ".join(repr(q) for q in judgement),
        )
    return fit, "backlog rank %d; all three tags read as lookups" % segment.rank


def _novelty(concept: Mapping, context: Context) -> tuple[float, str]:
    """Has this angle already been made.

    Compared against the jobs in queue/proposed, built and launched - the
    three directories that mean live work - and against the arms in
    creative/. Two measurements: how much of the concept's own wording a live
    job already contains, and whether a live job holds this segment at all.
    The segment floor applies to queue jobs only: a creative arm names a
    framing, not a segment, so it can share wording but cannot hold a trade.
    """
    if not context.jobs:
        return 1.0, "no live job in queue/proposed, built or launched, and no creative/ arm"

    mine = _words(concept.get("angle", "")) | _words(concept.get("hook", ""))
    segment_id = concept.get("segment")
    worst = 0.0
    why = "no live job or creative arm argues this angle"
    for job in context.jobs:
        similarity = _overlap(mine, job.words)
        reason = "%s shares %.0f%% of this angle's wording" % (
            job.path,
            100.0 * similarity,
        )
        same_segment = (
            job.segment is not None
            and isinstance(segment_id, str)
            and job.segment == segment_id
        )
        if same_segment and similarity < SAME_SEGMENT_SIMILARITY:
            similarity = SAME_SEGMENT_SIMILARITY
            reason = "%s already holds this segment" % job.path
        if similarity > worst:
            worst, why = similarity, reason

    return max(0.0, 1.0 - worst), why


# The four measured dimensions and what computes each. Keyed by the names in
# DIMENSIONS, so a renamed dimension is a KeyError here rather than a scorecard
# quietly missing a score.
MEASURED_SCORERS = {
    "pattern_evidence": _pattern_evidence,
    "claims_survivability": _claims_survivability,
    "icp_fit": _icp_fit,
    "novelty": _novelty,
}


def _concept_id(concept: Mapping, index: int) -> str:
    concept_id = concept.get("id")
    if not isinstance(concept_id, str) or not concept_id.strip():
        raise ValueError(
            "concept %d has id %r; a scorecard is addressed by id and the "
            "editorial scores come back keyed by it, so an unidentified "
            "concept cannot be scored" % (index, concept_id)
        )
    return concept_id


def _text_field(concept: Mapping, key: str) -> str:
    value = concept.get(key)
    return value if isinstance(value, str) else ""


def measured(concept: Mapping, context: Context, *, index: int = 0) -> Scorecard:
    """The four dimensions that cost nothing. No client, no network, no tokens.

    gate.structural()'s sibling: it runs first, it is free, and its verdict on
    claims survivability is final - nothing the model says later can revive a
    concept this refuses.
    """
    scores = {}
    reasons = []
    for name in MEASURED:
        value, why = MEASURED_SCORERS[name](concept, context)
        value = min(max(float(value), 0.0), 1.0)
        scores[name] = value
        reasons.append("%s %.2f: %s" % (name.replace("_", " "), value, why))

    # Unscored until editorial() runs, and named here so a scorecard is never
    # short a dimension - a missing key would read as a zero with no reason.
    scores[JUDGED] = 0.0

    return Scorecard(
        id=_concept_id(concept, index),
        segment=_text_field(concept, "segment"),
        placement=_text_field(concept, "placement"),
        scores=scores,
        reasons=reasons,
        eligible=scores["claims_survivability"] > 0.0,
    )


def _editorial_payload(concept: Mapping, index: int) -> dict:
    """What the model is shown: the words, and nothing that is measured.

    Deliberately not the whole concept record. needs_numbers and pattern_ids
    are already scored from files, and the offer is checked from a table by
    engine/concepts.py; sending any of them would invite the model to score
    them again - a second, unmeasured opinion on a settled question. The
    placement goes in because the first line of a Reel and the first line of
    a static image are read differently. Nothing from docs/ICP-BRIEF.md is
    sent here or anywhere else.
    """
    return {
        "id": _concept_id(concept, index),
        "segment": concept.get("segment", ""),
        "angle": concept.get("angle", ""),
        "hook": concept.get("hook", ""),
        "placement": concept.get("placement", ""),
    }


def editorial(concepts: Iterable, *, client=None) -> dict[str, Judgement]:
    """The one judged dimension, for EVERY concept, in EXACTLY ONE model call.

    One call, not one per concept. The concepts are scored against each other in
    a single prompt because that is the same answer for a twelfth of the quota -
    and because a model shown all twelve can rank them, where twelve independent
    calls each score in a vacuum and cluster around the same safe number.

    Returns {concept id: Judgement}. A concept the model did not score is absent
    from the mapping; the caller records that as a zero with a reason rather
    than pretending the dimension was measured. client=None builds
    model.client(), which raises ConfigError naming GEMINI_API_KEY before any
    socket.
    """
    concepts = list(concepts)
    if not concepts:
        # Nothing to score is not a reason to spend a call.
        return {}

    client = client or model.client()
    payload = [_editorial_payload(c, i) for i, c in enumerate(concepts)]

    response = model.call_model(
        client,
        model=MODEL_SCORE,
        max_tokens=MAX_TOKENS_SCORE,
        messages=[{
            "role": "user",
            "content": RUBRIC + json.dumps(payload, ensure_ascii=True, indent=2),
        }],
    )

    if response.stop_reason == "max_tokens":
        raise ValueError(
            "the editorial scores were truncated at max_tokens; a partial "
            "ranking would silently drop whichever concepts came last, so the "
            "run stops here. Re-run: the budget is a ceiling, not a spend"
        )

    # A thinking-capable model leads with thinking blocks, which carry no .text
    # at all. text_of takes the first block that says it is text.
    text = model.text_of(response)

    parsed = model.first_json_object(text)
    if parsed is None or not isinstance(parsed.get("scores"), list):
        raise ValueError(
            "could not read editorial scores from the model; expected "
            '{"scores": [{"id": ..., "score": ..., "reason": ...}]}, got %r'
            % text[:300]
        )

    judged = {}
    for entry in parsed["scores"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        notes: list[str] = []
        value = _number(entry.get("score"), "editorial score", notes)
        reason = entry.get("reason")
        reason = str(reason) if reason else "no reason given"
        if notes:
            reason = "%s (%s)" % (reason, "; ".join(notes))
        judged[entry["id"]] = Judgement(score=min(max(value, 0.0), 1.0), reason=reason)
    return judged


@dataclass(frozen=True)
class Spread:
    """What _spread decided, and enough of how to word every verdict.

    `by_segment` is {segment: the winner that took it first}, `by_placement`
    {placement: the winner that took it first}, and `placement_passed` the
    ids the placement pass looked at and skipped because their placement was
    already held - so a verdict can say that was the reason, rather than
    guess it from the totals.
    """

    winners: list[Scorecard]
    by_segment: dict[str, Scorecard]
    by_placement: dict[str, Scorecard]
    placement_passed: frozenset[str]


def _spread(eligible: list[Scorecard], top: int) -> Spread:
    """The best `top` scorecards: one per segment, then one per placement.

    Three passes, all in score order. The first takes the best card on each
    segment not yet spoken for: engine/propose.py files a job at
    queue/proposed/<segment>.json, so three winners on three segments are three
    ads, while three winners on one segment are one ad and two refusals - and
    engine/concepts.py only ASKS the model to spread its concepts across the
    segments, which is a request, not a guarantee.

    The second pass runs only when the eligible concepts name fewer segments
    than there are slots. Among the cards not yet chosen it takes the best on
    each placement no winner holds yet - the placements of the first pass's
    winners count as held - so that when a trade has to carry two ads they are
    a Reel and a static rather than two Reels. The third pass fills whatever
    is still open in plain score order: a rule that exists to protect an ad
    must not cost one.
    """
    winners: list[Scorecard] = []
    by_segment: dict[str, Scorecard] = {}
    by_placement: dict[str, Scorecard] = {}
    chosen: set[str] = set()

    def take(card: Scorecard) -> None:
        winners.append(card)
        chosen.add(card.id)
        by_segment.setdefault(card.segment, card)
        by_placement.setdefault(card.placement, card)

    for card in eligible:
        if len(winners) >= top:
            break
        if card.segment in by_segment:
            continue
        take(card)

    # A card skipped here was passed over FOR ITS PLACEMENT only if a card
    # below it was then taken for having a free one; skips with no later take
    # lost nothing to this pass, and saying otherwise would send the operator
    # after a placement problem that is not there.
    placement_passed: set[str] = set()
    pending: list[str] = []
    for card in eligible:
        if len(winners) >= top:
            break
        if card.id in chosen:
            continue
        if card.placement in by_placement:
            pending.append(card.id)
            continue
        take(card)
        placement_passed.update(pending)
        pending.clear()

    for card in eligible:
        if len(winners) >= top:
            break
        if card.id in chosen:
            continue
        take(card)

    return Spread(
        winners=winners,
        by_segment=by_segment,
        by_placement=by_placement,
        placement_passed=frozenset(placement_passed) - chosen,
    )


def select(
    concepts: Iterable,
    *,
    context: Context | None = None,
    client=None,
    top: int = TOP_N,
) -> Selection:
    """Score every concept, then take the best `top` that could actually ship.

    gate.run()'s sibling: the free dimensions first, then the single model call,
    then the verdict. What gate.run() saves by ordering them that way is tokens;
    what this saves is a wasted write and render, because the free half decides
    eligibility and nothing the model says afterwards can overturn it.

    "Best" is best-per-segment first, best-per-placement second and only then
    best-by-total - see _spread() - because `top` winners on one segment are
    not `top` ads. A concept the spread costs a slot is not dropped from the
    report: its scorecard says which concept took its segment (or its
    placement) and that it outscored a winner, so the trade this made is on
    the record and can be argued with.
    """
    if top < 0:
        raise ValueError("top must not be negative; got %r" % top)

    concepts = list(concepts)
    context = context if context is not None else load_context()

    cards = [measured(c, context, index=i) for i, c in enumerate(concepts)]

    seen: set[str] = set()
    for card in cards:
        if card.id in seen:
            raise ValueError(
                "duplicate concept id %r; scorecards and editorial scores are "
                "both keyed by id, so two concepts sharing one would overwrite "
                "each other's verdict" % card.id
            )
        seen.add(card.id)

    # Every concept goes into the one call, the doomed ones included: it is the
    # same single call either way, and a scorecard with a hole in it is worth
    # less than the handful of tokens it saves.
    judged = editorial(concepts, client=client)
    model_calls = 1 if concepts else 0

    scored = []
    for card in cards:
        judgement = judged.get(card.id)
        if judgement is None:
            value, why = 0.0, "the model returned no score for this concept"
        else:
            value, why = judgement.score, judgement.reason
        scores = dict(card.scores)
        scores[JUDGED] = value
        scored.append(
            replace(
                card,
                scores=scores,
                reasons=card.reasons + ["editorial %.2f: %s" % (value, why)],
            )
        )

    # Sorted by total, then by id, so identical inputs always select the same
    # three - a tie broken by list order would make the selection depend on
    # whatever order the concept writer happened to emit.
    ranked = sorted(scored, key=lambda c: (-c.total, c.id))
    eligible = [c for c in ranked if c.eligible]
    excluded = [c for c in ranked if not c.eligible]
    spread = _spread(eligible, top)

    chosen = {card.id for card in spread.winners}
    floor = min((card.total for card in spread.winners), default=0.0)

    # Who the spread cost a slot: in the top `top` on score alone, and not a
    # winner. Derived by comparing the two orders rather than guessed at from
    # the totals, so no verdict below claims a reason that was not the reason -
    # a concept that merely tied with the last winner lost on the id tiebreak,
    # not on its segment.
    displaced = {card.id for card in eligible[:top]} - chosen

    # Phrased once, so every concept below the line is told the same thing.
    cut = (
        "below the cut at %.4f" % floor
        if spread.winners
        else "below a cut of none - top was 0, so nothing could be selected"
    )

    final = []
    for rank, card in enumerate(eligible, start=1):
        first = spread.by_segment.get(card.segment)
        if card.id in chosen:
            verdict = "selected: rank %d of %d eligible, total %.4f" % (
                rank, len(eligible), card.total,
            )
            if first is not None and first.id != card.id:
                # A second winner on one segment, which only happens once the
                # eligible concepts have run out of segments. Said out loud
                # because one queue/proposed/ file can hold exactly one of them.
                verdict += (
                    "; %s already holds segment %r, so only one of the two can "
                    "be filed at queue/proposed/%s.json - the eligible concepts "
                    "named fewer than %d segments between them"
                    % (first.id, card.segment, card.segment, top)
                )
        elif card.id in displaced:
            holder = first.id if first is not None else "a higher-ranked winner"
            if card.id in spread.placement_passed:
                taken = spread.by_placement.get(card.placement)
                verdict = (
                    "not selected: rank %d of %d eligible, total %.4f, passed over "
                    "for segment and placement diversity - %s already won segment "
                    "%r (one segment is one job file, queue/proposed/%s.json) and "
                    "%s already won placement %r among the rest (two winners on "
                    "one placement for one trade are two of the same creative), "
                    "so a lower-scoring concept took the slot "
                    "(lowest selected total %.4f)"
                    % (rank, len(eligible), card.total, holder, card.segment,
                       card.segment,
                       taken.id if taken is not None else "a higher-ranked winner",
                       card.placement, floor)
                )
            else:
                verdict = (
                    "not selected: rank %d of %d eligible, total %.4f, passed over "
                    "for segment diversity - %s already won segment %r, and one "
                    "segment is one job file (queue/proposed/%s.json), so a "
                    "lower-scoring concept on a free segment took the slot "
                    "(lowest selected total %.4f)"
                    % (rank, len(eligible), card.total, holder, card.segment,
                       card.segment, floor)
                )
        else:
            verdict = "not selected: rank %d of %d eligible, total %.4f, %s" % (
                rank, len(eligible), card.total, cut,
            )
        final.append(replace(card, selected=card.id in chosen, verdict=verdict))

    for card in excluded:
        final.append(replace(
            card,
            selected=False,
            verdict=(
                "excluded: claims survivability is 0.00, so engine/gate.py would "
                "refuse this ad whatever else it scored (total %.4f)"
                % card.total
            ),
        ))

    by_id = {_concept_id(c, i): c for i, c in enumerate(concepts)}
    selected = [by_id[card.id] for card in final if card.id in chosen]

    return Selection(selected=selected, scorecards=final, model_calls=model_calls)
