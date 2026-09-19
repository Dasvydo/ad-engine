"""python -m engine.fanout [--budget N] [--max-ads N] [--concepts N] [--select N]

The weekly research run, composed end to end: discover -> analyse -> corpus ->
learn -> concepts -> score, and three concepts that each trace back to a real
ad that an advertiser's own money kept running.

THIS MODULE ORCHESTRATES AND NOTHING ELSE. Every step belongs to the module
that owns it and is called rather than reimplemented: engine.discover finds the
candidates in the Ad Library, engine.analyse reads them, engine.corpus stores
them, engine.learn counts the patterns, engine.concepts writes against those
patterns and engine.score picks the winners. What this file adds is the three
things none of them can decide alone - the ORDER, the BUDGET and the REPORT.

THE BUDGET IS THE DESIGN DECISION. Two ledgers, and they pull differently from
the reel loop's. The Ad Library side is cheap and exact: engine.discover
charges one call per result page BEFORE the socket opens, so `--budget` is a
hard ceiling and a run refused by it keeps nothing rather than half. The model
side is where the free tier bites - twenty requests a day per model, measured
in reel-engine from the 429 that killed propose run 26 - and engine.analyse
spends ONE CALL PER BATCH of twelve text ads (one per hand-saved creative on
top), not one per ad. So `--max-ads` caps what is analysed, the default is 24
because that is exactly two text batches, and the cap is spent where it is
worth most: candidates are ranked by `outlier_ratio`, which is the entire
point of discovery, then by `days_running`, then by id so the same week picks
the same ads twice. An ad already in the corpus is never analysed again - the
call would buy an answer we have, and re-analysing rewrites `fetched_at`,
which puts a diff in a committed file that did not change.

NOTHING THIN OVERWRITES SOMETHING GOOD. A week that discovers nothing, or a
corpus still too small for learn.MIN_SUPPORT, leaves research/patterns.json
exactly as it is and says why. A patterns file with no patterns in it is not a
fact about this week; it is the loss of everything the corpus learned before it.

A SKIP IS NOT A FAILURE. engine.analyse already reports the ad it could not
read and carries on with the rest, and that property is preserved end to end
here: skips are listed, and a run that skipped some ads is still `ok`. A
STAGE that could not run at all - discovery refused, no patterns to cite, the
model unreachable - IS a failure: it is named in the report, the run still does
whatever it can with what is on disk, and the exit code is 1, so an unattended
Monday morning goes red rather than quietly producing nothing every week.

THE REPORT IS AN OUTPUT, not a log line. research/selection.json carries the
concept records themselves, the winners' ids, and a scorecard for every concept
including the ones that lost - a selection nobody can audit is an oracle. It is
written on every live run, including a run that failed early: a stale report
left behind by a failed run is how the same three concepts get filed twice.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from engine import analyse, backlog, concepts, corpus, discover, learn, model, score
from engine.model import ConfigError

ROOT = Path(__file__).resolve().parents[1]

# The selection report. One file, overwritten weekly, because git history is
# this repository's audit log - the same reason research/corpus/ and queue/ are
# committed JSON rather than a database.
DEFAULT_REPORT = ROOT / "research" / "selection.json"

SCHEMA = 1

# How many ads one weekly run is allowed to analyse.
#
# TWELVE is exactly ONE text batch of analyse.BATCH_SIZE, so a research Monday
# with nothing hand-saved costs 1 + 1 (concepts) + 1 (editorial) = 3 of the 20
# daily calls the free tier allows per model - leaving 17 for the propose runs
# that fire on the same key three hours later.
#
# It was 24 (two batches, 4 calls). Twelve is the cheaper half of a deliberate
# trade: fanout._rank_key sorts by outlier ratio and then by days running, so
# the twelve that survive the cut are the twelve best-performing ads of the
# sweep, and the thirteenth was never going to teach the corpus much that the
# twelfth did not. A week that genuinely wants depth passes --max-ads by hand;
# the default is for the unattended Monday, where cheap and best-first beats
# thorough. Raise it only with docs/COST.md open.
DEFAULT_MAX_ADS = 12

# The two ledgers the report keeps. `model_calls` is what docs/COST.md prices
# against the free tier; `ad_library_calls` is engine.discover's own ledger,
# read back off its Quota.
COST_KEYS = ("model_calls", "ad_library_calls")


def _moment(now) -> datetime:
    """`now` as an aware UTC datetime: a datetime (naive read as UTC), a date
    (midnight UTC), an ISO-8601 string ('Z' honoured), or None for the clock.

    One reading per run, handed to discovery (its `today`), to analysis (its
    `fetched_at` stamp) and to the report, so a pinned `now` pins every byte
    the run writes - which is what makes an unchanged week diff as nothing.
    """
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)
    if isinstance(now, date):
        return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    if isinstance(now, str):
        text = now.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return _moment(datetime.fromisoformat(text))
    raise TypeError(
        "now must be a datetime, a date, an ISO-8601 string or None; got %r" % (now,)
    )


def _stamp(moment: datetime) -> str:
    """UTC to the second. The report is read on two machines, and a local
    offset in a committed file is a diff waiting to happen."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _where(path: Path | str | None, default: Path) -> str:
    """A path as a report line names it: relative to the repository root when
    it lives under it, absolute otherwise.

    The report is committed, and a runner's checkout is not at the operator's
    path: '/home/runner/work/ad-engine/ad-engine/research/seeds.yaml' in
    research/selection.json is a diff every time the machine changes and a
    line nobody can copy into a terminal. 'research/seeds.yaml' is both. A
    path outside the tree (every test's tmp_path) stays as given, because
    relative to what would be a guess.
    """
    resolved = Path(path) if path else default
    try:
        return resolved.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _client():
    """One model client for all three steps that need one.

    Built once and handed down rather than letting analyse, concepts and score
    each build their own: a run with no key should say so once, before it
    spends an Ad Library call on a discovery whose results it could never
    analyse. engine.model.client() raises the same ConfigError; this one names
    the three steps so the operator knows what the key is for.
    """
    if not model.api_key():
        raise ConfigError(
            "GEMINI_API_KEY is not set; the weekly run reads each batch of ads, "
            "writes the concepts and scores them with %s - three steps, one "
            "key. Mint a free key at aistudio.google.com" % model.MODEL_WRITE
        )
    return model.client()


@dataclass(frozen=True)
class RunReport:
    """What one run did, what it could not do, and what it cost.

    `failed` and `skipped` are deliberately different lists. A skip is an ad
    this run could not use and the next one might - a creative the model
    refused, a file over the inline limit - and it does not make the run
    unsuccessful. A failure is a stage that could not run, which is what the
    exit code reports.
    """

    generated_at: str
    dry_run: bool = False
    counts: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)
    estimate: dict = field(default_factory=dict)
    failed: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    selected: list = field(default_factory=list)
    concepts: list = field(default_factory=list)
    scorecards: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed

    def as_dict(self) -> dict:
        """The report as it goes to disk and to stdout under --json."""
        return {
            "schema": SCHEMA,
            "generated_at": self.generated_at,
            "dry_run": self.dry_run,
            "ok": self.ok,
            "counts": dict(self.counts),
            "cost": dict(self.cost),
            "estimate": dict(self.estimate),
            "failed": list(self.failed),
            "skipped": list(self.skipped),
            "selected": list(self.selected),
            "concepts": list(self.concepts),
            "scorecards": list(self.scorecards),
        }

    def summary(self) -> str:
        """The operator's version. One block, for a workflow log or a terminal."""
        counts = self.counts
        if self.dry_run:
            lines = [
                "research preflight %s: %s"
                % (
                    self.generated_at,
                    "ok" if self.ok else "%d problem(s)" % len(self.failed),
                ),
                "  seeds ask for %d page search(es) over %d seeded page(s) and "
                "%d quer(ies)"
                % (
                    self.estimate.get("page_calls", 0),
                    counts.get("seed_pages", 0),
                    counts.get("seed_queries", 0),
                ),
                "  on disk: %d corpus record(s), %d pattern(s), %d segment(s), "
                "%d hand-saved creative(s)"
                % (
                    counts.get("corpus", 0),
                    counts.get("patterns", 0),
                    counts.get("segments", 0),
                    counts.get("creatives", 0),
                ),
                "  a run would analyse up to %d ad(s), write %d concept(s), "
                "select %d, and spend up to %d model call(s) and %d of %d "
                "Ad Library call(s)"
                % (
                    self.estimate.get("max_ads", 0),
                    counts.get("concepts", 0),
                    counts.get("selected", 0),
                    self.estimate.get("model_calls", 0),
                    self.estimate.get("ad_library_calls", 0),
                    self.estimate.get("budget", 0),
                ),
            ]
        else:
            lines = [
                "research run %s: %d concept(s) selected"
                % (self.generated_at, counts.get("selected", 0)),
                "  discovered %d candidate(s), %d not yet analysed, %d analysed here"
                % (
                    counts.get("discovered", 0),
                    counts.get("new", 0),
                    counts.get("analysed", 0),
                ),
                "  corpus %d record(s) -> %d pattern(s) -> %d concept(s) -> %s"
                % (
                    counts.get("corpus", 0),
                    counts.get("patterns", 0),
                    counts.get("concepts", 0),
                    ", ".join(self.selected) or "nothing selected",
                ),
                "  spent %d model call(s) and %d Ad Library call(s)"
                % (
                    self.cost.get("model_calls", 0),
                    self.cost.get("ad_library_calls", 0),
                ),
            ]
        for label, entries in (("skipped", self.skipped), ("FAILED", self.failed)):
            if entries:
                lines.append("  %s %d:" % (label, len(entries)))
                lines.extend("    - %s" % entry for entry in entries)
        return "\n".join(lines)


def write_report(report: RunReport, path: Path | str | None = None) -> Path:
    """Write the selection report and return its path.

    learn.dumps rather than a second json.dumps call with the same arguments:
    sorted keys, two-space indent and a trailing newline are what make a
    committed file diff as the fields that actually changed, and one module
    should define that format for the whole research half.
    """
    path = Path(path) if path else DEFAULT_REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(learn.dumps(report.as_dict()), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# What a run would do, before it does it
# ---------------------------------------------------------------------------


def _seed_plan(seeds) -> dict:
    """What this seeds file asks discovery to do. Counts only, no calls.

    engine.discover.plan() is the price list - pages ten to a call per country
    list, one call per query, each search paged up to DEFAULT_MAX_PAGES - and
    it is read rather than re-derived so the arithmetic lives in the module
    that spends it. `competitors` is added here because it is the one count
    the run reports on and discover has no reason to.
    """
    if seeds is None:
        return {
            "pages": 0, "page_calls": 0, "queries": 0, "query_calls": 0,
            "min_calls": 0, "max_calls": 0, "competitors": 0,
        }
    planned = discover.plan(seeds)
    return {
        "pages": planned["pages"],
        "page_calls": planned["page_calls"],
        "queries": planned["queries"],
        "query_calls": planned["query_calls"],
        "min_calls": planned["min_calls"],
        "max_calls": planned["max_calls"],
        "competitors": sum(1 for page in seeds.pages if page.origin == "competitor"),
    }


def _creatives_on_disk(media_root: Path | str | None) -> int:
    """How many hand-saved creatives research/media/ holds, by suffix.

    Counted, not matched: which of them belong to an ad this run will choose
    is unknowable before discovery, so the number feeds a ceiling and nothing
    else. engine.analyse is what matches a file to its candidate.
    """
    root = Path(media_root) if media_root else analyse.MEDIA_ROOT
    if not root.is_dir():
        return 0
    return sum(
        1 for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in analyse.MEDIA_SUFFIXES
    )


def _estimate(plan: dict, *, max_ads: int, budget: int, creatives: int) -> dict:
    """What a live run would cost, before it makes a single call.

    The Ad Library figure is discover's own arithmetic: one call per ten
    seeded pages sharing a country list, one per query, each search paged up
    to DEFAULT_MAX_PAGES. `searches` is the floor (every search answers in
    one page) and `ad_library_calls` the ceiling (every search pages to the
    limit); the shipped seeds file - two pages, five queries - is 6 to 12.

    Model calls are a CEILING, not a forecast: at most one per text batch of
    analyse.BATCH_SIZE ads, plus one per hand-saved creative that might be
    among the chosen (every file on disk is ASSUMED to be, since nothing here
    knows before discovery), plus the one concepts call and the one editorial
    call, whatever N is. With nothing hand-saved and the default cap that is
    2 + 2 = 4 of the 20 daily requests the free tier allows per model.
    """
    cap = max(0, max_ads)
    media = min(creatives, cap)
    text = cap - media
    batches = -(-text // analyse.BATCH_SIZE)
    return {
        "ad_library_calls": plan["max_calls"],
        "searches": plan["min_calls"],
        "page_calls": plan["page_calls"],
        "query_calls": plan["query_calls"],
        "max_pages": discover.DEFAULT_MAX_PAGES,
        "budget": budget,
        "max_ads": cap,
        "model_calls": media + batches + 2,
    }


def _no_competitor_watched(seeds) -> str | None:
    """A seeds file watching no competitor, said out loud.

    This described the shipped file, which as of 2026-09-19 watches three
    competitors - Echo You, Fyxer and Jace.ai - so the note it returns is now
    the empty case rather than the normal one. The function stays because the
    empty case is the one worth catching: discovery is correct to search only
    what it is given, and a file that names only icp-adjacent pages is
    watching half the market with nothing to say so.
    """
    if seeds is None or not (seeds.pages or seeds.queries):
        return None
    if any(page.origin == "competitor" for page in seeds.pages):
        return None
    where = _where(seeds.path, discover.SEEDS_PATH)
    return (
        "discover: no page in %s has origin 'competitor' - every seeded page "
        "is icp-adjacent - so no competitor's ads reach the corpus. Seed one "
        "under 'pages:' by its numeric page_id (open the page's ads in the Ad "
        "Library UI and read view_all_page_id out of the URL; it is not the "
        "page name), with the countries it actually runs in. A keyword search "
        "for a competitor's name finds nothing: search matches creative text, "
        "and a company's name is rarely in its own copy."
        % where
    )


def _why_nothing_was_discovered(plan: dict, *, seeds, days: int | None) -> str:
    """The message a zero-candidate week gets. It has to name the fix."""
    where = _where(seeds.path if seeds is not None else None, discover.SEEDS_PATH)
    if not plan["pages"] and not plan["queries"]:
        return (
            "discover: %s asks for nothing - no page is seeded and there is "
            "no query. Add a page under 'pages:' by its numeric page_id (from "
            "the Ad Library UI's URL, not the page name), or a keyword under "
            "'queries:' in the market's own words."
            % where
        )
    window = (
        "the last %d day(s) this run asked for (--days)" % days
        if days
        else "the archive's whole history (no --days window)"
    )
    return (
        "discover: %d page search(es) over %d seeded page(s) and %d quer(ies) "
        "returned no candidate. Either nothing was delivered inside %s, or the "
        "seeded pages run no ads in the countries listed for them - a "
        "commercial ad that reached no EU country is not in the archive at "
        "all. Check %s."
        % (plan["page_calls"], plan["pages"], plan["queries"], window, where)
    )


def plan(
    *,
    seeds_path: Path | str | None = None,
    corpus_root: Path | str | None = None,
    patterns_path: Path | str | None = None,
    backlog_path: Path | str | None = None,
    media_root: Path | str | None = None,
    budget: int = discover.HOURLY_BUDGET_CALLS,
    max_ads: int = DEFAULT_MAX_ADS,
    n_concepts: int = concepts.DEFAULT_N,
    top: int = score.TOP_N,
    now=None,
) -> RunReport:
    """The preflight behind --dry-run. Reads files; calls nothing, writes nothing.

    Not a rehearsal of the run - a check of its preconditions. It answers the
    question an operator actually has before the first live Monday: is this
    repository in a state where the weekly run can produce anything, and what
    will it spend if it does. Every fault it finds is one that would otherwise
    cost a runner, an Ad Library call or a model call to discover. It needs no
    token and no key: the seeds file is read by engine.discover.load_seeds,
    which opens no socket.
    """
    failed: list[str] = []
    skipped: list[str] = []
    # A preflight reports what the run WOULD write, so `concepts` and
    # `selected` carry the numbers it was asked for rather than zero.
    counts = {
        "discovered": 0, "new": 0, "analysed": 0, "corpus": 0, "segments": 0,
        "patterns": 0, "concepts": n_concepts, "selected": top,
    }

    seeds = None
    try:
        seeds = discover.load_seeds(seeds_path)
    except discover.DiscoveryError as exc:
        failed.append("discover: %s" % exc)

    seed_plan = _seed_plan(seeds)
    creatives = _creatives_on_disk(media_root)
    estimate = _estimate(seed_plan, max_ads=max_ads, budget=budget, creatives=creatives)
    counts.update({
        "seed_pages": seed_plan["pages"],
        "seed_queries": seed_plan["queries"],
        "seed_competitors": seed_plan["competitors"],
        "creatives": creatives,
    })

    if estimate["ad_library_calls"] > budget:
        failed.append(
            "discover: this seeds file plans %d search(es), which is up to %d "
            "Ad Library call(s) at %d result page(s) each, and the budget for "
            "this run is %d. Raise --budget (the hourly allowance is about %d "
            "per token) or cut pages and queries from research/seeds.yaml - "
            "discovery refuses the call it cannot afford, and a run that runs "
            "out mid-flight keeps nothing."
            % (
                estimate["searches"],
                estimate["ad_library_calls"],
                estimate["max_pages"],
                budget,
                discover.HOURLY_BUDGET_CALLS,
            )
        )

    try:
        counts["corpus"] = len(corpus.load_all(corpus_root))
    except (FileNotFoundError, corpus.CorpusInvalid) as exc:
        failed.append("corpus: %s" % exc)

    try:
        document = learn.load(patterns_path)
        counts["patterns"] = len(document.get("patterns") or [])
    except FileNotFoundError:
        # Not a fault on a first run: the learn step writes this file, and a
        # corpus with something in it will produce one. Only a corpus that is
        # ALSO empty leaves the concepts step with nothing to cite.
        counts["patterns"] = 0
    except learn.PatternsInvalid as exc:
        failed.append("learn: %s" % exc)

    try:
        counts["segments"] = len(backlog.load(backlog_path))
    except (OSError, ValueError) as exc:
        failed.append("concepts: %s" % exc)

    if top > n_concepts:
        failed.append(
            "score: --select %d out of only %d concept(s) written, which the "
            "scorer can never reach - and it reaches it even less often than "
            "that, because a concept whose hook would fail the claims gate is "
            "refused outright. Ask for more concepts than you intend to select."
            % (top, n_concepts)
        )

    if not counts["corpus"] and not estimate["searches"]:
        failed.append(_why_nothing_was_discovered(seed_plan, seeds=seeds, days=None))

    note = _no_competitor_watched(seeds)
    if note:
        skipped.append(note)

    return RunReport(
        generated_at=_stamp(_moment(now)),
        dry_run=True,
        counts=counts,
        cost={key: 0 for key in COST_KEYS},
        estimate=estimate,
        failed=failed,
        skipped=skipped,
    )


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _rank_key(candidate: dict):
    """Best outlier ratio first, then the ad that ran longest, then id.

    The ratio is the one discovery computed - an ad that beat its own page is
    the one worth a call - and NO_BASELINE is 0.0, which sorts last, which is
    correct: an ad with no baseline is not a known outlier. Among equals, the
    longer-running ad is the stronger signal (docs/AD-RESEARCH-SCOPE.md 2.3:
    longevity is primary); the id breaks the last tie so the same week picks
    the same ads twice.
    """
    metrics = candidate.get("metrics") or {}
    try:
        ratio = float(candidate.get("outlier_ratio") or 0.0)
    except (TypeError, ValueError):
        ratio = 0.0
    try:
        days = float(metrics.get("days_running") or 0)
    except (TypeError, ValueError):
        days = 0.0
    return (-ratio, -days, str(candidate.get("id")))


def run(
    *,
    seeds_path: Path | str | None = None,
    corpus_root: Path | str | None = None,
    patterns_path: Path | str | None = None,
    backlog_path: Path | str | None = None,
    queue_root: Path | str | None = None,
    creative_root: Path | str | None = None,
    media_root: Path | str | None = None,
    report_path: Path | str | None = None,
    budget: int = discover.HOURLY_BUDGET_CALLS,
    days: int | None = None,
    max_ads: int = DEFAULT_MAX_ADS,
    n_concepts: int = concepts.DEFAULT_N,
    top: int = score.TOP_N,
    origin: str | None = None,
    client=None,
    ad_client=None,
    evidence=None,
    now=None,
) -> RunReport:
    """One weekly run. Writes the corpus records, the patterns and the report.

    `client` is the model client for all three steps that need one, and
    `ad_client` is the Ad Library client (an engine.discover.AdLibraryClient
    over an injected transport); both are injected by the tests, which is why
    no test in this suite needs a key, a token or a socket. `now` pins the
    clock for the whole run: the report's generated_at, discovery's `today`
    and the records' fetched_at all read it, so the same inputs write the
    same bytes.
    """
    moment = _moment(now)
    started = _stamp(moment)
    failed: list[str] = []
    skipped: list[str] = []
    counts = {
        "discovered": 0, "new": 0, "analysed": 0, "corpus": 0,
        "patterns": 0, "concepts": 0, "selected": 0,
        "seed_pages": 0, "seed_queries": 0, "seed_competitors": 0, "creatives": 0,
    }
    # The ledger docs/COST.md reads: one call per analysis batch (and one per
    # hand-saved creative), one for the concepts, one for the editorial score.
    # The analysis half is exact - engine.analyse counts the calls it made,
    # refusals included. Two edges downstream it cannot see, and they pull
    # opposite ways: a concepts reply the module refused after the model
    # answered is charged below as one call, while a concepts step that never
    # reached the wire is charged the same one. Neither shifts the order of
    # magnitude this invariant lives at; a run that needs the exact figure has
    # the per-call record in the provider's own console. The Ad Library half
    # is exact, because engine.discover charges its ledger before it opens the
    # socket, and it is read back as THIS run's delta so a shared ledger is
    # not over-reported.
    cost = {key: 0 for key in COST_KEYS}
    estimate: dict = {}
    written: list = []

    def finish(selection=None) -> RunReport:
        chosen = [c.get("id", "") for c in selection.selected] if selection else []
        counts["selected"] = len(chosen)
        report = RunReport(
            generated_at=started,
            counts=counts,
            cost=cost,
            estimate=estimate,
            failed=failed,
            skipped=skipped,
            selected=chosen,
            concepts=written,
            scorecards=[card.as_dict() for card in selection.scorecards]
            if selection
            else [],
        )
        write_report(report, report_path)
        return report

    # The model client first, and eagerly. Three of the six steps need it, so a
    # run without a key cannot finish whatever else happens - and finding that
    # out here means no Ad Library call is spent on a discovery that could
    # never be analysed.
    if client is None:
        try:
            client = _client()
        except ConfigError as exc:
            failed.append("model: %s" % exc)
            return finish()

    # The corpus is read BEFORE discovery, so a candidate already analysed is
    # never analysed a second time.
    try:
        existing = corpus.load_all(corpus_root)
    except (FileNotFoundError, corpus.CorpusInvalid) as exc:
        # Nothing downstream can run without a readable corpus: learn counts
        # it, and a partial read would quietly produce weaker patterns.
        failed.append("corpus: %s" % exc)
        return finish()
    known = {record.id for record in existing}

    # ---- discover ---------------------------------------------------------
    seeds = None
    candidates: list = []
    try:
        seeds = discover.load_seeds(seeds_path)
    except discover.DiscoveryError as exc:
        failed.append("discover: %s" % exc)

    seed_plan = _seed_plan(seeds)
    creatives = _creatives_on_disk(media_root)
    estimate = _estimate(seed_plan, max_ads=max_ads, budget=budget, creatives=creatives)
    counts.update({
        "seed_pages": seed_plan["pages"],
        "seed_queries": seed_plan["queries"],
        "seed_competitors": seed_plan["competitors"],
        "creatives": creatives,
    })

    if seeds is not None:
        spent_before = ad_client.quota.spent if ad_client is not None else 0
        try:
            if ad_client is None:
                # The token is read here, through engine.oauth, and a missing
                # or expired one is a DiscoveryError like any other: reported,
                # never a traceback, never a value.
                ad_client = discover.AdLibraryClient(budget=budget)
            candidates = discover.discover(
                seeds, client=ad_client, today=moment, days=days
            )
        except (discover.DiscoveryError, ValueError) as exc:
            # A refused token, an exhausted budget, an API error, or a --days
            # that is not a positive number. Reported and carried past rather
            # than raised: the corpus on disk still holds evidence, and a week
            # that cannot discover can still learn from what it has. The exit
            # code still says the run was degraded.
            failed.append("discover: %s" % exc)
        finally:
            if ad_client is not None:
                cost["ad_library_calls"] = ad_client.quota.spent - spent_before

    counts["discovered"] = len(candidates)
    # `not failed` because discovery is the only stage that can have failed by
    # this line, and a run refused by the quota does not also need to be told
    # its seeds file returned nothing.
    if not candidates and not failed:
        failed.append(_why_nothing_was_discovered(seed_plan, seeds=seeds, days=days))
    note = _no_competitor_watched(seeds)
    if note:
        skipped.append(note)

    fresh = [c for c in candidates if c.get("id") not in known]
    fresh.sort(key=_rank_key)
    counts["new"] = len(fresh)
    chosen = fresh[: max(0, max_ads)]

    # ---- analyse ----------------------------------------------------------
    batch = analyse.AnalysisRun()
    if chosen:
        try:
            batch = analyse.analyse_all(
                chosen, client=client, media_root=media_root, now=moment
            )
        except (analyse.AnalysisError, corpus.CorpusInvalid, ConfigError) as exc:
            # The prompt or the model being wrong for a whole batch, not for
            # one ad: analyse_all already absorbs the per-ad faults. The run
            # carries on with the corpus it had. A batch that raised part-way
            # through a run spent the calls before it and they are not in
            # the ledger - the console has them. Not a bare ValueError: that
            # would also swallow a candidate-shape bug, which is ours to fix.
            failed.append("analyse: %s" % exc)
    skipped.extend("analyse: %s" % line for line in batch.skipped)
    # batch.calls, NOT len(batch.records): a batch of twelve is one call, and
    # a refusal the model answered with is a call that was spent.
    cost["model_calls"] += batch.calls

    # ---- corpus -----------------------------------------------------------
    for record in batch.records:
        try:
            corpus.save(record, corpus_root)
        except (OSError, corpus.CorpusInvalid) as exc:
            # One unwritable record must not cost the others their place in the
            # corpus, exactly as one unreadable ad does not stop the batch.
            skipped.append("corpus: %s: %s" % (record.get("id", "?"), exc))
        else:
            counts["analysed"] += 1

    # Re-read rather than appending in memory, so what the learn step counts is
    # exactly what was committed - a record that failed to write is not learned
    # from.
    try:
        records = corpus.load_all(corpus_root)
    except (FileNotFoundError, corpus.CorpusInvalid) as exc:
        failed.append("corpus: %s" % exc)
        return finish()
    counts["corpus"] = len(records)

    # ---- learn ------------------------------------------------------------
    patterns_file = Path(patterns_path) if patterns_path else learn.DEFAULT_PATH
    try:
        document = learn.build(
            records,
            origin=origin,
            on_skip=lambda line: skipped.append("learn: %s" % line),
        )
    except (TypeError, ValueError) as exc:
        # An origin outside corpus.ORIGINS from a programmatic caller (the CLI
        # refuses one), or a record shape the corpus loader let through.
        failed.append("learn: %s" % exc)
        return finish()
    counts["patterns"] = len(document["patterns"])
    if not document["patterns"]:
        failed.append(
            "learn: %d corpus record(s)%s produced no pattern that %d or more "
            "ads support, so nothing was written and any existing %s was "
            "left exactly as it is. Analyse more ads - a pattern is a count, "
            "not an opinion, and one ad cannot make one."
            % (
                document["corpus_size"],
                " of origin %r" % origin if origin else "",
                learn.MIN_SUPPORT,
                _where(patterns_file, learn.DEFAULT_PATH),
            )
        )
        return finish()
    try:
        # Written only when the bytes differ. learn.build stamps generated_at
        # from the newest fetched_at in the corpus rather than the clock, so an
        # unchanged corpus produces an identical document, and an identical
        # document is not a write: the file's mtime then says the same thing
        # git does.
        text = learn.dumps(document)
        if not patterns_file.exists() or patterns_file.read_text(encoding="utf-8") != text:
            learn.write(document, patterns_file)
    except OSError as exc:
        failed.append("learn: could not write the patterns document: %s" % exc)
        return finish()

    # ---- concepts ---------------------------------------------------------
    try:
        segments = backlog.load(backlog_path)
    except (OSError, ValueError) as exc:
        # OSError: no backlog. ValueError: a malformed row. Neither reached
        # the model, so nothing is charged.
        failed.append("concepts: %s" % exc)
        return finish()
    try:
        written = concepts.generate(document, segments, n=n_concepts, client=client)
    except (ConfigError, OSError, ValueError) as exc:
        # Every ConceptsError - including the PatternsInvalid that engine.learn
        # defines and both readers inherit from, and the model's own refusal
        # of the backlog. Charged anyway: roughly half of what generate()
        # refuses, it refuses after the model has already answered.
        failed.append("concepts: %s" % exc)
        cost["model_calls"] += 1
        return finish()
    counts["concepts"] = len(written)
    cost["model_calls"] += 1

    # ---- score ------------------------------------------------------------
    try:
        context = score.load_context(
            patterns_path=patterns_file,
            backlog_path=Path(backlog_path) if backlog_path else None,
            queue_root=Path(queue_root) if queue_root else None,
            creative_root=Path(creative_root) if creative_root else None,
            evidence=evidence,
        )
        selection = score.select(written, context=context, client=client, top=top)
    except (ConfigError, OSError, ValueError) as exc:
        # The concepts are still reported: they cost a model call, and an
        # operator who has to re-run wants to see what was written before the
        # scorer refused it.
        failed.append("score: %s" % exc)
        return finish()
    cost["model_calls"] += selection.model_calls

    if len(selection.selected) < top:
        # Not a failure - the scorer refuses a concept that engine/gate.py
        # would hard-fail at the claims gate, and three eligible concepts is a
        # property of the week, not of this module. It is said out loud
        # because a week that files two jobs instead of three should not be
        # silent.
        skipped.append(
            "score: %d of %d concept(s) selected; the rest were below the cut "
            "or ineligible. research/selection.json carries every scorecard."
            % (len(selection.selected), top)
        )

    return finish(selection)


def main(argv: list[str] | None = None) -> int:
    """CLI: the weekly run, or a preflight of it.

    --json follows engine/discover.py: stdout carries exactly one document, so
    a caller can pipe it into a parser, and every human-facing line goes to
    stderr instead. Without --json the summary is the only output.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m engine.fanout",
        description="The weekly research run: discover, analyse, learn, "
                    "write concepts, and score them.",
    )
    parser.add_argument("--budget", type=int, default=discover.HOURLY_BUDGET_CALLS,
                        help="Ad Library calls this run may spend (default %d, "
                             "the reported hourly allowance; research.yml "
                             "passes less so a same-hour re-run still fits)"
                             % discover.HOURLY_BUDGET_CALLS)
    parser.add_argument("--max-ads", type=int, default=DEFAULT_MAX_ADS,
                        help="ads to analyse, best outlier ratio first (default "
                             "%d: two text batches of %d). One model call per "
                             "batch, plus one per hand-saved creative."
                             % (DEFAULT_MAX_ADS, analyse.BATCH_SIZE))
    parser.add_argument("--concepts", type=int, default=concepts.DEFAULT_N,
                        help="concepts to write in the one call (default %d)"
                             % concepts.DEFAULT_N)
    parser.add_argument("--select", type=int, default=score.TOP_N,
                        help="how many concepts to select (default %d)" % score.TOP_N)
    parser.add_argument("--days", type=int, default=None,
                        help="only ads delivered in the last N days "
                             "(ad_delivery_date_min); default is the whole archive")
    parser.add_argument("--origin", default=None, choices=list(corpus.ORIGINS),
                        help="learn from ads of this origin only")
    parser.add_argument("--seeds", default=None,
                        help="path to research/seeds.yaml (default %s)" % discover.SEEDS_PATH)
    parser.add_argument("--corpus", default=None,
                        help="corpus directory (default %s)" % corpus.DEFAULT_ROOT)
    parser.add_argument("--patterns", default=None,
                        help="patterns document (default %s)" % learn.DEFAULT_PATH)
    parser.add_argument("--backlog", default=None,
                        help="path to queue/backlog.md (default %s)" % backlog.DEFAULT_PATH)
    parser.add_argument("--queue", default=None,
                        help="queue root, read for what is already live (default %s)"
                             % score.DEFAULT_QUEUE)
    parser.add_argument("--media-root", default=None,
                        help="where hand-saved creatives are looked for "
                             "(default %s)" % analyse.MEDIA_ROOT)
    parser.add_argument("--out", default=None,
                        help="selection report (default %s)" % DEFAULT_REPORT)
    parser.add_argument("--dry-run", action="store_true",
                        help="check what a run would do and what it would cost; "
                             "makes no model call, no Ad Library call, needs no "
                             "token or key, and writes nothing")
    parser.add_argument("--json", action="store_true",
                        help="the report on stdout, the summary on stderr")
    args = parser.parse_args(argv)

    if args.dry_run:
        report = plan(
            seeds_path=args.seeds,
            corpus_root=args.corpus,
            patterns_path=args.patterns,
            backlog_path=args.backlog,
            media_root=args.media_root,
            budget=args.budget,
            max_ads=args.max_ads,
            n_concepts=args.concepts,
            top=args.select,
        )
    else:
        report = run(
            seeds_path=args.seeds,
            corpus_root=args.corpus,
            patterns_path=args.patterns,
            backlog_path=args.backlog,
            queue_root=args.queue,
            media_root=args.media_root,
            report_path=args.out,
            budget=args.budget,
            days=args.days,
            max_ads=args.max_ads,
            n_concepts=args.concepts,
            top=args.select,
            origin=args.origin,
        )

    print(report.summary(), file=sys.stderr if args.json else sys.stdout)
    if args.json:
        sys.stdout.write(learn.dumps(report.as_dict()))

    # Nonzero means "a stage could not run", NOT "nothing was produced". What
    # the run did produce is on disk and in the report either way, which is why
    # research.yml commits before it reads this.
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
