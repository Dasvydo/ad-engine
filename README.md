# ad-engine

Meta ads for DoviLoop. Audiences, creative, a gate that stops unverifiable
claims reaching a public ad — and a research loop that reads what the market is
already running, counts what repeats, and writes the next ad from that rather
than from taste.

Sibling to `reel-engine` and `outreach-engine`; all three work from the same
locked brief in `docs/ICP-BRIEF.md`.

```
audiences/<name>.json     who         targeting specs, ranked by priority
creative/<variant>.json   the words   hand-written ad copy, one per A/B arm
claims/evidence.json      the truth   what may be claimed, what may not, and
                                      which offers this business actually makes
research/                 evidence    seeds, the ad corpus, patterns, the weekly
                                      report, what our own ads did
queue/                    the state   the segment backlog and one JSON per ad
                                      job — its directory is its status
engine/                   the code    the research loop, the claims gate,
                                      approval, measure, feed-back
tools/                    the edges   backlog sync, a push that retries
docs/                     the why     scope, contracts, cost, secrets
```

---

## Quick start

```bash
pip install -r requirements.txt

python -m engine.cli plan                                  # audiences + blockers
python -m engine.cli check                                 # claims gate over creative
python -m engine.cli audience ../outreach-engine/queue/acc-dk.csv --out queue/aud.csv

python -m engine.fanout --dry-run                          # the whole research plan,
                                                           # no key, no token, no socket
```

## The targeting problem, and the answer

This ICP is **~700–800 firms**. Meta cannot target "Danish accounting firms with
10+ staff" — that targeting does not exist — and a 750-company audience is far
below what its optimiser needs.

**So stop asking Meta to do the targeting.** `outreach-engine` already produces
the exact list. Upload it hashed as a Custom Audience and Meta becomes
account-based air cover over outreach, not a prospecting channel:

> ~750 firms × 2–3 contacts ≈ **2,000 people**, comfortably over Meta's 1,000
> minimum — but only with both countries and all three verticals combined. A
> single-vertical slice will under-deliver.

Audiences are ranked accordingly: `outreach-list` (1), `site-retargeting` (2),
`broad-interest` (3, kept for practice rather than results).

All PII is SHA-256 hashed after normalisation, per Meta's spec, so the raw list
never leaves this machine.

## Research: where an ad concept comes from

A hook is not invented here. It is taken from ads that strangers are **still
paying to run**, and every concept names the patterns — and through them the
ads — it was built from. "Why this hook" has an answer with days-running under
it.

Seven stages and the hand-edited seed file that starts them, all upstream of
the backlog:

```
research/seeds.yaml   the manual half   page ids, keyword searches, countries
engine/discover.py    candidates        seeds + the Meta Ad Library API
engine/analyse.py     one call a BATCH  twelve ads -> twelve corpus records
engine/corpus.py      the store         research/corpus/meta-ad-<id>.json
engine/learn.py       patterns          the corpus -> research/patterns.json
engine/concepts.py    12 concepts       patterns + queue/backlog.md
engine/score.py       the best 3        a scorecard for every concept
engine/fanout.py      all of the above  -> research/selection.json
```

**Discovery.** The Ad Library API is free, documented, and rate-limited in
public — about 200 calls an hour per token, which every guide reports and
Meta's reference does not print. So the budget is a correctness property rather
than a nicety: a `Quota` ledger is charged **before** the socket opens and a
call it cannot afford is refused instead of sent, carrying what it needed and
what was left. Two seeded pages go in one `search_page_ids` call, each keyword
query is one call, and `research/seeds.yaml` is where the bill is decided.

**A competitor is reached by page id, never by searching its name.** Searching
`Fyxer` across five countries returned 2,642 ads and not one of theirs: keyword
search matches creative *text*, and a company's own name is rarely in its copy.
The same lesson `reel-engine`'s seed file already records for YouTube channels.

**There is no view count here, so "best performing" is re-pointed at what the
archive does expose.** Longevity is primary — an ad still running after eight
weeks is the one number in the archive that an advertiser's own money voted on.
Reach per day is the numerator, and `outlier_ratio` is that over the **median
of the OTHER ads from the same page in the same run**, so a page that reaches
50k with everything it runs has no outliers, and the page whose median is 3k
and whose one ad did 60k has something worth reading. `variants` — several ads
from one page sharing a first line — is a page telling you which hook it is
scaling.

**Analysis, batched.** An ad's copy is a few hundred characters, and a batch of
things that only have to be *read* is one call. So twelve ads go into **one**
model call and come back as twelve records keyed by id, with a per-ad
`{"refuse": ...}` escape. A reply short an id, or truncated at `max_tokens`,
raises rather than returning what arrived: half a batch would be counted
downstream as evidence. That is what makes a research week ~2 model calls
instead of ~24, against a free tier of 20 a day per model.

What it extracts is how the ad is **built**, not what it is about: the hook and
its device, the structure as an ordered label list, the offer, the proof type,
the CTA, the objections the copy answers, the word count. Those are the
mechanics a writer reuses against a different product.

**The creative is never fetched.** `ad_snapshot_url` is a rendered page, not a
download. If a concept needs the video's mechanics, an operator opens the
snapshot in a browser and saves the file by hand into
`research/media/fb-<id>.mp4`, and only then does that ad get its own call with
the file attached. There is no code path that fetches one and no place to add
one: `tests/test_analyse.py` AST-parses the module, forbids every transport
import, and asserts the source contains no `snapshot_url` at all. This is
`reel-engine`'s Instagram seam, byte for byte.

**The corpus.** One committed JSON file per analysed ad, sorted keys, trailing
newline. A few hundred records accumulating a handful a week is a directory,
not a database, and committing them makes git history the audit log: a bad
analysis is undone by reverting a commit. It also outlives the archive — Meta
keeps a commercial EU ad for about twelve months after its last impression, and
the corpus does not forget. Validation refuses rather than repairs.

**Learning.** The corpus becomes `research/patterns.json` with **zero model
calls**; `tests/test_learn.py` AST-parses the module to prove it cannot reach
one. A pattern is a count, not an opinion: one repeated device, the corpus ids
it was read off, and the median days-running and reach of those ads. Fewer than
two supporters is an anecdote and is dropped. `generated_at` is the newest
`fetched_at` in the corpus rather than the clock, so regenerating from an
unchanged corpus produces the same bytes instead of a weekly diff that says
nothing changed.

Nine kinds are counted: hook device, copy length band, structure shape and
section, CTA, offer, proof, objection, longevity band — and `ctr`, which only
our own ads can supply. That last one is why this loop is better than the reel
loop it was copied from: a competitor's ad contributes longevity; our own ad
contributes a real click-through rate, and a hook device that appears in three
long-running competitor ads *and* in our own best-CTR ad is the strongest
citation this system can write.

**Concepts.** 12 of them, from the patterns and `queue/backlog.md`, in **one**
model call. A call per concept would spend twelve times the quota to buy
something worse — a model cannot avoid repeating itself across calls it cannot
see. Two rules are enforced here rather than left to review: every concept
cites a pattern id that exists in the file it was given, and names a segment id
from the backlog. An unknown citation raises instead of being dropped, because
a concept that quietly loses its citation looks identical to one that never had
a claim to make. A concept also names its **placement** and its **offer**, and
the offer must be one `claims/evidence.json` marks verified.

`docs/ICP-BRIEF.md` is never opened by any of this and nothing from it reaches a
prompt — asserted three ways in `tests/test_concepts.py` and again in
`tests/test_write.py`. A model sees a segment's trade, its three recurring
questions, and its note.

**Scoring.** Five dimensions. Four are measured off files already in the tree
and cost nothing; one is judged, and the whole batch's judgement is bought with
a single model call.

```
pattern evidence      0.30   n and median_days_running of every pattern it cites
ICP fit               0.25   the segment is a ranked row in queue/backlog.md,
                             and how many of its three tags read as lookups
novelty               0.15   wording shared with a live job in queue/, or with
                             a hand-written arm in creative/
claims survivability  0.10   a number in the hook that claims/evidence.json
                             does not attest                           GATE
editorial             0.20   the one model call, across the whole batch
```

0.80 of the total is measured evidence and 0.20 is the model's taste, so taste
cannot outvote the evidence. Claims survivability is a **gate, not a weight**: a
concept needing an unattested number cannot be selected whatever else it
scored, because `engine/gate.py` would refuse that ad anyway. The three winners
are spread across **segments first and placements second**, so three winners
are three different trades and, where the field allows, not three Reels.

Every concept gets a scorecard with the sentence that explains each score, and
the whole thing is written to `research/selection.json` on every live run —
including a failed one. A selection nobody can audit is an oracle, and an
oracle cannot be argued with when it is wrong.

```bash
python -m engine.fanout --dry-run              # the plan and the call count; writes nothing
python -m engine.fanout --budget 150           # the weekly sweep, all seven stages
python -m engine.discover --days 30 --json     # discovery on its own
python -m engine.learn                         # -> research/patterns.json
python -m engine.learn --stdout                # what it would write
```

`engine/analyse.py`, `engine/concepts.py`, `engine/score.py` and
`engine/write.py` have no argument parser of their own. They are library calls,
so the step that chains them stays one place rather than five.
`docs/SECRETS.md` has the keys and `docs/COST.md` prices every call.

### Seeds: the one manual step

`research/seeds.yaml` is edited by hand and committed, so git history is the
record of what the engine was told to watch, and when.

```
countries:   the default ad_reached_countries — DK and LT. The Ad Library only
             returns a commercial ad if it reached an EU country, which is the
             whole basis of the plan
pages:       who we watch, by Facebook PAGE ID, each competitor | icp-adjacent.
             A page may carry its own countries: a UK competitor that never
             reaches DK is invisible under the default
queries:     keyword searches in the market's own words, with the language they
             run in so a Danish word is not matched inside a Swedish ad
own:         OUR page and ad account. Ships blank
```

It ships with two Danish accounting pages seeded — both seen live in this
session's probe — and both competitor rows **commented out with blank ids on
purpose**: a page id has to be read out of the Ad Library UI by hand, and a
wrong one reads somebody else's ads while costing a call every week. A dry run
says so as a skip, not a failure.

## The claims gate

**Ads make public factual assertions. This repo refuses to ship ones nothing
backs.** `claims/evidence.json` records what may be claimed; `engine/gate.py`
scans copy for measurable assertions and blocks any that aren't verified.

Currently blocked, deliberately:

| Claim | Why |
|---|---|
| Any time-saving number | No customer outcome exists. The pricing page's "10 hours" is a model, not an observation. |
| "Trusted by N firms", logos, testimonials | Zero closed customers as of 2026-08-31. |
| Any percentage | Nothing has been measured. |

Currently allowed, because each is a verifiable product fact: never auto-sends ·
never leaves Outlook · EU-hosted · answers from the firm's own documents · a
voice profile per person.

This is not pedantry. An investor specifically warned that a public measurable
promise with nothing behind it is real exposure for a company with no liability
cap and no insurance.

**There is now one claims policy across both repositories, and it is
`reel-engine`'s.** The five named regexes above still run, unchanged, and so
does the number policy ported from `reel-engine/reel/build.py`: a number is a
digit **or a number word** — "one", "half", "twice", "dozen" — and the only
thing that clears one is an attestation in `claims/evidence.json`, keyed by a
hash of the field name and the exact spoken text. A failing gate prints the key
to add. The attestations section is empty on purpose: no ad has yet needed a
number.

The gate has two layers and they run in that order:

```
structural   shape, {en,da,lt} maps, character limits, the CTA and placement
             enums, the offer looked up in the offers table, the five claim
             regexes, unattested numbers, refused constructions    0 model calls
editorial    four rules, one call, fail closed on an unreadable verdict
```

Rule 2 of the rubric — *the offer named in the copy is one this business
actually makes* — is a **lookup, not a judgement**. `claims/evidence.json`
carries an offers table (`guarantee`, `design_partner` and `demo` verified;
`free_trial` UNVERIFIED, because no self-serve trial exists), and three
different modules refuse an unverified offer before a model is ever asked. The
other three rules — no unsupportable promise, the hook names a moment in that
trade's week rather than a generic complaint, nothing claims a customer or logo
or testimonial or measured outcome exists — are the one editorial call.

A structural failure parks the exact draft in `queue/rejected/`, so the printed
`evidence_key` still hashes the same text and you can attest the number or fix
the copy and re-gate it:

```bash
python -m engine.propose --regate queue/rejected/<segment>.json
```

## Creative

Two variants, matching outreach-engine's arms so both channels test the same
variable:

| Variant | Framing |
|---|---|
| `capacity` | More clients, same team — **recommended, untested** |
| `hours` | Stop re-typing the same reply — **control** |

The `hours` arm deliberately carries **no number**, so it tests the framing
rather than smuggling in a metric the gate would block.

Video and stills come from `reel-engine` — reuse those renders rather than
commissioning new creative. `creative/example-job.json` is the worked example
the writer imitates: a complete, gate-passing ad job for a segment deliberately
**off** the backlog, so nothing can mistake it for a live one.

## Propose, approve, build, launch

An ad job **is** a JSON file, and its directory is its status. Git history is
the audit log.

```
queue/
  backlog.md         ranked segments — a COPY of reel-engine's table
  proposed/*.json    copy gated, awaiting approval        label stage:copy
  built/*.json       creative shot, awaiting launch       label stage:creative
  launched/*.json    live in Ads Manager, ad ids pinned
  rejected/*.json    parked drafts awaiting a fix or an attestation
```

A segment is used when it has a job in one of the three live stages. A parked
draft in `rejected/` deliberately does **not** count, so its segment stays in
the backlog and gets picked again.

Two files travel with a job and move with it: `<segment>.jpg`, the still
`reel-engine` shot, and `<segment>.reel.json`, the selection document
`reel-engine`'s own `load_selection` accepts — so the build step hands the
sibling repository a concept rather than a prose brief.

**The backlog is a copy, on purpose.** The ICP is one ranked list and
`reel-engine` owns it, but reading `../reel-engine/queue/backlog.md` at run
time would mean the weekly research cron needs a second repository's token to
read one markdown table. So the rows are copied and `tools/sync_backlog.py`
keeps them honest from a checkout that has both:

```bash
python tools/sync_backlog.py            # rewrite the rows from ../reel-engine
python tools/sync_backlog.py --check    # exit 1 and print the diff if they drift
```

Never hand-edit the rows on this side. Edit them over there and sync.

To take the next unused segment, write the ad, and put it through the gate:

```bash
python -m engine.propose                        # the next unused backlog row
python -m engine.propose --from-selection       # the concepts the sweep picked
python -m engine.propose --segment payroll-bureaus --placement static-1x1
```

An editorial failure is retried once with the gate's own reasons as feedback,
then it stops and asks you. A structural failure parks the draft and does not
retry — nothing a second attempt does will attest a number.

### The taps

```
propose.yml opens one issue per proposed segment      labels: stage:copy
  you add  go   -> build.yml shoots the creative in reel-engine, commits the
                   still beside the job, moves it to queue/built/, comments the
                   Ads Manager steps, swaps the label to stage:creative
  you add  no   -> reject.yml drops the job; the segment returns to the backlog
```

`issues.labeled` is a native trigger, so **approving is the trigger** — no
bridge, no webhook, no bot token. The stage labels are a human-readable mirror
of the job's directory and are never the authority on stage: the two taps look
identical in the webhook payload, and a workflow that finds the label and the
directory disagreeing stops rather than guessing.

**The last step is not a label, and that is deliberate.** Uploading the ad is a
human in Ads Manager, and what comes back is an **ad id** — which a label
cannot carry. So the job is pinned by running the `launch` workflow with the id
you just copied:

```bash
gh workflow run launch.yml -f segment=payroll-bureaus -f ad_id=<AD ID> -f issue=<N>
```

That writes `ads: {"<ad id>": {...}}` and `launched_at` into the job, moves it
to `queue/launched/` and closes the issue. **The guess is made once, by a
human**, and every later measurement is an exact lookup rather than a match — a
wrong pin looks correct forever, which is why nothing here guesses one.

`engine/approval.py` is the seam: a pure decision half and a six-method
transport protocol, GitHub issues today. Secrets and the four labels you have
to create are in `docs/SECRETS.md`.

## Measure, and feed the results back

The loop closes here. What a launched ad actually did is read back off **our
own** ad account, and then becomes evidence for next week's concepts — in the
same corpus, under the same schema, as the strangers' ads research collects.

```
engine/measure.py    what ours did      queue/launched/ + the Marketing API
                                        insights edge -> research/measurements.json
engine/feedback.py   ours as evidence   a measured ad -> a corpus record,
                                        origin "own", no model call
```

**Measure.** One call per pinned ad id, once a week, against the insights edge:
impressions, reach, clicks, CTR, CPC, CPM, spend, the video quartiles and the
actions. Hook rate (3-second plays over impressions) and hold rate (thruplays
over 3-second plays) are derived in the module and say so in the document.
**Absent is `null`, never 0** — a rate computed off a zero denominator is not a
zero, and `engine/learn.py` takes medians over what it is handed. Nothing
launched costs nothing, and a run that measured nothing leaves a good document
exactly as it was.

**Two Meta reads, one token, and they cannot be confused in code.** Discovery
reads `ads_archive` for strangers' ads. Measurement reads `/{ad_id}/insights`
for ours, scoped by `ads_read` on our own ad account — and by an ad id a human
typed. Neither has a spelling for the other's job.

**Feed results back.** A launched, measured ad becomes a corpus record with
`origin: "own"` and `model: "none (authored)"`, and `engine/learn.py` counts it
into patterns exactly as it counts a stranger's ad. **It makes zero model
calls, and that is the whole point.** We wrote this copy: the hook, the
structure, the offer and the CTA are in `queue/launched/<segment>.json`
verbatim. Asking a model to read our own ad would be paying to rediscover our
own job file, and the answer would be less exact than the file it was guessing
at. `tests/test_feedback.py` AST-parses the module to prove it cannot reach a
model or the network, and what is derived rather than measured says so under
`analysis.derived_from`.

An ad with zero or missing impressions is **skipped by name, not written**: a
record measured at zero is indistinguishable from one nobody measured, and it
would drag down every median it supported with nothing in the file to say why.
It becomes a record the week it has real numbers.

```bash
python -m engine.oauth --status      # is the token set, and how much of 60 days is left
python -m engine.measure --dry-run   # calls the API, prints the document, writes nothing
python -m engine.measure --dry-run --raw   # plus Meta's raw insights object, for run one
python -m engine.feedback --dry-run  # what it would write into the corpus
python -m engine.feedback            # -> research/corpus/meta-ad-fb-own-*.json
```

`measure.yml` runs both, 05:00 Monday, an hour before the research sweep that
consumes what they write. The order is not cosmetic.

## Known state

- **Meta pixel is not installed on doviloop.dev.** `site-retargeting` cannot be
  built until it is, and it needs to start collecting well before ads run or
  there will be nobody in it. **Do this first — it costs nothing and it is the
  only audience that compounds.**
- **Revenue is switched off** in the product (`TEST_MODE` plus two `BYPASS_*`
  flags). Traffic can arrive and convert to a conversation, but not to a payment.
- Danish and Lithuanian creative is drafted, **not native-checked**. Every `da`
  and `lt` field the writer produces says `NEEDS_NATIVE_PROOFREAD` and the model
  never gets to declare copy native. That is a gate in the approval flow.

## Status

**In the tree, and never yet run against a live credential.** All of it — the
seven research stages, the gate's new layers, the queue, the four
label-and-dispatch workflows, measure and feed-back. Every test is offline,
every transport and every model client is injected, and no test needs a key or
a token; `tests.yml` runs the whole suite with `contents: read` and no browser
anywhere.

What that means concretely, today:

- **No call has ever been made to `ads_archive`.** `research/corpus/` holds
  only its `.gitkeep` and `research/patterns.json` has never been written.
- **No call has ever been made to the insights edge.** `queue/launched/` is
  empty and `research/measurements.json` does not exist. `INSIGHT_FIELDS` in
  `engine/measure.py` carries a `TODO(integration): UNVERIFIED AGAINST A LIVE
  RESPONSE` block for exactly this: the field names are the Marketing API
  reference as remembered, and `python -m engine.measure --dry-run --raw` is
  what checks them.
- **`META_ACCESS_TOKEN` does not exist yet**, and identity verification at
  `facebook.com/ID` — a government id, one to three business days — is what
  gates it. That is the long pole for the whole loop.
- **The 60-day token lifetime is an assumption**, carried over from
  `reel-engine`'s Instagram experience. It is wrong in the safe direction: it
  refuses a live token on day 61 rather than letting a dead one through.
- **Meta's Ad Library API terms have not been read**, and what a corpus record
  may store is still open on them (`docs/AD-RESEARCH-SCOPE.md` §8, decision 6).
  Read them before the first record is committed.

**What the first live run proves,** in order: that the Ad Library returns the
field set §2.2 of the scope document could not confirm; that 200 calls an hour
is the real budget; that a Danish keyword search over DK returns ICP-adjacent
pages worth a baseline; and — later, once one ad has run — that the insights
field names are right. `docs/SECRETS.md`'s *before you trust the cron* is the
order to check it in, and `docs/COST.md` is the ledger the whole thing is
budgeted inside.

`docs/AD-RESEARCH-SCOPE.md` is why each stage exists and what it could not
verify; `docs/CONTRACTS.md` is exactly what each one reads and writes.

## Why this runs at all

The brief argues ads are the weakest of the three channels for this ICP, and
that stands. It runs anyway, deliberately: the operator wants the reps —
pixel, audiences, creative testing, attribution — and that is a legitimate
reason. **Judge it on what it teaches, not on pipeline.** Cold outreach is where
the pipeline should come from.
