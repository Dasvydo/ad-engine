"""python -m engine.discover [--days N] [--budget N] [--json] [--out PATH] [--dry-run]

Discovery: which of a page's ads its advertiser's own money kept alive, and
for whom.

One source, the Meta Ad Library API (`ads_archive`), read through the same
posture `reel-engine/engine/discover.py` takes with the YouTube Data API: a
ledger charged BEFORE the socket opens, one transport seam, and a record shape
written in exactly one place. The differences from the reel module are what
the archive is, and they are all deliberate.

**There is no view count.** A commercial ad in the archive carries no spend,
no impressions, no clicks and nothing social. What it does carry is when it
started, when it stopped (absent while it runs), how far it reached in the EU
and, across the run's results, how many versions of one hook its page is
running. So "performing" here means LONGEVITY first - an ad still running
after eight weeks is the one number an advertiser's own money has voted on -
with reach per day as the outlier numerator and the variant count as the
scaling signal. `docs/AD-RESEARCH-SCOPE.md` section 2.3 is the argument.

**A competitor is reached by page id, never by searching its name.** Keyword
search matches creative TEXT, and a company's name is rarely in its own copy:
a search for "Fyxer" across five countries returned 2,642 ads and none of
Fyxer's (measured, this session). `research/seeds.yaml` seeds a page by id
and refuses a blank one at load, the same lesson the reel seeds record for
YouTube channel ids.

**The rate limit is a budget, not a documented number.** About 200 calls an
hour per token is what every guide reports; Meta's reference names the error
(code 613) and not the figure. `Quota` charges one unit per RESULT PAGE
fetched, before the request, and refuses what it cannot afford, so a run
never dies mid-flight with half its candidates collected and no record of
why. `HOURLY_BUDGET_CALLS` is a parameter so a measured figure replaces the
reported one in one line.

**Nothing here fetches a snapshot.** `ad_snapshot_url` is a rendered page,
not a download, under terms nobody in this repository has read. A candidate
carries its Ad Library URL so a human can open it; no code path requests it,
and `tests/test_discover.py` asserts that no transport call ever targets one
even when the API hands them back. This is the Instagram seam of the reel
module, byte for byte: a creative a concept needs is saved by hand into
`research/media/` and analysed from the file.

## What makes an ad an outlier

Not that it reached many people - that its page's own audience treated it
differently. `outlier_ratio` is an ad's reach per day over the MEDIAN reach
per day of the OTHER ads collected for the same page in the same run. A page
that reaches 50k with every ad has a median of 50k and no outliers; the page
whose median is 3k and whose one ad did 60k has something worth reading.
That is what stops the ranking from rewarding whoever spends most.

Two consequences are load-bearing:

  - Inactive ads inside the window are kept, not dropped. A finished ad has a
    measured `stop - start`, which is the honest longevity figure; the
    active ones are measured to `today`.
  - A page with fewer than MIN_BASELINE_ADS other ads in the run has no
    baseline and yields the sentinel `NO_BASELINE` (0.0) rather than a
    divide-by-zero or an invented 1.0. 0.0 is safe to read as "not an
    outlier": the only real ratio it collides with is an ad with zero reach,
    which is not an outlier either.

## The transport seam

One module-level function, `_http(url, token) -> dict`, is the only thing
here that opens a socket, and `AdLibraryClient(transport=...)` replaces it.
The token travels in an `Authorization: Bearer` header and never in a URL,
so a URL can sit in a log line; and it is scrubbed out of anything the
transport raises, because Meta echoes tokens back in error bodies. Every test
injects a stub; none needs a token and none touches the network.
"""
from __future__ import annotations

import json
import os
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SEEDS_PATH = ROOT / "research" / "seeds.yaml"

# Unversioned on purpose: an unversioned Graph call runs against the oldest
# version the app still supports, which is the most stable thing to pin an
# unattended cron to. META_GRAPH_VERSION in the environment inserts one
# ("v21.0") when a field this module reads turns out to need it.
API = "https://graph.facebook.com/ads_archive"
GRAPH_VERSION_ENV = "META_GRAPH_VERSION"

# The name of the secret, for messages. The VALUE is read by engine/oauth.py
# and only there, so the age of the token is counted in one place.
META_ACCESS_TOKEN = "META_ACCESS_TOKEN"

# Every field a commercial EU ad documents, and nothing political-only:
# impressions, spend, currency and the demographic breakdowns come back for
# political ads and are not built on. `eu_total_reach` is the one reach
# figure a commercial ad carries. TODO(integration): UNVERIFIED AGAINST A
# LIVE RESPONSE - the names are Meta's reference page as read this session;
# the first call with a real token is the proof, and an unknown field name is
# a 400 that names it.
FIELDS = (
    "id",
    "page_id",
    "page_name",
    "ad_creation_time",
    "ad_delivery_start_time",
    "ad_delivery_stop_time",
    "ad_snapshot_url",
    "ad_creative_bodies",
    "ad_creative_link_titles",
    "ad_creative_link_descriptions",
    "ad_creative_link_captions",
    "publisher_platforms",
    "languages",
    "eu_total_reach",
)

# The reported allowance per token per hour. Reported, not published: see
# the module docstring. A parameter so a measured number replaces it.
HOURLY_BUDGET_CALLS = 200

# One unit per result page. The archive prices every call the same, which is
# why the page count, not the endpoint, is the figure worth watching.
UNIT_COSTS = {"ads_archive": 1}

# Results per page, and how many pages one search may fetch. Two pages of a
# hundred is a page's recent output, which is what the baseline needs; its
# whole archive would make the baseline a set of hits.
DEFAULT_LIMIT = 100
DEFAULT_MAX_PAGES = 2

# The archive ACCEPTS up to ten page ids in one call.
MAX_PAGE_IDS_PER_CALL = 10

# ...and we send one. This used to be ten, described as "the difference
# between one call and ten for the same data". It is not the same data.
#
# MEASURED 2026-09-19, against the live archive: a search for Fyxer
# (484462831408750) and Jace.ai (591862607340162) together, DK and LT, over
# the 1,260 ads the two of them have, returned FIFTY FYXER ADS AND NOTHING
# OF JACE'S. The archive orders a result set strictly by recency across the
# whole batch, and every Fyxer ad is newer than Jace's newest - June 2026
# against January. At DEFAULT_LIMIT x DEFAULT_MAX_PAGES = 200 slots, Jace
# would have contributed nothing, this week and every week, with no error
# and no empty-result warning anywhere: its ads exist, they were asked for,
# and they were simply outranked by a page-mate that posts more.
#
# That is worse than the call it saves, and it compounds. `outlier_ratio` is
# computed per page_id over the ads of THIS run, so a starved page does not
# merely arrive thin - it arrives with fewer than MIN_BASELINE_ADS peers,
# scores NO_BASELINE, sorts last in fanout._rank_key and is never chosen for
# analysis. A page can be seeded, searched, returned and still never reach
# the corpus.
#
# One page per search costs 15 searches instead of 3 on the shipped file -
# 40 calls at the ceiling against a budget of 200, and research.yml's
# --budget 150. Cheap, next to a seed that silently watches nothing.
PAGE_IDS_PER_SEARCH = 1

ORIGINS = ("competitor", "icp-adjacent")

# `meta-ad` and nothing else in this repository; the reel platforms live in
# the sibling. C2 fixes the id prefix, and it is what lets anything
# downstream tell an ad record from a reel record by its id alone.
PLATFORM = "meta-ad"
PLATFORMS = (PLATFORM,)
ID_PREFIX = "fb-"

# The page a human opens to see the creative. Written into every record and
# never requested by anything here.
LIBRARY_URL = "https://www.facebook.com/ads/library/?id="

# Search parameters that do not vary. `ALL` returns every commercial ad that
# reached an EU country, which for DK and LT is every commercial ad;
# KEYWORD_UNORDERED matches the words in any order, which a two-word Danish
# or Lithuanian phrase needs.
AD_TYPE = "ALL"
SEARCH_TYPE = "KEYWORD_UNORDERED"
ACTIVE_STATUSES = ("ACTIVE", "INACTIVE", "ALL")

# See the module docstring. A float, in schema, and safe to sort on.
NO_BASELINE = 0.0

# How many OTHER ads from the same page a median needs before it means
# anything. One is arithmetically enough and thin; refusing it would discard
# most pages in a small weekly run, so one it is - and the sentinel is
# reserved for the genuinely baseline-less case.
MIN_BASELINE_ADS = 1

COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2}$")
PAGE_ID_RE = re.compile(r"^\d+$")
EPOCH_RE = re.compile(r"^\d{9,}$")
GRAPH_VERSION_RE = re.compile(r"^v?\d+\.\d+$")

HTTP_TIMEOUT_SECONDS = 30

# A token shorter than this is not a credential, and blanket-replacing it
# would turn a message into confetti and hide the real problem.
REDACTED = "<redacted>"
MIN_REDACTABLE = 4

QUOTA_ADVICE = (
    "The Ad Library API allows about 200 calls an hour per token (reported, "
    "not published; Meta's error for it is code 613). Wait for the hour to "
    "roll over, cut pages or queries from research/seeds.yaml, lower "
    "max_pages, or raise --budget only if the limit measured on this token is "
    "higher."
)


class DiscoveryError(RuntimeError):
    """Anything that stops discovery. Always names what the operator fixes."""


class MissingTokenError(DiscoveryError):
    """No usable Meta access token. Never carries a value."""


class QuotaExceededError(DiscoveryError):
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
            f"ad library {endpoint} needs {needed} call(s) and {remaining} "
            f"remain of the {budget}-call hourly budget. {QUOTA_ADVICE}"
        )


class ApiError(DiscoveryError):
    """The Ad Library API answered with an error. Carries Meta's own message."""


class SeedsError(DiscoveryError):
    """research/seeds.yaml says something this module cannot act on."""


# ---------------------------------------------------------------------------
# Quota
# ---------------------------------------------------------------------------


class Quota:
    """The call ledger for one run. Refuses, it does not warn.

    Meta counts on receipt of the request, so calls are charged here before
    the socket opens. That direction is deliberate: this ledger can over-count
    (a request that never reached Meta), never under-count, and only
    under-counting produces the failure that matters - a run killed mid-flight
    by a 613 with half its candidates collected and no record of why.
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
                f"{', '.join(sorted(UNIT_COSTS))}. Add it to UNIT_COSTS before "
                f"calling it."
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
# Seeds - the hand-maintained half
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Page:
    """One page being watched, by its numeric id.

    `countries` is None when the page runs in the file's default list; a
    tuple is the page's own override. Resolved in `discover`, not at load, so
    the record can say which list the ad was actually searched under.
    """

    id: str
    name: str
    page_id: str
    origin: str
    countries: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Query:
    """One keyword search, the origin its results carry, and where it runs."""

    text: str
    origin: str = "icp-adjacent"
    countries: tuple[str, ...] | None = None
    languages: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Own:
    """OUR page and ad account. Validated here, read by engine/feedback.py.

    Ships blank. Nothing in this module reads it beyond validating its shape
    at load, and engine/measure.py never opens this file at all - it works
    from the ad ids pinned into queue/launched/<segment>.json, which is the
    only place that says which ads are ours. A blank block is therefore not
    an error: engine/feedback.py writes page_id "" into the record, which is
    true, rather than guessing.
    """

    page_id: str | None = None
    page_name: str | None = None
    ad_account_id: str | None = None


@dataclass(frozen=True)
class Seeds:
    countries: tuple[str, ...] = ()
    pages: tuple[Page, ...] = ()
    queries: tuple[Query, ...] = ()
    own: Own = field(default_factory=Own)
    path: Path | None = None


TOP_LEVEL_KEYS = ("countries", "pages", "queries", "own")


def _require_origin(value, where: str) -> str:
    if value not in ORIGINS:
        raise SeedsError(
            f"{where} has origin {value!r}; it must be one of "
            f"{' or '.join(ORIGINS)}. Fix it in research/seeds.yaml."
        )
    return value


def _countries(raw, where: str, *, required: bool) -> tuple[str, ...] | None:
    """A list of ISO-2 country codes, upper-cased. None when absent and optional."""
    if raw is None:
        if required:
            raise SeedsError(
                f"{where} has no countries. ad_reached_countries is required by "
                f"the Ad Library API: give it a list of ISO-2 codes, e.g. "
                f"[DK, LT], in research/seeds.yaml."
            )
        return None
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        raise SeedsError(
            f"{where} has countries: {raw!r}; it must be a non-empty list of "
            f"ISO-2 codes, e.g. [DK, LT]."
        )
    codes: list[str] = []
    for item in raw:
        code = str(item or "").strip()
        if not COUNTRY_RE.match(code):
            raise SeedsError(
                f"{where} has country {item!r}, which is not an ISO-2 code. "
                f"Write the two-letter code - DK, not Denmark."
            )
        code = code.upper()
        if code not in codes:
            codes.append(code)
    return tuple(codes)


def _languages(raw, where: str) -> tuple[str, ...] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        raise SeedsError(
            f"{where} has languages: {raw!r}; it must be a non-empty list of "
            f"ISO-2 codes, e.g. [da], or be left out."
        )
    codes: list[str] = []
    for item in raw:
        code = str(item or "").strip()
        if not LANGUAGE_RE.match(code):
            raise SeedsError(
                f"{where} has language {item!r}, which is not an ISO-2 code. "
                f"Write the two-letter code - da, not Danish."
            )
        code = code.lower()
        if code not in codes:
            codes.append(code)
    return tuple(codes)


def _page_id(raw, where: str) -> str:
    """A numeric page id. Blank is refused, not skipped - see the seeds file."""
    text = str(raw if raw is not None else "").strip()
    if not text:
        raise SeedsError(
            f"{where} has no page_id. A page is reached by its numeric id, "
            f"never by searching its name (the name is rarely in its own "
            f"copy): open the page's ads in the Ad Library UI and read the "
            f"view_all_page_id out of the URL, quote it, and paste it in - or "
            f"comment the entry out until you have it."
        )
    if not PAGE_ID_RE.match(text):
        raise SeedsError(
            f"{where} has page_id {raw!r}, which is not a numeric id. It is "
            f"the digits in the Ad Library UI's URL for that page, quoted - "
            f"not the page name and not a URL."
        )
    return text


def _optional_str(raw) -> str | None:
    text = str(raw if raw is not None else "").strip()
    return text or None


def load_seeds(path: Path | str | None = None) -> Seeds:
    """Read and validate research/seeds.yaml. Opens no socket.

    Everything that can be wrong with the file is wrong here, at load, rather
    than halfway through a run that has already spent calls.
    """
    import yaml

    path = Path(path) if path else SEEDS_PATH
    if not path.exists():
        raise SeedsError(
            f"no seeds file at {path}. It is hand-maintained and committed; "
            f"restore it from git, or create it with 'countries: [DK, LT]' "
            f"and empty 'pages:' and 'queries:' lists."
        )

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise SeedsError(
            f"{path} must be a mapping with 'countries', 'pages', 'queries' "
            f"and 'own' keys, not a {type(document).__name__}."
        )
    unknown = sorted(str(k) for k in document if k not in TOP_LEVEL_KEYS)
    if unknown:
        raise SeedsError(
            f"{path} has keys this module does not read: {', '.join(unknown)}. "
            f"The keys are {', '.join(TOP_LEVEL_KEYS)}; a misspelt block would "
            f"otherwise be ignored silently."
        )

    default_countries = _countries(
        document.get("countries"), f"{path}", required=False
    ) or ()

    pages: list[Page] = []
    by_id: dict[str, Page] = {}
    by_page_id: dict[str, Page] = {}
    for entry in document.get("pages") or []:
        if not isinstance(entry, dict):
            raise SeedsError(f"{path}: every pages entry must be a mapping")
        slug = str(entry.get("id") or "").strip()
        if not slug:
            raise SeedsError(
                f"{path}: a pages entry has no id. The id is a short slug that "
                f"errors and skip lines name, e.g. balance-dk."
            )
        where = f"page {slug!r}"
        if slug in by_id:
            raise SeedsError(
                f"{path}: two pages share the id {slug!r}. Ids are how a "
                f"message names an entry, so they must be unique."
            )
        page_id = _page_id(entry.get("page_id"), where)
        if page_id in by_page_id:
            raise SeedsError(
                f"{path}: {where} and page {by_page_id[page_id].id!r} share "
                f"page_id {page_id}. One entry per page - a page seeded twice "
                f"would count its own ads as each other's variants."
            )
        countries = _countries(entry.get("countries"), where, required=False)
        if not (countries or default_countries):
            raise SeedsError(
                f"{path}: {where} has no countries and the file has no default "
                f"'countries:' list. ad_reached_countries is required; set one "
                f"or the other."
            )
        page = Page(
            id=slug,
            name=str(entry.get("name") or "").strip() or slug,
            page_id=page_id,
            origin=_require_origin(entry.get("origin"), where),
            countries=countries,
        )
        pages.append(page)
        by_id[slug] = page
        by_page_id[page_id] = page

    queries: list[Query] = []
    seen_queries: set[tuple] = set()
    for entry in document.get("queries") or []:
        if isinstance(entry, str):
            # A bare string is the common case: a topic search is icp-adjacent
            # by definition, because a competitor is seeded by page id.
            text = entry.strip()
            if not text:
                raise SeedsError(f"{path}: a query is an empty string")
            query = Query(text)
        elif isinstance(entry, dict):
            text = str(entry.get("query") or "").strip()
            if not text:
                raise SeedsError(f"{path}: a queries entry has no 'query'")
            where = f"query {text!r}"
            query = Query(
                text=text,
                origin=_require_origin(entry.get("origin", "icp-adjacent"), where),
                countries=_countries(entry.get("countries"), where, required=False),
                languages=_languages(entry.get("languages"), where),
            )
        else:
            raise SeedsError(f"{path}: every query must be a string or a mapping")
        if len(query.text) > 100:
            raise SeedsError(
                f"{path}: query {query.text[:40]!r}... is longer than the 100 "
                f"characters search_terms accepts. Shorten it."
            )
        if not (query.countries or default_countries):
            raise SeedsError(
                f"{path}: query {query.text!r} has no countries and the file "
                f"has no default 'countries:' list. ad_reached_countries is "
                f"required; set one or the other."
            )
        key = (query.text.casefold(), query.countries, query.languages)
        if key in seen_queries:
            raise SeedsError(
                f"{path}: query {query.text!r} appears twice with the same "
                f"countries and languages. Each copy costs a call for the "
                f"same results; remove one."
            )
        seen_queries.add(key)
        queries.append(query)

    own_raw = document.get("own") or {}
    if not isinstance(own_raw, dict):
        raise SeedsError(
            f"{path}: 'own' must be a mapping with page_id, page_name and "
            f"ad_account_id, each of which may be blank."
        )
    own_page_id = _optional_str(own_raw.get("page_id"))
    if own_page_id is not None and not PAGE_ID_RE.match(own_page_id):
        raise SeedsError(
            f"{path}: own.page_id is {own_page_id!r}, which is not a numeric "
            f"page id. It is the digits of OUR page's id, quoted."
        )
    own = Own(
        page_id=own_page_id,
        page_name=_optional_str(own_raw.get("page_name")),
        ad_account_id=_optional_str(own_raw.get("ad_account_id")),
    )

    return Seeds(
        countries=default_countries,
        pages=tuple(pages),
        queries=tuple(queries),
        own=own,
        path=path,
    )


# ---------------------------------------------------------------------------
# The Ad Library API
# ---------------------------------------------------------------------------


def api_url() -> str:
    """The ads_archive endpoint, versioned only if the environment says so."""
    version = os.environ.get(GRAPH_VERSION_ENV, "").strip()
    if not version:
        return API
    if not GRAPH_VERSION_RE.match(version):
        raise DiscoveryError(
            f"{GRAPH_VERSION_ENV} is {version!r}, which is not a Graph API "
            f"version. Write it as v21.0, or unset it to call the endpoint "
            f"unversioned."
        )
    if not version.startswith("v"):
        version = "v" + version
    parts = urlsplit(API)
    return f"{parts.scheme}://{parts.netloc}/{version}{parts.path}"


def _redact(text: str, token: str | None) -> str:
    """Cut the token value out of `text`, whole OR IN PART.

    DELEGATES to engine.oauth._redact. It used to be a local
    `text.replace(token, REDACTED)` with a comment arguing that partial
    echoes were engine/oauth.py's problem because "this module sees only
    bodies, and whole-value is what Meta echoes".

    That reasoning was wrong, and MEASURED wrong on 2026-09-19 with a
    200-character sentinel token: this module truncates Meta's body itself,
    at `_api_error` and at the non-JSON branch of `_http`, both `body[:200]`.
    A token near that length comes back SLICED by our own truncation, and a
    whole-value replace cannot match a slice. 116 and 121 characters of a live
    token reached stderr out of main(), and 40 characters were written into
    research/selection.json - which .github/workflows/research.yml git-adds
    and pushes. A token in a committed file is a token an attacker has, and
    the promise it broke is the one whose failure is silent and permanent.

    So there is now ONE definition of the cut in this repository, in
    engine/oauth.py, where `_cut_runs` also removes any run of
    MIN_REDACTED_RUN characters taken from the value. A second copy of a
    security primitive is what caused this: the copy was made, the original
    was hardened, and the copy was not.

    FAIL CLOSED when the scrubber is absent. engine/oauth.py is imported
    lazily here for the reason `_token` gives - this module loads and every
    test that passes `token=` runs without it - so a broken checkout could
    reach this function with a token and no scrubber. It drops the body
    rather than printing it: an unreadable error is recoverable, a leaked
    credential is not.
    """
    if not isinstance(token, str) or len(token) < MIN_REDACTABLE:
        return text
    try:
        from engine import oauth
    except ImportError:
        return (
            "<body withheld: engine/oauth.py, which scrubs the token out of it, "
            "is not in this checkout, and printing it unscrubbed could leak the "
            "credential. Restore engine/oauth.py to read this error.>"
        )
    return oauth._redact(text, [token])


def _scrubbed(token: str | None, work):
    """Run `work()`; scrub the token out of anything it raises.

    EVERY exception is converted, not only DiscoveryError: an injected
    transport is arbitrary caller code and may raise anything, with anything
    in it. The replacement is raised AFTER the except block, so the original
    is not chained on as `__context__` with its unscrubbed message readable to
    anything that walks the chain.

    THE REPLACEMENT IS ALWAYS A FRESH OBJECT. This used to read
    `error = exc if clean == str(exc) else type(exc)(clean)`, re-using the
    original whenever its own message happened to need no scrubbing - and a
    message needing no scrubbing says nothing about what is hanging off it.
    An exception raised inside `work` carries whatever `__context__` it picked
    up in there, so a perfectly clean refusal rides out with, say, a date
    parser's "Invalid isoformat string: '<the token>'" attached and readable
    to anything that walks the chain. engine/oauth.py's `_never_leak`
    documents that exact trap as load-bearing; this function had the bug it
    describes.

    BELOW Exception the catch is deliberate and the types are KEPT.
    KeyboardInterrupt, SystemExit and asyncio.CancelledError derive from
    BaseException and sail straight past `except Exception` with their
    messages and their chains intact. They are scrubbed argument by argument
    rather than rebuilt from a string, so `SystemExit(2)` keeps its integer
    exit code and Ctrl-C still kills the run on the first press instead of
    becoming an ApiError nobody expected.
    """
    try:
        return work()
    except QuotaExceededError:
        raise  # carries numbers, never a value; charged before this wrapper
    except DiscoveryError as exc:
        clean = _redact(str(exc), token)
        try:
            error = type(exc)(clean)
        except TypeError:
            # A subclass with its own __init__ - QuotaExceededError's shape,
            # which is already returned above, but a future one would land
            # here. Still a DiscoveryError, still scrubbed.
            error = ApiError(clean)
    except Exception as exc:
        error = ApiError(_redact(f"{type(exc).__name__}: {exc}", token))
    except BaseException as exc:  # noqa: BLE001 - deliberate; see above
        cleaned = tuple(
            _redact(arg, token) if isinstance(arg, str) else arg
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
    module that opens a socket - replace it, and discovery is offline.

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
        raise ApiError(f"could not reach the Ad Library API: {exc.reason}")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise ApiError(f"the Ad Library API returned non-JSON: {body[:200]!r}")
    if not isinstance(parsed, dict):
        raise ApiError(
            f"the Ad Library API returned {type(parsed).__name__}, not an object"
        )
    return parsed


def _api_error(status: int, body: str) -> str:
    """Meta's message, plus the one piece of advice it never gives."""
    message, code, kind = body[:200], None, ""
    try:
        error = (json.loads(body) or {}).get("error") or {}
        message = error.get("message") or message
        code = error.get("code")
        kind = error.get("type") or ""
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    text = f"Ad Library API {status}: {message}"
    if code is not None:
        text += f" (code {code}{', ' + kind if kind else ''})"
    if code in (4, 17, 32, 613):
        # Meta's counter is authoritative and ours may be a fresh ledger in
        # the same hour - another run, or a hand-run script, spent it.
        text += f". {QUOTA_ADVICE}"
    elif code == 10 or (isinstance(code, int) and 200 <= code <= 299) or status == 403:
        # Permission errors are typed OAuthException too, so they are told
        # apart by code before the token branch below catches the type.
        text += (
            ". A permission error here usually means the token's user has "
            "not completed identity confirmation at facebook.com/ID, or the "
            "app does not have the Ad Library API product added. Both are "
            "one-time steps in the Meta developer dashboard."
        )
    elif code == 190 or kind == "OAuthException":
        text += (
            f". The token {META_ACCESS_TOKEN} holds was refused: it has "
            f"expired, was revoked, or was minted without the Ad Library API "
            f"product on its app. Mint a fresh one and update the secret and "
            f"META_TOKEN_ISSUED in the same visit; python -m engine.oauth "
            f"--status says how old the stored one is."
        )
    elif code == 100:
        text += (
            ". Code 100 is a parameter Meta did not accept. The list "
            "parameters are sent as JSON arrays and the fields as a "
            "comma-separated list; if this is the first live call, one of "
            "them is the unverified guess."
        )
    return text


def _token_from_oauth() -> str:
    """The token, aged and checked by engine/oauth.py before any socket.

    Imported here rather than at module top so this module loads, and every
    test with a token passed in runs, without the oauth module - and so no
    token is read at import time by a module that may never make a call.
    """
    try:
        from engine import oauth
    except ImportError:
        raise MissingTokenError(
            f"no Meta access token for the Ad Library API ({META_ACCESS_TOKEN}): "
            f"engine/oauth.py, which reads and ages it, is not present in this "
            f"checkout. Pass token= explicitly, or restore engine/oauth.py."
        ) from None
    try:
        return oauth.meta_token()
    except oauth.OAuthError as exc:
        # Already scrubbed by oauth; re-raised as a DiscoveryError so main()
        # prints it as one line. The name is repeated so the message says
        # which secret whatever oauth read first.
        raise MissingTokenError(
            f"no Meta access token for the Ad Library API ({META_ACCESS_TOKEN}): {exc}"
        ) from None


class AdLibraryClient:
    """The ads_archive endpoint behind a call ledger and one swappable transport."""

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

    def _get(self, params: dict) -> dict:
        # Charge first. A call this run cannot afford is never made, which is
        # the whole point - see Quota. Charged outside the scrubber because a
        # refusal carries numbers and no value.
        self.quota.charge("ads_archive")
        url = f"{api_url()}?{urlencode(params)}"
        token = self._token

        def fetch() -> dict:
            body = self._transport(url, token)
            if isinstance(body, dict) and "error" in body:
                # The API normally signals errors with a status code, but a
                # 200 carrying an error object would otherwise read as zero
                # results.
                raise ApiError(_api_error(200, json.dumps(body)))
            if not isinstance(body, dict):
                raise ApiError(
                    f"the Ad Library API returned {type(body).__name__}, not an object"
                )
            return body

        return _scrubbed(token, fetch)

    def archive(
        self,
        *,
        countries,
        page_ids=None,
        search_terms: str | None = None,
        active_status: str = "ALL",
        date_min: str | None = None,
        limit: int = DEFAULT_LIMIT,
        max_pages: int = DEFAULT_MAX_PAGES,
        languages=None,
    ) -> list[dict]:
        """Raw archived ads. One charge per result page fetched.

        `page_ids` are searched ten to a call, each batch paginated on its
        own. Paging follows the `after` cursor Meta returns and rebuilds the
        URL here, rather than requesting `paging.next` verbatim: a URL Meta
        hands back is not one this module wrote, and the token stays in the
        header either way. Stops at `max_pages` or when `paging.next` is
        absent.

        `languages` is not in the contract's signature and is the one
        addition: a seeded query carries them and there is nowhere else for
        them to go.
        """
        if not page_ids and not search_terms:
            raise ValueError("archive needs page_ids, search_terms, or both")
        if active_status not in ACTIVE_STATUSES:
            raise ValueError(
                f"active_status must be one of {ACTIVE_STATUSES}, got {active_status!r}"
            )
        countries = [str(c) for c in countries]
        if not countries:
            raise ValueError("archive needs at least one country; ad_reached_countries is required")
        if max_pages < 1:
            raise ValueError(f"max_pages must be at least 1, got {max_pages}")

        base = {
            # TODO(integration): UNVERIFIED AGAINST A LIVE RESPONSE. Graph
            # list parameters are documented as JSON arrays; the first live
            # call is the proof, and a code-100 error names the parameter.
            "ad_reached_countries": json.dumps(countries),
            "ad_type": AD_TYPE,
            "ad_active_status": active_status,
            "fields": ",".join(FIELDS),
            "limit": max(1, int(limit)),
        }
        if search_terms:
            base["search_terms"] = search_terms
            base["search_type"] = SEARCH_TYPE
        if date_min:
            base["ad_delivery_date_min"] = date_min
        if languages:
            base["languages"] = json.dumps([str(l) for l in languages])

        batches = [None]
        if page_ids:
            # PAGE_IDS_PER_SEARCH, not MAX_PAGE_IDS_PER_CALL: the archive
            # accepts ten, and sending ten loses the smaller pages. See the
            # constant.
            batches = list(_batched(list(dict.fromkeys(str(p) for p in page_ids)),
                                    PAGE_IDS_PER_SEARCH))

        ads: list[dict] = []
        for batch in batches:
            params = dict(base)
            if batch:
                params["search_page_ids"] = json.dumps(batch)
            after = None
            for _ in range(max_pages):
                if after:
                    params["after"] = after
                body = self._get(params)
                ads.extend(item for item in body.get("data") or [] if isinstance(item, dict))
                paging = body.get("paging") or {}
                if not paging.get("next"):
                    break
                after = _after_cursor(paging)
        return ads


def _after_cursor(paging: dict) -> str:
    """The cursor for the next page, out of `paging.cursors.after` or, failing
    that, the `after` parameter of `paging.next`. Refuses rather than guesses
    when `next` is present and neither says where it points."""
    cursors = paging.get("cursors") or {}
    after = cursors.get("after") if isinstance(cursors, dict) else None
    if not after:
        query = urlsplit(str(paging.get("next") or "")).query
        after = (parse_qs(query).get("after") or [None])[0]
    if not after:
        raise ApiError(
            "the Ad Library API returned a paging.next link with no 'after' "
            "cursor in paging.cursors or in the link itself. Paging follows the "
            "cursor, not the link; keys seen: "
            + ", ".join(sorted(str(k) for k in paging))
        )
    return str(after)


def _batched(values: list, size: int):
    for start in range(0, len(values), size):
        yield values[start:start + size]


# ---------------------------------------------------------------------------
# Time - the archive's two clocks
# ---------------------------------------------------------------------------


def parse_time(value) -> datetime | None:
    """An archive timestamp as an aware UTC datetime; None when absent.

    The API has emitted both forms: ISO 8601 with a basic offset
    ("2026-09-17T13:26:25+0000") and epoch seconds (an int, or a string of
    digits). A date alone is midnight UTC; a naive timestamp is read as UTC.
    Anything else raises ValueError naming both accepted forms.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{value!r} is not a timestamp")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if EPOCH_RE.match(text):
        return datetime.fromtimestamp(int(text), tz=timezone.utc)
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"{text[:40]!r} is not a timestamp this module reads. The archive "
            f"emits ISO 8601 (2026-09-17T13:26:25+0000) or epoch seconds."
        ) from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _as_datetime(today) -> datetime:
    """`today=` as an aware UTC datetime. None is the clock."""
    if today is None:
        return datetime.now(timezone.utc)
    if isinstance(today, datetime):
        return today if today.tzinfo else today.replace(tzinfo=timezone.utc)
    if isinstance(today, date):
        return datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    parsed = parse_time(today)
    if parsed is None:
        raise ValueError("today must be a date, a datetime or a timestamp")
    return parsed


def is_active(stop, today) -> bool:
    """Whether the ad is still delivering: no stop time, or one in the future.

    A stop time in the future is a scheduled end on an ad that is running
    now, which the archive reports; it is active until then.
    """
    stopped = parse_time(stop)
    return stopped is None or stopped > _as_datetime(today)


def days_running(start, stop, today) -> int:
    """Whole days an ad has delivered, per section 2.3 of the scope.

    `today - start` while it runs (stop None or in the future), `stop - start`
    once it has finished. ISO strings or epoch ints for both. Floored to whole
    days and never negative: a start in the future is a clock the archive and
    this run disagree on, and reads as day zero rather than a negative age.
    A missing start raises ValueError - an ad with no start time cannot be
    dated and the caller decides what to do with it.
    """
    started = parse_time(start)
    if started is None:
        raise ValueError(
            "ad_delivery_start_time is absent; an ad cannot be dated without "
            "it, and the archive documents it for every ad."
        )
    now = _as_datetime(today)
    stopped = parse_time(stop)
    end = stopped if stopped is not None and stopped <= now else now
    return max(0, (end - started).days)


# ---------------------------------------------------------------------------
# Candidates - contract C2
# ---------------------------------------------------------------------------


def _int(value) -> int:
    """An archive count. Absent reads as 0, which sorts below every number."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _first(value) -> str:
    """The first entry of a creative list, "" when absent.

    The creative lists carry one entry per card of a carousel; the first card
    is the one a feed shows and the hook a variant is grouped by. A bare
    string, should the API ever send one, is taken as-is.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        return first if isinstance(first, str) else str(first or "")
    return ""


def _str_list(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None]
    return []


def candidate(
    *,
    id: str,
    url: str,
    channel: str,
    origin: str,
    platform: str = PLATFORM,
    eu_total_reach: int = 0,
    days_running: int = 0,
    active: bool = True,
    variants: int = 1,
    page_id: str = "",
    publisher_platforms=(),
    languages=(),
    countries=(),
    primary_text: str = "",
    headline: str = "",
    description: str = "",
    link_caption: str = "",
    outlier_ratio: float = NO_BASELINE,
) -> dict:
    """One candidate record, contract C2. The only place its shape is written."""
    if platform not in PLATFORMS:
        raise ValueError(f"platform must be one of {PLATFORMS}, got {platform!r}")
    if origin not in ORIGINS:
        raise ValueError(f"origin must be one of {ORIGINS}, got {origin!r}")
    # C2 names the prefix, and it is what lets anything downstream tell an ad
    # record from a reel record by its id alone.
    if not isinstance(id, str) or not id.startswith(ID_PREFIX) or len(id) <= len(ID_PREFIX):
        raise ValueError(
            f"a {platform} candidate id must start with {ID_PREFIX!r} followed "
            f"by the Ad Library id, got {id!r}"
        )
    if not isinstance(active, bool):
        raise ValueError(f"active must be a bool, got {active!r}")
    if int(variants) < 1:
        raise ValueError(f"variants counts the ad itself and cannot be below 1, got {variants!r}")
    return {
        "id": id,
        "platform": platform,
        "url": url,
        "channel": channel,
        "origin": origin,
        "metrics": {
            "eu_total_reach": _int(eu_total_reach),
            "days_running": _int(days_running),
            "active": active,
            "variants": int(variants),
            "page_id": str(page_id or ""),
            "publisher_platforms": _str_list(publisher_platforms),
            "languages": _str_list(languages),
            "countries": _str_list(countries),
        },
        "copy": {
            "primary_text": primary_text or "",
            "headline": headline or "",
            "description": description or "",
            "link_caption": link_caption or "",
        },
        "outlier_ratio": outlier_ratio,
    }


def _normalised(text: str) -> str:
    """The hook, lowered and stripped of punctuation and spacing, so the same
    line with a different emoji or full stop counts as the same hook."""
    words = re.findall(r"\w+", (text or "").casefold())
    return " ".join(words)


def _group_key(row: dict) -> str:
    # A blank page_id is an unknown page, not a shared one: such ads are
    # each their own group rather than each other's baseline.
    return row["metrics"].get("page_id") or f"id:{row['id']}"


def add_variants(candidates: list[dict]) -> list[dict]:
    """Count, per page, how many of the run's ads open with the same hook.

    Grouped by page_id, then by the normalised first primary text (the
    headline when the body is empty). A page running six versions of one
    hook is scaling it, which is the signal; an ad with no text at all is its
    own group rather than everything textless on that page. Counts include
    the ad itself, so the floor is 1.
    """
    groups: dict[tuple[str, str], int] = {}
    keys: list[tuple[str, str]] = []
    for row in candidates:
        hook = _normalised(row["copy"]["primary_text"]) or _normalised(row["copy"]["headline"])
        key = (_group_key(row), hook or f"id:{row['id']}")
        keys.append(key)
        groups[key] = groups.get(key, 0) + 1
    return [
        {**row, "metrics": {**row["metrics"], "variants": groups[key]}}
        for row, key in zip(candidates, keys)
    ]


def reach_per_day(row: dict) -> float:
    """eu_total_reach over days running, with day zero counted as one day so a
    launch-day ad is measured rather than divided by nothing."""
    metrics = row["metrics"]
    return metrics["eu_total_reach"] / max(metrics["days_running"], 1)


def add_outlier_ratios(candidates: list[dict]) -> list[dict]:
    """Score each candidate against the OTHER ads of its own page.

    Reach per day over the median reach per day of the page's other ads in
    this run. Grouped by page_id, not page name: two pages can share a name
    and one page can be renamed.
    """
    groups: dict[str, list[int]] = {}
    for position, row in enumerate(candidates):
        groups.setdefault(_group_key(row), []).append(position)

    scored = []
    for position, row in enumerate(candidates):
        peers = [
            reach_per_day(candidates[other])
            for other in groups[_group_key(row)]
            if other != position
        ]
        ratio = NO_BASELINE
        if len(peers) >= MIN_BASELINE_ADS:
            baseline = statistics.median(peers)
            if baseline > 0:
                ratio = round(reach_per_day(row) / baseline, 3)
        scored.append({**row, "outlier_ratio": ratio})
    return scored


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _resolved_countries(seed, seeds: Seeds) -> tuple[str, ...]:
    return tuple(seed.countries or seeds.countries)


def plan(seeds: Seeds | None = None, *, max_pages: int = DEFAULT_MAX_PAGES) -> dict:
    """How many calls a run of these seeds costs, without a token or a socket.

    One search per page, under that page's own country list; one per query;
    each search may page up to `max_pages`. The spread is the floor to the
    ceiling. Pages used to go ten to a call - see PAGE_IDS_PER_SEARCH for the
    measurement that ended it.
    """
    seeds = seeds if seeds is not None else load_seeds()
    batches = 0
    for pages in _pages_by_countries(seeds).values():
        batches += -(-len(pages) // PAGE_IDS_PER_SEARCH)
    searches = batches + len(seeds.queries)
    return {
        "pages": len(seeds.pages),
        "page_calls": batches,
        "queries": len(seeds.queries),
        "query_calls": len(seeds.queries),
        "min_calls": searches,
        "max_calls": searches * max_pages,
        "budget": HOURLY_BUDGET_CALLS,
    }


def _pages_by_countries(seeds: Seeds) -> dict[tuple[str, ...], list[Page]]:
    groups: dict[tuple[str, ...], list[Page]] = {}
    for page in seeds.pages:
        groups.setdefault(_resolved_countries(page, seeds), []).append(page)
    return groups


def discover(
    seeds: Seeds | None = None,
    *,
    client: AdLibraryClient | None = None,
    today=None,
    days: int | None = None,
) -> list[dict]:
    """Candidates from the archive: seeded pages first, then keyword queries.

    First find wins: an ad reached through a seeded competitor page is the
    competitor's even if a query returns it too, and a page search's ads
    carry that page's origin. Every ad is searched under a country list and
    the record says which. `days` sets ad_delivery_date_min to `today - days`
    so the run reads what a page is running now, not its archive; inactive
    ads inside the window are kept because a finished ad has a measured
    stop - start.

    A missing token or an exhausted budget raises rather than returning what
    was found so far: an unattended weekly run that looks healthy while
    discovering nothing is the failure this repository keeps guarding
    against.
    """
    seeds = seeds if seeds is not None else load_seeds()
    client = client or AdLibraryClient()
    now = _as_datetime(today)
    date_min = None
    if days is not None:
        if int(days) < 1:
            raise ValueError(f"days must be a positive number of days, got {days!r}")
        date_min = (now - timedelta(days=int(days))).strftime("%Y-%m-%d")

    # ad id -> the ad and what it was found under. First find wins, and
    # pages are searched first, so a seeded page's origin beats a query's.
    found: dict[str, dict] = {}

    def remember(ad: dict, *, origin: str, countries, channel: str) -> None:
        ad_id = str(ad.get("id") or "").strip()
        if not ad_id:
            return  # an ad without an id cannot be a candidate at all
        found.setdefault(ad_id, {
            "ad": ad, "origin": origin, "countries": list(countries), "channel": channel,
        })

    for countries, pages in _pages_by_countries(seeds).items():
        by_page_id = {page.page_id: page for page in pages}
        ads = client.archive(
            countries=countries,
            page_ids=[page.page_id for page in pages],
            date_min=date_min,
        )
        for ad in ads:
            # The origin is the seeded page's, per ad and not per call: one
            # batch may mix competitor and icp-adjacent pages. An ad from a
            # page nobody asked for has no known origin and is not guessed.
            page = by_page_id.get(str(ad.get("page_id") or ""))
            if page is None:
                continue
            remember(ad, origin=page.origin, countries=countries, channel=page.name)

    for query in seeds.queries:
        countries = _resolved_countries(query, seeds)
        ads = client.archive(
            countries=countries,
            search_terms=query.text,
            languages=query.languages,
            date_min=date_min,
        )
        for ad in ads:
            remember(ad, origin=query.origin, countries=countries, channel="")

    rows = []
    for ad_id, context in found.items():
        ad = context["ad"]
        try:
            running = days_running(
                ad.get("ad_delivery_start_time"), ad.get("ad_delivery_stop_time"), now
            )
        except ValueError:
            # No start time: the ad cannot be dated, and a longevity signal
            # that is guessed is worse than a candidate that is missing.
            continue
        rows.append(candidate(
            id=f"{ID_PREFIX}{ad_id}",
            url=f"{LIBRARY_URL}{ad_id}",
            channel=str(ad.get("page_name") or context["channel"] or ""),
            origin=context["origin"],
            eu_total_reach=_int(ad.get("eu_total_reach")),
            days_running=running,
            active=is_active(ad.get("ad_delivery_stop_time"), now),
            page_id=str(ad.get("page_id") or ""),
            publisher_platforms=ad.get("publisher_platforms") or [],
            languages=ad.get("languages") or [],
            countries=context["countries"],
            primary_text=_first(ad.get("ad_creative_bodies")),
            headline=_first(ad.get("ad_creative_link_titles")),
            description=_first(ad.get("ad_creative_link_descriptions")),
            link_caption=_first(ad.get("ad_creative_link_captions")),
        ))

    return add_outlier_ratios(add_variants(rows))


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m engine.discover",
        description="Outlier candidates from the Meta Ad Library, by page and by keyword.",
    )
    parser.add_argument("--seeds", default=None, help="path to seeds.yaml")
    parser.add_argument("--days", type=int, default=None,
                        help="only ads delivered in the last N days (ad_delivery_date_min)")
    parser.add_argument("--budget", type=int, default=HOURLY_BUDGET_CALLS,
                        help=f"Ad Library calls for this run (default {HOURLY_BUDGET_CALLS})")
    parser.add_argument("--out", default=None, help="write the JSON document here")
    parser.add_argument("--json", action="store_true",
                        help="write the JSON document to stdout (the summary stays on stderr)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the call plan and exit; needs no token")
    args = parser.parse_args(argv)

    try:
        seeds = load_seeds(args.seeds)
        if args.dry_run:
            planned = plan(seeds)
            print(
                f"plan: {planned['pages']} seeded pages in {planned['page_calls']} "
                f"call(s), {planned['queries']} queries; {planned['min_calls']}-"
                f"{planned['max_calls']} Ad Library calls of the {args.budget} budget. "
                f"No call made.",
                file=sys.stderr,
            )
            return 0
        client = AdLibraryClient(budget=args.budget)
        rows = discover(seeds, client=client, days=args.days)
    except DiscoveryError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    document = json.dumps(rows, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(document, encoding="utf-8")
    if args.json:
        sys.stdout.write(document)

    counts = {origin: sum(1 for r in rows if r["origin"] == origin) for origin in ORIGINS}
    active = sum(1 for r in rows if r["metrics"]["active"])
    print(
        f"discovered {len(rows)} candidates ({counts['competitor']} competitor, "
        f"{counts['icp-adjacent']} icp-adjacent; {active} active) from "
        f"{len(seeds.pages)} seeded pages and {len(seeds.queries)} queries; "
        f"spent {client.quota.spent} of {args.budget} Ad Library calls",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
