"""The engine's model provider: Gemini Flash, on the free tier.

A copy of `reel-engine/engine/model.py`'s provider client with the call-site
helpers that lived in `reel-engine/engine/script.py` moved in beside it:
`ConfigError`, `CapacityError`, `call_model`, `first_json_object`, plus
`client()` and `text_of()`. In the sibling those helpers live in the writer,
so every research module there imports the writer to make a model call. Here
they live with the provider, so analyse, concepts, score, gate and write all
import ONE module, and nothing that reads strangers' ads has to import the
thing that writes ours.

## The internal contract

Every model call in the engine goes through `call_model`, which expects a
client shaped like this:

    client.messages.create(model=..., max_tokens=..., messages=[...])
        -> reply.content     a list of blocks; text lives on `.type == "text"`
        -> reply.stop_reason "max_tokens" when the answer was cut short

That shape is not Gemini's. It is the engine's own, and every call site plus
its stub (tests/stubs.py) speaks it. `GeminiClient` presents it over the
Google SDK so the provider can change without touching a call site or a stub.

A `system` role in `messages` is folded into the prompt: Gemini takes a system
instruction on the config, but the engine has never used one, and one place to
be wrong is better than two.

## What a message may attach

A message may carry `"media": {"kind", "ref", "mime_type"}`. Two kinds only:
`local-file`, a creative an operator saved BY HAND from a snapshot page into
`research/media/` (docs/AD-RESEARCH-SCOPE.md 3.3 - the Instagram seam, byte
for byte), and `file-uri`, one already uploaded through the File API. There is
no `youtube-url` kind because nothing in this repository watches YouTube, and
there is no kind that fetches anything, because there is no code path that
fetches anything. Images join the video suffixes because an ad creative is as
often a still as a clip.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The board's stack says "Script Writing - Gemini 2.5 Flash - FREE", and that
# exact model is no longer obtainable: a new key gets 404 "no longer available
# to new users" for both gemini-2.5-flash and gemini-2.5-flash-lite. The
# sibling engine runs on a grandfathered one. So this matches the TIER, not the
# string.
#
# Measured by reel-engine's .github/workflows/models.yml, which calls each
# candidate rather than trusting models.list() - 2.5-flash is IN that list and
# still 404s:
#
#     REJECTED  gemini-2.5-flash        404 NOT_FOUND
#     REJECTED  gemini-2.5-flash-lite   404 NOT_FOUND
#     OK        gemini-3.5-flash
#     OK        gemini-3.6-flash
#     OK        gemini-3.5-flash-lite
#     OK        gemini-flash-latest
#
# A full flash, not a lite, because the editorial gate makes judgement calls.
# A pinned id, not gemini-flash-latest, because a safety gate whose model
# changes under it silently is a gate nobody can reason about. When this 404s
# in turn, run the models workflow and pin what it says.
MODEL_FLASH = "gemini-3.5-flash"

# --- why there are two model ids and not one -------------------------------
#
# MEASURED on propose run 26, from the 429 the run died on:
#
#     Quota exceeded for metric: generate_content_free_tier_requests,
#     limit: 20, model: gemini-3.5-flash
#     quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier
#     quotaValue: 20
#
# TWENTY REQUESTS A DAY. Not per minute - per DAY, and docs/COST.md said this
# cap "has orders of magnitude of room", which is the opposite of true. One
# propose run of three concepts at three attempts each is up to 18 calls, and
# a research sweep is up to 14. A single day that does both cannot fit in one
# model's allowance, and run 26 proved it by dying on the second concept.
#
# Read the quota id again, though: PerProjectPerModel. The 20 is counted per
# MODEL, so two model ids are two allowances. Splitting writing from judging
# doubles the day's headroom without a second key, a second project, or a
# penny.
#
# WHICH HALF MOVES MATTERS, and the gate is the half that stays. It is a
# safety check, its judgement is the thing this repository exists to protect,
# and gemini-3.5-flash is the model that has actually been observed making it:
# run 26 refused a latency promise and a judgement-call tag, then passed the
# rewrite. That behaviour is measured, and moving it would trade a known judge
# for an unknown one to save a quota the gate is not what exhausts.
#
# Writing is the half that moves. It is generative rather than adjudicating,
# it is where the retries multiply (three attempts per concept, each a fresh
# call), and a sibling flash model writes a reel script as well as its cousin.
#
# It buys a second property worth having on its own terms: the model that
# writes the copy is no longer the model that judges it. A writer marking its
# own homework is the weaker of the two arrangements, and until now that is
# exactly what this was.
#
# gemini-3.6-flash is measured OK by reel-engine's .github/workflows/models.yml,
# which calls each candidate rather than trusting models.list(). When it 404s
# in turn, run that workflow and pin what it says - the same rule MODEL_FLASH
# carries. Both ids are shared with the sibling on purpose: one measurement,
# two repositories.
MODEL_WRITE = "gemini-3.6-flash"

# Free-tier keys are minted at aistudio.google.com. GOOGLE_API_KEY is the
# name the Google SDK reads on its own, so both are accepted and GEMINI_API_KEY
# wins - it is the one docs/SECRETS.md tells an operator to set.
KEY_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


# --- surviving a free-tier capacity spike ----------------------------------
#
# WHAT WENT WRONG. Four propose runs in a row died like this, the last of them
# on the FIRST model call of the run, before a single draft existed:
#
#     segment: Payroll bureaus (rank 2)
#     scripting (attempt 1)
#     google.genai.errors.ServerError: 503 UNAVAILABLE. This model is
#     currently experiencing high demand. Spikes in demand are usually
#     temporary. Please try again later.
#
# A 503 says so in its own message: temporary, try again. Nothing tried again.
# `tenacity` appears in that traceback, which is exactly what makes this easy
# to misread as a retry loop that was not patient enough - it is not a retry
# loop at all. MEASURED against google-genai as installed:
#
#     genai.Client(api_key=k)._api_client._retry.stop.max_attempt_number == 1
#
# The SDK wraps every request in tenacity and then, when no retry_options are
# given, configures that wrapper to stop after one attempt. Its own docstring
# is blunt about it: "If None, the 'never retry' stop strategy will be used."
# So a single blip on a free-tier endpoint that is explicitly described as
# spiky threw away the whole run, and the only recovery was a human noticing
# and pressing the button again.
#
# THE LADDER. MEASURED from the constructed client, in seconds of sleep after
# each failed attempt: 2.9, 4.6, 8.2, 16.7, 32.9 - about 65s of patience per
# call before it gives up, jitter included (the SDK adds U(0,1) to each).
#
# Bounded on purpose. propose scripts and gates up to three concepts, so six
# calls; if every one of them needed its last retry the run would spend ~6.5
# extra minutes, which still lands inside that workflow's timeout-minutes: 25
# alongside its ~5 minutes of real work. Runner minutes are the budget that
# matters here - docs/COST.md - and waiting spends them, so patience has to
# have a ceiling rather than being "keep trying".
#
# WHY 429 IS DELIBERATELY NOT IN THIS LIST, though the SDK's own default set
# includes it. A 429 here is the free tier's quota, and call_model below
# already turns it into one plain line telling the operator it resets on its
# own. Some of those are a per-minute ceiling that a wait would clear; the
# rest are the per-DAY one, which no amount of waiting clears - and the two
# are not reliably distinguishable from the error. Retrying the day limit
# burns a minute of runner time per call to re-ask a question whose answer is
# a calendar. That trade is a separate decision with a quota cost of its own;
# this change is about transport faults, and leaves the quota behaviour
# exactly as it was.
#
# 408 and the 5xx family are different in kind: they are the service saying it
# failed, not that we asked too much.
RETRY_STATUS_CODES = (
    408,  # request timeout
    500,  # internal
    502,  # bad gateway
    503,  # UNAVAILABLE - the one that has actually been costing runs
    504,  # gateway timeout
)
RETRY_ATTEMPTS = 6        # the initial call plus five retries
RETRY_INITIAL_DELAY = 2.0  # seconds before the first retry
RETRY_EXP_BASE = 2.0
RETRY_MAX_DELAY = 60.0     # ceiling on any single wait


def http_options():
    """The retry policy above, as the SDK's config object.

    Built here rather than inline in the constructor so a test can read the
    policy without standing up a client, and so the numbers above are the only
    place they are written down.
    """
    from google.genai import types

    return types.HttpOptions(
        retry_options=types.HttpRetryOptions(
            attempts=RETRY_ATTEMPTS,
            initial_delay=RETRY_INITIAL_DELAY,
            exp_base=RETRY_EXP_BASE,
            max_delay=RETRY_MAX_DELAY,
            http_status_codes=list(RETRY_STATUS_CODES),
        )
    )


@dataclass(frozen=True)
class TextBlock:
    text: str
    type: str = "text"


@dataclass(frozen=True)
class Reply:
    """What a call site reads. Deliberately the shape the tests already stub."""

    content: list[TextBlock] = field(default_factory=list)
    stop_reason: str = "end_turn"


def api_key() -> str | None:
    for name in KEY_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


# --- the operator's faults ---------------------------------------------------


class ConfigError(RuntimeError):
    """A missing or invalid piece of the environment the engine needs.

    Distinct from RuntimeError so a workflow entry point can turn a setup
    fault - the operator's to fix - into one line, while a genuine bug still
    gets its traceback. Subclasses it so anything already catching
    RuntimeError keeps working.
    """


class CapacityError(ConfigError):
    """The provider is temporarily out of capacity - a 503, after retrying.

    A ConfigError so every existing handler keeps treating it as one line
    rather than a traceback. A SUBCLASS because it is the one fault in that
    family that is not identical for every concept in a run: a missing key
    and a rejected key would fail all three the same way, so aborting is
    right, while a capacity spike is per-call and intermittent. The concept
    after this one may well go through, and a selection loop catches this
    specifically to give it that chance.
    """


# --- attaching a creative ----------------------------------------------------

# A local file has to be sent in the request, and the generateContent request
# body is the limit that bites first - well below what the File API would
# accept - so an oversized file is refused by name here rather than as a 400
# from the wire. 20 MiB is the documented inline ceiling for the body.
INLINE_LIMIT = 20 * 1024 * 1024

# Video for a Reels or feed creative, images for a static one. An ad is as
# often a still as a clip, which is why the image types are here and were not
# in the sibling. Anything else is refused by suffix, naming the file.
MIME_BY_SUFFIX = {
    ".mp4": "video/mp4", ".mov": "video/quicktime",
    ".m4v": "video/x-m4v", ".webm": "video/webm",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
}

MEDIA_KINDS = ("local-file", "file-uri")


def _media_part(types, media: dict):
    """One `media` entry from a message, as a part the model actually reads."""
    kind = media.get("kind")
    ref = media.get("ref")
    if not ref:
        raise ValueError("a media entry carries no 'ref'; nothing to attach")

    if kind == "local-file":
        path = Path(ref)
        if not path.is_file():
            raise ValueError(
                f"no media file at {path}. A creative is saved by hand from "
                "the snapshot page into research/media/; nothing fetches one"
            )
        mime = MIME_BY_SUFFIX.get(path.suffix.lower())
        if mime is None:
            raise ValueError(
                f"{path.name} has suffix {path.suffix!r}; expected one of "
                + ", ".join(sorted(MIME_BY_SUFFIX))
            )
        data = path.read_bytes()
        if len(data) > INLINE_LIMIT:
            raise ValueError(
                f"{path.name} is {len(data) / (1024 * 1024):.1f}MB, over the "
                f"{INLINE_LIMIT // (1024 * 1024)}MB a request body can "
                "carry inline. Trim the clip, or upload it with the File API "
                "and pass kind='file-uri'."
            )
        return types.Part.from_bytes(data=data, mime_type=mime)

    if kind == "file-uri":
        # Already uploaded via the File API; ref is the returned uri. The
        # service records the mime type at upload, so a caller may omit it -
        # but Part.from_uri infers one from the uri's suffix and RAISES when
        # there is none to infer, which a File API uri (.../files/abc123)
        # never has. Measured against google-genai 2.24.0. So the part is
        # built directly, carrying the uri and whatever mime type we were
        # given, the same way the sibling builds a YouTube part.
        mime = media.get("mime_type") or MIME_BY_SUFFIX.get(
            Path(str(ref)).suffix.lower()
        )
        return types.Part(file_data=types.FileData(file_uri=str(ref), mime_type=mime))

    raise ValueError(
        f"unknown media kind {kind!r}; expected one of " + ", ".join(MEDIA_KINDS)
    )


class _Messages:
    def __init__(self, client):
        self._client = client

    def create(self, *, model: str, max_tokens: int, messages: list[dict], **_):
        from google.genai import types

        prompt = "\n\n".join(
            m["content"] for m in messages if m.get("content")
        )

        # A message may carry `media`, and attaching it is the difference
        # between the model SEEING a creative and being TOLD about one. Naming
        # a URL in prompt text gets a confident answer written from whatever
        # the model already knows, which is indistinguishable from analysis
        # and completely untrustworthy. So the media travels as a real part.
        #
        # contents stays a bare string when nothing is attached, so every
        # text-only call site - gate, concepts, score, write, the analyse
        # batches - sends exactly the bytes it would without this existing.
        parts = [_media_part(types, m["media"]) for m in messages if m.get("media")]
        contents = [types.Part.from_text(text=prompt), *parts] if parts else prompt

        response = self._client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(max_output_tokens=max_tokens),
        )

        # `.text` is a convenience that concatenates the text parts, and it is
        # None when the answer carried none - a MAX_TOKENS stop that spent its
        # whole budget thinking produces exactly that. Coerce, so a call site
        # reading a text block never meets None.
        text = response.text or ""

        stop = "end_turn"
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            reason = getattr(candidates[0], "finish_reason", None)
            if reason is not None and getattr(reason, "name", str(reason)) == "MAX_TOKENS":
                stop = "max_tokens"

        return Reply(content=[TextBlock(text=text)], stop_reason=stop)


class GeminiClient:
    """Google's SDK behind the engine's internal model contract."""

    def __init__(self, key: str):
        from google import genai

        # http_options carries the retry policy. Without it the SDK stops
        # after one attempt and a single 503 - which the free tier issues
        # routinely and describes as temporary - ends the run.
        self._client = genai.Client(api_key=key, http_options=http_options())
        self.messages = _Messages(self._client)


def client() -> GeminiClient:
    """The one client a run builds and hands down.

    Raises ConfigError naming the variable to set, before any socket: a
    missing key is the operator's to fix and the message says how.
    """
    key = api_key()
    if not key:
        raise ConfigError(
            "GEMINI_API_KEY is not set; the engine judges with %s and writes "
            "with %s. Mint a free key at aistudio.google.com"
            % (MODEL_FLASH, MODEL_WRITE)
        )
    return GeminiClient(key)


# --- the call-site helpers ---------------------------------------------------


def call_model(client, *, model: str, max_tokens: int, messages: list[dict]) -> Reply:
    """messages.create, with the operator's faults turned into ConfigError.

    A key the provider rejects, or a project without access, is not a bug and
    no retry fixes it - it is the operator's to fix, the same class as a
    missing key. Observed in CI on the sibling's previous provider: the raw
    API error escaped as a traceback mid-run, one attempt after a perfectly
    good verdict, and read like a crash.

    Credential, quota and exhausted-capacity faults are converted. A malformed
    request keeps its traceback because it is a bug.

    Note what "converted" does NOT mean for a 503: GeminiClient carries a
    retry ladder that spends about 65 seconds on one before it ever reaches
    here, so this branch is the spike that outlasted the waiting, not the
    first blip.
    """
    from google.genai import errors

    try:
        return client.messages.create(
            model=model, max_tokens=max_tokens, messages=messages
        )
    except errors.ServerError as exc:
        # The free tier spikes, says so in the error, and the SDK does not
        # retry on its own - see the ladder above. Four propose runs died on
        # this as a bare traceback, which reads like the engine broke; it did
        # not, and there is nothing to fix but the clock.
        raise CapacityError(
            "Gemini is out of capacity right now (%s: %s). The free tier "
            "spikes through the day and this run already waited and retried. "
            "Nothing is wrong with the setup - re-run it later, or let the "
            "schedule do it."
            % (getattr(exc, "code", "5xx"),
               getattr(exc, "message", None) or "no detail given")
        ) from exc
    except errors.ClientError as exc:
        text = str(exc)
        code = getattr(exc, "code", None)
        if code in (401, 403) or "API_KEY_INVALID" in text or "PERMISSION_DENIED" in text:
            raise ConfigError(
                "Gemini rejected the key: %s. Mint a free one at "
                "aistudio.google.com and set GEMINI_API_KEY" % text
            ) from exc
        if code == 429 or "RESOURCE_EXHAUSTED" in text:
            raise ConfigError(
                "the Gemini free tier is rate limited right now: %s. It "
                "resets on its own - re-run rather than changing anything" % text
            ) from exc
        raise


def text_of(reply) -> str:
    """The first block that says it is text, or "" when there is none.

    A thinking-capable model leads with thinking blocks, which carry no .text
    at all, so `reply.content[0].text` is the wrong read and every call site
    goes through this one instead. tests/stubs.py leads every stubbed reply
    with a thinking block for exactly that reason.
    """
    for block in getattr(reply, "content", None) or []:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", None) or ""
    return ""


def first_json_object(text: str) -> dict | None:
    """The one JSON object in a model's answer, or None.

    A well-behaved response is the object and nothing else, so try the whole
    string first; the greedy regex is the fallback for prose or a code fence
    around it. When even that fails - prose AFTER the object that happens to
    contain a brace - decode from the first `{` and stop where the object
    stops. Anything that is not an object is None, never a list or a string.
    """
    try:
        whole = json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(whole, dict):
            return whole

    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        found = json.loads(match.group(0))
    except json.JSONDecodeError:
        try:
            found, _ = json.JSONDecoder().raw_decode(text, match.start())
        except json.JSONDecodeError:
            return None
    return found if isinstance(found, dict) else None
