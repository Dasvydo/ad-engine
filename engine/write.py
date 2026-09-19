"""Segment + selected concept -> one C3 ad job.

The ads twin of reel-engine/engine/script.py. That module hands the model a
tested guide verbatim, withholds a hook the claims policy does not attest,
renders the refused constructions from the machine-checked list rather than
retyping them, and appends the previous attempt's failures last, closest to
the answer. All four are kept. What changes is the thing being written: five
English strings instead of a 36-row reel, and a job file the structural gate
reads before anyone spends a second call.

ONE CALL, ENGLISH ONLY, EVERYTHING ELSE STAMPED. The model writes exactly
AUTHORED - primary_text, headline, description, cta, hypothesis - as bare
strings. The writer stamps the rest of C3: `da` and `lt` as the native
placeholder (the model does not get to declare copy native), the ids, the
placement, the offer, the destination, the creative source, the timestamp.
A model that volunteers a Danish headline or an id has written a field it was
never asked for, and the field is dropped, not kept.

THE PRODUCT FACTS ARE A TABLE, NOT A BRIEF. The only things the copy may say
about the product are the `safe_phrasings` of the verified entries in
claims/evidence.json plus the chosen offer's, rendered into the prompt as the
list of what has evidence behind it. The market brief is never opened: an
audience context a model may see is the segment's own trade, questions and
note. An offer's `evidence` line cites the brief and is deliberately not
rendered either; tests prove no substantial line of the brief reaches the
prompt and that a run opens nothing under that directory.

THE CONCEPT NEVER CARRIES AN UNATTESTED NUMBER PAST THE CLAIMS POLICY. A hook
whose figure claims/evidence.json does not attest is WITHHELD from the prompt
rather than softened inside it: a model cannot copy a number it was never
shown, and an instruction not to is a request, not a guarantee. The check is
engine.gate's own regex, field name and hashing (`unattested_numbers("hook",
hook)`), so a hook attested for the reel build is attested here. The
structural gate still runs afterwards, in engine.propose. This is the defence
in front of it, not a replacement for it.

THE PLACEMENT DECIDES THE CREATIVE. reels-9x16 and feed-4x5 are a video
reel-engine renders (templates reel-c and reel-b, the only two aspects it
shoots); static-1x1 is a still frame reel-engine shoots from a built reel. So
every placement gets a `creative_source` naming the sibling repository, a
template and the selection sidecar `reel_selection()` writes for it - a
document reel-engine's own `load_selection` accepts, with `pattern_ids` empty
because this repository's q-ids are not citations into that repository's
patterns file.
"""
from __future__ import annotations

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from engine import gate, model

ROOT = Path(__file__).resolve().parents[1]

# The worked example the model imitates: the gate-tested C3 job in creative/,
# reduced to its English fields at call time. Read as JSON rather than pasted
# into the prompt so the example the writer sees is the file the gate's tests
# run over - the sibling learned the hard way that an example carrying a
# refused construction teaches the model to write it.
EXAMPLE = ROOT / "creative" / "example-job.json"

MODEL_WRITE = model.MODEL_WRITE

# The contract's figure. A thinking-capable model spends the budget on
# thinking before it writes a single visible token, so the ceiling covers
# both; the sibling measured that a reel's JSON plus its deliberation needs
# 16000. Five short strings need far less visible output, and 8000 is the
# contract's allowance for the deliberation over them - unmeasured on a live
# call. A response that stops on max_tokens is a truncated object, never a
# usable one, and is refused below.
MAX_TOKENS_WRITE = 8000

# What the model authors, in English, as bare strings. Everything else in C3
# is stamped by this module.
AUTHORED = ("primary_text", "headline", "description", "cta", "hypothesis")

DESTINATION = "https://doviloop.dev"
DEFAULT_PLACEMENT = "reels-9x16"
NO_OFFER = "none"
NATIVE_PLACEHOLDER = gate.NATIVE_PLACEHOLDER
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Where the creative comes from, per placement. reel-engine shoots exactly two
# aspects: 9:16 (reel-c, reel-s, reel-d) and 4:5 (reel-b). A Reel is reel-c,
# the sibling's own fallback template; a feed video is reel-b, the only 4:5
# staging. A static is one frame of a built reel (reel-engine/engine/still.py
# takes a content JSON, not an image brief), so it needs the same template
# and the same selection; reel-c again, and how that 9:16 frame is cropped to
# 1:1 is the still path's business - UNVERIFIED, nothing has been shot at 1:1.
CREATIVE_REPO = "reel-engine"
CREATIVE_BY_PLACEMENT = {
    "reels-9x16": ("reel", "reel-c"),
    "feed-4x5": ("reel", "reel-b"),
    "static-1x1": ("still", "reel-c"),
}
SELECTION_PATH = "queue/proposed/%s.reel.json"

# The placement as the writer reads it: a request for a video or a picture,
# not a size. The first sentence of primary_text doubles as a reel's spoken
# first line, which is why the writer is told what the creative is.
PLACEMENT_NOTES = {
    "reels-9x16": "a vertical video in Reels and Stories, 9:16, built from "
                  "this ad's opening line; sound is usually on",
    "feed-4x5": "a video in the feed, 4:5, usually watched with the sound "
                "off, so the copy has to carry the argument on its own",
    "static-1x1": "a still image in the feed, 1:1; the copy does all the work",
}

# The concept's placement in the words reel-engine's selection carries as
# `format`. reel-engine's template resolver reads `format` for staging
# keywords (inbox, split screen, objection); none of these words is one, so
# the resolver falls back to reel-c, and build.yml passes the template from
# creative_source explicitly anyway. The words are for the human reading the
# sidecar, and they say the aspect rather than pretending to stage a scene.
FORMAT_BY_PLACEMENT = {
    "reels-9x16": "vertical reel, 9:16",
    "feed-4x5": "feed video, 4:5",
    "static-1x1": "still frame, 1:1",
}

# The selection document reel-engine/engine/script.py's load_selection reads:
# a schema, a `selected` list of ids and a `concepts` list carrying them.
SELECTION_SCHEMA = 1
SELECTION_SOURCE = "ad-engine"


INSTRUCTION = """Write the copy for one Meta ad.

SEGMENT
  trade:     {trade}
  questions: {questions}
  note:      {note}

The three questions are the subject matter. The argument is that a knowledge
base built from this firm's own answers can draft the reply to each of them,
in each person's own words, inside the inbox they already use.

Return ONLY a JSON object with exactly these keys: {authored}.
English only, a bare string per key - not a language map, not a list. The
Danish and Lithuanian copy is stamped afterwards for a native to write; the
job's id, segment, placement, offer, destination and timestamps are stamped
too. Do not write any of them.

  primary_text  the paragraph above the creative. Only its FIRST SENTENCE
                shows before "See more", so that sentence is the hook and it
                has to earn the tap. Line breaks are allowed. At most
                {primary_text_limit} characters.
  headline      the bold line under the creative.
                At most {headline_limit} characters.
  description   the grey line under the headline.
                At most {description_limit} characters.
  cta           the button. Exactly one of: {cta_types}.
  hypothesis    one sentence saying what this ad tests, for the human who
                reads the results. It is not copy and is not gated.

THIS AD RUNS AS {placement}: {placement_note}.

WHAT THE COPY MAY SAY ABOUT THE PRODUCT. These are the only product facts
with evidence behind them. Say them in these words, or in words that claim
no more; anything the product does that is not on this list is not a thing
the copy may say it does:
{claims}

THE OFFER is {offer}.
{offer_lines}

HARD FAILURES. A structural gate reads the job before anyone does and rejects
it outright on any of these. A rejected job is parked, not retried, so
getting one wrong wastes the run:

  - LENGTH. primary_text at most {primary_text_limit} characters.
    headline at most {headline_limit}. description at most {description_limit}.
    Counted on the raw string with line breaks included. Meta truncates
    longer copy with an ellipsis, which is how a headline loses its verb on
    a phone.
  - cta is one of {cta_types}, spelled exactly.
  - NO NUMBER in primary_text, headline or description. This is the trap
    that kills most drafts, because the check matches number WORDS as well
    as digits, and it matches them anywhere - inside a sentence, as a
    pronoun, as an article. The banned words are:
{number_words}
    "one" is the one that catches honest writing. Write around it:
      "no one should retype this"  ->  "nobody should retype this"
      "one click"                  ->  "a click"
      "one of them"                ->  "any of them"
      "the one that matters"       ->  "the reply that matters"
    Same for "half the day" -> "most of the day", "twice a week" -> "again and
    again", and "Microsoft 365" -> "Outlook" - the digits count. Read all
    three fields back word by word before you answer.
  - NO ACCURACY, LATENCY OR PERFORMANCE PROMISE. A promise is the one kind of
    line a reader cannot check. Describe the behaviour instead, so a reader
    can go and check it. Every line below was written by a real draft and
    refused:
{refused}
    A guardrail is safe when it is true BY CONSTRUCTION - "nothing sends
    until you read it" describes the code, and passes.
  - no time-saving figure, no customer count, no percentage. None is
    measured, and each is refused by name.

STRONG STYLE REQUIREMENTS. The structural gate does NOT check these - no error
message will tell you when you miss one - but an editorial gate and the humans
reading the ad reject on them, and you will have wasted the run anyway:

  - THE HOOK NAMES A MOMENT in the working week of this trade - a request that
    lands, a deadline that recurs, a document asked for again - and not a
    generic complaint about email, busyness or admin that any trade could
    read as its own.
  - NOTHING THAT DOES NOT EXIST. The business has no customers, no logos, no
    testimonials and no measured outcome. Copy that states or implies any of
    those - "firms like yours already", "trusted by", a quoted client, a
    result, a saving - fails.
  - ONE ARGUMENT. hypothesis says what this ad tests; the headline, the
    primary text and the description carry that one thing and nothing else.
    Copy that argues capacity AND accuracy AND price is three ads and passes
    as none.
  - plain words, the trade's own. No exclamation marks, no emoji, nothing
    "revolutionised".

If these three questions are judgement calls rather than lookups, do not bend
the copy. Return {{"refuse": "one sentence saying why"}} instead.

--- WORKED EXAMPLE (a different trade; match its shape, not its words) ---
{example}
"""


FEEDBACK_HEADER = (
    "A previous draft failed the editorial gate for these reasons - do not "
    "repeat them:"
)


# --- writing from a selected concept --------------------------------------

CONCEPT_HEADER = "--- THE SELECTED CONCEPT ---"

CONCEPT_PREAMBLE = """This ad was chosen by the weekly research run, not invented here. The angle
and the hook below are that decision; write THAT ad rather than a fresh guess
at one. Everything above still applies without exception - a concept never
licenses breaking a hard failure, and the gate does not know a concept exists."""

# Named for the operator reading a withheld hook, not for the model: the fix is
# to attest the figure or to let the next run select a concept that needs none.
HOOK_WITHHELD = """WITHHELD. The selected hook carries %s, and claims/evidence.json
             does not attest it. Write the opening line from the angle
             instead, with no figure in it at all - the concept does not
             license a number that the gate will reject."""

NEEDS_NUMBERS_NOTE = """This concept is marked needs_numbers, so its argument leans on a figure.
Nothing here attests one. Make the same argument without counting: describe the
repetition rather than measuring it."""

PATTERN_HEADER = """--- THE PATTERNS BEHIND IT ---
Each was measured on real ads in this market that advertisers kept paying to
run. `evidence` lists the ads it was read off, `median_days_running` is how
long those ads ran, `median_reach` is how many EU users they reached, and `n`
is how many there were. Keep the device the hook was built on; those figures
are why it was chosen and are NOT material for the copy."""


def _text(value) -> str:
    """A trimmed string, or "" for anything that is not a usable one."""
    return value.strip() if isinstance(value, str) else ""


def _stamp(now) -> str:
    """`now` as the contract's UTC timestamp. None is the clock; a naive
    datetime is read as UTC; an ISO-8601 string ('Z' honoured) is parsed."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif isinstance(now, str):
        now = datetime.fromisoformat(now.strip().replace("Z", "+00:00"))
    if not isinstance(now, datetime):
        raise TypeError(
            "now must be a datetime, an ISO-8601 string or None, got %s"
            % type(now).__name__
        )
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).strftime(TIMESTAMP_FORMAT)


# --- the prompt's blocks ---------------------------------------------------

def verified_claims(document: dict | None = None) -> dict[str, list[str]]:
    """The safe phrasings of every verified claim, by claim id, in file order.

    Read straight off claims/evidence.json's `claims` section (engine.gate
    reads that section only to refuse a risky phrase; it has no helper that
    hands the verified ones out). An entry whose status is not `verified`
    contributes nothing, whatever its `note` says: the note is advice to the
    operator and is not a product fact. Underscore keys are documentation.
    """
    if document is None:
        document = json.loads(gate.EVIDENCE.read_text(encoding="utf-8"))
    section = document.get("claims") or {}
    claims: dict[str, list[str]] = {}
    for claim_id, entry in section.items():
        if claim_id.startswith("_") or not isinstance(entry, dict):
            continue
        if entry.get("status") != "verified":
            continue
        phrasings = [
            p.strip() for p in entry.get("safe_phrasings") or []
            if isinstance(p, str) and p.strip()
        ]
        if phrasings:
            claims[claim_id] = phrasings
    return claims


def _claims_block(claims: dict[str, list[str]]) -> str:
    """One bullet per verified claim, its phrasings joined by " / ".

    Not wrapped: a phrasing is a unit the writer may quote, and a line break
    inside one ("Grounded in your / documents, not the internet") hands the
    model two fragments where the table holds one sentence.
    """
    if not claims:
        return ("  (none: claims/evidence.json verifies no product fact, so the "
                "copy may assert nothing about the product)")
    return "\n".join(
        "  - " + " / ".join('"%s"' % p for p in phrasings)
        for phrasings in claims.values()
    )


def _offer_block(offer: str, offers: dict) -> str:
    if offer == NO_OFFER:
        return ("Make no offer at all: no trial, no discount, no price, no "
                "guarantee, no bonus.\nAn ad that argues and asks for nothing "
                "has nothing to verify.")
    phrasings = [
        p for p in (offers.get(offer) or {}).get("safe_phrasings") or []
        if isinstance(p, str) and p.strip()
    ]
    lines = ["Say it in these words, or in words that claim no more:"]
    lines.extend('  - "%s"' % p.strip() for p in phrasings)
    lines.append("Make no other offer: no trial, no discount, no price, no "
                 "bonus. None exists.")
    return "\n".join(lines)


def _number_words() -> str:
    """Every word the gate's NUM_RE reads as a number, quoted, so the prompt
    lists what the gate actually matches rather than a remembered sample."""
    words = gate.CARDINALS.split("|") + gate.MULTIPLIERS.split("|")
    return textwrap.fill(
        ", ".join('"%s"' % w for w in words) + ".",
        width=76, initial_indent="    ", subsequent_indent="    ",
    )


def refused_block() -> str:
    """gate.REFUSED_CONSTRUCTIONS as the writer sees them.

    Rendered rather than retyped into the prompt, so a construction cannot be
    added to the machine-checked list and left out of the brief the writer
    reads - which is the exact way the latency promise survived four of the
    sibling's runs.
    """
    return "\n".join("      - %s" % why for _, why in gate.REFUSED_CONSTRUCTIONS)


def example_block() -> str:
    """creative/example-job.json reduced to the fields the model writes.

    The three copy maps become their `en` strings, so the example is exactly
    the object the model is asked to return - a worked example carrying the
    placeholder or the stamped bookkeeping would teach the model to write
    fields it was told not to.
    """
    job = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    reduced = {}
    for key in AUTHORED:
        if key not in job:
            raise ValueError(
                "creative/example-job.json has no %r, so it cannot serve as the "
                "writer's worked example; restore the field" % key
            )
        value = job[key]
        reduced[key] = value.get("en") if isinstance(value, dict) else value
    return json.dumps(reduced, indent=2, ensure_ascii=True)


def concept_block(concept: dict, patterns=None) -> str:
    """The selected concept as the lines that follow the instruction.

    Its own function rather than inline in generate() because this is the
    joint between the research half and the writing half - the only place a
    researched hook can reach the copy - and a joint that matters is one that
    should be readable and testable on its own, with no client in sight. It
    reads nothing but its arguments and claims/evidence.json's attestations.
    """
    concept = concept if isinstance(concept, dict) else {}
    lines = [
        "",
        CONCEPT_HEADER,
        CONCEPT_PREAMBLE,
        "",
        "  concept:   %s" % (_text(concept.get("id")) or "(unnamed)"),
        "  angle:     %s" % _text(concept.get("angle")),
        "  placement: %s" % _text(concept.get("placement")),
        "  offer:     %s" % (_text(concept.get("offer")) or NO_OFFER),
    ]

    hook = _text(concept.get("hook"))
    unattested = gate.unattested_numbers("hook", hook) if hook else []
    if unattested:
        lines.append(
            "  hook:      %s" % (HOOK_WITHHELD % ", ".join(repr(u) for u in unattested))
        )
    else:
        lines.append("  hook:      %s" % hook)
        lines.append("")
        lines.append(
            "Open with that hook, in those words, as the first sentence of "
            "primary_text.\nThen the rest of the paragraph carries the angle "
            "to its conclusion."
        )

    if concept.get("needs_numbers"):
        lines.extend(["", NEEDS_NUMBERS_NOTE])

    rows = list(patterns or [])
    if rows:
        lines.extend([
            "",
            PATTERN_HEADER,
            "",
            json.dumps(rows, indent=2, sort_keys=True, ensure_ascii=True),
        ])

    return "\n".join(lines) + "\n"


def _feedback_block(feedback) -> str:
    items = ["  - " + str(f).replace("\n", "\n    ") for f in feedback]
    return "\n--- PREVIOUS ATTEMPT ---\n%s\n%s\n" % (FEEDBACK_HEADER, "\n".join(items))


# --- what is stamped, and the checks before a call is spent ----------------

def _segment_id(segment) -> str:
    """The segment's id, from a backlog.Segment or a bare id string."""
    value = segment if isinstance(segment, str) else getattr(segment, "id", None)
    segment_id = _text(value)
    if not segment_id:
        raise ValueError(
            "segment names no id; pass a queue/backlog.md row (engine.backlog"
            ".Segment) or its id"
        )
    return segment_id


def _check_concept(concept, segment_id: str) -> dict:
    """The concept as a dict, or a ValueError naming what is wrong with it.

    A concept is refused, before any call, when it is not an object, names no
    id (a job must cite the concept it was written from, or be written with
    none), or names a different segment than the one being written for - a
    concept for accountants written for bookkeepers is somebody else's ad.
    """
    if not isinstance(concept, dict):
        raise ValueError(
            "concept must be a C4 concept object, got %s" % type(concept).__name__
        )
    if not _text(concept.get("id")):
        raise ValueError(
            "concept names no id; a job cites the concept it was written from. "
            "Pass a record from research/selection.json, or no concept at all"
        )
    named = concept.get("segment")
    if named is not None and _text(named) != segment_id:
        raise ValueError(
            "concept %s is for segment %r, not %r; write it for its own segment "
            "or pick a concept selected for this one"
            % (concept["id"], named, segment_id)
        )
    return concept


def _placement(concept: dict, placement) -> str:
    """The job's placement: an explicit placement= wins outright (an operator
    naming one is a decision, not a preference - the same rule the sibling's
    --template follows), then the concept's, then the default."""
    chosen = placement or concept.get("placement") or DEFAULT_PLACEMENT
    if chosen not in gate.PLACEMENTS:
        raise ValueError(
            "placement %r is not one of %s" % (chosen, ", ".join(gate.PLACEMENTS))
        )
    return chosen


def _offer(concept: dict, offers: dict) -> str:
    """The job's offer: the concept's, checked against the offers table before
    a call is spent, or "none" when there is no concept. An offer the business
    does not make is a promise with nothing behind it, and the gate would
    refuse the finished job for it - after the call was paid for."""
    offer = concept.get("offer", NO_OFFER)
    if offer == NO_OFFER:
        return NO_OFFER
    verified = sorted(
        k for k, v in offers.items() if isinstance(v, dict) and v.get("status") == "verified"
    )
    entry = offers.get(offer) if isinstance(offer, str) else None
    if entry is None:
        raise ValueError(
            "offer %r is not in claims/evidence.json offers; use %r or one of %s"
            % (offer, NO_OFFER, ", ".join(verified) or "(no verified offer)")
        )
    if entry.get("status") != "verified":
        raise ValueError(
            "offer %r is %s in claims/evidence.json: %s; use %r or one of %s"
            % (offer, entry.get("status"), entry.get("evidence", ""), NO_OFFER,
               ", ".join(verified) or "(no verified offer)")
        )
    return offer


def creative_source(placement: str, segment_id: str) -> dict:
    """The C3 creative_source for a placement: kind, repository, template and
    the selection sidecar that travels with the job."""
    if placement not in CREATIVE_BY_PLACEMENT:
        raise ValueError(
            "placement %r is not one of %s" % (placement, ", ".join(gate.PLACEMENTS))
        )
    kind, template = CREATIVE_BY_PLACEMENT[placement]
    return {
        "kind": kind,
        "repo": CREATIVE_REPO,
        "template": template,
        "selection": SELECTION_PATH % segment_id,
    }


def _fold_cta(value: str) -> str:
    """"Learn more" -> "LEARN_MORE": case and separator only, never meaning.
    Whether the result is a button the gate knows is the gate's call."""
    return "_".join(value.strip().upper().replace("-", " ").replace("_", " ").split())


def _authored_from(reply: dict) -> dict:
    """Exactly AUTHORED out of the model's object, each a non-empty string.

    Every missing key is named at once - a writer retrying on the first alone
    would meet the second on the next run. A language map or a list where a
    string was asked for is named with what was asked for; a blank is named.
    Anything the model volunteered beyond AUTHORED is dropped here.
    """
    missing = [k for k in AUTHORED if k not in reply]
    if missing:
        raise ValueError(
            "model output is missing required field(s): %s" % ", ".join(missing)
        )
    authored = {}
    for key in AUTHORED:
        value = reply[key]
        if not isinstance(value, str):
            raise ValueError(
                "model output's %s is %s, not a string; the writer asks for "
                "English only as a bare string - the language map is stamped "
                "afterwards" % (key, type(value).__name__)
            )
        if not value.strip():
            raise ValueError("model output's %s is blank" % key)
        authored[key] = value.strip()
    authored["cta"] = _fold_cta(authored["cta"])
    return authored


def _job(segment_id: str, *, concept: dict, placement: str, offer: str,
         authored: dict, now) -> dict:
    """The C3 job, keys in gate.JOB_KEYS order, everything but AUTHORED stamped."""
    copy = {
        name: {"en": authored[name], "da": NATIVE_PLACEHOLDER, "lt": NATIVE_PLACEHOLDER}
        for name in gate.SPOKEN_FIELDS
    }
    stamped = {
        "id": segment_id,
        "segment": segment_id,
        "concept_id": _text(concept.get("id")) or None,
        "pattern_ids": [str(p) for p in concept.get("pattern_ids") or []],
        "placement": placement,
        "offer": offer,
        "hypothesis": authored["hypothesis"],
        "primary_text": copy["primary_text"],
        "headline": copy["headline"],
        "description": copy["description"],
        "cta": authored["cta"],
        "destination": DESTINATION,
        "creative_source": creative_source(placement, segment_id),
        "proposed_at": _stamp(now),
        "ads": {},
        "launched_at": None,
    }
    # The gate's key list is the contract's; a key added there and not here
    # is a half-record, and the file order is the authored order.
    return {key: stamped[key] for key in gate.JOB_KEYS}


def generate(
    segment,
    *,
    concept: dict | None = None,
    patterns=None,
    placement: str | None = None,
    client=None,
    feedback=None,
    now=None,
) -> dict:
    """Write one ad's C3 job.

    segment is a queue/backlog.md row (anything with .id, .trade, .questions,
    .note). concept is one C4 record the weekly run selected and patterns the
    records it cites; both are optional and both default to nothing, so
    generate(segment) writes an ad from the segment alone. feedback carries
    the previous attempt's editorial failures - without it a rewrite is a
    blind re-roll of a byte-identical prompt. The concept block is appended
    BEFORE the feedback block, so the reasons a draft was rejected stay
    closest to the answer. now= pins proposed_at.

    Everything that can be refused is refused before the client is built:
    a bad concept, an unknown placement, an offer the table does not verify.
    ONE call; the reply must be a JSON object holding exactly AUTHORED as
    strings, and a refusal, a truncation or an unreadable reply is a
    ValueError naming it.
    """
    segment_id = _segment_id(segment)
    for attr in ("trade", "questions", "note"):
        if not hasattr(segment, attr):
            raise ValueError(
                "segment %r has no %s; generate() needs a queue/backlog.md row "
                "(engine.backlog.Segment), not just an id" % (segment_id, attr)
            )
    concept = _check_concept(concept, segment_id) if concept is not None else {}
    placement = _placement(concept, placement)
    offers = gate.load_offers()
    offer = _offer(concept, offers)

    prompt = INSTRUCTION.format(
        trade=segment.trade,
        questions=", ".join(str(q) for q in segment.questions),
        note=segment.note,
        authored=", ".join(AUTHORED),
        primary_text_limit=gate.LIMITS["primary_text"],
        headline_limit=gate.LIMITS["headline"],
        description_limit=gate.LIMITS["description"],
        cta_types=", ".join(gate.CTA_TYPES),
        placement=placement,
        placement_note=PLACEMENT_NOTES[placement],
        claims=_claims_block(verified_claims()),
        offer=offer,
        offer_lines=_offer_block(offer, offers),
        number_words=_number_words(),
        refused=refused_block(),
        example=example_block(),
    )

    if concept:
        prompt += concept_block(concept, patterns)

    if feedback:
        prompt += _feedback_block(feedback)

    client = client or model.client()
    response = model.call_model(
        client,
        model=MODEL_WRITE,
        max_tokens=MAX_TOKENS_WRITE,
        messages=[{"role": "user", "content": prompt}],
    )

    if response.stop_reason == "max_tokens":
        raise ValueError(
            "the model response was truncated at max_tokens; the copy is "
            "incomplete and cannot be trusted"
        )

    # A thinking-capable model leads with thinking blocks, which carry no
    # .text at all. text_of takes the first block that says it is text.
    text = model.text_of(response)

    reply = model.first_json_object(text)
    if reply is None:
        raise ValueError("could not parse JSON from the model: %r" % text[:400])

    if "refuse" in reply:
        raise ValueError("the model refused this segment: %s" % reply["refuse"])

    authored = _authored_from(reply)
    return _job(segment_id, concept=concept, placement=placement, offer=offer,
                authored=authored, now=now)


def reel_selection(concept: dict, segment, *, now=None) -> dict:
    """The concept as a selection document reel-engine writes a reel from.

    reel-engine/engine/script.py's load_selection wants an object carrying a
    `selected` list of ids and a `concepts` list holding every record it
    names, non-empty. This writes exactly one of each. `format` is the
    placement's aspect in words; `pattern_ids` is EMPTY on purpose: the ids a
    concept cites here are this repository's q-patterns, and reel-engine
    would look them up in its own research/patterns.json, where they do not
    exist - a citation into the wrong file reads as evidence and is none.
    The hook travels verbatim; reel-engine's own claims policy withholds an
    unattested figure on its side, with the same hashing as this one.
    """
    segment_id = _segment_id(segment)
    concept = _check_concept(concept, segment_id)
    needs_numbers = concept.get("needs_numbers")
    if not isinstance(needs_numbers, bool):
        raise ValueError(
            "concept %s has needs_numbers %r; it must be a JSON boolean, and "
            "engine.concepts writes one" % (concept["id"], needs_numbers)
        )
    placement = _placement(concept, None)
    return {
        "schema": SELECTION_SCHEMA,
        "generated_at": _stamp(now),
        "source": SELECTION_SOURCE,
        "selected": [concept["id"]],
        "concepts": [{
            "id": concept["id"],
            "segment": segment_id,
            "angle": _text(concept.get("angle")),
            "hook": _text(concept.get("hook")),
            "pattern_ids": [],
            "format": FORMAT_BY_PLACEMENT[placement],
            "needs_numbers": needs_numbers,
        }],
    }
