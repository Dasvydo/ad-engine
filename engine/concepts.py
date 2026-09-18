"""Learned patterns + the segment backlog -> N ad concepts, in ONE call.

A port of reel-engine/engine/concepts.py. The reel loop's concept is the seed
of a video; this one is the seed of a Meta ad, and an ad is two things a reel
is not: it runs somewhere (a placement - a vertical Reel, a feed video, or a
square still, which is what tells the writer whether a video is being asked
for) and it may make an offer (one this business actually makes, checked
from claims/evidence.json rather than judged). Those are the two keys added
to the record; everything else is the sibling's design, kept because it is
what makes the stage trustworthy.

One model call writes all N. A call per concept would spend N times the free
tier's quota to buy nothing: every concept is written against the same patterns
and the same backlog, and writing them together is the only thing that stops
them being N rewordings of the same idea - a model cannot avoid repeating
itself across calls it cannot see.

Four referential rules are enforced here rather than left to review, because
they are the point of this stage:

  - every concept cites at least one pattern id that exists in the patterns
    file it was given. A hook citing q07 when no q07 was ever counted is an
    invented hook wearing a citation, and the whole research -> learn ->
    concept chain exists so a hook traces back to an ad that an advertiser's
    own money demonstrably kept running. An unknown id raises
    UnknownPatternError rather than being dropped: a concept that loses its
    citation looks identical to one that never had a claim to make.
  - every concept names a segment id from the backlog it was given. A concept
    aimed at an audience nobody ranked cannot become a job.
  - every concept names a placement the gate accepts. The writer stamps
    creative_source from it, so a placement nobody renders is a job that
    cannot be built.
  - every concept offers "none" or an offer whose status in
    claims/evidence.json is verified. A free trial does not exist, and a
    concept built on one is a promise the copy would have to keep.

The `id` field is stamped here, not written by the model - it is bookkeeping,
not words, and a01..a12 has to be stable and sortable for the scorer that reads
these next. The prefix is `a` so an ad concept can never be mistaken for one of
the reel loop's c-ids, the same reason the patterns here are q-ids and not
p-ids.

The ICP brief is never opened by this module and nothing from it reaches a
prompt. The audience context a model sees is exactly what the reel loop's
writer already sends: a segment's trade, its three recurring questions, and
its note. What an offer means reaches the prompt as its safe phrasing from
claims/evidence.json, never as the evidence line that cites the brief.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

from engine import gate
from engine import learn
from engine import model
from engine.backlog import Segment
from engine.model import call_model

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATTERNS = ROOT / "research" / "patterns.json"

MODEL_CONCEPTS = model.MODEL_WRITE

# Twelve is what the scorer needs to have a real choice: it picks three, and a
# shortlist of three is not a shortlist. A parameter, because the right number
# moves with how many patterns the corpus has actually earned.
DEFAULT_N = 12

# The schema of research/patterns.json this module reads.
SCHEMA = 1

# Every key the C5 patterns contract fixes, as engine.learn writes them.
# `kind` is deliberately NOT checked against learn.KINDS: a learn step that
# finds a tenth kind must not be rejected by the module that consumes it, and
# a concept cites an id, not a kind.
PATTERN_KEYS = (
    "id", "kind", "device", "description", "evidence",
    "median_days_running", "median_reach", "n",
)

# The gate's tuple, not a copy of it: a concept's placement becomes the job's
# placement unchanged, and the gate is what refuses a job. Two tuples would
# be two places for one list to drift apart.
PLACEMENTS = gate.PLACEMENTS

# What each placement asks the writer for. The writer stamps creative_source
# from the placement (a reel for the two video slots, a still for the
# square), so the model has to read a placement as a request for a video or
# for a picture, not as a size.
PLACEMENT_NOTES = {
    "reels-9x16": "a vertical video in Reels, built from this concept's hook",
    "feed-4x5": "a video in the feed, usually watched with the sound off",
    "static-1x1": "a still image in the feed; the copy does all the work",
}

# The offer that is no offer. Always allowed: an ad that argues and asks for
# nothing has nothing to verify.
NO_OFFER = "none"

# The concept record. The scorer and the writer read exactly these, so nothing
# is added and nothing is renamed here.
AUTHORED = ("segment", "angle", "hook", "pattern_ids", "placement", "offer",
            "needs_numbers")
KEYS = ("id",) + AUTHORED

# A thinking-capable model spends its budget on thinking before it writes a
# visible token, so the ceiling has to cover both. Only what is used is billed,
# which makes a tight value pure downside - and this is the call that cannot be
# lost cheaply, because a run makes exactly one of it. The floor matches the
# other one-call stages; it grows past DEFAULT_N because N is a parameter and
# headroom for twelve concepts is not headroom for forty.
MAX_TOKENS_BASE = 16000
MAX_TOKENS_PER_EXTRA_CONCEPT = 400


def max_tokens_for(n: int) -> int:
    return MAX_TOKENS_BASE + MAX_TOKENS_PER_EXTRA_CONCEPT * max(0, n - DEFAULT_N)


INSTRUCTION = """Write {n} ad concepts for a Meta ad engine.

A concept is the seed of one ad: who it is for, what it argues, its opening
line, where it runs and what it offers. A later step writes the whole ad from
it and an editorial gate judges that copy, so a concept that cannot survive
the gate is wasted work here.

THE AD. A Meta ad is a primary text (the paragraph above the creative; only
its first sentence shows before "See more"), a headline of at most
{headline_limit} characters, a description of at most {description_limit},
one call-to-action button, and a creative in ONE placement:

{placements}

It may make ONE offer. Only these are real; anything else is a promise the
copy would have to keep:

{offers}

PATTERNS. Each was measured on real ads in this market - ads that
advertisers kept paying to run for a long time, which is the one number the
Ad Library exposes that somebody's own money has voted on. `evidence` lists
the ads it was read off, `median_days_running` is how long those ads ran,
`median_reach` is how many EU users they reached, and `n` is how many there
were. Draw on a pattern BECAUSE it worked, and say which.

{patterns}

SEGMENTS. The audience backlog, highest priority first. `questions` are the
three things that audience is asked over and over, and they are the subject
matter of the ad: the argument is that a knowledge base can answer them.

{segments}

Return ONLY a JSON object of this shape, holding EXACTLY {n} concepts:

  {{"concepts": [{{"segment": "...", "angle": "...", "hook": "...",
                 "pattern_ids": ["..."], "placement": "...",
                 "offer": "...", "needs_numbers": false}}]}}

Each concept object has exactly these keys: {authored}

  segment        one of the segment ids above, spelled exactly.
  angle          one sentence: what this ad argues to that audience.
  hook           the first sentence of the primary text - what a reader sees
                 before "See more" - under 90 characters. For a video
                 placement it is also the spoken first line.
  pattern_ids    the patterns this concept is built on, at least one, spelled
                 exactly as listed above.
  placement      one of the placement ids above, spelled exactly.
  offer          "{no_offer}", or one of the offer ids above, spelled exactly.
  needs_numbers  JSON true or false. Never a string.

HARD FAILURES. This step rejects the whole reply on any of these, and the run
is wasted:

  - exactly {n} concepts. Not one fewer, not a round dozen when {n} is asked.
  - every pattern_ids entry is an id from the list above. An id that is not
    there is rejected by name: a citation pointing at nothing is worse than no
    citation, because it reads as evidence.
  - segment is an id from the list above.
  - placement is one of the placement ids above.
  - offer is "{no_offer}" or one of the offer ids above. A free trial, a
    discount, a price, a bonus: none of these exists, and a concept that
    depends on one is rejected by name.
  - needs_numbers is a JSON boolean.
  - do not add, rename or drop a key, and do not write an id field - ids are
    stamped afterwards.

needs_numbers DECIDES WHETHER A CONCEPT CAN BE BUILT AT ALL. Set it true when
the argument DEPENDS on a specific statistic: "bureaus lose four hours a week"
only lands if the four is real. The gate downstream hard-fails any copy
carrying an unattested number, and it matches number WORDS as well as digits,
so a concept that needs a figure usually dies at the gate. Write most of them
so they need none - describe the repetition rather than counting it. Mark it
honestly either way: a concept that needs a number and says it does not dies
later instead, and takes the run with it.

STRONG STYLE REQUIREMENTS. None of these is checked, so no error will tell you
when you miss one - but a human reads these and drops the weakest:

  - spread the concepts across the segments rather than writing {n} for the
    first one, AND across the placements rather than making every concept a
    Reel: the scorer picks winners per segment first and per placement
    second, so three winners should be three different ads, not three videos
    for one trade. Each segment's angle must be its own; the same argument
    re-pointed at another trade is one concept, not two.
  - the hook must carry the device of the pattern it cites. Citing a
    negative-flip and then writing a plain question is a citation that is not
    true.
  - the hook names a moment in that trade's week - the payslip query that
    lands on Monday, the receipt that arrives as a photo - not a generic
    complaint about email.
  - no two hooks share an opening construction.
  - keep numbers and number words out of the hook unless needs_numbers is
    true. The gate matches every one of these as a number:
{number_words}
    "one" is the word that catches honest writing.
  - never promise accuracy and never promise latency. "It never guesses a
    figure" and "replies ready before you open your inbox" are the two most
    reliable ways to fail the editorial gate. Describe what the thing does
    instead: "it shows where each figure came from", "the reply is waiting
    in your drafts".
  - never claim that a customer, a logo, a testimonial or a measured outcome
    exists. None does yet, and the gate knows it.
  - the three questions are lookups, not judgement calls - that is why the
    segment is ranked at all. If a segment's questions read as judgement calls
    to you, write no concept for it and use the others.

If no segment above can honestly carry an ad, return
{{"refuse": "one sentence saying why"}} instead.
"""


class ConceptsError(ValueError):
    """A concepts run that cannot be trusted.

    A ValueError, like the rest of the data contracts in this engine, so a
    caller already catching ValueError around a model step keeps working. The
    message always names the offending concept, pattern, placement or offer
    id, because the reader is an operator looking at twelve near-identical
    records.
    """


class PatternsInvalid(ConceptsError, learn.PatternsInvalid):
    """research/patterns.json is not a complete schema-1 document.

    Also an engine.learn.PatternsInvalid, so a caller that catches the
    writer's class catches the reader's too: the fix is the same file.
    """


class ConceptInvalid(ConceptsError):
    """A concept the model returned is not a complete C4 record."""


class UnknownPatternError(ConceptInvalid):
    """A concept cites a pattern id that is not in the patterns file.

    Its own class because it is the failure this stage exists to catch, and
    because a caller may want to retry on it - a re-roll can fix an invented
    citation, where a missing key usually means the prompt drifted.
    """


class UnknownSegmentError(ConceptInvalid):
    """A concept names a segment id that is not in the backlog it was given."""


def validate_patterns(document, *, source: Path | None = None) -> list[dict]:
    """Raise PatternsInvalid unless `document` is a complete schema-1 patterns
    document, and return its patterns.

    Nothing is coerced and nothing is defaulted: a pattern missing `evidence`
    is a bug in the learn step, and filling it in here would hide that bug
    behind concepts that look cited.
    """
    where = f"the patterns document ({source})" if source else "the patterns document"

    if not isinstance(document, dict):
        raise PatternsInvalid(
            f"{where} must be a JSON object with a 'patterns' list; got "
            f"{type(document).__name__}"
        )

    if document.get("schema") != SCHEMA:
        raise PatternsInvalid(
            f"{where} has schema {document.get('schema')!r}; this module reads "
            f"schema {SCHEMA} only. Regenerate the file with python -m "
            f"engine.learn or bump SCHEMA in engine/concepts.py - reading an "
            f"unknown version would cite ids that no longer mean what they meant."
        )

    rows = document.get("patterns")
    if not isinstance(rows, list):
        raise PatternsInvalid(
            f"{where} key 'patterns' must be a list; got {type(rows).__name__}"
        )

    seen: set[str] = set()
    for position, row in enumerate(rows):
        label = f"{where}, pattern {position}"
        if not isinstance(row, dict):
            raise PatternsInvalid(
                f"{label} is not a JSON object; got {type(row).__name__}"
            )
        for key in PATTERN_KEYS:
            if key not in row:
                raise PatternsInvalid(f"{label} is missing required key {key!r}")
        if not isinstance(row["id"], str) or not row["id"].strip():
            raise PatternsInvalid(f"{label} has id {row['id']!r}; expected a name")
        if not isinstance(row["evidence"], list):
            raise PatternsInvalid(
                f"{label} key 'evidence' must be a list of corpus ids; got "
                f"{type(row['evidence']).__name__}"
            )
        if row["id"] in seen:
            # Not harmless: a concept citing that id would be traceable to two
            # different pieces of evidence, which is the same as tracing to
            # neither.
            raise PatternsInvalid(
                f"{label} repeats pattern id {row['id']!r}; one pattern is one "
                f"id, so re-id or drop whichever is wrong"
            )
        seen.add(row["id"])

    return rows


def load_patterns(path: Path | str | None = None) -> dict:
    """The patterns document at `path`, validated.

    An empty `patterns` list is a valid document and is refused later, by
    generate(): whether the file is well formed and whether it can support a
    concept are different questions with different fixes.
    """
    path = Path(path) if path else DEFAULT_PATTERNS
    if not path.exists():
        raise FileNotFoundError(
            f"no patterns file at {path}; the learn step writes it from the "
            f"analysed corpus, so run python -m engine.learn before asking for "
            f"concepts"
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # Reported apart from the schema failures because the fix is different:
        # this file is not JSON at all, which in practice means a truncated
        # write or a merge conflict marker left in the tree.
        raise PatternsInvalid(f"{path} is not valid JSON: {exc}") from exc
    validate_patterns(document, source=path)
    return document


def verified_offers(offers: dict) -> list[str]:
    """The offer ids a concept may name, sorted: those whose status is
    `verified`. Anything else in the table - an UNVERIFIED entry, an entry
    that is not an object - is not an offer an ad may make."""
    return sorted(
        offer_id for offer_id, entry in offers.items()
        if isinstance(entry, dict) and entry.get("status") == "verified"
    )


def _render_placements() -> str:
    """The placement block of the prompt: every id the gate accepts, with what
    it asks the writer for. An id without a note is still listed - the gate
    accepts it - so widening gate.PLACEMENTS never hides a placement here."""
    lines = []
    for placement in PLACEMENTS:
        note = PLACEMENT_NOTES.get(placement)
        lines.append(
            "  %-12s %s" % (placement, note) if note else "  %s" % placement
        )
    return "\n".join(lines)


def _render_offers(offers: dict) -> str:
    """The offer block of the prompt.

    A verified offer is shown as its id and its safe phrasing - what an ad may
    say about it - never as its `evidence` line, which cites the strategy
    document this module keeps out of every prompt. The unverified ones are
    named as unavailable on purpose: "free trial" is the offer a model reaches
    for by default, and telling it once here is cheaper than a rejected run.
    """
    lines = ["  %-16s no offer; the ad argues and asks for nothing more"
             % NO_OFFER]
    verified = verified_offers(offers)
    for offer_id in verified:
        phrasings = offers[offer_id].get("safe_phrasings") or []
        said = " / ".join(str(p) for p in phrasings if p)
        lines.append(
            "  %-16s %s" % (offer_id, said) if said else "  %s" % offer_id
        )
    unavailable = sorted(k for k in offers if k not in verified)
    if unavailable:
        lines.append(
            "  NOT AVAILABLE (UNVERIFIED in claims/evidence.json; do not build "
            "a concept on one): " + ", ".join(unavailable)
        )
    return "\n".join(lines)


def _render_segments(segments: list[Segment]) -> str:
    """The segment block of the prompt.

    Exactly the audience context the reel loop's writer sends - trade, the
    three questions, the note - plus the id, which is a label the model has
    to quote back rather than anything about the audience. Nothing here comes
    from the ICP brief, and nothing may: the brief is a strategy document
    about a real market and it is not model input.
    """
    lines = []
    for segment in segments:
        lines.append("  [%s] %s" % (segment.id, segment.trade))
        lines.append("      questions: %s" % ", ".join(segment.questions))
        lines.append("      note:      %s" % segment.note)
    return "\n".join(lines)


def _number_words() -> str:
    """Every word the gate's NUM_RE reads as a number, quoted, so the prompt
    lists what the gate actually matches rather than a remembered sample.
    Wrapped to the prompt's own margin: one 700-character line is what a
    model skims past."""
    words = gate.CARDINALS.split("|") + gate.MULTIPLIERS.split("|")
    return textwrap.fill(
        ", ".join('"%s"' % w for w in words) + ".",
        width=76, initial_indent="    ", subsequent_indent="    ",
    )


def _concept_from(
    raw,
    *,
    position: int,
    width: int,
    segment_ids: list[str],
    pattern_ids: list[str],
    offers: dict,
) -> dict:
    """One validated C4 record, or a raised error naming what is wrong with it."""
    concept_id = "a%0*d" % (width, position)
    where = f"concept {concept_id} (number {position} in the reply)"

    if not isinstance(raw, dict):
        raise ConceptInvalid(f"{where} is not a JSON object; got {type(raw).__name__}")

    missing = [key for key in AUTHORED if key not in raw]
    if missing:
        raise ConceptInvalid(
            f"{where} is missing required field(s): {', '.join(missing)}"
        )

    for key in ("segment", "angle", "hook", "placement", "offer"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            raise ConceptInvalid(
                f"{where} has {key} {raw[key]!r}; expected a non-empty string"
            )

    if raw["segment"] not in segment_ids:
        raise UnknownSegmentError(
            f"{where} is for segment {raw['segment']!r}, which is not in the "
            f"backlog it was given. Known segments: {', '.join(segment_ids)}"
        )

    cited = raw["pattern_ids"]
    if not isinstance(cited, list) or not cited:
        raise ConceptInvalid(
            f"{where} has pattern_ids {cited!r}; expected a non-empty list of "
            f"pattern ids - a concept that cites nothing cannot be traced to an "
            f"ad that worked, which is the only reason this step exists"
        )
    for pattern_id in cited:
        if not isinstance(pattern_id, str):
            raise ConceptInvalid(
                f"{where} cites pattern id {pattern_id!r}; expected a string"
            )
        if pattern_id not in pattern_ids:
            raise UnknownPatternError(
                f"{where} cites pattern {pattern_id!r}, which is not in the "
                f"patterns file. Known patterns: {', '.join(pattern_ids)}. An "
                f"invented citation reads as evidence, so the reply is rejected "
                f"rather than trimmed - re-run to get concepts that cite what "
                f"was actually measured."
            )

    # Checked against the gate's own list, because the writer copies the
    # placement into the job unchanged and the gate refuses what is not here.
    if raw["placement"] not in PLACEMENTS:
        raise ConceptInvalid(
            f"{where} has placement {raw['placement']!r}, which is not one of "
            f"{', '.join(PLACEMENTS)}. A placement nobody renders is a job that "
            f"cannot be built."
        )

    # Checked from a table, not judged: the offer is the one product fact a
    # concept asserts, and an offer the business does not make is a promise
    # the copy would have to keep.
    offer = raw["offer"]
    if offer != NO_OFFER:
        verified = verified_offers(offers)
        allowed = ", ".join(verified) or "(no verified offer)"
        entry = offers.get(offer)
        if entry is None:
            raise ConceptInvalid(
                f"{where} offers {offer!r}, which is not in claims/evidence.json "
                f"offers; a concept may offer \"{NO_OFFER}\" or one of {allowed}"
            )
        if offer not in verified:
            evidence = entry.get("evidence") if isinstance(entry, dict) else None
            raise ConceptInvalid(
                f"{where} offers {offer!r}, which is UNVERIFIED in "
                f"claims/evidence.json"
                + (f": {evidence}" if evidence else "")
                + f"; a concept may offer \"{NO_OFFER}\" or one of {allowed}"
            )

    # Checked as a real boolean because the scorer branches on it: the string
    # "false" is truthy, so a coerced one would quietly flip every concept the
    # model marked safe into one that needs a statistic.
    if not isinstance(raw["needs_numbers"], bool):
        raise ConceptInvalid(
            f"{where} has needs_numbers {raw['needs_numbers']!r}; expected JSON "
            f"true or false, not a {type(raw['needs_numbers']).__name__}"
        )

    # Built key by key rather than copied, so a stray field the model invented
    # cannot reach the scorer and an id it wrote cannot override the stamped one.
    concept = {"id": concept_id}
    concept.update({key: raw[key] for key in AUTHORED})
    concept["pattern_ids"] = list(cited)
    return concept


def _looks_like_segments(value) -> bool:
    return (
        isinstance(value, list) and bool(value)
        and all(isinstance(row, Segment) for row in value)
    )


def _looks_like_patterns(value) -> bool:
    return isinstance(value, dict) and "patterns" in value


def generate(
    patterns,
    segments,
    *,
    n: int = DEFAULT_N,
    client=None,
    offers: dict | None = None,
) -> list[dict]:
    """N concept records from the learned patterns and the segment backlog.

    `patterns` is the patterns document (as load_patterns returns it) or a path
    to one. `segments` is what engine.backlog.load() returns, highest rank
    first; only their trade, questions and note reach the prompt. `offers` is
    the offers table as gate.load_offers() returns it, and defaults to exactly
    that; a test injects one so no test reads the committed file.

    Exactly one model call is made whatever N is, and a reply that does not
    hold N complete, citable concepts raises. Half a batch is worse than none:
    the scorer downstream would rank what survived and nobody would see that
    the rest was thrown away.
    """
    if n < 1:
        raise ConceptsError(f"n is {n}; ask for at least one concept")

    if isinstance(patterns, (str, Path)):
        patterns = load_patterns(patterns)
    if _looks_like_segments(patterns) or _looks_like_patterns(segments):
        # The two arguments are both collections and a swap would otherwise
        # surface as "patterns document must be a JSON object", which sends the
        # reader to the wrong file entirely.
        raise ConceptsError(
            "generate() was given segments where the patterns document belongs; "
            "the order is generate(patterns, segments)"
        )

    rows = validate_patterns(patterns)
    if not rows:
        raise PatternsInvalid(
            "the patterns document holds no patterns, so no concept could cite "
            "one; run the learn step over an analysed corpus first"
        )

    segments = list(segments)
    if not segments:
        raise ConceptsError(
            "no segments were given; concepts are written for an audience in "
            "queue/backlog.md, so there is nothing to write about"
        )

    if offers is None:
        offers = gate.load_offers()
    if not isinstance(offers, dict):
        raise ConceptsError(
            "offers must be the offers table as gate.load_offers() returns it "
            "(offer id -> entry with a status); got %s" % type(offers).__name__
        )

    pattern_ids = [row["id"] for row in rows]
    segment_ids = [segment.id for segment in segments]

    prompt = INSTRUCTION.format(
        n=n,
        headline_limit=gate.LIMITS["headline"],
        description_limit=gate.LIMITS["description"],
        placements=_render_placements(),
        offers=_render_offers(offers),
        patterns=json.dumps(rows, indent=2, sort_keys=True, ensure_ascii=True),
        segments=_render_segments(segments),
        authored=", ".join(AUTHORED),
        no_offer=NO_OFFER,
        number_words=_number_words(),
    )

    response = call_model(
        client or model.client(),
        model=MODEL_CONCEPTS,
        max_tokens=max_tokens_for(n),
        messages=[{"role": "user", "content": prompt}],
    )

    if response.stop_reason == "max_tokens":
        raise ConceptsError(
            "the model response was truncated at max_tokens; the concept list "
            "is incomplete and cannot be trusted. Ask for fewer concepts, or "
            "raise MAX_TOKENS_BASE in engine/concepts.py"
        )

    # A thinking-capable model leads with thinking blocks, which carry no
    # .text at all; text_of takes the first block that says it is text.
    text = model.text_of(response)

    document = model.first_json_object(text)
    if document is None:
        raise ConceptsError("could not parse JSON from the model: %r" % text[:400])

    if "refuse" in document:
        raise ConceptsError(
            "the model refused this backlog: %s" % document["refuse"]
        )

    written = document.get("concepts")
    if not isinstance(written, list):
        keys = ", ".join(sorted(document)) or "none"
        raise ConceptsError(
            "the model returned no 'concepts' list; the object it returned "
            "carries these keys: %s" % keys
        )

    if len(written) != n:
        raise ConceptsError(
            "the model returned %d concepts, not the %d it was asked for; "
            "re-run rather than scoring a short list" % (len(written), n)
        )

    # Zero-padded to the width of N so the ids stay sortable as strings past
    # a09, which is the order the scorer and every queue filename read them in.
    width = max(2, len(str(n)))
    return [
        _concept_from(
            raw,
            position=position,
            width=width,
            segment_ids=segment_ids,
            pattern_ids=pattern_ids,
            offers=offers,
        )
        for position, raw in enumerate(written, start=1)
    ]
