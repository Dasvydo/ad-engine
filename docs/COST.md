# Cost

The invariant: the research loop in this repository runs at **$0.00/month**.
Not "cheap" - zero. Every service it touches is on a free tier, no account has
a card attached, and the failure mode of every limit below is a 429, a 613, a
403 or a stopped run, never an invoice.

**One line is outside that invariant by definition: the ad spend itself.**
Discovering, analysing, counting, writing, gating, approving and measuring cost
nothing. Running the ad costs whatever the campaign budget says. Nothing in
this design requires an ad to run for the research half to work - phases A
through C of `docs/AD-RESEARCH-SCOPE.md` §7 need no ad account, no pixel and no
spend - and the one step that can spend money is a human typing a budget into
Ads Manager after tapping `go` twice. It is not a research cost and it is not
in the ledger.

This file is the budget. **Settings > Billing and plans > Plans and usage is
the authority.** If the two disagree, the billing page is right and this file
is stale - correct it here. The ledger below is
`docs/AD-RESEARCH-SCOPE.md` §5 with the modules that actually exist filled in.

One number makes the whole thing enforceable: **GitHub's default spending limit
is $0.** Leave it there. With it at $0 an Actions overage stops runs instead of
billing for them, which is the difference between a claim and a guarantee.

Cadence assumed throughout: the crons as they ship - `measure.yml` 05:00
Monday, `research.yml` 06:00 Monday, `propose.yml` 09:00 Monday and Thursday -
so **one research sweep and two propose runs a week**, with `build.yml`,
`launch.yml` and `reject.yml` firing only when a human taps a label.

## Measured or arithmetic

Every row says which it is, because the difference decides what to do when a
number is wrong. There is exactly one measured allowance in this file, and it
was measured in the sibling repository:

- **Measured** - somebody hit the limit and read the error. Only the Gemini
  row, and it was measured in `reel-engine` from the 429 that killed its
  propose run 26.
- **Arithmetic** - a published (or widely reported) allowance with this
  repository's own call counts divided into it. Every call count below is
  either pinned by a test or printed by `--dry-run`, so it is arithmetic on
  code rather than on intent.
- **Estimate** - a guess with nothing behind it yet. The Actions minutes row,
  and it says so twice.

**Nothing in this repository has ever made a live Ad Library call or a live
insights call.** Every test injects a transport and no test needs a token. The
first live run is the first proof of both, and that is a `docs/SECRETS.md`
problem before it is a cost one.

## The ledger

| Surface | Free allowance | Load, weekly | Measured or arithmetic | If it is ever exceeded |
| --- | --- | --- | --- | --- |
| **Meta Ad Library API** (`ads_archive`) | **~200 calls per hour per token.** Reported by every secondary guide; Meta's reference names the error code (613) and not the number. Free - there is no paid tier to overspend into | **6 to 12 calls a sweep** with `research/seeds.yaml` as it ships: two seeded pages go in ONE `search_page_ids` call (up to 10 ids per call) and five queries are one call each, so 6 searches, each paginated to at most `DEFAULT_MAX_PAGES = 2`. `research.yml` passes `--budget 150`, not the module default of 200, so a sweep cannot eat a whole hour's allowance and leave nothing for a re-run. Measure adds 0 to this row - it is a different endpoint on the same token | **Arithmetic**, on `engine/discover.py`'s own `plan()`. `python -m engine.fanout --dry-run` prints the spread for the seed file as it stands, with no token and no socket, and `tests/test_fanout.py` pins `searches == 6` and `ad_library_calls == 12` against the committed seeds. Never called live | Error 613, never a charge. `Quota(150)` is charged **before** the socket opens and refuses the call it cannot afford, carrying `needed`, `remaining` and `budget` in the message. Seeding a page that runs no ads in DK or LT is the way this row grows for nothing: a page that returns nothing costs a call every week |
| **Marketing API insights** (our own ad account) | Free. Rate-limited per ad account by Meta's business-use-case formula rather than a flat number, so there is no figure to have headroom against | **1 call per pinned ad id, once a week. 0 with nothing launched**, which is the state today - `queue/launched/` is empty. `engine/measure.py` reads `/{ad_id}/insights` one ad at a time because the ad id is the whole lookup; the batched account-level form is a second URL shape nobody has verified, and it is deliberately not built | **Arithmetic** on the module and the cron. `engine/measure.py` has never run against a live token | HTTP 429 or an error body, never a charge. Not retried - the next Monday reads the same numbers. `Quota(200)` is charged before the socket here too. The rate-limit codes the module names are 4, 17, 32, 613 and 80004 |
| **Gemini API** (AI Studio key, free tier) | **MEASURED, in `reel-engine`, from the 429 that killed its propose run 26: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue: 20`. Twenty requests a DAY, per model, per project.** Read the quota id: the 20 is counted per MODEL, which is why `engine/model.py` pins two - `MODEL_FLASH = gemini-3.5-flash` judges and `MODEL_WRITE = gemini-3.6-flash` writes - giving 20 + 20 rather than 20 shared. No billing is possible without enabling it | **Research sweep: up to 4 calls, all on `gemini-3.6-flash`** - at most 2 analysis batches (`--max-ads 24` at `BATCH_SIZE = 12`), 1 concepts call whatever the concept count, 1 editorial scoring call across the whole batch - **plus 1 per hand-saved creative** among the ads it chose, because a file is watched one at a time. **Propose run: 2 calls per attempt per segment**, one write on `gemini-3.6-flash` and one editorial gate on `gemini-3.5-flash`; `propose.yml` passes `--retries 2`, so up to 3 attempts, and `--from-selection` takes the 3 concepts the sweep selected: **up to 9 and 9**. A Monday that does both is **up to 13 of 20 on the writer and up to 9 of 20 on the judge**. Zero calls, forever, from `engine/learn.py`, `engine/corpus.py`, `engine/measure.py`, `engine/feedback.py`, `engine/backlog.py` and `engine/approval.py`; the first two of those are AST-proved | **Arithmetic** on the batch size, the retry count and `TOP_N = 3`, against a measured allowance. Every figure is a ceiling: a batch of twelve ads is one call, a concepts run is one call whatever N, and a segment that passes the gate first time spends 2 and not 6 | 429, never a charge, and it resets on its own at midnight Pacific. **A 429 is not retried and must not be**: `engine/model.py`'s ladder covers 408 and the 5xx family, where waiting helps, and deliberately excludes the quota, where no wait inside a run clears a daily counter. `engine/propose.py` writes its id file in a `finally` so a quota death mid-run does not discard the segments that already passed. If the two loops ever collide on one Monday, **this repository can take its own AI Studio key** - free, and it doubles the headroom rather than sharing 20 a day with `reel-engine`'s sweep (`docs/AD-RESEARCH-SCOPE.md` §8, decision 7) |
| **GitHub Actions minutes** (Linux, private repo) | 2,000 min/month | **~14 min a week of scheduled work, ~60 a month**: `research.yml` ~2m (no browser - nothing in this repository installs one except `build.yml`), `propose.yml` ~5m twice, `measure.yml` ~2m. On top of that, demand-driven and so not projectable from a cadence: `build.yml` ~8m per approved reel - it checks out `Dasvydo/reel-engine` as a sibling, installs it AND Chromium, and renders there - plus `launch.yml` and `reject.yml` at ~1m each, and `tests.yml` at ~2m a run (install plus a fully offline suite, no browser anywhere), once per push to a pull request and once per push to `main` | **ESTIMATE, and it cannot be anything else yet: not one of these workflows has run.** Every one of them stamps `JOB_STARTED` in its first step and appends the elapsed wall clock to `$GITHUB_STEP_SUMMARY` in its last under `if: always()`, so each replaces its own figure with a real number on its first run | It stops, it does not bill, while the spending limit is $0. Never move a job off `ubuntu-latest`: Windows bills 2x and macOS 10x against the same pool. Do not try to save the browser install in `build.yml` - it is the render. Do not add one anywhere else: `tests.yml`, `research.yml`, `propose.yml` and `measure.yml` each say in their own header that they need no browser, and `tests/test_workflows.py` holds them to it |
| **Actions artifact storage** | 500MB (shared with Packages on GitHub Free) | One MP4 (~12MB) and one still per built ad, at 14-day retention. At one approved ad a week that is ~24MB standing | **Arithmetic**, on `reel-engine`'s measured render sizes | Cut `retention-days` in `build.yml`, or delete artifacts by hand. The artifact only has to outlive the gap between the creative being shot and a human uploading it in Ads Manager |
| **GitHub API** via `GITHUB_TOKEN` | 1,000 requests/hour/repo | Tens per run, all of them through `gh` inside `engine/approval.py` | **Arithmetic** | Two orders of magnitude of room, and label-triggered jobs are serialised per issue by a `concurrency` group already. Back off in the module, not in a `run:` block |
| **Meta developer app** | Free. An app with the Ad Library API product added, and identity verification behind it | - | - | Nothing to exceed. The cost here is calendar time: identity verification takes one to three business days |
| **Ad spend** | **Not in this ledger.** | - | - | The only money in the design. It is a campaign decision behind a human tap, never a research cost, and every stage above works with it set to nothing |

## What the sweep actually costs, end to end

A default Monday, with the tree exactly as it ships:

```
05:00  measure.yml    0 insights calls (nothing launched), 0 model calls, ~2m
06:00  research.yml   6-12 Ad Library calls, up to 4 model calls, ~2m
09:00  propose.yml    up to 9 writer calls + up to 9 judge calls, ~5m
```

Two things make that smaller than it looks. **A candidate already in the corpus
is never analysed twice**, so the second sweep over unchanged seeds makes zero
analysis calls and the model row drops to 2. And **a segment that passes the
gate on its first attempt spends 2 model calls, not 6** - the retries are a
ceiling for the run where the editorial gate keeps refusing, not a plan.

Two things make it bigger. A hand-saved creative under `research/media/` is one
extra call each, because a file is watched one at a time. And a sweep that
discovers a lot of fresh ads spends up to `--max-ads / 12` analysis calls, with
`--max-ads` defaulting to 24.

## How the minutes get measured

`research.yml`, `propose.yml`, `build.yml`, `launch.yml`, `reject.yml` and
`measure.yml` each stamp `JOB_STARTED` in their first step and append the
elapsed wall clock to `$GITHUB_STEP_SUMMARY` in their last, under `if:
always()` so a failed run still reports what it spent. Open any run and the
summary says how long the job took.

`tests.yml` is deliberately not in that list. The stamp exists so a scheduled
job nobody watches leaves its own cost written down; a test run is opened by
whoever pushed, and GitHub already shows its duration on the run page.

Two things to know about reading it:

- **Billing rounds every job up to the whole minute.** A 3m07s job bills 4. Add
  up the billed figure, not the wall clock.
- **A failed run costs full price.** A `build.yml` run that dies after
  `playwright install` in the sibling checkout has already spent nearly all of
  its minutes, which is why the step is `always()` and not `success()`.

## The three things nobody has paid yet

Every allowance above is either published, widely reported, or measured next
door. What has **not** happened is a single live call, and three of the rows
are the ones to check on the first run:

1. **200 calls an hour** is the figure every guide reports and Meta's reference
   does not print. `Quota`'s budget is a parameter, so a measured figure
   replaces it in one line - `--budget` on `engine.fanout`, and the default in
   `engine/discover.py`.
2. **The insights rate limit is a formula, not a number.** Meta computes it per
   ad account from spend and activity. One call per launched ad per week will
   not come near it, and the module refuses to retry into it anyway.
3. **`INSIGHT_FIELDS` is unverified.** The field names in `engine/measure.py`
   carry a `TODO(integration): UNVERIFIED AGAINST A LIVE RESPONSE` block, and
   the first live run is `python -m engine.measure --dry-run --raw`: it calls
   the API, prints each row's raw insights object, and writes nothing. A wrong
   field name costs a call and a correction, not money.

## What would break $0.00 first

Ranked by likelihood, not by size:

1. **A Monday that runs both loops on one Gemini key.** `reel-engine`'s sweep
   and this one both fire on Monday morning against the same 20-a-day per
   model. Run 26 over there is what a collision looks like: the run dies
   halfway and takes finished work with it. The fix is free - a second AI
   Studio key, in this repository's own secret - and it is the first lever to
   pull.
2. **Seeding pages that run no EU ads.** Every seeded page costs a call every
   week whether or not it returns anything. The seed file's comments say to
   check that a page runs ads in some EU country before pasting its id in;
   this is the only way the Ad Library row grows for nothing.
3. **A paid "ad intelligence" service.** Products exist that sell exactly what
   the Ad Library gives away, plus the snapshot downloads this repository
   refuses to make. That is the bill this design is shaped to avoid: the
   creative is saved by hand or not at all.
4. **Artifact retention creeping up.** 14 days is enough to review a render and
   upload it. 90 is how `reel-engine` put ~470MB into artifacts nobody reads.
5. **A render loop in `build.yml`.** It is the only job that installs a
   browser, and the only one whose minutes are worth watching.

None of these bills silently. All of them start with someone deciding a limit
is inconvenient - except the ad spend, which is a decision somebody is supposed
to make.
