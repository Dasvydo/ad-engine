# Build contracts

The fixed interfaces every module in this repository is written against. This
file exists so that modules built in parallel meet in the middle; it is the
ads twin of the C1-C6 contracts in `reel-engine/RUN-STATE.md`. When a module
and this file disagree, this file wins and the module is wrong. When this file
is wrong, change it in the same commit as every module it affects.

`docs/AD-RESEARCH-SCOPE.md` says why each stage exists. This file says exactly
what each one reads and writes.

---

## Conventions, all of them load-bearing

- Python 3.11. Dependencies are `google-genai`, `PyYAML`, `pytest` and the
  standard library. HTTP is `urllib` behind one `_http` function per module,
  replaced in every test by `transport=`.
- `ROOT = Path(__file__).resolve().parents[1]` in every module.
- Every test is offline. No test needs a key, a token or a socket. A test that
  would reach the network is a bug.
- Every committed JSON document is written with `sort_keys=True, indent=2,
  ensure_ascii=False` and a trailing newline (corpus records, patterns, the
  selection report, measurements). Job files under `queue/` are written with
  `indent=2, ensure_ascii=False` and a trailing newline, keys in authored
  order.
- Errors name the fix. A message that says what is wrong but not what to do
  about it is incomplete.
- Refuse rather than guess: a blank id, an ambiguous match, an unattested
  number, a half-record, an unknown enum value - each is named and refused.
- Nothing in this repository fetches an ad's snapshot page, downloads a
  creative, or scrapes anything. The Ad Library API is the only read for
  strangers' ads; the Marketing API insights edge is the only read for our own.
- Secrets are read from `os.environ` by one named helper each; a value is never
  interpolated into a message, a log line or a filename.
- Model calls go through `engine.model.call_model` only. Nothing imports
  `google.genai` outside `engine/model.py`.
- Timestamps are UTC, `%Y-%m-%dT%H:%M:%SZ`. Any function whose output depends
  on "now" takes `today=` or `now=` so a test can pin it.

## Secrets and variables

| Name | Kind | Read by |
|---|---|---|
| `GEMINI_API_KEY` (`GOOGLE_API_KEY` accepted as fallback) | secret | `engine/model.py` |
| `META_ACCESS_TOKEN` | secret | `engine/oauth.py` -> discover, measure |
| `META_TOKEN_ISSUED` | **variable**, `YYYY-MM-DD` | `engine/oauth.py` |
| `REEL_ENGINE_TOKEN` | secret, fine-grained PAT, contents:read on `Dasvydo/reel-engine` | `build.yml` only |
| `GITHUB_TOKEN` | automatic | the workflows that open, label or close issues |

## File ownership

One builder per row. Nobody edits a file outside their row.

| Row | Files |
|---|---|
| model | `engine/model.py`, `tests/test_model.py`, `tests/stubs.py` |
| corpus | `engine/corpus.py`, `tests/test_corpus.py` |
| backlog | `engine/backlog.py`, `queue/backlog.md`, `tools/sync_backlog.py`, `tests/test_backlog.py` |
| oauth | `engine/oauth.py`, `tests/test_oauth.py` |
| discover | `research/seeds.yaml`, `engine/discover.py`, `tests/test_discover.py` |
| gate | `engine/gate.py`, `claims/evidence.json`, `tests/test_gate.py`, `creative/example-job.json` |
| analyse | `engine/analyse.py`, `tests/test_analyse.py` |
| learn | `engine/learn.py`, `tests/test_learn.py` |
| approval | `engine/approval.py`, `tests/test_approval.py` |
| concepts | `engine/concepts.py`, `tests/test_concepts.py` |
| score | `engine/score.py`, `tests/test_score.py` |
| measure | `engine/measure.py`, `tests/test_measure.py` |
| feedback | `engine/feedback.py`, `tests/test_feedback.py` |
| write | `engine/write.py`, `tests/test_write.py` |
| fanout | `engine/fanout.py`, `tests/test_fanout.py` |
| propose | `engine/propose.py`, `tests/test_propose.py` |
| workflows | `.github/workflows/*.yml`, `tools/push_with_retry.sh`, `tests/test_workflows.py` |
| docs | `README.md`, `docs/COST.md`, `docs/SECRETS.md`, `docs/AD-RESEARCH-SCOPE.md`, `.gitignore` |

Already present and not to be broken: `engine/audience.py`, `engine/cli.py`,
`audiences/*.json`, `creative/capacity.json`, `creative/hours.json`,
`docs/ICP-BRIEF.md`, the eight tests in `tests/test_gate.py` as they stand.

---

## engine/model.py

A copy of `reel-engine/engine/model.py`'s provider client with the call-site
helpers that live in `reel-engine/engine/script.py` moved in beside it, so no
research module has to import the writer.

```python
MODEL_FLASH = "gemini-3.5-flash"    # the judge: the editorial gate
MODEL_WRITE = "gemini-3.6-flash"    # everything that writes: analyse, concepts, score, write
KEY_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")

def api_key() -> str | None
class ConfigError(RuntimeError)          # operator's to fix; one line, no traceback
class CapacityError(ConfigError)         # a 503 that outlasted the retry ladder
def client() -> GeminiClient              # raises ConfigError naming GEMINI_API_KEY
def call_model(client, *, model, max_tokens, messages) -> Reply   # converts provider faults
def text_of(reply) -> str                 # the first block whose type == "text", else ""
def first_json_object(text) -> dict | None

@dataclass(frozen=True) class TextBlock: text: str; type: str = "text"
@dataclass(frozen=True) class Reply: content: list[TextBlock]; stop_reason: str = "end_turn"
class GeminiClient:  # .messages.create(model=, max_tokens=, messages=) -> Reply
```

A message is `{"role": "user", "content": str}` and may carry `"media":
{"kind": "local-file" | "file-uri", "ref": str, "mime_type": str | None}`.
`MIME_BY_SUFFIX` covers `.mp4 .mov .m4v .webm .jpg .jpeg .png .webp`.
`INLINE_LIMIT = 20 * 1024 * 1024`. The retry ladder constants and
`http_options()` are copied verbatim. No `youtube-url` kind: nothing here
watches YouTube.

`tests/stubs.py` ships `StubClient(replies)`: `.messages.create(**kw)` pops the
next `Reply` (or raises if none left), records every `kw` in `.calls`. Every
later test file uses it.

## engine/corpus.py

A copy of `reel-engine/engine/corpus.py` with these constants:

```python
SCHEMA = 1
PLATFORMS = ("meta-ad",)
ORIGINS = ("competitor", "icp-adjacent", "own")
REQUIRED_KEYS = ("schema", "id", "platform", "url", "channel", "origin",
                 "fetched_at", "metrics", "analysis", "model")
REQUIRED_NESTED = {
    "metrics": ("eu_total_reach", "days_running", "active", "variants", "page_id"),
    "analysis": ("copy", "hook", "structure", "offer", "proof", "cta",
                 "objections", "creative"),
    "analysis.copy": ("primary_text", "headline", "description", "link_caption", "words"),
    "analysis.hook": ("words", "text", "device"),
    "analysis.offer": ("type", "text"),
    "analysis.proof": ("type", "text"),
    "analysis.cta": ("type", "text"),
    "analysis.creative": ("kind",),
}
REQUIRED_LISTS = ("analysis.structure", "analysis.objections")
DEFAULT_ROOT = ROOT / "research" / "corpus"
```

Filename `<platform>-<id>.json`, i.e. `meta-ad-fb-123.json`. Same public
surface: `CorpusInvalid`, `validate`, `CorpusRecord`, `path_for`, `save`,
`load`, `load_all`.

### C1 - corpus record

```json
{"schema": 1, "id": "fb-961046237012883", "platform": "meta-ad",
 "url": "https://www.facebook.com/ads/library/?id=961046237012883",
 "channel": "Balance - Your AI Powered Accountants", "origin": "icp-adjacent",
 "fetched_at": "2026-09-22T06:04:11Z",
 "metrics": {"eu_total_reach": 12000, "days_running": 41, "active": true,
             "variants": 3, "page_id": "1007614045762121",
             "publisher_platforms": ["facebook", "instagram"],
             "languages": ["da"], "countries": ["DK"]},
 "analysis": {
   "copy": {"primary_text": "...", "headline": "...", "description": "...",
            "link_caption": "doviloop.dev", "words": 48},
   "hook": {"words": 9, "text": "...", "device": "question"},
   "structure": ["hook", "problem", "offer", "cta"],
   "offer": {"type": "none", "text": ""},
   "proof": {"type": "none", "text": ""},
   "cta": {"type": "learn-more", "text": "Se om vi kan..."},
   "objections": ["..."],
   "creative": {"kind": "text-only"},
   "outlier_ratio": 2.4},
 "model": "gemini-3.6-flash"}
```

Own records (written by feedback) additionally carry
`analysis.own_metrics: {"ctr": float, "hook_rate": float | null, "hold_rate":
float | null}`, `analysis.derived_from: {"note": "..."}`, and `model: "none
(authored)"`.

## engine/backlog.py

A verbatim copy of `reel-engine/engine/backlog.py` reading `queue/backlog.md`
in THIS repository. `queue/backlog.md` is a copy of the sibling's table with a
header saying so; `tools/sync_backlog.py` replaces the table from
`../reel-engine/queue/backlog.md` when that checkout exists and `--check` exits
1 on drift. Local rather than cross-repo because the research cron must not
need a second repository's token to run.

`Segment(rank, id, trade, questions: tuple[str, str, str], note)`, `load(path)
-> list[Segment]` sorted by rank, `next_unused(segments, used) -> Segment`.

## engine/oauth.py

The Meta half of `reel-engine/engine/oauth.py`, and only that half.

```python
META_ACCESS_TOKEN = "META_ACCESS_TOKEN"
META_TOKEN_ISSUED = "META_TOKEN_ISSUED"       # a repository VARIABLE, YYYY-MM-DD
TOKEN_LIFETIME_DAYS = 60
WARN_FROM_DAY = 40
class OAuthError(RuntimeError); class MissingCredential(OAuthError); class TokenExpired(OAuthError)
def token_age_days(issued: str, today: datetime | None = None) -> float
def meta_token(*, on_warning=None, today=None) -> str   # warns from day 40, refuses past 60, before any socket
def status(out=None, today=None) -> int                  # names, never values; nonzero inside the warning band
def main(argv=None) -> int                                # --status
```

Every exception message is scrubbed of the token value, **whole or in part**.
`_never_leak` is the wrapper inside `engine/oauth.py`; the two consumers do not
call it, they call `oauth._redact` from their own `_scrubbed` wrappers, and
this line used to name the wrapper as though it covered them. It does not, and
the difference was a live leak: `engine/discover.py` kept a LOCAL copy of the
cut that matched whole values only, while truncating Meta's error body itself
to 200 characters - so a ~200-character token came back sliced by our own
truncation into a fragment the copy could not match. Measured on 2026-09-19:
116 characters to stderr and 40 into a committed file. **There is now one
definition of the cut, `oauth._redact`, and both consumers delegate to it.**

A `META_TOKEN_ISSUED` more than a day in the future is refused, and one that
does not parse as a date is described by shape and length rather than echoed -
a Meta app secret is exactly 32 characters, so a credential pasted into that
variable by mistake must never be quoted back into an Actions log.

## research/seeds.yaml and engine/discover.py

```yaml
countries: [DK, LT]           # default ad_reached_countries
pages:                        # competitors and icp-adjacent pages, by PAGE ID
  - id: balance-dk
    name: Balance - Your AI Powered Accountants
    page_id: "1007614045762121"
    origin: icp-adjacent
    countries: [DK]           # optional override; a US competitor needs its own
queries:                      # keyword searches; a bare string is icp-adjacent
  - regnskab
  - query: buhalterine apskaita
    countries: [LT]
    languages: [lt]
own:                          # OUR page and ad account; validated by discover, read by feedback
  page_id:
  page_name:
  ad_account_id:
```

```python
API = "https://graph.facebook.com/ads_archive"     # unversioned; META_GRAPH_VERSION env inserts one
FIELDS = ("id", "page_id", "page_name", "ad_creation_time", "ad_delivery_start_time",
          "ad_delivery_stop_time", "ad_snapshot_url", "ad_creative_bodies",
          "ad_creative_link_titles", "ad_creative_link_descriptions",
          "ad_creative_link_captions", "publisher_platforms", "languages", "eu_total_reach")
HOURLY_BUDGET_CALLS = 200
UNIT_COSTS = {"ads_archive": 1}
DEFAULT_LIMIT = 100          # per page
DEFAULT_MAX_PAGES = 2
MAX_PAGE_IDS_PER_CALL = 10
ORIGINS = ("competitor", "icp-adjacent")
NO_BASELINE = 0.0
MIN_BASELINE_ADS = 1

class DiscoveryError(RuntimeError); MissingTokenError; QuotaExceededError(endpoint, needed, remaining, budget); ApiError; SeedsError
class Quota(budget, *, spent=0): remaining, cost(endpoint), charge(endpoint), affords(endpoint)   # copied from reel-engine
def load_seeds(path=None) -> Seeds        # Seeds(countries, pages, queries, own, path); Page(id, name, page_id, origin, countries); Query(text, origin, countries, languages); Own(page_id, page_name, ad_account_id)
class AdLibraryClient(token=None, *, budget=HOURLY_BUDGET_CALLS, quota=None, transport=None)
    .archive(*, countries, page_ids=None, search_terms=None, active_status="ALL",
             date_min=None, limit=DEFAULT_LIMIT, max_pages=DEFAULT_MAX_PAGES) -> list[dict]   # raw ads, one charge per page
def days_running(start, stop, today) -> int          # ISO strings or epoch ints; stop None => still running
def candidate(**fields) -> dict                       # the ONLY place C2 is written
def add_variants(rows) -> list[dict]                  # per page_id, by normalised first body or headline
def add_outlier_ratios(rows) -> list[dict]            # per page_id, reach_per_day over the median of the OTHERS
def discover(seeds=None, *, client=None, today=None, days=None) -> list[dict]
def main(argv=None) -> int                            # --days --budget --seeds --out --json
```

The token is `oauth.meta_token()` unless passed, and travels in an
`Authorization: Bearer` header, never in the URL. `transport(url, token) ->
dict`. Ads returned by a page search carry that page's origin; a query's
results are `icp-adjacent` unless the query says otherwise. First find wins.
`tests/test_discover.py` must include a test that asserts no transport call
ever targets `facebook.com/ads/library` and a test that `load_seeds` opens no
socket.

### C2 - candidate record

```json
{"id": "fb-961046237012883", "platform": "meta-ad",
 "url": "https://www.facebook.com/ads/library/?id=961046237012883",
 "channel": "Balance - Your AI Powered Accountants", "origin": "icp-adjacent",
 "metrics": {"eu_total_reach": 12000, "days_running": 41, "active": true,
             "variants": 3, "page_id": "1007614045762121",
             "publisher_platforms": ["facebook", "instagram"],
             "languages": ["da"], "countries": ["DK"]},
 "copy": {"primary_text": "...", "headline": "...", "description": "...",
          "link_caption": "..."},
 "outlier_ratio": 2.4}
```

## engine/gate.py and claims/evidence.json

Keep `check(text) -> ClaimVerdict`, `check_creative(spec) -> ClaimVerdict`,
`ClaimVerdict`, `_RISKY` and the eight existing tests exactly as they are. Add
the number policy ported from `reel-engine/reel/build.py` and the two gate
layers `reel-engine/engine/gate.py` has:

```python
CARDINALS, MULTIPLIERS, NUM_RE      # verbatim from reel/build.py
def spoken(text) -> str
def evidence_key(field, text) -> str            # sha256("field|spoken text")
def load_attestations() -> dict                 # claims/evidence.json["attestations"], kinds validated
def load_offers() -> dict                       # claims/evidence.json["offers"]
def unattested_numbers(field, text) -> list[str]
SPOKEN_FIELDS = ("primary_text", "headline", "description")
LANGUAGES = ("en", "da", "lt")
NATIVE_PLACEHOLDER = "NEEDS_NATIVE_PROOFREAD"
LIMITS = {"primary_text": 600, "headline": 40, "description": 60}
CTA_TYPES = ("LEARN_MORE", "SIGN_UP", "BOOK_NOW", "CONTACT_US", "GET_OFFER")
PLACEMENTS = ("reels-9x16", "feed-4x5", "static-1x1")
@dataclass(frozen=True) class GateResult: ok: bool; layer: str; failures: list[str]
def structural(job: dict) -> GateResult     # shape, limits, enums, offer verified, named claims, numbers; no model
def editorial(job: dict, *, client=None) -> GateResult   # one call, MODEL_FLASH; fail closed
def run(path, *, client=None) -> GateResult # structural first; editorial only if it passed
REFUSED_CONSTRUCTIONS                       # ported from reel-engine/engine/script.py, used by write.py and asserted here
```

Structural checks: every key of C3 present; `primary_text`, `headline`,
`description` are `{en, da, lt}` maps; `en` non-empty; `da`/`lt` either the
placeholder or text; every non-placeholder string under `LIMITS`; `cta` in
`CTA_TYPES`; `placement` in `PLACEMENTS`; `offer` is `"none"` or an offer id
whose status is `verified`; `check()` passes on every non-placeholder string;
no unattested number in any non-placeholder spoken field (attestation key is
`evidence_key("<field>.<lang>", text)`); no `REFUSED_CONSTRUCTIONS` match.
Editorial rubric, four rules: no unsupportable promise (latency, accuracy);
the hook names a moment in that trade's week rather than a generic complaint;
nothing claims a customer, logo, testimonial or outcome exists; the copy
argues one thing. Returns `{"pass": bool, "failures": [...]}`.

`claims/evidence.json` gains two sections beside the existing `claims`:

```json
"attestations": { "<sha256>": {"kind": "measured|architectural|illustrative",
                               "field": "headline.en", "text": "...", "source": "...", "asOf": "YYYY-MM-DD"} },
"offers": {
  "guarantee":      {"status": "verified", "evidence": "docs/ICP-BRIEF.md: knowledge base first; if the drafts are not good enough to send after the trial, they do not pay and keep it", "safe_phrasings": ["If the drafts are not good enough to send, you do not pay and you keep the knowledge base"]},
  "design_partner": {"status": "verified", "evidence": "docs/ICP-BRIEF.md: first ten firms, onboarding waived, in exchange for a case study", "safe_phrasings": ["Design-partner terms for the first firms in"]},
  "demo":           {"status": "verified", "evidence": "a call can be booked", "safe_phrasings": ["See it on your own inbox"]},
  "free_trial":     {"status": "UNVERIFIED", "evidence": "no self-serve trial exists; revenue is switched off in the product", "safe_phrasings": []}
}
```

`creative/example-job.json` is a complete, gate-passing C3 record for the
writer's worked example.

### C3 - ad job, `queue/<stage>/<segment>.json`

```json
{"id": "payroll-bureaus", "segment": "payroll-bureaus", "concept_id": "a01",
 "pattern_ids": ["q03", "q07"], "placement": "reels-9x16", "offer": "guarantee",
 "hypothesis": "one sentence on what this ad tests; not gated",
 "primary_text": {"en": "...", "da": "NEEDS_NATIVE_PROOFREAD", "lt": "NEEDS_NATIVE_PROOFREAD"},
 "headline": {"en": "...", "da": "NEEDS_NATIVE_PROOFREAD", "lt": "NEEDS_NATIVE_PROOFREAD"},
 "description": {"en": "...", "da": "NEEDS_NATIVE_PROOFREAD", "lt": "NEEDS_NATIVE_PROOFREAD"},
 "cta": "LEARN_MORE", "destination": "https://doviloop.dev",
 "creative_source": {"kind": "reel", "repo": "reel-engine", "template": "reel-c",
                     "selection": "queue/proposed/payroll-bureaus.reel.json"},
 "proposed_at": "2026-09-22T09:03:00Z",
 "ads": {}, "launched_at": null}
```

`creative_source.kind` is `reel` (a video `reel-engine` renders), `still` (a
frame `reel-engine` shoots), or `none` (copy only). `ads` is filled by
`approval launch`: `{"<ad id>": {"campaign_id": "...", "adset_id": "..."}}`.
Fields the gate never reads as copy: `id`, `segment`, `concept_id`,
`pattern_ids`, `hypothesis`, `destination`, `creative_source`, `proposed_at`,
`ads`, `launched_at`.

## engine/analyse.py

```python
MODEL_ANALYSE = model.MODEL_WRITE
MAX_TOKENS_ANALYSE = 16000
BATCH_SIZE = 12
MEDIA_ROOT = ROOT / "research" / "media"
MEDIA_SUFFIXES = (".mp4", ".mov", ".m4v", ".webm", ".jpg", ".jpeg", ".png", ".webp")
HOOK_DEVICES = ("question", "negative-flip", "cost-of-inaction", "named-enemy", "before-after",
                "credential", "social-proof", "curiosity-gap", "direct-offer", "how-to", "story")
STRUCTURE_LABELS = ("hook", "problem", "agitate", "demo", "proof", "offer", "guarantee", "cta")
OFFER_TYPES = ("none", "free-trial", "demo", "guarantee", "price", "discount", "lead-magnet")
PROOF_TYPES = ("none", "testimonial", "number", "logo", "case-study", "award")
CTA_TYPES = ("learn-more", "sign-up", "book-demo", "message", "download", "shop", "none")
TEXT_ONLY = "text-only"; LOCAL_FILE = "local-file"
class AnalysisError(ValueError); class SkippedCandidate(RuntimeError)
@dataclass class AnalysisRun: records: list[dict]; skipped: list[str]; calls: int
def local_media(candidate, *, media_root=None) -> Path | None
def analyse_batch(candidates, *, client, now=None) -> AnalysisRun     # ONE call; reply {"ads": {"<id>": {...} | {"refuse": "..."}}}
def analyse_media(candidate, *, client, media_root=None, now=None) -> dict   # ONE call with the file attached
def analyse_all(candidates, *, client=None, batch_size=BATCH_SIZE, media_root=None, now=None) -> AnalysisRun
```

A candidate with a hand-saved file at `research/media/<id>.<suffix>` goes
through `analyse_media` (one call, `creative: {"kind": "local-file", "ref":
str}`); every other candidate goes into text batches (`creative: {"kind":
"text-only"}`). A batch reply missing an id, truncated at `max_tokens`, or not
JSON raises `AnalysisError`: half a batch is worse than none. A per-ad
`refuse` is a skip. Every record passes `corpus.validate` before it is
returned. `analysis.copy` is the candidate's `copy` plus `words` (the model's
count of whitespace-separated words in `primary_text`). Nothing here fetches
anything.

## engine/learn.py

The counting step, ported. Zero model calls; `tests/test_learn.py` AST-parses
the module and asserts it imports nothing from `engine.model`, `google`,
`urllib`, `http`, `socket`, `requests`.

```python
SCHEMA = 1; MIN_SUPPORT = 2; EPOCH = "1970-01-01T00:00:00Z"
KINDS = ("hook", "length", "structure", "cta", "offer", "proof", "objection", "longevity", "ctr")
LENGTH_EDGES = (20, 50, 100, 200)         # words:0-19, 20-49, 50-99, 100-199, 200+
LONGEVITY_EDGES = (7, 28, 60, 120)         # days:0-6, 7-27, 28-59, 60-119, 120+
CTR_BANDS = ((0.5, "0-0.4"), (1.0, "0.5-0.9"), (2.0, "1.0-1.9"), (None, "2.0+"))   # ctr-pct:<label>
@dataclass class Pattern: kind, device, description, evidence, median_days_running, median_reach, id=""; n property
def find_patterns(records, *, origin=None, on_skip=None) -> list[Pattern]
def build(records, *, origin=None, generated_at=None, on_skip=None) -> dict
def dumps(document) -> str; def write(document, path=None) -> Path; def load(path=None) -> dict
class PatternsInvalid(ValueError)
```

Devices: `hook` = the slug of `analysis.hook.device`; `length` =
`words:<band>` over `analysis.copy.words`; `structure` = `shape:a>b>c` and
`section:<label>`; `cta` = slug of `analysis.cta.type`; `offer` = slug of
`analysis.offer.type`; `proof` = slug of `analysis.proof.type`; `objection` =
the normalised objection text; `longevity` = `days:<band>` over
`metrics.days_running`; `ctr` = `ctr-pct:<label>` over
`analysis.own_metrics.ctr`, absent silently when the record has none. Pattern
ids are `q01`, `q02`, ... widened past 99.

### C5 - `research/patterns.json`

```json
{"schema": 1, "generated_at": "...", "corpus_size": 0,
 "patterns": [{"id": "q03", "kind": "longevity", "device": "days:60-119",
   "description": "60-119 days running; median 74.0", "evidence": ["fb-..."],
   "median_days_running": 74, "median_reach": 12000, "n": 2}]}
```

## engine/approval.py

`reel-engine/engine/approval.py` with the stages renamed:

```python
LIVE_STAGES = ("proposed", "built", "launched"); REJECTED = "rejected"
STAGE_LABEL = {"proposed": "stage:copy", "built": "stage:creative"}
GO = "go"; NO = "no"
MARKER_RE = r"<!--\s*doviloop-ad:\s*([A-Za-z0-9._-]+)\s*-->"
def decide(job, label) -> Action   # NO on proposed|built -> "reject"; GO on proposed -> "build"; GO on built -> "launch"; else ValueError
def compose_proposal(segment, job: dict, still_url: str | None) -> (title, body)   # "Ad: <trade> (<id>)"
def advance(segment_id, to_stage) -> Job
LAUNCHED_AT = "launched_at"
def launch(segment_id, ads: dict, *, now=None) -> Job     # built -> launched; writes `ads` and `launched_at`
def drop(segment_id) -> Job
class Approvals(Protocol)  # open, comment, add_label, remove_label, close, body_of
class GitHubIssues(Approvals)  # via `gh`, as reel-engine
CLI: open --segment [--still-url]; resolve --issue [--expect]; advance --segment --to;
     launch --segment --ad ID[:campaign_id[:adset_id]] (repeatable); drop --segment;
     comment --issue --body-file; label --issue [--add] [--remove]; close --issue [--comment-file]
```

`Job.still` is `<segment>.jpg` beside the JSON and travels with it. The
`reel_selection` file `<segment>.reel.json` travels with it too.

## engine/concepts.py

```python
MODEL_CONCEPTS = model.MODEL_WRITE; DEFAULT_N = 12; SCHEMA = 1
PLACEMENTS = ("reels-9x16", "feed-4x5", "static-1x1")
AUTHORED = ("segment", "angle", "hook", "pattern_ids", "placement", "offer", "needs_numbers")
KEYS = ("id",) + AUTHORED
def load_patterns(path=None) -> dict; def validate_patterns(document, *, source=None) -> list[dict]
def generate(patterns, segments, *, n=DEFAULT_N, client=None, offers=None) -> list[dict]
class ConceptsError(ValueError); PatternsInvalid; ConceptInvalid; UnknownPatternError; UnknownSegmentError
```

`offers` defaults to `gate.load_offers()`; a concept's `offer` must be
`"none"` or a verified offer id. Ids are stamped `a01`.. by position.

### C4 - concept record

```json
{"id": "a01", "segment": "payroll-bureaus", "angle": "...", "hook": "...",
 "pattern_ids": ["q03"], "placement": "reels-9x16", "offer": "guarantee",
 "needs_numbers": false}
```

## engine/score.py

Ported with these substitutions: `WEIGHTS` unchanged; `EVIDENCE_FULL_N = 3`;
`DAYS_FULL = 120` replaces `VIEWS_FULL` and `median_days_running` replaces
`median_views` on a log scale; `_claims_survivability` uses
`gate.unattested_numbers("hook", hook)` and `needs_numbers`; `_icp_fit`
unchanged; `_novelty` compares the concept's hook and angle words against
`headline.en` and `primary_text.en` of every job in `queue/proposed`,
`queue/built`, `queue/launched` **and** every `creative/*.json` except
`example-job.json`; `_spread` takes the best per segment first, then the best
per placement among the rest, then score order. `RUBRIC` judges an ad's
opening line and angle for that trade. `Selection.as_dict()` is `{"selected":
[ids], "model_calls": int, "scorecards": [...]}`.

## engine/measure.py

Our own launched ads, read through the Marketing API insights edge.

```python
GRAPH = "https://graph.facebook.com"        # META_GRAPH_VERSION env inserts a version
INSIGHT_FIELDS = ("impressions", "reach", "clicks", "ctr", "cpc", "cpm", "spend", "actions",
                  "cost_per_action_type", "video_play_actions", "video_thruplay_watched_actions",
                  "video_p25_watched_actions", "video_p50_watched_actions",
                  "video_p75_watched_actions", "video_p100_watched_actions")
DATE_PRESET = "maximum"
HOURLY_BUDGET_CALLS = 200; UNIT_COSTS = {"insights": 1}
MEASUREMENTS_PATH = ROOT / "research" / "measurements.json"; SCHEMA = 1
class MeasureError(RuntimeError); class UnmeasurableJob(MeasureError)
class MeasureClient(token=None, *, budget=HOURLY_BUDGET_CALLS, quota=None, transport=None)
    .insights(ad_id) -> dict    # GET {GRAPH}/{ad_id}/insights?fields=...&date_preset=maximum, one charge
def launched_jobs() -> list[approval.Job]
def measurement(*, segment, ad_id, campaign_id, launched_at, insights: dict, now=None) -> dict   # C6 row
def measure_all(*, client=None, now=None) -> MeasureRun     # MeasureRun(rows, skipped, calls)
def document(rows) -> dict; def write_measurements(rows, path=None) -> Path; def load(path=None) -> dict
def main(argv=None) -> int     # --dry-run --strict --out
```

`INSIGHT_FIELDS` carries a `TODO(integration): UNVERIFIED AGAINST A LIVE
RESPONSE` comment: the names are from the Marketing API reference as
remembered, and the first live run is the proof. `plays_3s` is read from
`actions` where `action_type == "video_view"`; `results` and
`cost_per_result` from `actions` / `cost_per_action_type` for the first of
`lead`, `schedule`, `contact`, `link_click`. Absent is `null`, never 0.

### C6 - measurement row

```json
{"segment": "payroll-bureaus", "ad_id": "1234", "campaign_id": "5678",
 "launched_at": "2026-09-29T10:00:00Z", "measured_at": "2026-10-06T05:02:00Z",
 "date_preset": "maximum",
 "metrics": {"impressions": 4100, "reach": 3300, "clicks": 51, "ctr": 1.24, "cpc": 0.61,
             "cpm": 7.6, "spend": 31.2, "plays_3s": 1200, "thruplays": 240,
             "p25": null, "p50": null, "p75": null, "p100": null,
             "results": 4, "cost_per_result": 7.8},
 "derived": {"hook_rate": 0.293, "hold_rate": 0.2}}
```

The document is `{"schema": 1, "generated_at": "...", "rows": [...]}` sorted
by `(segment, ad_id)`.

## engine/feedback.py

Launched jobs plus measurement rows become corpus records with `origin: own`.
Zero model calls and no network; `tests/test_feedback.py` AST-parses it.

```python
ORIGIN = "own"; MODEL = "none (authored)"
def record_for(job: dict, row: dict, *, own: discover.Own | None, now=None) -> dict   # C1, id "fb-own-<segment>-<ad_id>"
def feed_back(*, corpus_root=None, measurements_path=None, seeds_path=None, now=None) -> FeedbackRun   # (written, skipped)
def main(argv=None) -> int   # --dry-run
```

`metrics.eu_total_reach` is the row's `reach`; `days_running` is
`measured_at - launched_at` in whole days; `active` is `true`; `variants` is
the number of launched ads for that segment; `page_id` is `own.page_id` or
`""`. `analysis.copy` is the job's `en` copy; `hook.text` is the first
sentence of `primary_text.en`, `hook.device` is `"authored"`, `structure` is
`["hook", "offer", "cta"]` if the offer is not `none` else `["hook", "cta"]`,
`cta.type` is the lowercase-hyphen form of the job's `cta`,
`offer.type` is the job's `offer`, `proof` is `{"type": "none", "text": ""}`,
`objections` is `[]`, `creative` is `{"kind": "authored"}`,
`own_metrics` carries `ctr`, `hook_rate`, `hold_rate` from the row, and
`derived_from.note` says all of that. A row with `impressions` null or 0 is
skipped by name.

## engine/write.py

```python
MODEL_WRITE = model.MODEL_WRITE; MAX_TOKENS_WRITE = 8000
AUTHORED = ("primary_text", "headline", "description", "cta", "hypothesis")   # English only; the model writes these
def generate(segment, *, concept=None, patterns=None, placement=None, client=None, feedback=None, now=None) -> dict   # a C3 job
def reel_selection(concept, segment, *, now=None) -> dict
def concept_block(concept, patterns) -> str      # the same withheld-hook rule as reel-engine/engine/script.py
```

The prompt carries: the segment (trade, three questions, note); the verified
claims' `safe_phrasings` and the chosen offer's `safe_phrasings` from
`claims/evidence.json` as the only product facts it may assert; the number
ban with the number-word list; `gate.REFUSED_CONSTRUCTIONS`; `gate.LIMITS`;
the C3 worked example `creative/example-job.json` (en fields only); the
selected concept block with the hook withheld if it carries an unattested
number; `feedback` as a "previous attempt failed for these reasons" block.
Nothing from `docs/ICP-BRIEF.md` is read. The writer stamps `da` and `lt` to
`NEEDS_NATIVE_PROOFREAD`, `id`/`segment`, `concept_id`, `pattern_ids`,
`placement` (the concept's, or `placement=`, default `reels-9x16`), `offer`,
`destination = "https://doviloop.dev"`, `creative_source` (`reel` for
`reels-9x16`/`feed-4x5` with template `reel-c` or `reel-b`; `still` for
`static-1x1`), `proposed_at`, `ads: {}`, `launched_at: null`.

`reel_selection` returns a document `reel-engine/engine/script.py`'s
`load_selection` accepts: `{"schema": 1, "generated_at": "...", "source":
"ad-engine", "selected": ["<concept id>"], "concepts": [{"id", "segment",
"angle", "hook", "pattern_ids": [], "format": "<placement words>",
"needs_numbers"}]}`.

## engine/fanout.py

`reel-engine/engine/fanout.py` with `discover.AdLibraryClient` in place of the
YouTube client, `analyse.analyse_all` (batched), `--max-ads` in place of
`--max-videos` (default 12: one text batch), the cost ledger counting
`model_calls` and `ad_library_calls`, and the report at
`research/selection.json`. `plan()` is `--dry-run`. Candidates already in the
corpus are never analysed twice; fresh ones are ranked by `outlier_ratio` then
`days_running` then id.

## engine/propose.py

`reel-engine/engine/propose.py` with `write.generate` in place of
`script.generate` and `gate.run` as the gate. Flags: `--segment`, `--concept`,
`--from-selection`, `--selection`, `--placement`, `--regate`, `--id-file`,
`--retries` (default 1), `--force`. Writes `queue/proposed/<segment>.json` and,
when `creative_source.kind == "reel"`, `queue/proposed/<segment>.reel.json`
from `write.reel_selection`. A structural failure parks the draft in
`queue/rejected/`; an editorial failure retries with feedback. The id file
lists one segment per line, written in a `finally`.

## Workflows

| File | Trigger | Does |
|---|---|---|
| `tests.yml` | pull_request, push to main | `python -m pytest -q`; `contents: read`; cancel-in-progress true; no browser |
| `research.yml` | `0 6 * * 1`, dispatch (`max_ads`, `dry_run`) | requires `GEMINI_API_KEY`, `META_ACCESS_TOKEN`; `python -m engine.fanout --budget 150`; commits `research/corpus research/patterns.json research/selection.json` by name; `contents: write` only |
| `propose.yml` | `0 9 * * 1`, `0 9 * * 4`, dispatch (`segment`, `ignore_selection`) | requires `GEMINI_API_KEY`; `engine.propose --from-selection --retries 2 --id-file`; commits `queue`; one issue per proposed segment via `engine.approval open --segment` (no still yet); `contents: write`, `issues: write` |
| `build.yml` | `issues.labeled` `go` + `stage:copy` | resolve `--expect proposed`; if `creative_source.kind == reel`: require `REEL_ENGINE_TOKEN` and `GEMINI_API_KEY`, checkout `Dasvydo/reel-engine` at `../reel-engine`, install it plus Chromium, run its `engine.propose --concept <id> --selection <abs path to .reel.json> --template <t> --still --render`, upload the MP4 and still as artifacts (14 days), copy the still to `queue/built/<segment>.jpg`; then `approval advance --to built`, commit, comment with the artifact link and the Ads Manager steps, swap labels to `stage:creative` |
| `launch.yml` | dispatch (`segment`, `ad_id`, `campaign_id`, `issue`) | `approval launch`, commit, comment and close the issue |
| `reject.yml` | `issues.labeled` `no` | `approval drop`, commit, close |
| `measure.yml` | `0 5 * * 1`, dispatch (`dry_run`) | requires `META_ACCESS_TOKEN`; `engine.measure` then `engine.feedback`; commits `research/measurements.json research/corpus` by name; `contents: write` only |

Every committing workflow uses `tools/push_with_retry.sh`, stamps
`JOB_STARTED` and reports minutes under `if: always()`, sets
`timeout-minutes`, and checks out a branch (not a detached HEAD) when it
pushes. Label-triggered jobs declare job-level concurrency
`ad-${{ github.event.issue.number }}` with `cancel-in-progress: false` and
guard on the label name. No `run:` body interpolates a `${{ }}` expression
directly; values pass through `env:`.
