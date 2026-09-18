"""The claims gate, in two layers. An ad ships only if both pass.

It exists because DoviLoop has no customers, no case studies and no measured
outcomes yet - precisely the state in which unverifiable claims get written,
and precisely the exposure an investor flagged: a public measurable promise
with nothing behind it.

## One gate, not two standards

`reel-engine` gates a video's spoken lines with a number regex that matches
number WORDS as well as digits, a per-field sha256 attestation in
`claims/evidence.json`, and a hard build failure. This repository used to gate
an ad with five regexes keyed by claim id. The reel policy is the stronger one,
and it is the policy the ad's own video will be gated by anyway when
`reel-engine` renders it - so an ad that passed a looser gate here would still
die there, one render later. So this module adopts the reel policy whole:
`CARDINALS`, `MULTIPLIERS`, `NUM_RE`, `spoken()` and `evidence_key()` are
copied verbatim from `reel-engine/reel/build.py`, and a headline attested here
hashes exactly as a hook attested there. The five regexes stay as additional
named checks (`check()`), because "10 timer" in a Danish field is a claim the
number policy alone would only report as an unattested "10".

## Two layers, cheapest first

`structural(job)` is free: shape, limits, enums, the offer table, the five
named claims, the number policy and the refused constructions, every failure
one named line that says what to change. `editorial(job)` is ONE call to the
judge model against a four-rule rubric, and it fails closed: a truncated or
unreadable verdict is not an approval. `run(path)` runs structural first and
spends the call only when it passed. This mirrors `reel-engine/engine/gate.py`
exactly, minus the subprocess: an ad job is a dict, not a build.

`check()`, `check_creative()`, `ClaimVerdict` and `_RISKY` are the original
gate and keep working exactly as they did; `creative/*.json` and
`engine/cli.py` still call them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from engine import model

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "claims" / "evidence.json"

# Patterns that assert something measurable. Each must be backed or removed.
_RISKY = (
    (re.compile(r"\b\d+\s*(hours?|hrs?|timer|valand)", re.I), "hours_saved"),
    (re.compile(r"\bsaves?\s+\d", re.I), "hours_saved"),
    (re.compile(r"\b(trusted by|used by|join)\s+\d", re.I), "customer_count"),
    (re.compile(r"\b\d+\s*(firms?|companies|customers|clients)\s+(use|trust)", re.I), "customer_count"),
    (re.compile(r"\d+\s*%", re.I), "percentage_claim"),
)


@dataclass(frozen=True)
class ClaimVerdict:
    passed: bool
    failures: tuple[str, ...]


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))["claims"]


def check(text: str) -> ClaimVerdict:
    """Scan ad copy for measurable claims and verify each against evidence."""
    ev = _evidence()
    failures: list[str] = []

    for pattern, claim_id in _RISKY:
        match = pattern.search(text)
        if not match:
            continue
        entry = ev.get(claim_id)
        if entry is None:
            failures.append(
                f"{match.group(0)!r} asserts {claim_id!r}, absent from claims/evidence.json"
            )
        elif entry.get("status") != "verified":
            failures.append(f"{match.group(0)!r} -> {claim_id} UNVERIFIED. {entry.get('note','')}")

    return ClaimVerdict(not failures, tuple(failures))


def check_creative(spec: dict) -> ClaimVerdict:
    """Check every rendered string in a creative spec."""
    blobs: list[str] = []

    def walk(node):
        if isinstance(node, str):
            blobs.append(node)
        elif isinstance(node, dict):
            for k, v in node.items():
                if not k.startswith("_") and k != "hypothesis":
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(spec)
    return check("\n".join(blobs))


# ---------------------------------------------------------------------------
# The number policy, verbatim from reel-engine/reel/build.py.
#
# Copied rather than imported: this repository's research cron must not need
# the sibling checkout to run (the same reason queue/backlog.md is a copy), and
# a policy that is one file in each repository cannot drift by accident the way
# a "slightly adapted" one can. If build.py's regex changes, this one changes
# in the same commit.
# ---------------------------------------------------------------------------

CARDINALS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    "thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    "thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    "hundred|hundreds|thousand|thousands|million|millions|billion|dozen"
)
MULTIPLIERS = (
    "half|halve|halves|halved|twice|double|doubles|doubled|"
    "triple|triples|tripled|quadruple|quadruples|tenfold"
)
NUM_RE = re.compile(
    r"\d+(?:[.,]\d+)?|\b(?:%s|%s)\b" % (CARDINALS, MULTIPLIERS), re.I
)


def spoken(text):
    """The words as they would be said: emphasis stripped, whitespace collapsed."""
    return re.sub(r"\s+", " ", str(text).replace("**", "")).strip()


def evidence_key(field, text):
    import hashlib
    return hashlib.sha256(
        ("%s|%s" % (field, spoken(text))).encode("utf-8")
    ).hexdigest()


# The three kinds are a closed set. An unrecognised one is a wildcard: without
# this, "kind": "vibes" attests a number as convincingly as a measurement does,
# and the claims gate becomes decorative.
EVIDENCE_KINDS = ("measured", "architectural", "illustrative")


class EvidenceError(ValueError):
    """claims/evidence.json is malformed. The message names the entry and the
    fix; nothing is gated until the operator has corrected the file."""


def _evidence_document() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def load_attestations() -> dict:
    """claims/evidence.json["attestations"], kinds validated.

    Keyed by `evidence_key(field, text)`. A `_note` or any other underscore
    key is documentation, not an attestation, and is skipped. A missing
    section is `{}`: no attestations yet is legitimate, every number simply
    fails instead. An entry whose kind is not one of EVIDENCE_KINDS is
    refused by name, because a kind nobody declared attests nothing.
    """
    section = _evidence_document().get("attestations") or {}
    entries = {}
    for key, entry in section.items():
        if key.startswith("_"):
            continue
        kind = entry.get("kind") if isinstance(entry, dict) else None
        if kind not in EVIDENCE_KINDS:
            raise EvidenceError(
                "claims/evidence.json attestation %s has kind %r; must be one "
                "of %s. Fix the entry or delete it - a kind nobody declared "
                "attests nothing." % (key[:12], kind, ", ".join(EVIDENCE_KINDS))
            )
        entries[key] = entry
    return entries


def load_offers() -> dict:
    """claims/evidence.json["offers"]: every offer an ad may name, by id.

    An offer's `status` is `verified` or it is not made; the structural gate
    refuses a job whose `offer` is anything but `"none"` or a verified id, and
    concepts.py refuses a concept the same way. `_note` keys are skipped.
    """
    section = _evidence_document().get("offers") or {}
    return {k: v for k, v in section.items() if not k.startswith("_")}


def unattested_numbers(field, text, *, attestations=None) -> list[str]:
    """The numbers in a spoken field that claims/evidence.json leaves unattested.

    build.py's own regex, field name and hashing: a hook the reel build accepts
    is one this accepts, and an operator who can attest one can attest the
    other. `attestations` is for a caller that has already loaded the file
    once for many fields; absent, the file is read.
    """
    found = NUM_RE.findall(spoken(text))
    if not found:
        return []
    entries = load_attestations() if attestations is None else attestations
    if evidence_key(field, text) in entries:
        return []
    return found


# ---------------------------------------------------------------------------
# The C3 job's shape, as the gate reads it.
# ---------------------------------------------------------------------------

SPOKEN_FIELDS = ("primary_text", "headline", "description")
LANGUAGES = ("en", "da", "lt")
NATIVE_PLACEHOLDER = "NEEDS_NATIVE_PROOFREAD"
# Meta's recommended maxima for the three copy slots, in characters, inclusive.
# Longer copy is truncated with an ellipsis in most placements, which is how a
# headline loses its verb on a phone.
LIMITS = {"primary_text": 600, "headline": 40, "description": 60}
CTA_TYPES = ("LEARN_MORE", "SIGN_UP", "BOOK_NOW", "CONTACT_US", "GET_OFFER")
PLACEMENTS = ("reels-9x16", "feed-4x5", "static-1x1")
CREATIVE_KINDS = ("reel", "still", "none")
# Every key of docs/CONTRACTS.md C3. Missing is refused by name; the fields the
# gate never reads as copy are still required to be present, because a job
# without `ads` or `launched_at` is a half-record approval cannot advance.
JOB_KEYS = (
    "id", "segment", "concept_id", "pattern_ids", "placement", "offer",
    "hypothesis", "primary_text", "headline", "description", "cta",
    "destination", "creative_source", "proposed_at", "ads", "launched_at",
)


# PHRASINGS THE EDITORIAL GATE HAS REFUSED, and what to write instead.
#
# The editorial rule 1 below fails "any latency or performance promise" and
# requires that not guessing be described rather than promised. That is not a
# style preference: a promise is the one kind of line a viewer cannot check,
# and reel-engine's gate has spent a model call refusing these on every run
# that ever reached it.
#
# They are declared once, here, and used TWICE - rendered into the writer's
# brief by engine/write.py so the model is told, and asserted by structural()
# against every job before a call is spent, so the gate cannot be reached by
# copy the writer was already told not to write.
#
# The second use is the one reel-engine was missing. Until 2026-09-16 all
# seven of its content files carried two of these, INCLUDING the worked
# example its prompt hands the model as the thing to imitate. The prompt said
# an accuracy promise was the surest way to fail; the example showed one ("It
# **never guesses**"). The prompt said nothing at all about latency; the
# example showed one ("Replies ready before you open your inbox"). Runs 23 and
# 26 then refused four drafts for those two shapes - "ready before you open
# the inbox", "Drafts prepared before you open your inbox", "your client
# questions answered before you open them" - each costing a write call and a
# gate call out of twenty a day, per model. Here creative/example-job.json is
# gated by the same tuple, so the worked example cannot contradict the brief.
#
# Patterns are deliberately narrow: each one matches copy that was actually
# refused, not everything that resembles it. "never sends without you" must
# keep passing - rule 1 names it as true by construction.
REFUSED_CONSTRUCTIONS = (
    (r"never\s+(?:\*\*)?\s*(?:guess|invent)",
     'an accuracy promise. "It never guesses a figure" -> "It shows where '
     'each figure came from"'),
    (r"always\s+(?:\*\*)?\s*accurate",
     'an accuracy promise. "It is always accurate" -> "It quotes your own '
     'filing notes back"'),
    (r"never\s+gets\s+it\s+wrong",
     'an accuracy promise. "It never gets it wrong" -> "It leaves the field '
     'blank when your notes do not answer it"'),
    (r"before\s+you\s+open",
     'a latency promise - it claims the work finished before you looked. '
     '"Replies ready before you open your inbox" -> "The reply is waiting '
     'in your drafts"'),
    (r"by\s+the\s+time\s+you",
     "a latency promise. Say where the draft is, not when it got there"),
    (r"instantly|in\s+seconds|within\s+minutes",
     "a latency promise. Nothing in the system can guarantee a speed"),
    (r"finds\s+the\s+exact",
     'a performance promise. "It finds the exact policy rule" -> "It quotes '
     "the rule your own notes cite\""),
)
_REFUSED = tuple((re.compile(p, re.I), why) for p, why in REFUSED_CONSTRUCTIONS)


@dataclass(frozen=True)
class GateResult:
    ok: bool
    layer: str
    failures: list[str] = field(default_factory=list)


def _copy_fields(job: dict) -> list[tuple[str, str, str]]:
    """(field, lang, text) for every string the gate reads as copy.

    Only well-formed entries: a map that is not a map, or a value that is not
    a string, is reported by the shape check and skipped here rather than
    reported twice.
    """
    out = []
    for name in SPOKEN_FIELDS:
        block = job.get(name)
        if not isinstance(block, dict):
            continue
        for lang in LANGUAGES:
            text = block.get(lang)
            if isinstance(text, str):
                out.append((name, lang, text))
    return out


def structural(job: dict) -> GateResult:
    """Layer 1: everything that can be checked without a model.

    Shape (every C3 key; the three copy maps are {en, da, lt}), limits, the
    cta and placement enums, the offer table, the five named claims, the
    number policy and the refused constructions. Every failure is one named
    line that says what to change, and ALL of them are reported - a writer
    retrying on the first alone would meet the second on the next run.
    """
    failures: list[str] = []

    if not isinstance(job, dict):
        return GateResult(ok=False, layer="structural", failures=[
            "job is %s, not an object; a C3 job is the JSON object in "
            "docs/CONTRACTS.md C3" % type(job).__name__
        ])

    for key in JOB_KEYS:
        if key not in job:
            failures.append(
                "missing key %r; a C3 job carries every key in docs/CONTRACTS.md C3"
                % key
            )

    # The three copy maps. Every language in LANGUAGES, no other: a language
    # the gate does not read is silently unchecked copy, the exact hole
    # build.py's claimTextFields check exists to close.
    for name in SPOKEN_FIELDS:
        block = job.get(name)
        if name not in job:
            continue
        if not isinstance(block, dict):
            failures.append(
                "%s must be a {en, da, lt} map, got %s" % (name, type(block).__name__)
            )
            continue
        for lang in LANGUAGES:
            if lang not in block:
                failures.append(
                    "%s is missing %r; write the copy or stamp %s"
                    % (name, lang, NATIVE_PLACEHOLDER)
                )
        for lang in block:
            if lang not in LANGUAGES:
                failures.append(
                    "%s has unknown language %r; LANGUAGES are %s - a language "
                    "the gate does not read is unchecked copy"
                    % (name, lang, ", ".join(LANGUAGES))
                )
        for lang, text in block.items():
            if lang not in LANGUAGES:
                continue
            if not isinstance(text, str):
                failures.append(
                    "%s.%s must be a string, got %s" % (name, lang, type(text).__name__)
                )
                continue
            if lang == "en" and text.strip() == NATIVE_PLACEHOLDER:
                failures.append(
                    "%s.en is %s; the English copy is authored here, never "
                    "stamped for a native" % (name, NATIVE_PLACEHOLDER)
                )
            elif not text.strip():
                failures.append(
                    "%s.%s is empty; write the copy%s"
                    % (name, lang, "" if lang == "en" else " or stamp " + NATIVE_PLACEHOLDER)
                )

    if "cta" in job and job["cta"] not in CTA_TYPES:
        failures.append(
            "cta %r is not one of %s" % (job["cta"], ", ".join(CTA_TYPES))
        )
    if "placement" in job and job["placement"] not in PLACEMENTS:
        failures.append(
            "placement %r is not one of %s" % (job["placement"], ", ".join(PLACEMENTS))
        )
    source = job.get("creative_source")
    if isinstance(source, dict) and source.get("kind") not in CREATIVE_KINDS:
        failures.append(
            "creative_source.kind %r is not one of %s"
            % (source.get("kind"), ", ".join(CREATIVE_KINDS))
        )
    elif "creative_source" in job and not isinstance(source, dict):
        failures.append(
            "creative_source must be an object with a kind in %s, got %s"
            % (", ".join(CREATIVE_KINDS), type(source).__name__)
        )

    # The offer is checked from a table, not judged: an offer the business
    # does not make is a promise with nothing behind it, whatever the copy
    # says about it.
    if "offer" in job:
        offer = job["offer"]
        offers = load_offers()
        verified = sorted(k for k, v in offers.items() if v.get("status") == "verified")
        if offer != "none":
            entry = offers.get(offer) if isinstance(offer, str) else None
            if entry is None:
                failures.append(
                    "offer %r is not in claims/evidence.json offers; use \"none\" "
                    "or one of %s" % (offer, ", ".join(verified) or "(no verified offer)")
                )
            elif entry.get("status") != "verified":
                failures.append(
                    "offer %r is %s in claims/evidence.json: %s; use \"none\" or one "
                    "of %s" % (offer, entry.get("status"), entry.get("evidence", ""),
                               ", ".join(verified) or "(no verified offer)")
                )

    # Copy checks, per string. The placeholder is skipped, not failed: it is
    # the writer saying a native has not signed this off yet, and the gate has
    # nothing to read in it.
    attestations = load_attestations()
    for name, lang, text in _copy_fields(job):
        if text.strip() == NATIVE_PLACEHOLDER or not text.strip():
            continue
        path = "%s.%s" % (name, lang)
        limit = LIMITS[name]
        if len(text) > limit:
            failures.append(
                "%s is %d characters; the limit is %d" % (path, len(text), limit)
            )
        for why in check(text).failures:
            failures.append("%s: %s" % (path, why))
        found = unattested_numbers(path, text, attestations=attestations)
        if found:
            failures.append(
                "%s contains %s with no attestation in claims/evidence.json.\n"
                "    text: %s\n"
                "    add:  %r: {\"kind\": \"measured|architectural|illustrative\", "
                "\"field\": %r, \"text\": %r, \"source\": \"...\", \"asOf\": \"YYYY-MM-DD\"}"
                % (path, ", ".join(repr(f) for f in found), spoken(text),
                   evidence_key(path, text), path, spoken(text))
            )
        for pattern, why in _REFUSED:
            match = pattern.search(text)
            if match:
                failures.append(
                    "%s: %r is %s" % (path, match.group(0), why)
                )

    return GateResult(ok=not failures, layer="structural", failures=failures)


MODEL_GATE = model.MODEL_FLASH

# A thinking-capable model spends the budget on thinking before it writes a
# single visible token. 1024 was enough for the verdict and nothing else, so a
# long deliberation could consume the whole allowance and return no text block
# at all. 4096 leaves room for both.
# A ceiling on thinking PLUS response, and only what is used is billed - so a
# tight value buys nothing and costs a whole run. Measured in reel-engine: a
# first pass returning three detailed objections fits in 4096; the RETRY,
# which carries those objections back in as feedback, does not - it truncated
# and the run died with the verdict unreadable. The retry is the expensive
# path to lose. An ad's copy is shorter than a reel's content, but the
# deliberation is not, so the ceiling carries over unchanged.
MAX_TOKENS_GATE = 16000

RUBRIC = """You are the editorial gate on an ad engine. Judge the ad copy below
against four rules and return JSON only.

1. NO UNSUPPORTABLE PROMISE. "Nothing sends until you read it" is true by
   construction. Not guessing must be described, never promised: "it does
   not guess" fails, "it quotes your own fee schedule back" passes. Any
   latency, accuracy or performance promise fails - "ready before you open
   your inbox", "in seconds", "finds the exact rule", "always right".
2. THE HOOK NAMES A MOMENT. The first line of primary_text names a moment
   in the working week of the trade __SEGMENT__ - a request that lands, a
   deadline that recurs, a document asked for again - and not a generic
   complaint about email, busyness or admin that any trade could read as
   its own.
3. NOTHING THAT DOES NOT EXIST. The business has no customers, no logos, no
   testimonials and no measured outcome. Copy that states or implies any of
   those - "firms like yours already", "trusted by", a quoted client, a
   result, a saving - fails.
4. ONE ARGUMENT. `hypothesis` says what this ad tests. The headline, the
   primary text and the description carry that one thing and nothing else;
   copy that argues capacity AND accuracy AND price is three ads and passes
   as none.

Return exactly this JSON and nothing that contradicts it:
{"pass": true|false, "failures": ["one sentence per failure"]}

AD:
"""


# Substituted rather than str.format()-ed: the rubric ends with a literal
# {"pass": ...} that the model is told to return, and format() would read those
# braces as fields and raise. A token nobody would write by accident is safer
# than escaping every brace in a prompt somebody will edit later.
def rubric_for(segment: str) -> str:
    """The four rules, with rule 2 carrying THIS job's trade."""
    return RUBRIC.replace("__SEGMENT__", str(segment) or "(unnamed)")


def _editorial_view(job: dict) -> dict:
    """What the judge reads: the English copy and the fields that frame it.

    English only. `da` and `lt` are either the placeholder or a native's
    proofread of the same argument, and the judge reads one argument once;
    `ads`, `launched_at`, `proposed_at` and `creative_source` are bookkeeping
    the rubric has no rule about.
    """
    view = {
        "segment": job.get("segment"),
        "placement": job.get("placement"),
        "offer": job.get("offer"),
        "hypothesis": job.get("hypothesis"),
    }
    for name in SPOKEN_FIELDS:
        block = job.get(name)
        view[name] = block.get("en") if isinstance(block, dict) else block
    view["cta"] = job.get("cta")
    return view


def editorial(job: dict, *, client=None) -> GateResult:
    """Layer 2: one call to the judge model. Fails closed."""
    client = client or model.client()
    response = model.call_model(
        client,
        model=MODEL_GATE,
        max_tokens=MAX_TOKENS_GATE,
        messages=[{
            "role": "user",
            "content": rubric_for(job.get("segment", ""))
            + json.dumps(_editorial_view(job), ensure_ascii=True, indent=2),
        }],
    )

    if response.stop_reason == "max_tokens":
        # The budget ran out before the verdict was written. There is nothing
        # to read, and an unreadable verdict is not an approval.
        return GateResult(
            ok=False,
            layer="editorial",
            failures=["model response truncated at max_tokens - verdict unreadable"],
        )

    # A thinking-capable model leads with thinking blocks, which carry no
    # .text at all. text_of takes the first block that says it is text.
    text = model.text_of(response)

    verdict = model.first_json_object(text)
    if verdict is None or "pass" not in verdict:
        # Fail closed. An unreadable verdict is not an approval.
        return GateResult(
            ok=False,
            layer="editorial",
            failures=["could not parse a verdict from the model: %r" % text[:300]],
        )

    if verdict["pass"]:
        return GateResult(ok=True, layer="editorial")

    # A model that answers "failures": "one sentence" instead of a list would
    # otherwise be iterated into characters - one bullet per letter, at exactly
    # the moment a human needs to read why.
    failures = verdict.get("failures", ["unspecified"])
    if not isinstance(failures, list):
        failures = [failures]
    return GateResult(
        ok=False,
        layer="editorial",
        failures=[str(f) for f in failures],
    )


def run(path, *, client=None) -> GateResult:
    """Both layers, cheapest first. A structural failure spends no tokens."""
    path = Path(path)
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return GateResult(ok=False, layer="structural", failures=[
            "%s is not JSON (%s); a job file is the C3 object in "
            "docs/CONTRACTS.md, written with indent=2" % (path, exc)
        ])
    result = structural(job)
    if not result.ok:
        return result
    return editorial(job, client=client)
