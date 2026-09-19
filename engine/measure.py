"""python -m engine.measure [--dry-run] [--strict] [--out PATH] [--raw]

The MEASURE stage: what our OWN launched ads actually did, read back off the
Marketing API insights edge - one call per pinned ad id, no model call, and a
null wherever Meta gave nothing.

THE DESIGN DECISION, and the reason this module is SIMPLER than the one it is
ported from. `reel-engine/engine/measure.py` has to MATCH: Buffer schedules a
post and returns no permalink, so the first measurement of a reel is a guess
over our own recent uploads, pinned into the job once made and refused when
two uploads look alike. Nothing here guesses, because nothing here has to.
The second `go` on an ad publishes nothing: a human uploads the creative in
Ads Manager and pastes the ad id back with `python -m engine.approval
launch`, which pins it under `ads` before the job can enter queue/launched/
at all (docs/AD-RESEARCH-SCOPE.md 3.11). Launch IS the pin. Every measurement
is an exact lookup of an id a human wrote down, no job file is ever written
here, and the whole matcher - the window, the similarity, both refusals - has
no twin in this file.

ONE CALL PER AD, NOT ONE PER FIFTY. The scope document (3.12) budgets "one
call per fifty ids", which is the account-level read: `/act_<id>/insights?
level=ad&filtering=[...]` - an account id from research/seeds.yaml, a JSON
filter parameter, a paging cursor. That is a SECOND URL shape, and nobody
here has verified either shape against a live response. `/{ad_id}/insights`
is the one form whose answer for one ad is the same object as its answer for
fifty, so it is the one form the first live run has to prove, and the cost
of getting it wrong is one ad rather than the run. A repository with twenty
launched ads spends twenty of a 200-an-hour budget once a week. Batching is a
one-method change on the day a live response is in hand. It is also why
`own.ad_account_id` in research/seeds.yaml is NOT read here: an ad id is
globally unique on the Graph API and the token's `ads_read` on our own
account is what scopes the answer, so the account id is a fact the batched
form needs and this one does not.

NO MODEL CALL. Every number in a row is Meta's, parsed and nothing more, and
the two derived rates are two divisions that say so in their name. Nothing
here imports engine.model, and nothing should: a measurement is the one place
in the loop where a number was OBSERVED rather than judged (scope 1.2, rule
2), and it is the strongest evidence the loop ever holds - the only
click-through rate in the whole design is our own.

ABSENT IS NULL, NEVER 0. A field Meta did not return - every video metric on
an image ad, `actions` on an ad that has not converted, `reach` on an ad too
new to have any - is null in the row; an ad with no insights row at all is a
named skip rather than a row of zeros. engine.learn medians the CTR and
engine.feedback refuses a row with no impressions BY NAME, so a fabricated 0
would either sink a median or be refused for the wrong reason. Booleans and
NaN are refused the same way, because True is 1 to a median.

THE LEDGER IS DISCOVERY'S, COPIED. `Quota` below is engine/discover.py's
class shape for shape - charged BEFORE the socket opens, refusing what it
cannot afford, carrying the numbers on the refusal - with its own price list
and its own advice, because the Marketing API is not the Ad Library API: Meta
rate-limits the insights edge per AD ACCOUNT by a business-use-case formula
it publishes as a formula and not as a number. HOURLY_BUDGET_CALLS is the
contract's 200, a ceiling nothing here approaches, and a measured figure
replaces it in one line. Copied rather than imported so that this module and
discovery can each be read, tested and replaced on their own.

THE TOKEN is engine.oauth's - aged from its stored issue date, warned about
from day 40 and refused past day 60 before any socket - and travels in an
`Authorization: Bearer` header, never in a URL and never in a message. Every
transport call runs inside a scrub that cuts the value, whole or in part, out
of anything raised, because Meta echoes tokens in error bodies and
http.client echoes a bad header in its own. `_http(url, token)` is the ONLY
function here that opens a socket; `MeasureClient(transport=...)` replaces
it, and every test in tests/test_measure.py is offline.

A JOB THAT CANNOT BE MEASURED IS REPORTED, NOT FATAL - the same posture as
engine.analyse.analyse_all and the reel measure. One ad Meta refuses, one job
whose `ads` map somebody emptied by hand, one unreadable file: each is a line
in `MeasureRun.skipped` naming the file and the fix, and every other ad is
measured. A missing token or an exhausted budget is a different thing: that
is the whole run misconfigured, and it raises.

DETERMINISM. Given the same jobs and the same bodies the document is
byte-identical: rows are sorted by (segment, ad id), `launched_at` is what
approval stamped, `measured_at` and `generated_at` come from `now=`, and the
wall clock is read in exactly one place, `main()`.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from engine import approval, oauth

ROOT = Path(__file__).resolve().parents[1]

# Unversioned on purpose, the same rule engine/discover.py applies to the
# archive: an unversioned Graph call runs against the oldest version the app
# still supports, which is the most stable thing to pin an unattended cron
# to. META_GRAPH_VERSION in the environment inserts one ("v21.0") when a
# field this module reads turns out to need it.
GRAPH = "https://graph.facebook.com"
GRAPH_VERSION_ENV = "META_GRAPH_VERSION"
GRAPH_VERSION_RE = re.compile(r"^v?\d+\.\d+$")

# The name of the secret, for messages. The VALUE is read by engine/oauth.py
# and only there, so the age of the token is counted in one place.
META_ACCESS_TOKEN = oauth.META_ACCESS_TOKEN

# TODO(integration): UNVERIFIED AGAINST A LIVE RESPONSE.
#
# Every name below, and every `action_type` string this module reads out of
# `actions` and the video lists, is the Marketing API insights reference AS
# REMEMBERED - docs/AD-RESEARCH-SCOPE.md section 9 says so, and nobody has
# called the edge with a real token. What is assumed, exactly:
#
#   - the fifteen field names are accepted by `/{ad_id}/insights?fields=`;
#     an unknown one is a 400 with code 100 that names it, and _api_error
#     points back at this block;
#   - counts and money come back as STRINGS ("4100", "0.61"), which is why
#     every reader below parses rather than trusts a type;
#   - `actions` is a list of {"action_type": ..., "value": ...} and the
#     3-second play count is the entry whose action_type is PLAY_ACTION;
#   - `video_thruplay_watched_actions` and the four `video_pNN_watched_actions`
#     lists carry one entry each, and its `value` is the count;
#   - a lead, a booked call, a contact and a link click are the action_type
#     strings in RESULT_ACTIONS, in that order of preference.
#
# The first live run is the proof: `python -m engine.measure --dry-run --raw`
# and read each row's `raw` block against this list. `raw` is the insights
# object exactly as Meta returned it, on a row ONLY when --raw is passed; the
# committed document never carries one by default. `video_play_actions` is
# requested so that run can compare it against actions[PLAY_ACTION]; it is
# not read into any C6 field.
INSIGHT_FIELDS = (
    "impressions",
    "reach",
    "clicks",
    "ctr",
    "cpc",
    "cpm",
    "spend",
    "actions",
    "cost_per_action_type",
    "video_play_actions",
    "video_thruplay_watched_actions",
    "video_p25_watched_actions",
    "video_p50_watched_actions",
    "video_p75_watched_actions",
    "video_p100_watched_actions",
)

# The ad's whole life. A measurement is cumulative and `launched_at` on the
# row says how long that life has been; engine.feedback turns the two into
# days_running. A rolling window would make two runs' rows incomparable.
DATE_PRESET = "maximum"

# The action_type of a 3-second video play inside `actions`. See the TODO.
PLAY_ACTION = "video_view"

# What counts as a "result", in order of preference: the first of these that
# `actions` carries is the row's `results`, and its `cost_per_action_type`
# twin is `cost_per_result`. A lead beats a booked call beats a contact beats
# a link click, because each is nearer the thing the ad was for. See the TODO.
RESULT_ACTIONS = ("lead", "schedule", "contact", "link_click")

# Contract C6, in the contract's order. The document is written sort_keys so
# the file is alphabetical; this is the order a row is built in.
METRIC_KEYS = (
    "impressions", "reach", "clicks", "ctr", "cpc", "cpm", "spend",
    "plays_3s", "thruplays", "p25", "p50", "p75", "p100",
    "results", "cost_per_result",
)
DERIVED_KEYS = ("hook_rate", "hold_rate")

# Derived rates are arithmetic done here and rounded here; Meta's own numbers
# are stored as Meta gave them. Three places: 1200 of 4100 impressions is
# 0.293, and a fourth place would be precision nobody measured.
RATE_PLACES = 3

# The contract's figure, copied from the Ad Library budget in
# engine/discover.py. The insights edge is limited per ad account by a
# formula, not a count, so this is a ceiling a weekly run of one call per
# launched ad never approaches - and a parameter so a measured one replaces it.
HOURLY_BUDGET_CALLS = 200

# One unit per insights call. There is one endpoint here and every call to it
# costs the same, so the ad count, not the endpoint, is the figure to watch.
UNIT_COSTS = {"insights": 1}

MEASUREMENTS_PATH = ROOT / "research" / "measurements.json"

# Contract C6. `schema` is the version of the document, not of a row.
SCHEMA = 1

# The terminal stage. A job anywhere else has not gone out and has nothing to
# measure - the directory IS the status (engine/approval.py).
STAGE = "launched"

HTTP_TIMEOUT_SECONDS = 30

QUOTA_ADVICE = (
    "The insights edge is rate-limited per ad account by Meta's business-use-"
    "case formula (a formula, not a published count; codes 4, 17, 32, 613 and "
    "80004 name it). Nothing here retries. A run costs one call per launched "
    "ad, so wait for the hour to roll over, or raise the budget only if the "
    "limit measured on this account is higher."
)


class MeasureError(RuntimeError):
    """Anything that stops a measurement. Always names what the operator fixes."""


class MissingTokenError(MeasureError):
    """No usable Meta access token. Never carries a value."""


class QuotaExceededError(MeasureError):
    """A call was refused because the run cannot afford it.

    Raised BEFORE the request, so a refused call costs nothing. Carries the
    numbers as attributes as well as in the message: a caller that wants to
    degrade gracefully - keep what it already found, skip the rest - needs
    them without parsing prose.
    """

    def __init__(self, endpoint: str, needed: int, remaining: int, budget: int):
        self.endpoint = endpoint
        self.needed = needed
        self.remaining = remaining
        self.budget = budget
        super().__init__(
            f"marketing api {endpoint} needs {needed} call(s) and {remaining} "
            f"remain of the {budget}-call hourly budget. {QUOTA_ADVICE}"
        )


class ApiError(MeasureError):
    """The Marketing API answered with an error. Carries Meta's own message."""


class UnmeasurableJob(MeasureError):
    """One launched ad produced no row, and the message says what to do.

    Collected by measure_all() rather than raised out of it: an ad that has
    not delivered yet, or a job whose `ads` map was emptied by hand, is one
    job's problem and is not fixed by refusing the other nine their row.
    """


# ---------------------------------------------------------------------------
# Quota - discovery's ledger, copied
# ---------------------------------------------------------------------------


class Quota:
    """The call ledger for one run. Refuses, it does not warn.

    Meta counts on receipt of the request, so calls are charged here before
    the socket opens. That direction is deliberate: this ledger can over-count
    (a request that never reached Meta), never under-count, and only
    under-counting produces the failure that matters - a run killed
    mid-flight with half its ads measured and no record of why.
    """

    def __init__(self, budget: int = HOURLY_BUDGET_CALLS, *, spent: int = 0):
        if budget < 0:
            raise ValueError(f"quota budget cannot be negative, got {budget}")
        self.budget = budget
        self.spent = spent

    @property
    def remaining(self) -> int:
        return self.budget - self.spent

    def cost(self, endpoint: str) -> int:
        try:
            return UNIT_COSTS[endpoint]
        except KeyError:
            raise ValueError(
                f"unknown endpoint {endpoint!r}; this module prices only "
                f"{', '.join(sorted(UNIT_COSTS))}. Add it to measure.UNIT_COSTS "
                f"before calling it - never guess a price."
            ) from None

    def charge(self, endpoint: str) -> int:
        """Reserve the units for one call, or refuse it. Returns the cost."""
        needed = self.cost(endpoint)
        if needed > self.remaining:
            raise QuotaExceededError(endpoint, needed, self.remaining, self.budget)
        self.spent += needed
        return needed

    def affords(self, endpoint: str) -> bool:
        """Whether one more call of this kind fits. Charges nothing."""
        return self.cost(endpoint) <= self.remaining


# ---------------------------------------------------------------------------
# The Marketing API
# ---------------------------------------------------------------------------


def graph_url() -> str:
    """The Graph host, versioned only if the environment says so.

    The same rule as engine/discover.py's api_url(), so one variable steers
    both of this repository's Graph reads.
    """
    version = os.environ.get(GRAPH_VERSION_ENV, "").strip()
    if not version:
        return GRAPH
    if not GRAPH_VERSION_RE.match(version):
        raise MeasureError(
            f"{GRAPH_VERSION_ENV} is {version!r}, which is not a Graph API "
            f"version. Write it as v21.0, or unset it to call the edge "
            f"unversioned."
        )
    if not version.startswith("v"):
        version = "v" + version
    return f"{GRAPH}/{version}"


def insights_url(ad_id: str) -> str:
    """GET {GRAPH}/{ad_id}/insights?fields=...&date_preset=maximum. No token.

    The id has been checked as digits before it reaches a path, so the URL
    cannot be steered anywhere but an ad's own insights edge.
    """
    return f"{graph_url()}/{ad_id}/insights?" + urlencode({
        "fields": ",".join(INSIGHT_FIELDS),
        "date_preset": DATE_PRESET,
    })


def _scrubbed(token: str, work):
    """Run `work()`; scrub the token out of anything it raises.

    engine.oauth._redact is the repository's one definition of the cut - the
    whole value and any run of it twelve characters or longer - and it is
    called here rather than a copy of it, so the two Graph consumers and the
    module that owns the token can never disagree about what a leak is.

    EVERY exception is converted, not only MeasureError: an injected
    transport is arbitrary caller code and may raise anything, with anything
    in it. The replacement is a FRESH object raised AFTER the except block,
    both halves load-bearing: raising inside the handler would chain the
    original on as `__context__` with its unscrubbed message readable to
    anything that walks the chain, and re-raising the same object would carry
    whatever `__context__` it already had from inside `work`.
    """
    try:
        return work()
    except QuotaExceededError:
        raise  # carries numbers, never a value; charged before this wrapper
    except MeasureError as exc:
        clean = oauth._redact(str(exc), [token])
        try:
            error = type(exc)(clean)
        except TypeError:
            # A subclass carrying its own __init__ signature. Rebuilding it
            # from one string is a TypeError, and an uncaught one HERE would
            # escape the scrubber with the original exception as its
            # __context__ - the leak this wrapper exists to prevent, arriving
            # through the wrapper itself. Still a MeasureError, still scrubbed.
            error = ApiError(clean)
    except Exception as exc:
        error = ApiError(oauth._redact(f"{type(exc).__name__}: {exc}", [token]))
    except BaseException as exc:  # noqa: BLE001 - deliberate
        # KeyboardInterrupt, SystemExit and asyncio.CancelledError derive from
        # BaseException and sail past `except Exception` with their messages
        # and their chains intact. Scrubbed argument by argument and KEEPING
        # their own type, so SystemExit(2) keeps its exit code and Ctrl-C
        # still kills the run on the first press.
        cleaned = tuple(
            oauth._redact(arg, [token]) if isinstance(arg, str) else arg
            for arg in exc.args
        )
        try:
            error = type(exc)(*cleaned)
        except TypeError:
            error = type(exc)()
    raise error


def _http(url: str, token: str) -> dict:
    """The default transport: one GET, one JSON document back.

    urllib rather than a new dependency. This is the ONLY function in this
    module that opens a socket - replace it, and measurement is offline.

    The token goes in the Authorization header and nowhere else, so the URL
    never carries it and can be logged. Meta's own error body is what an
    operator needs; it is passed up and scrubbed by the caller.
    """
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise ApiError(_api_error(exc.code, exc.read().decode("utf-8", "replace")))
    except urllib.error.URLError as exc:
        raise ApiError(f"could not reach the Marketing API: {exc.reason}")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise ApiError(f"the Marketing API returned non-JSON: {body[:200]!r}")
    if not isinstance(parsed, dict):
        raise ApiError(
            f"the Marketing API returned {type(parsed).__name__}, not an object"
        )
    return parsed


def _api_error(status: int, body: str) -> str:
    """Meta's message, plus the one piece of advice it never gives."""
    message, code, subcode, kind = body[:200], None, None, ""
    try:
        error = (json.loads(body) or {}).get("error") or {}
        message = error.get("message") or message
        code = error.get("code")
        subcode = error.get("error_subcode")
        kind = error.get("type") or ""
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    text = f"Marketing API {status}: {message}"
    if code is not None:
        text += f" (code {code}{', ' + kind if kind else ''})"
    if code in (4, 17, 32, 613, 80004):
        # Meta's counter is authoritative and ours may be a fresh ledger in
        # the same hour - another run, or a hand-run script, spent it.
        text += f". {QUOTA_ADVICE}"
    elif code == 100 and (subcode == 33 or "does not exist" in str(message)):
        # The id is not an ad the token can see: a typo in the paste, an ad
        # deleted in Ads Manager, or an ad account the token was never
        # granted. Told apart from a bad parameter by Meta's own subcode.
        text += (
            ". The ad id is not one this token can see: it was pasted wrong "
            "at `approval launch`, the ad was deleted in Ads Manager, or the "
            "token's user has no ads_read on the ad account it lives in. "
            "Check the id against Ads Manager's Ad ID column and correct it "
            "under \"ads\" in the job file in queue/launched/."
        )
    elif code == 10 or (isinstance(code, int) and 200 <= code <= 299) or status == 403:
        # Permission errors are typed OAuthException too, so they are told
        # apart by code before the token branch below catches the type.
        text += (
            ". A permission error here usually means the token has no "
            "ads_read on OUR ad account: the token's user must be granted "
            "the account in Business Manager and the app must have the "
            "Marketing API product. docs/SECRETS.md has the steps."
        )
    elif code == 100:
        # Before the token branch: Meta types a bad-fields error as
        # OAuthException too, and the fix for that is this file, not the
        # secret.
        text += (
            ". Code 100 is a parameter Meta did not accept. The field names "
            "in engine/measure.py's INSIGHT_FIELDS are unverified against a "
            "live response (see the TODO(integration) block there); if this "
            "is the first live call, one of them is the guess, and Meta's "
            "message above usually names it."
        )
    elif code == 190 or kind == "OAuthException":
        text += (
            f". The token {META_ACCESS_TOKEN} holds was refused: it has "
            f"expired, was revoked, or was minted without ads_read. Mint a "
            f"fresh one and update the secret and META_TOKEN_ISSUED in the "
            f"same visit; python -m engine.oauth --status says how old the "
            f"stored one is."
        )
    return text


def _token_from_oauth() -> str:
    """The token, aged and checked by engine/oauth.py before any socket."""
    try:
        return oauth.meta_token()
    except oauth.OAuthError as exc:
        # Already scrubbed by oauth; re-raised as a MeasureError so main()
        # prints it as one line. The name is repeated so the message says
        # which secret whatever oauth read first. Raised OUTSIDE the except
        # block: `from None` hides the original from a printed traceback but
        # leaves it hanging off __context__, and a clean chain is the
        # property tests/test_oauth.py proves for oauth's own refusals.
        error = MissingTokenError(
            f"no Meta access token for the Marketing API insights edge "
            f"({META_ACCESS_TOKEN}): {exc}"
        )
    raise error


class MeasureClient:
    """The insights edge behind a call ledger and one swappable transport.

    Not a subclass of discover.AdLibraryClient: that client exists to search
    an archive with a page-id batch and a cursor, and none of that applies to
    an exact lookup by id. What the two share - charge before the socket,
    header not URL, a scrub around the transport - is short enough to be read
    twice and long enough that each file must be right on its own.
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        budget: int = HOURLY_BUDGET_CALLS,
        quota: Quota | None = None,
        transport=None,
    ):
        self._token = token or _token_from_oauth()
        self.quota = quota if quota is not None else Quota(budget)
        self._transport = transport or _http

    def insights(self, ad_id: str) -> dict:
        """The one insights object for one ad, or a refusal. One charge.

        Returns `data[0]` of the response - the object whose keys are
        INSIGHT_FIELDS - not the envelope around it. No `data` at all is an
        ApiError (the edge did not answer in its own shape); an EMPTY `data`
        is an UnmeasurableJob, because that is what Meta says for an ad that
        has not delivered an impression, and a row of zeros for it would be a
        number nobody observed. More than one object is refused too: this
        module asks for no breakdown and no time increment, so a second row
        means the edge's shape is not the assumed one.
        """
        ad_id = str(ad_id or "").strip()
        if not approval.META_ID_RE.fullmatch(ad_id):
            raise ValueError(
                f"ad id {ad_id!r} is not a Meta id (all digits); it is the "
                f"number in Ads Manager's Ad ID column, pinned by "
                f"`approval launch`"
            )
        # Charge first. A call this run cannot afford is never made, which is
        # the whole point - see Quota. Charged outside the scrubber because a
        # refusal carries numbers and no value.
        self.quota.charge("insights")
        url = insights_url(ad_id)
        token = self._token

        def fetch() -> dict:
            body = self._transport(url, token)
            if not isinstance(body, dict):
                raise ApiError(
                    f"the Marketing API returned {type(body).__name__}, not an object"
                )
            if "error" in body:
                # The API normally signals errors with a status code, but a
                # 200 carrying an error object would otherwise read as no data
                # - which reads as an ad nobody saw.
                raise ApiError(_api_error(200, json.dumps(body)))
            return body

        body = _scrubbed(token, fetch)

        data = body.get("data")
        if not isinstance(data, list):
            raise ApiError(
                f"ad {ad_id}: the insights edge answered without a `data` list "
                f"(keys seen: {', '.join(sorted(str(k) for k in body)) or 'none'}). "
                f"That is not the documented shape; run with --dry-run --raw "
                f"once the read below is fixed to see what it is."
            )
        if not data:
            raise UnmeasurableJob(
                f"ad {ad_id}: Meta returned no insights row for "
                f"date_preset={DATE_PRESET}. The ad has not delivered an "
                f"impression yet, or the token cannot see the ad account it "
                f"lives in (ads_read on our own account). Nothing was written "
                f"for it - a row of zeros would be a number nobody measured - "
                f"and the next weekly run asks again."
            )
        if len(data) > 1:
            first = data[0] if isinstance(data[0], dict) else {}
            raise UnmeasurableJob(
                f"ad {ad_id}: Meta returned {len(data)} insights rows where one "
                f"was expected. This module asks for no breakdown and no time "
                f"increment, so the edge's shape is not the assumed one; the "
                f"first row's keys are {', '.join(sorted(str(k) for k in first)) or 'none'}. "
                f"Fix the read in engine/measure.py (MeasureClient.insights) "
                f"rather than taking the first row on faith."
            )
        row = data[0]
        if not isinstance(row, dict):
            raise ApiError(
                f"ad {ad_id}: the insights row is a {type(row).__name__}, not "
                f"an object"
            )
        return row


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def launched_jobs() -> list[approval.Job]:
    """Every terminal job, in filename order. Sidecars are not jobs.

    approval.jobs_in() rather than a glob of queue/launched/: every launched
    reel job leaves a `<segment>.reel.json` selection beside it, and a bare
    glob would count that as a second ad. Reading QUEUE through approval at
    call time is also what lets a test redirect the whole run by patching one
    name.
    """
    return approval.jobs_in(STAGE)


def _job_path(segment_id: str) -> str:
    """The path an operator has to open, spelled the way they will see it."""
    return f"queue/{STAGE}/{segment_id}.json"


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def parse_time(value) -> datetime | None:
    """An ISO-8601 timestamp to an aware UTC datetime. None if unreadable.

    A naive timestamp is read as UTC: everything in this pipeline that writes
    one writes Z, and guessing a local zone would move a launch by hours.
    """
    if isinstance(value, datetime):
        moment = value
    else:
        if isinstance(value, bool) or not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _stamp(value) -> str:
    """UTC, whole seconds, Z. One spelling, so two runs produce one file."""
    moment = parse_time(value)
    if moment is None:
        raise ValueError(
            f"expected a datetime or an ISO-8601 timestamp, got {value!r}"
        )
    return moment.strftime(approval.TIMESTAMP_FORMAT)


def _as_datetime(now) -> datetime:
    """`now=` as an aware UTC datetime. None is the clock."""
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if isinstance(now, date):
        return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    parsed = parse_time(now)
    if parsed is None:
        raise ValueError(
            f"now must be a datetime, a date or an ISO-8601 timestamp, got {now!r}"
        )
    return parsed


# ---------------------------------------------------------------------------
# Values - null is not zero
# ---------------------------------------------------------------------------


def _number(value) -> float | None:
    """Meta's number, or None when it gave nothing usable.

    Insights values arrive as strings ("4100", "0.611765"), so a string is
    parsed. Booleans are refused rather than coerced: True is an int in
    Python and would median as 1.0 in engine.learn, the exact failure the
    null-is-not-zero rule exists to prevent. NaN and infinities are refused
    because JSON cannot carry them and a median cannot survive them.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _count(value) -> int | None:
    """A whole count, or None. A count Meta did not give is never 0."""
    number = _number(value)
    return None if number is None else int(number)


def _first_entry_value(entries) -> float | None:
    """`entries[0].value` of a video list, or None.

    The thruplay and video_pNN lists carry one entry each (see the TODO
    block), so the first entry is the count; an empty list, a missing list
    or an entry with no value is null.
    """
    if not isinstance(entries, list) or not entries:
        return None
    first = entries[0]
    if not isinstance(first, dict):
        return None
    return _number(first.get("value"))


def _action_value(entries, action_type: str) -> float | None:
    """The `value` of the first entry whose action_type matches, or None."""
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("action_type") == action_type:
            return _number(entry.get("value"))
    return None


def _result_type(actions) -> str | None:
    """Which of RESULT_ACTIONS this ad's `actions` carries first, if any."""
    if not isinstance(actions, list):
        return None
    present = {
        entry.get("action_type")
        for entry in actions
        if isinstance(entry, dict)
    }
    for action_type in RESULT_ACTIONS:
        if action_type in present:
            return action_type
    return None


def _ratio(numerator, denominator) -> float | None:
    """numerator / denominator to RATE_PLACES, or None.

    None when either side is null or the denominator is 0: a rate over
    nothing is not 0%, it is unmeasured, and 0.0 here would be the fabricated
    zero the module docstring refuses.
    """
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(numerator / denominator, RATE_PLACES)


def metrics_of(insights: dict) -> dict:
    """The C6 `metrics` block, read defensively off one insights object.

    Every key is present and every value Meta did not give is null. This and
    derived_of() are the only readers of the insights shape; the TODO block
    at INSIGHT_FIELDS is the list of what they assume.
    """
    actions = insights.get("actions")
    costs = insights.get("cost_per_action_type")
    result = _result_type(actions)
    return {
        "impressions": _count(insights.get("impressions")),
        "reach": _count(insights.get("reach")),
        "clicks": _count(insights.get("clicks")),
        "ctr": _number(insights.get("ctr")),
        "cpc": _number(insights.get("cpc")),
        "cpm": _number(insights.get("cpm")),
        "spend": _number(insights.get("spend")),
        "plays_3s": _count(_action_value(actions, PLAY_ACTION)),
        "thruplays": _count(_first_entry_value(insights.get("video_thruplay_watched_actions"))),
        "p25": _count(_first_entry_value(insights.get("video_p25_watched_actions"))),
        "p50": _count(_first_entry_value(insights.get("video_p50_watched_actions"))),
        "p75": _count(_first_entry_value(insights.get("video_p75_watched_actions"))),
        "p100": _count(_first_entry_value(insights.get("video_p100_watched_actions"))),
        "results": _count(_action_value(actions, result)) if result else None,
        "cost_per_result": _action_value(costs, result) if result else None,
    }


def derived_of(metrics: dict) -> dict:
    """The C6 `derived` block: two divisions, and null over nothing.

    hook_rate is 3-second plays over impressions - how many of the people the
    ad was shown to stopped for it. hold_rate is thruplays over 3-second plays
    - how many of those who stopped stayed. Both are derived here, not read
    off Meta, and the block's name says so.
    """
    return {
        "hook_rate": _ratio(metrics.get("plays_3s"), metrics.get("impressions")),
        "hold_rate": _ratio(metrics.get("thruplays"), metrics.get("plays_3s")),
    }


# ---------------------------------------------------------------------------
# Records - contract C6
# ---------------------------------------------------------------------------


def measurement(
    *,
    segment: str,
    ad_id: str,
    campaign_id: str | None,
    launched_at,
    insights: dict,
    now=None,
) -> dict:
    """One row, contract C6. The only place its shape is written.

    `insights` is the one object MeasureClient.insights() returns, and every
    number in the row is read off it by metrics_of(). `launched_at` is what
    `approval launch` stamped and is refused when unreadable: engine.feedback
    subtracts it from `measured_at`, and a row that cannot be dated would fail
    there with a message about the wrong module. `now` is the moment of
    measurement; None reads the clock, and measure_all() passes one moment
    for every row so a run's rows agree with each other.
    """
    if not isinstance(insights, dict):
        raise ValueError(
            f"{segment}: insights must be the object MeasureClient.insights() "
            f"returns, got {type(insights).__name__}"
        )
    ad_id = str(ad_id or "").strip()
    if not ad_id:
        raise ValueError(f"{segment}: a measurement needs an ad id")
    stamped = parse_time(launched_at)
    if stamped is None:
        raise ValueError(
            f"{segment}: launched_at is {launched_at!r}, which is not a "
            f"timestamp. `approval launch` writes it as YYYY-MM-DDTHH:MM:SSZ "
            f"in {_job_path(segment)}; restore it there."
        )
    metrics = metrics_of(insights)
    return {
        "segment": segment,
        "ad_id": ad_id,
        "campaign_id": None if campaign_id is None else str(campaign_id),
        "launched_at": _stamp(stamped),
        "measured_at": _stamp(_as_datetime(now)),
        "date_preset": DATE_PRESET,
        "metrics": metrics,
        "derived": derived_of(metrics),
    }


def _order(row: dict):
    """(segment, ad id): a segment's ads together, and a total order because
    an ad id is pinned under one segment only, so the file is byte-stable."""
    return (str(row.get("segment") or ""), str(row.get("ad_id") or ""))


def document(rows, *, now=None) -> dict:
    """The whole file, contract C6. `now` is generated_at; None is the clock."""
    return {
        "schema": SCHEMA,
        "generated_at": _stamp(_as_datetime(now)),
        "rows": sorted(rows, key=_order),
    }


def dumps(doc: dict) -> str:
    """The document as this repository writes every committed JSON file."""
    return json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_measurements(rows, path: Path | str | None = None, *, now=None) -> Path:
    """Write research/measurements.json. Same encoding as every other writer."""
    path = Path(path) if path else MEASUREMENTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(document(rows, now=now)), encoding="utf-8")
    return path


def load(path: Path | str | None = None) -> dict:
    """Read a C6 document back. Refuses one this module would not have written."""
    path = Path(path) if path else MEASUREMENTS_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"no measurements at {path}; run `python -m engine.measure` to "
            f"write one from queue/launched/"
        )
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MeasureError(f"{path} is not JSON ({exc})") from None
    if not isinstance(doc, dict):
        raise MeasureError(
            f"{path} holds a JSON {type(doc).__name__}; C6 is an object with "
            f"schema, generated_at and rows"
        )
    if doc.get("schema") != SCHEMA:
        raise MeasureError(
            f"{path} has schema {doc.get('schema')!r}; this engine/measure.py "
            f"writes and reads schema {SCHEMA}. Re-run `python -m "
            f"engine.measure` to rewrite it, or check out the engine that "
            f"wrote it."
        )
    if not isinstance(doc.get("rows"), list):
        raise MeasureError(
            f"{path} has rows {type(doc.get('rows')).__name__}; C6 says a list"
        )
    return doc


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


@dataclass
class MeasureRun:
    """What one run produced, and what it could not.

    Two lists rather than an exception, mirroring analyse.AnalysisRun: an ad
    that has not delivered yet is normal, and must not cost the others.
    `calls` is the number of insights calls this run charged for.
    """

    rows: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    calls: int = 0


@dataclass(frozen=True)
class _Target:
    """One pinned ad on its way to a row."""

    segment: str
    ad_id: str
    campaign_id: str | None
    launched_at: str


def _targets(jobs, skipped: list[str]) -> list[_Target]:
    """Every (job, ad id) pair that can be looked up, and why the rest cannot.

    Everything that can be wrong with a job file is wrong HERE, before a
    client is built or a call is charged: an unreadable file, a file whose
    fields disagree with its name, an `ads` map that is empty or not a map,
    an id that is not digits, a launched_at nothing can subtract from, and an
    ad id two jobs both claim. Each is a line in `skipped` naming the file
    and the fix. Nothing is guessed past.
    """
    targets: list[_Target] = []
    claims: dict[str, list[str]] = {}

    for job in jobs:
        try:
            content = approval.load_job(job)
        except ValueError as exc:
            skipped.append(
                f"{job.segment_id}: {exc} Every other launched ad was measured."
            )
            continue

        ads = content.get(approval.ADS)
        if not isinstance(ads, dict) or not ads:
            skipped.append(
                f"{job.segment_id}: {_job_path(job.segment_id)} carries no ad "
                f"ids under \"{approval.ADS}\", so there is nothing to look up. "
                f"`approval launch` is the only way into queue/{STAGE}/ and "
                f"refuses an empty map, so this file was moved by hand; add "
                f"{{\"<ad id>\": {{\"campaign_id\": null, \"adset_id\": null}}}} "
                f"under \"{approval.ADS}\" - the number in Ads Manager's Ad ID "
                f"column - and run again."
            )
            continue

        launched_at = content.get(approval.LAUNCHED_AT)
        if parse_time(launched_at) is None:
            skipped.append(
                f"{job.segment_id}: {_job_path(job.segment_id)} has "
                f"{approval.LAUNCHED_AT} {launched_at!r}, which is not a "
                f"timestamp, so its rows could not be dated and engine.feedback "
                f"could not count days running. `approval launch` writes it as "
                f"YYYY-MM-DDTHH:MM:SSZ; restore it there and run again."
            )
            continue

        for ad_id, ids in ads.items():
            ad_id = str(ad_id).strip()
            if not approval.META_ID_RE.fullmatch(ad_id):
                skipped.append(
                    f"{job.segment_id}: ad id {ad_id!r} in "
                    f"{_job_path(job.segment_id)} is not a Meta id (all "
                    f"digits), so it cannot be looked up. Copy it from Ads "
                    f"Manager's Ad ID column and correct it under "
                    f"\"{approval.ADS}\"."
                )
                continue
            ids = ids or {}
            if not isinstance(ids, dict):
                skipped.append(
                    f"{job.segment_id}: ad {ad_id} in {_job_path(job.segment_id)} "
                    f"wants a {{campaign_id, adset_id}} object, got "
                    f"{type(ids).__name__}. `approval launch` writes both keys, "
                    f"null when not given; restore that shape."
                )
                continue
            campaign_id = ids.get("campaign_id")
            if campaign_id is not None:
                campaign_id = str(campaign_id).strip() or None
            if campaign_id is not None and not approval.META_ID_RE.fullmatch(campaign_id):
                skipped.append(
                    f"{job.segment_id}: campaign_id {campaign_id!r} for ad "
                    f"{ad_id} in {_job_path(job.segment_id)} is not a Meta id "
                    f"(all digits). It would be written into the row as a "
                    f"fact; correct it, or set it to null."
                )
                continue
            targets.append(_Target(job.segment_id, ad_id, campaign_id, str(launched_at)))
            claims.setdefault(ad_id, []).append(job.segment_id)

    # One ad id pinned under two segments would give both a history that is
    # half somebody else's. Refused for both, named for both, and nothing is
    # measured for either until a human says which segment the ad belongs to.
    disputed = {ad_id: names for ad_id, names in claims.items() if len(names) > 1}
    if disputed:
        kept = []
        for target in targets:
            if target.ad_id in disputed:
                others = ", ".join(disputed[target.ad_id])
                skipped.append(
                    f"{target.segment}: ad {target.ad_id} is pinned under "
                    f"{len(disputed[target.ad_id])} launched jobs at once - "
                    f"{others} - so its numbers would belong to two segments. "
                    f"Nothing is measured for it; remove the id from every "
                    f"job but the one it was created from, under "
                    f"\"{approval.ADS}\" in queue/{STAGE}/."
                )
            else:
                kept.append(target)
        targets = kept
    return targets


def measure_all(*, client: MeasureClient | None = None, now=None, raw: bool = False) -> MeasureRun:
    """Measure every pinned ad of every launched job. Skips are collected.

    One row per (job, ad id), one insights call each. The client is built
    lazily, so a repository with nothing launched - or with launched jobs
    that all fail the checks in _targets() - asks for no token and opens no
    socket. `now` is the moment of measurement, read once and shared by every
    row; None is the clock.

    `raw` puts the insights object on each row under "raw", exactly as Meta
    returned it, for the first live run to read against the TODO block at
    INSIGHT_FIELDS. Off by default so the committed document never carries
    one.

    QuotaExceededError and MissingTokenError are NOT collected: an exhausted
    budget or a dead token is the whole run misconfigured, not one ad's
    problem, and a run that returned half its rows as though it were healthy
    is the unattended failure this repository keeps designing against.
    """
    measured_at = _stamp(_as_datetime(now))
    run = MeasureRun()
    targets = _targets(launched_jobs(), run.skipped)
    if not targets:
        return run

    client = client or MeasureClient()
    spent_before = client.quota.spent

    for target in targets:
        try:
            insights = client.insights(target.ad_id)
        except (ApiError, UnmeasurableJob) as exc:
            run.skipped.append(f"{target.segment}: {exc}")
            continue
        row = measurement(
            segment=target.segment,
            ad_id=target.ad_id,
            campaign_id=target.campaign_id,
            launched_at=target.launched_at,
            insights=insights,
            now=measured_at,
        )
        if raw:
            row["raw"] = insights
        run.rows.append(row)

    run.calls = client.quota.spent - spent_before
    return run


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m engine.measure",
        description=(
            "How our own launched ads performed, read off the Marketing API "
            "insights edge for one call per ad."
        ),
    )
    parser.add_argument("--out", default=None,
                        help=f"where to write the document (default {MEASUREMENTS_PATH})")
    parser.add_argument("--dry-run", action="store_true",
                        help="call the API and print the document to stdout; "
                             "write nothing")
    parser.add_argument("--strict", action="store_true",
                        help="exit nonzero if any launched ad was skipped")
    parser.add_argument("--raw", action="store_true",
                        help="keep Meta's insights object on each row under "
                             "\"raw\" - for the first live run to check the "
                             "field names in INSIGHT_FIELDS against; never on "
                             "by default")
    args = parser.parse_args(argv)

    # The ONLY clock read in this module. Every row's measured_at and the
    # document's generated_at are this one moment.
    now = datetime.now(timezone.utc)

    try:
        run = measure_all(now=now, raw=args.raw)
    except MeasureError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for line in run.skipped:
        print(f"skipped {line}", file=sys.stderr)

    path = Path(args.out) if args.out else MEASUREMENTS_PATH
    if args.dry_run:
        sys.stdout.write(dumps(document(run.rows, now=now)))
        written = "nothing (dry run)"
    elif not run.rows and path.exists():
        # Scope rule 6: nothing thin overwrites something good. A run that
        # measured no ad - every one skipped, or the API away for the morning
        # - leaves last week's document for engine.feedback to read, rather
        # than replacing it with an empty one that looks like a clean week.
        written = f"nothing: {path} kept as it was, since no ad was measured this run"
    else:
        written = str(write_measurements(run.rows, path, now=now))

    print(
        f"measured {len(run.rows)} launched ad(s) in {run.calls} insights "
        f"call(s); {len(run.skipped)} skipped; wrote {written}",
        file=sys.stderr,
    )
    return 1 if (args.strict and run.skipped) else 0


if __name__ == "__main__":
    raise SystemExit(main())
