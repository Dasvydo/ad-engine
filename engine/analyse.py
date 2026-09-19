"""Candidates in, corpus records out - one call per BATCH of copy, one call per
creative that has to be watched.

THE DESIGN DECISION is the split into two paths, and rule 3 of
docs/AD-RESEARCH-SCOPE.md 1.2 is why: one call per thing that has to be
WATCHED, one call per batch of things that only have to be READ. An ad's copy
is a few hundred characters, so twelve of them fit in one prompt and cost one
call, where the sibling's twelve videos cost twelve. That arithmetic is the
point of this module: MEASURED in engine/model.py, the free tier allows twenty
requests a day per model, and a research week that analysed one ad per call
would spend most of them here. Batched, it spends two or three.

The batch size is a starting guess from the scope (3.3 says "start at 12"),
not a measured optimum. What IS measured is the failure mode it trades
against: a reply cut off at max_tokens loses the whole batch, not the last
ad, so the batch is refused as a unit. A half-batch counted as evidence would
be worse than a week with none - learn/ would count the ads that happened to
come first as the pattern.

THE MEDIA PATH IS MANUAL-SEED ONLY, byte for byte the sibling's Instagram
seam. When a concept needs the creative's mechanics - the on-screen opening,
what the first two seconds show - the operator opens the ad's snapshot page
in a browser and saves the file by hand into research/media/<id>.<suffix>.
That file is inlined by engine/model.py (up to its 20 MiB request ceiling)
and read on top of the copy, one call per creative. There is no code path
that fetches a snapshot or downloads a creative, and there is no place to
add one; tests/test_analyse.py parses this module to keep it that way.

WHAT IS EXTRACTED is what a copywriter reuses against a different product,
not a summary: the hook and its device, the section order, the offer, the
proof, the ask, and the objection the copy answers. The labels come from
closed lists (HOOK_DEVICES and friends) because learn/ COUNTS them across
ads, and two names for one device halve its evidence. A label outside the
list is therefore a skip for that ad rather than a record: writing it would
plant a device nothing else can match, and refusing the whole batch would
throw away eleven good analyses over one word. The record says which path
produced it (`analysis.creative.kind`: text-only or local-file), because a
reading from copy alone and a reading that watched the creative are not the
same evidence and nothing downstream could otherwise tell them apart.

ONE REPLY SHAPE FOR BOTH PATHS. A batch answers {"ads": {"<id>": {...}}} and
a media call answers the same envelope with one id, so there is one parser,
one set of refusals (short an id, truncated, not JSON) and one place a
per-ad {"refuse": "..."} is turned into a skip that names the ad.

PROVENANCE LIVES INSIDE `analysis`. engine.corpus closes the top level on
purpose - the top level is the schema - so the path that produced the record,
the file it watched and the candidate's outlier ratio are stamped under
`analysis`, after the model's own keys, where the corpus deliberately leaves
room. The candidate's facts (id, url, channel, metrics) are copied from the
candidate and never from the reply: the model is asked what the ad does, not
which ad it was.

TRANSPORT NOTE. A creative travels in the call as a structured `media` entry
on the message; turning that into whatever part the SDK wants is
engine/model.py's business, the engine's single seam onto a provider. The
`kind` emitted here must stay inside the set model.py handles, and a test
pins the two sides together: a divergence would send no file at all and the
"watched" analysis would quietly become a reading of the copy.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from engine import corpus, model

ROOT = Path(__file__).resolve().parents[1]

MODEL_ANALYSE = model.MODEL_WRITE

# Twelve analyses of a few hundred tokens each, plus whatever a
# thinking-capable model spends thinking before it writes a visible token -
# the allowance covers both. Only what is used is billed, and a truncated
# batch costs the whole batch's call and returns nothing, so a tight value
# here buys nothing and loses twelve ads at once.
MAX_TOKENS_ANALYSE = 16000

# Ads per text call. The scope's starting guess, not a measured optimum: the
# ceiling is the reply fitting under MAX_TOKENS_ANALYSE, and the first live
# run is the proof. fanout's default of 24 ads is two of these.
BATCH_SIZE = 12

# Where a hand-saved creative is looked for, named after the candidate id so
# the operator never has to tell this step anything: `fb-961046237012883.mp4`
# is the whole instruction. Not created here - an empty directory would look
# like a corpus that had been analysed and found nothing. research/media/
# README.md documents the convention; everything there but the README is
# gitignored because it is somebody else's creative.
MEDIA_ROOT = ROOT / "research" / "media"

# Video for a Reels or feed creative, an image for a static one; ordered by
# what a phone produces when a clip is saved, then the stills. Must stay
# equal to what engine/model.py can attach - a suffix found here that the
# transport refuses is a skip, and a test pins the two tuples together.
MEDIA_SUFFIXES = (".mp4", ".mov", ".m4v", ".webm", ".jpg", ".jpeg", ".png", ".webp")

# The closed vocabularies. learn/ slugs and counts these across the corpus,
# so the prompt renders them from here and a label outside them is refused
# rather than filed - see the module docstring. `hook` devices are the
# sibling's list with the moves ad copy makes that a reel rarely does
# (direct-offer, social-proof, how-to).
HOOK_DEVICES = (
    "question", "negative-flip", "cost-of-inaction", "named-enemy", "before-after",
    "credential", "social-proof", "curiosity-gap", "direct-offer", "how-to", "story",
)
STRUCTURE_LABELS = ("hook", "problem", "agitate", "demo", "proof", "offer", "guarantee", "cta")
OFFER_TYPES = ("none", "free-trial", "demo", "guarantee", "price", "discount", "lead-magnet")
PROOF_TYPES = ("none", "testimonial", "number", "logo", "case-study", "award")
CTA_TYPES = ("learn-more", "sign-up", "book-demo", "message", "download", "shop", "none")

# `analysis.creative.kind`: which path produced the record.
TEXT_ONLY = "text-only"
LOCAL_FILE = "local-file"

# Read off the schema rather than retyped, so a corpus that grows an analysis
# field cannot silently stop being asked for it. `creative` is this module's
# provenance stamp, not the model's to write, so it is the one key held back.
ANALYSIS_KEYS = corpus.REQUIRED_NESTED["analysis"]
STAMPED_KEYS = ("creative",)
MODEL_KEYS = tuple(key for key in ANALYSIS_KEYS if key not in STAMPED_KEYS)

# Which reply field each vocabulary governs. `structure` is a list and is
# checked apart.
VOCABULARIES = (
    ("hook.device", HOOK_DEVICES),
    ("offer.type", OFFER_TYPES),
    ("proof.type", PROOF_TYPES),
    ("cta.type", CTA_TYPES),
)

# The keys of a candidate this step reads, after `id` and `platform` (which
# are checked first because every message names them).
CANDIDATE_KEYS = ("url", "channel", "origin", "metrics", "copy")


class AnalysisError(ValueError):
    """The model's answer is not a usable analysis for the ads it was asked.

    A truncated, unparseable or short reply: the prompt or the model being
    wrong for the whole batch rather than one ad in it, so the batch is
    refused as a unit. ValueError to match engine/model.py's own refusals.
    """


class SkippedCandidate(RuntimeError):
    """This ad produced no record, and the message says what to do about it.

    Per-ad and not a bug: the model refused it (empty copy, say), it used a
    label outside the vocabulary, or the creative it was given could not be
    attached. None is fixed by running again unchanged with no other change -
    which is why it is separate from AnalysisError, which stops the run.

    `cost` is the model calls spent learning this: 1 when the model answered
    (a refusal, an off-vocabulary label), 0 when the skip was decided before
    the wire (a file the transport refused). Inside a batch the batch's own
    count is the ledger and this is informational.
    """

    def __init__(self, message: str, *, candidate_id: str = "", cost: int = 0):
        super().__init__(message)
        self.candidate_id = candidate_id
        self.cost = cost


@dataclass(frozen=True)
class AnalysisRun:
    """What a run produced: the records, a line per ad that made none, and
    the model calls it spent - the number docs/COST.md's ledger reads, and
    not len(records), because a batch of twelve is one."""

    records: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    calls: int = 0


INSTRUCTION = """Read the {count} Meta ad(s) below and return JSON describing how each one is BUILT.

Each ad is its copy as the Ad Library archive stores it - primary text,
headline, description, link caption - with what the archive reports about it:
days running, whether it is still running, how many variants the page runs,
its EU reach. Read the mechanics, not the subject. A writer will reuse the
shape of an ad - its hook device, its section order, its offer, the objection
it answers - against a different product, so record what is measurable and
quote what the copy actually says, in its own language.

ADS
{ads}

Return ONLY a JSON object of this shape, with one entry per id above and no
id missing:

  {{"ads": {{"<id>": {{...}}, ...}}}}

where each {{...}} has exactly these keys: {keys}.

  copy        {{"words": 48}}
              words is the literal count of whitespace-separated words in
              primary_text. Count them; do not estimate. 0 when it is empty.
  hook        {{"words": 9, "text": "...", "device": "question"}}
              text is the opening line verbatim: the first sentence of
              primary_text up to the pause that lands the promise, or the
              headline when primary_text is empty. words is the literal count
              of whitespace-separated words in text. Count them.
              device is one of: {hook_devices}.
  structure   ["hook", "problem", "offer", "cta"]
              the sections of the copy in the order they appear, one label
              each, from: {structure_labels}. No timings - copy has none.
  offer       {{"type": "none", "text": ""}}
              type is one of: {offer_types}. text is the offer as the copy
              words it, verbatim; "" when there is none.
  proof       {{"type": "none", "text": ""}}
              type is one of: {proof_types}. text is the proof verbatim - the
              number, the name, the quote; "" when there is none.
  cta         {{"type": "learn-more", "text": "..."}}
              type is one of: {cta_types}, read from the link caption and the
              ask in the copy. text is the exact ask, verbatim; "" when there
              is none.
  objections  ["..."] what a sceptical reader holds against this pitch that
              the copy ANSWERS. One sentence each, phrased as the reader's
              objection rather than as the copy's answer - the objection is
              what travels to a different product, where the hook does not.
              [] when it answers none.

Every label comes from its list above. Pick the closest one; never invent a
synonym or a new label. Labels are counted across ads, and two names for one
device halve its evidence. Numbers are numbers, not strings. Quote in the ad's
own language; do not translate.

Do not guess. If an ad cannot be read - its copy is empty, or is not ad copy at
all - put {{"refuse": "one sentence saying why"}} in place of its analysis and
analyse the others. Never leave an id out: an analysis you cannot give is a
refusal, not a gap.
"""

MEDIA_INSTRUCTION = """
THE CREATIVE IS ATTACHED: {name}, saved by hand from this ad's snapshot page.
Watch it - or look at it, if it is a still - and fold what its first two
seconds show into the analysis, because that is where a viewer decides:
  - hook.text quotes the opening the viewer meets first, whether that is the
    on-screen text, the first spoken line or the copy; hook.device is the move
    that opening makes.
  - structure begins with what those first two seconds do, then follows the
    creative and the copy together.
Burned-in captions, titles and spoken lines are copy too: read them for the
offer, the proof, the cta and the objections.

If you were handed no creative at all, or cannot read the one attached, return
{{"ads": {{"{id}": {{"refuse": "one sentence saying why"}}}}}} and nothing else.
An analysis written from the copy alone would be recorded as one that watched
the creative, and nothing downstream could tell them apart.
"""


# --- reading the candidate ---------------------------------------------------


def _field(candidate: dict, key: str):
    try:
        return candidate[key]
    except (TypeError, KeyError):
        raise ValueError(
            "candidate is missing %r; this step reads the record that "
            "engine.discover.candidate() produces (contract C2)" % key
        ) from None


def _check_candidates(candidates: list[dict]) -> list[str]:
    """Every candidate is a meta-ad C2 record with a unique id, or nothing
    happens. Run before a client is built and before any call, so a list the
    caller assembled wrongly costs neither a key nor a request."""
    ids: list[str] = []
    for candidate in candidates:
        cid = _field(candidate, "id")
        if not isinstance(cid, str) or not cid:
            raise ValueError(
                "candidate has a blank id (%r); an id is half a corpus filename "
                "and cannot be guessed" % (cid,)
            )
        platform = _field(candidate, "platform")
        if platform not in corpus.PLATFORMS:
            raise ValueError(
                "%s has platform %r; this step reads %s only"
                % (cid, platform, " and ".join(corpus.PLATFORMS))
            )
        for key in CANDIDATE_KEYS:
            _field(candidate, key)
        for key in ("metrics", "copy"):
            if not isinstance(candidate[key], dict):
                raise ValueError(
                    "%s: candidate %r must be a JSON object, got %s (contract C2)"
                    % (cid, key, type(candidate[key]).__name__)
                )
        if cid in ids:
            raise ValueError(
                "candidate id %r appears twice; one reply entry cannot serve two "
                "ads, so de-duplicate the list (engine.fanout does this by "
                "reading the corpus first)" % cid
            )
        ids.append(cid)
    return ids


def local_media(candidate: dict, *, media_root: str | Path | None = None) -> Path | None:
    """The hand-saved creative for this candidate, or None if nobody saved one.

    Found by name alone - `<id>` plus one of MEDIA_SUFFIXES - in the order the
    suffixes are listed, so a clip wins over a still of the same ad. The suffix
    is matched case-insensitively because a phone saves `.MOV` as readily as
    `.mov` and engine/model.py accepts either.
    """
    root = Path(media_root) if media_root else MEDIA_ROOT
    stem = _field(candidate, "id")
    if not root.is_dir():
        return None
    found: dict[str, Path] = {}
    for path in sorted(root.iterdir()):
        if not path.is_file() or not path.name.startswith(stem + "."):
            continue
        suffix = path.name[len(stem):].lower()
        if suffix in MEDIA_SUFFIXES:
            found.setdefault(suffix, path)
    for suffix in MEDIA_SUFFIXES:
        if suffix in found:
            return found[suffix]
    return None


def _provenance_ref(path: Path) -> str:
    """How the record names the file it watched: relative to the repository
    when it lives inside it (`research/media/fb-1.mp4` reads the same on every
    machine, which a committed record needs), absolute otherwise."""
    path = Path(path)
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _stamp(now) -> str:
    """When the record was made, to the second. UTC with a Z, because the
    corpus is read on two machines and a local offset in a filename-stable
    file is a diff waiting to happen. `now` pins it for a test: an aware or
    naive (read as UTC) datetime, or an ISO string."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif isinstance(now, str):
        now = datetime.fromisoformat(now)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- the prompt ----------------------------------------------------------------


def _ad_view(candidate: dict) -> dict:
    """What the model is shown of one ad: its id, who ran it, the archive's
    numbers and the copy. Rendered as JSON so copy that happens to contain a
    heading or a brace cannot pose as part of the prompt's own structure."""
    return {
        "id": candidate["id"],
        "channel": candidate["channel"],
        "metrics": dict(candidate["metrics"]),
        "copy": dict(candidate["copy"]),
    }


def _prompt(candidates: list[dict], *, media_name: str | None = None) -> str:
    text = INSTRUCTION.format(
        count=len(candidates),
        ads=json.dumps([_ad_view(c) for c in candidates], ensure_ascii=False, indent=2),
        keys=", ".join(MODEL_KEYS),
        hook_devices=", ".join(HOOK_DEVICES),
        structure_labels=", ".join(STRUCTURE_LABELS),
        offer_types=", ".join(OFFER_TYPES),
        proof_types=", ".join(PROOF_TYPES),
        cta_types=", ".join(CTA_TYPES),
    )
    if media_name is not None:
        text += MEDIA_INSTRUCTION.format(name=media_name, id=candidates[0]["id"])
    return text


# --- the reply -----------------------------------------------------------------


def _span(ids: list[str]) -> str:
    if len(ids) == 1:
        return ids[0]
    return "batch of %d (%s .. %s)" % (len(ids), ids[0], ids[-1])


def _analyses_from(reply, ids: list[str]) -> dict[str, dict]:
    """The per-ad objects out of one reply, or AnalysisError.

    Every id asked for must be answered - with an analysis or a refusal - or
    the whole reply is refused: half a batch would be counted as evidence by
    learn/ and score/ forever afterwards, and there is no way to tell which
    half the model actually read.
    """
    label = _span(ids)
    if reply.stop_reason == "max_tokens":
        raise AnalysisError(
            "%s: the model response was truncated at max_tokens, so the "
            "analysis is incomplete. A half-batch is worse than none - it would "
            "be counted as evidence - so nothing is returned. Fewer ads per call "
            "(batch_size) or a larger MAX_TOKENS_ANALYSE is the fix." % label
        )

    # Read past the thinking block; see engine.model.text_of.
    text = model.text_of(reply)
    parsed = model.first_json_object(text)
    if parsed is None:
        raise AnalysisError(
            "%s: could not parse JSON from the model: %r" % (label, text[:400])
        )

    ads = parsed.get("ads")
    if not isinstance(ads, dict):
        raise AnalysisError(
            "%s: the reply carries no 'ads' object (its keys are %s); the "
            "prompt asks for {\"ads\": {\"<id>\": {...}}} and nothing else"
            % (label, ", ".join(repr(k) for k in parsed) or "none")
        )

    missing = [cid for cid in ids if cid not in ads]
    if missing:
        raise AnalysisError(
            "%s: the reply is short %d of %d ads - missing %s; it answered for "
            "%s. Half a batch is worse than none, so nothing is returned. A "
            "smaller batch_size usually fixes it."
            % (
                label, len(missing), len(ids), ", ".join(missing),
                ", ".join(repr(k) for k in ads) or "nothing",
            )
        )

    malformed = [cid for cid in ids if not isinstance(ads[cid], dict)]
    if malformed:
        raise AnalysisError(
            "%s: the entry for %s is not a JSON object; an analysis is an object "
            "and a refusal is {\"refuse\": \"...\"}, nothing else"
            % (label, ", ".join(malformed))
        )

    # Only what was asked for. An id the model volunteered is ignored: it is
    # not one this run can attach a candidate to.
    return {cid: ads[cid] for cid in ids}


def _slug(value: str) -> str:
    """Case and separator folding only - `Negative_Flip` is `negative-flip`.
    Anything past that would be a guess about meaning."""
    return re.sub(r"[\s_]+", "-", value.strip().lower())


def _normalise_labels(body: dict) -> list[str]:
    """Fold each label to its slug and name every one outside its vocabulary.

    A missing block or key is left for engine.corpus to name - its message
    points at the file as it is laid out. A label that is present but is not
    a string is off-vocabulary by definition: nothing downstream could count
    it.
    """
    off: list[str] = []
    for dotted, allowed in VOCABULARIES:
        parent, key = dotted.split(".")
        block = body.get(parent)
        if not isinstance(block, dict) or key not in block:
            continue
        value = block[key]
        label = _slug(value) if isinstance(value, str) else None
        if label in allowed:
            block[key] = label
        else:
            off.append("%s %r is not one of %s" % (dotted, value, ", ".join(allowed)))

    structure = body.get("structure")
    if isinstance(structure, list):
        for index, item in enumerate(structure):
            label = _slug(item) if isinstance(item, str) else None
            if label in STRUCTURE_LABELS:
                structure[index] = label
            else:
                off.append(
                    "structure[%d] %r is not one of %s"
                    % (index, item, ", ".join(STRUCTURE_LABELS))
                )
    return off


def _record(candidate: dict, analysis: dict, *, creative: dict, now) -> dict:
    """One candidate plus the model's answer for it -> one C1 record.

    Raises SkippedCandidate for a refusal or an off-vocabulary label, and
    CorpusInvalid (naming the key, as the file lays it out) for an answer
    short a field. The returned record has already passed engine.corpus, so a
    caller can save it without checking anything.
    """
    cid = candidate["id"]

    if "refuse" in analysis:
        # The honest refusal. Per-ad and not a bug, so the run reports it and
        # carries on with the rest of the batch.
        raise SkippedCandidate(
            "%s: skipped - the model refused to analyse it: %s"
            % (cid, analysis["refuse"]),
            candidate_id=cid, cost=1,
        )

    # Exactly the keys the model was asked for. Anything else it volunteered
    # - an id, a url, a model name, a creative block - is dropped here, so the
    # record's facts are the candidate's and this module's, never the reply's.
    body = {key: analysis[key] for key in MODEL_KEYS if key in analysis}

    off = _normalise_labels(body)
    if off:
        raise SkippedCandidate(
            "%s: skipped - the model used a label outside the vocabulary: %s. "
            "The labels are counted across ads, so one outside the list would "
            "never match another; the next run usually lands inside it, and if "
            "the same label keeps coming back the vocabulary in "
            "engine/analyse.py is what to widen." % (cid, "; ".join(off)),
            candidate_id=cid, cost=1,
        )

    # analysis.copy is the candidate's copy - the archive's text, verbatim -
    # plus the one thing the model was asked to add to it. A reply that
    # restates the copy does not get to change it.
    copy = dict(candidate["copy"])
    counted = body.get("copy")
    if isinstance(counted, dict) and "words" in counted:
        copy["words"] = counted["words"]
    body["copy"] = copy

    # Stamped after the model's own keys, so provenance is this module's fact
    # rather than something the reply could overwrite. Inside `analysis`
    # because engine.corpus closes the top level to exactly its schema.
    body["creative"] = dict(creative)
    body["outlier_ratio"] = candidate.get("outlier_ratio")

    record = {
        "schema": corpus.SCHEMA,
        "id": cid,
        "platform": candidate["platform"],
        "url": candidate["url"],
        "channel": candidate["channel"],
        "origin": candidate["origin"],
        "fetched_at": _stamp(now),
        "metrics": dict(candidate["metrics"]),
        "analysis": body,
        "model": MODEL_ANALYSE,
    }

    # engine.corpus is the single definition of a complete record, and its
    # message already names the missing key as the file lays it out
    # ("analysis.hook.words"), so it is raised as it is rather than rephrased.
    corpus.validate(record)
    return record


# --- the two paths -------------------------------------------------------------


def analyse_batch(candidates: list[dict], *, client, now=None) -> AnalysisRun:
    """Up to BATCH_SIZE text candidates (C2) -> their records (C1), ONE call.

    The reply is all or nothing: short an id, truncated, or not JSON raises
    AnalysisError and no record is returned. A per-ad refusal, or a label
    outside the vocabulary, is a skip naming the ad, and the rest of the
    batch survives. An empty list costs no call.
    """
    candidates = list(candidates)
    ids = _check_candidates(candidates)
    if not candidates:
        return AnalysisRun()

    reply = model.call_model(
        client,
        model=MODEL_ANALYSE,
        max_tokens=MAX_TOKENS_ANALYSE,
        messages=[{"role": "user", "content": _prompt(candidates)}],
    )
    analyses = _analyses_from(reply, ids)

    records: list[dict] = []
    skipped: list[str] = []
    for candidate in candidates:
        try:
            records.append(
                _record(
                    candidate, analyses[candidate["id"]],
                    creative={"kind": TEXT_ONLY}, now=now,
                )
            )
        except SkippedCandidate as exc:
            skipped.append(str(exc))
    return AnalysisRun(records=records, skipped=skipped, calls=1)


def analyse_media(
    candidate: dict,
    *,
    client,
    media_root: str | Path | None = None,
    now=None,
) -> dict:
    """One candidate with a hand-saved creative -> one record, ONE call with
    the file attached.

    The file rides on the message as a `media` entry; engine/model.py inlines
    it. A file the transport refuses - over its inline ceiling, an unreadable
    suffix - is raised there as a plain ValueError before any socket, and
    becomes a SkippedCandidate here that names the file and the fix, because
    one 21 MiB clip is one operator's problem and not the run's. A refusal
    from the model is a SkippedCandidate too. A truncated or unreadable reply
    is an AnalysisError.
    """
    _check_candidates([candidate])
    cid = candidate["id"]
    path = local_media(candidate, media_root=media_root)
    if path is None:
        root = Path(media_root) if media_root else MEDIA_ROOT
        raise SkippedCandidate(
            "%s: skipped - there is no creative for the model to watch. Nothing "
            "here downloads one: open the ad's snapshot page at %s, save the "
            "creative by hand to %s (any of %s) and run this step again - or "
            "let analyse_all read the ad from its copy alone."
            % (cid, candidate["url"], root / (cid + MEDIA_SUFFIXES[0]),
               ", ".join(MEDIA_SUFFIXES)),
            candidate_id=cid,
        )

    creative = {"kind": LOCAL_FILE, "ref": _provenance_ref(path)}
    try:
        reply = model.call_model(
            client,
            model=MODEL_ANALYSE,
            max_tokens=MAX_TOKENS_ANALYSE,
            # The file travels as a structured `media` entry; engine/model.py
            # turns it into a real part so the model SEES the creative rather
            # than being told about one. A client that only reads `content`
            # ignores it.
            messages=[{
                "role": "user",
                "content": _prompt([candidate], media_name=path.name),
                "media": {"kind": LOCAL_FILE, "ref": str(path)},
            }],
        )
    except ValueError as exc:
        # engine/model.py's refusal of the file itself, raised before the wire
        # and with the fix in its message (trim it, or use the File API). It
        # is the only ValueError a transport can raise ahead of a reply.
        raise SkippedCandidate(
            "%s: skipped - the creative could not be attached: %s" % (cid, exc),
            candidate_id=cid, cost=0,
        ) from None

    analyses = _analyses_from(reply, [cid])
    return _record(candidate, analyses[cid], creative=creative, now=now)


def analyse_all(
    candidates: list[dict],
    *,
    client=None,
    batch_size: int = BATCH_SIZE,
    media_root: str | Path | None = None,
    now=None,
) -> AnalysisRun:
    """Every candidate, by the cheapest honest path.

    A candidate with a hand-saved creative under `media_root` goes through
    analyse_media, one call each, first and in list order; every other one
    joins a text batch of up to `batch_size`, one call per batch, in list
    order. Records come back in the order the candidates were given.

    A skip is collected and the run continues, because one refused ad or one
    oversized file must not cost the other twenty-three their analysis. An
    AnalysisError or a CorpusInvalid still raises: that is the prompt or the
    model being wrong for a whole batch, and finishing the run would write a
    corpus nobody can trust. An empty list builds no client and needs no key.
    """
    candidates = list(candidates)
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1, got %r" % (batch_size,))
    ids = _check_candidates(candidates)
    if not candidates:
        return AnalysisRun()

    # Built once and handed down. After the empty check, because a run with
    # nothing to analyse should not demand a key to say so.
    if client is None:
        client = model.client()

    with_media: list[dict] = []
    text_only: list[dict] = []
    for candidate in candidates:
        if local_media(candidate, media_root=media_root) is None:
            text_only.append(candidate)
        else:
            with_media.append(candidate)

    by_id: dict[str, dict] = {}
    skipped: list[str] = []
    calls = 0

    for candidate in with_media:
        try:
            by_id[candidate["id"]] = analyse_media(
                candidate, client=client, media_root=media_root, now=now
            )
            calls += 1
        except SkippedCandidate as exc:
            skipped.append(str(exc))
            calls += exc.cost

    for start in range(0, len(text_only), batch_size):
        run = analyse_batch(text_only[start:start + batch_size], client=client, now=now)
        calls += run.calls
        skipped.extend(run.skipped)
        for record in run.records:
            by_id[record["id"]] = record

    records = [by_id[cid] for cid in ids if cid in by_id]
    return AnalysisRun(records=records, skipped=skipped, calls=calls)
