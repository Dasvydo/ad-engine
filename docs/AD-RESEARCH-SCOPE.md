# Scope: the reel research loop, re-applied to Meta ads

Written 2026-09-18. Nothing in this document is built. It records what
`reel-engine` actually does today, what the Meta Ad Library actually returns,
and how the one maps onto the other - stage by stage, with the seams named and
the manual steps counted. Where a number was measured it says so; where it is
arithmetic or a secondary source it says that instead.

---

## 0. The answer in one paragraph

`reel-engine` is a loop of seven committed files. Discovery finds videos that
beat their own channel, one model call analyses each into a corpus record,
counting the corpus (no model) yields patterns, one call writes twelve concepts
against those patterns, one call scores them, the winners are scripted and
gated, a human taps `go` twice, and what shipped is measured and fed back in as
evidence. Every stage hands the next a file, every number traces back to a
video with a real view count, and the whole thing runs at $0.00 inside
published free allowances.

**The ads version keeps every one of those stages and changes four things.**
The discovery transport (YouTube Data API becomes the Ad Library API - free,
documented, rate-limited in public, so it sits where YouTube sits and not where
Instagram sits). The definition of "performing" (a stranger's ad has no view
count; it has how long it has been running, how far it reached in the EU and
how many variants its page is scaling - and our own ads have real CTR, which is
better evidence than anything the reel loop can read). The analysis schema (an
ad is copy plus a creative, not a 25-second timeline). And the writer's output
(ad copy plus a `reel-engine` content JSON, rendered by `reel-engine`
unchanged). The corpus, the pattern counting, the one-call concepts, the
five-dimension score, the claims gate, the two-tap approval and the cost ledger
carry over in shape, mostly by copying modules across.

**Home: this repository.** `ad-engine` already declares itself the sibling that
reuses `reel-engine`'s renders, its claims gate already "mirrors reel-engine's
claims discipline", and its README already reaches across to a sibling checkout
by relative path. Putting the research half here keeps `reel-engine`'s strict
corpus schema untouched and keeps ad-specific transports (Ad Library, Marketing
API) out of a repository whose tests assert it has no Meta transport at all.

---

## 1. What is actually built in `reel-engine`

Read off the tree at `388dab9` (merge of PR #11), not off its README. About
1,300 tests, every one offline; two model ids pinned; five scheduled workflows.

### 1.1 The stages

| Stage | Module | In -> out | Cost per run | The rule that makes it honest |
|---|---|---|---|---|
| **Seeds** | `research/seeds.yaml` | hand-edited, committed | 0 | Git history is the record of what the engine was told to watch. Competitors are reached by channel **id**, never by searching their name. |
| **Discover** | `engine/discover.py` | seeds -> candidate records (in memory) | 602-607 YouTube units (6 searches at 100 + hydration at 1) | A `Quota` ledger is charged **before** the socket opens and refuses what it cannot afford. `outlier_ratio` = a video's views / median of the OTHER videos from the same channel in the same run; searches ordered by date so the baseline is a channel's ordinary output. Instagram has **no transport**: a test explodes every socket and runs the Instagram path to completion. |
| **Analyse** | `engine/analyse.py` + `engine/model.py` | one candidate -> one corpus record | 1 model call per video | The video is never downloaded; the YouTube URL is attached as a real media part. A local file (a hand-saved Reel) is inlined up to 20MB. A model that cannot watch returns `{"refuse": ...}` and the candidate is skipped by name. A half-record raises rather than being written. |
| **Corpus** | `engine/corpus.py` | record -> `research/corpus/<platform>-<id>.json` | 0 | Sorted keys, trailing newline, strict top level, permissive `analysis`. A duplicate id raises. A directory, not a database; reverting a commit undoes a bad analysis. |
| **Learn** | `engine/learn.py` | corpus -> `research/patterns.json` | **0 model calls**, AST-proved | A pattern is a count: one repeated device, the ids it was read off, their median views. Fewer than 2 supporters is an anecdote and is dropped. `generated_at` is the newest `fetched_at`, not the clock, so an unchanged corpus rewrites the same bytes. A null is never a zero. |
| **Concepts** | `engine/concepts.py` | patterns + backlog -> 12 concepts | **1** model call | Every concept cites a pattern id that exists and a segment id from the backlog; an unknown citation raises rather than being dropped. `docs/ICP-BRIEF.md` never reaches a prompt. |
| **Score** | `engine/score.py` | 12 concepts -> scorecards + best 3 | **1** model call | Five dimensions: pattern evidence 0.30, ICP fit 0.25, novelty 0.15, claims survivability 0.10 (a **gate**, not a weight), editorial 0.20. Measured is 0.80, judged is 0.20, so taste cannot outvote evidence. Every concept gets a scorecard with a sentence per score. Winners are spread across segments first. |
| **Fan-out** | `engine/fanout.py` | the six above, in order, with a budget and a report | up to 14 calls (12 videos + 2) | Orchestrates only. Never watches a video twice. Nothing thin overwrites something good: a corpus too small for `MIN_SUPPORT` leaves `patterns.json` alone. `research/selection.json` is written on every live run, including a failed one. |
| **Write** | `engine/script.py` | segment (+ selected concept) -> content JSON | 1 call per attempt | The guide is sent verbatim. A hook carrying an unattested number is **withheld** from the prompt rather than softened inside it. Refused phrasings (latency and accuracy promises) are declared once and both rendered into the brief and asserted against every worked example. |
| **Gate** | `engine/gate.py` + `reel/build.py` | draft -> pass / structural fail / editorial fail | 0 then 1 call | Structural and claims run first and cost nothing; the editorial rubric is one call, judged against the template's own declared argument; fail closed on an unreadable verdict. A structural failure parks the exact text in `queue/rejected/` so the printed `evidence_key` still hashes it. |
| **Propose** | `engine/propose.py` + `propose.yml` | selection -> `queue/proposed/<segment>.json` + still + one issue each | 09:00 Mon and Thu | Never overwrites a live job. A capacity spike is per call and the loop moves on; a daily quota is identical for every concept and aborts. Whatever proposed is committed **before** the job goes red. |
| **Approve** | `engine/approval.py` + `render.yml` / `publish.yml` / `reject.yml` | label `go`, twice | native `issues.labeled` trigger | The directory is the stage; the label is a mirror, never the authority. A pure decision half and a six-method transport protocol (GitHub issues today). |
| **Render** | `engine/cli.py`, `reel/build.py`, `engine/browser.py`, `engine/seek.js` | content JSON -> MP4 + still | ~8 Actions minutes | Deterministic frame seeking; pure ASCII, self-contained HTML; a number in a spoken field without an attestation in `claims/evidence.json` is a hard fail. Four templates: `reel-c` (9:16, default), `reel-s`, `reel-d` (9:16), `reel-b` (4:5). |
| **Publish** | `engine/publish.py`, `engine/copy.py`, `engine/media.py` | MP4 -> public media repo -> Buffer x3 | Buffer free plan, 3 of 3 channels used | Unverified against a live Buffer response, and says so in a `TODO(integration)` block. |
| **Measure** | `engine/measure.py`, `engine/ig_measure.py` | published jobs + Data API -> `research/measurements.json` | 3 units, then 1 once pinned | Matches once by string distance, pins the id into the job, refuses ambiguity in both directions. `published_at` is recorded because CI has no mtimes. |
| **Insights (tier 2)** | `engine/oauth.py`, `engine/insights.py` | rows -> `tier2` block (retention, reach, saves) | OAuth; optional | A tier 2 failure never costs a tier 1 number. Meta's 60-day token ages from a stored issue date: warns from day 40, refuses past 60, before opening a socket. |
| **Feedback** | `engine/feedback.py` | measured own reels -> corpus records, origin `own` | **0 model calls**, AST-proved | We wrote these reels; asking a model to watch them would pay to rediscover the content JSON. What is derived says so in the record. A zero-view reel is skipped, not written. |

Cadence: `measure.yml` 05:00 Monday, `research.yml` 06:00 Monday, `propose.yml`
09:00 Monday and Thursday, so what a reel did is evidence the same morning and
what the sweep selects is what a human taps `go` on three hours later.

### 1.2 The seven rules that *are* the infrastructure

These are what makes the loop trustworthy, and they are what has to survive the
port. Everything else is a module.

1. **Files, not conversation.** Each stage hands the next a committed JSON file
   with sorted keys, so git history is the audit log and a hook traces back
   through a concept, a pattern and a corpus record to a real number.
2. **Measured outranks judged.** Counting is free and honest; a model is asked
   only what counting cannot answer, and never to summarise its own output.
3. **One call per thing that has to be watched; one call per batch of things
   that only have to be read.** Twelve videos are twelve calls. Twelve concepts
   are one call, so they cannot repeat each other.
4. **Refuse rather than guess.** A blank id, an ambiguous match, an unattested
   number, a half-record: each is named and refused. A wrong pin looks correct
   forever.
5. **Where there is no free, documented source, the seam is manual and has no
   transport.** Instagram competitor numbers are typed in by a human. The test
   for it makes every socket explode.
6. **Nothing thin overwrites something good, and a skip is not a failure.**
   A quiet week leaves last week's patterns and selection in place.
7. **$0.00 is a correctness property.** A ledger is charged before the socket,
   the GitHub spending limit stays at $0, and `docs/COST.md` prices every call.

### 1.3 Where `ad-engine` stands today

Three modules and no loop. `engine/audience.py` hashes an outreach CSV into a
Custom Audience. `engine/gate.py` is a five-regex claims gate over
`claims/evidence.json`, whose format (claim id -> status, safe phrasings) is
**not** `reel-engine`'s (a hash of field and text -> kind, source, asOf).
`creative/{capacity,hours}.json` are two hand-written arms with
`NEEDS_NATIVE_PROOFREAD` in both Danish and Lithuanian. `audiences/*.json` are
three targeting specs, one blocked on the pixel. Eight tests. No research, no
corpus, no queue, no workflow, no approval, no measure. Its README already says
video and stills come from `reel-engine`.

---

## 2. What the Meta Ad Library actually gives you

### 2.1 Measured this session

This session holds a Meta MCP connector with an `ads_library_search` tool. Two
probes, both read-only, both against `ad_type=ALL`:

| Probe | Result | What it proves |
|---|---|---|
| `regnskab`, country DK, active | **509** active ads. Top five included `Balance - Your AI Powered Accountants` ("Se om vi kan gore dit regnskab bedre og billigere") and `GoSimple` ("Orneblik over dit regnskab. Hver eneste dag"). | Commercial, non-political ads reaching an EU country are in the archive under `ALL`. ICP-adjacent Danish advertisers are findable by a Danish keyword. |
| `Fyxer`, countries GB/DE/NL/DK/SE | 2,642 ads, none from Fyxer - "Jack & Jill - AI Recruiters" four times over with the same "Free to sign up" title. | Keyword search matches creative **text**, and a competitor's own name is rarely in its copy. **A competitor is reached by page id, not by searching its name** - the same lesson `research/seeds.yaml` already records for YouTube channels. Four identical ads from one page is also the first sighting of the `variants` signal below. |

The MCP returned eight fields per ad: `id`, `page_id`, `page_name`,
`ad_creative_link_title`, `ad_creation_time`, `ad_delivery_start_time`,
`ad_snapshot_url`, `currency`. That is a fixed subset, capped at 50 results, and
its own description forbids bulk extraction. **It is a hand tool for probing
and for finding page ids to seed. It is not the engine's transport**, which
has to run unattended from a cron with its own token.

### 2.2 Documented

The engine's transport is the Graph API endpoint `ads_archive`, read with
`urllib` behind one `_http` seam exactly as `engine/discover.py` reads YouTube.
From Meta's reference page for the endpoint and its `ArchivedAd` node, plus
three secondary guides where the reference is silent:

**Parameters.** `ad_reached_countries` is required (ISO-2 list). "Ads that did
not reach any location in the EU will only return if they are about social
issues, elections or politics" - so for DK and LT, `ad_type=ALL` returns every
commercial ad, which is the whole basis of this plan. `search_terms` (up to 100
characters, `KEYWORD_UNORDERED` or `KEYWORD_EXACT_PHRASE`), `search_page_ids`
(up to 10 page ids per call), `ad_active_status` (ACTIVE / INACTIVE / ALL),
`ad_delivery_date_min` / `max`, `media_type` (ALL / IMAGE / MEME / VIDEO /
NONE), `languages`, `publisher_platforms`. Paginated.

**Fields, by how sure this document is:**

| Certainty | Fields | Note |
|---|---|---|
| Documented for every ad | `id`, `page_id`, `page_name`, `ad_creation_time`, `ad_delivery_start_time`, `ad_delivery_stop_time`, `ad_snapshot_url`, `ad_creative_bodies`, `ad_creative_link_titles`, `ad_creative_link_descriptions`, `ad_creative_link_captions`, `publisher_platforms`, `languages` | `ad_delivery_stop_time` is absent on an ad still running. The creative lists carry one entry per card of a carousel. |
| Documented for EU delivery | `eu_total_reach`, `beneficiary_payers` | `eu_total_reach` is one number per ad, the only reach figure a commercial ad carries. |
| Reported by DSA guides, ambiguous in the reference | `target_ages`, `target_gender`, `target_locations`, `age_country_gender_reach_breakdown` | The first live call settles it. Nothing below depends on them. |
| **Political ads only - never for us** | `impressions`, `spend`, `estimated_audience_size`, `currency`, `bylines`, `demographic_distribution`, `delivery_by_region`, `total_reach_by_location` | The MCP's `currency` field is the exception that proves the point: it came back for commercial ads through the MCP, and the reference says political only. Do not build on it. |

**Three walls that shape the design:**

- **No performance metric exists for a commercial ad.** No spend, no
  impressions, no clicks, no likes, comments or shares. Section 2.3 is what
  "best performing" honestly means under that constraint.
- **The creative file is not in the API.** `ad_snapshot_url` is a rendered
  page, not a download, and Meta's page says individual creative "may be
  downloaded for analysis subject to its data-storage and platform terms".
  This document treats the snapshot the way `reel-engine` treats an Instagram
  Reel: a human opens it and saves the file by hand, and the engine has no
  code path that fetches it. Section 3.3.
- **Retention is about a year.** A commercial EU ad stays in the archive for
  roughly twelve months after its last impression (political ads: seven
  years). The corpus, being committed, outlives the archive - which is one
  more reason the corpus is a file per ad.

**Access.** Identity verification at `facebook.com/ID` (a government id; one to
three business days), a Meta developer app with the **Ad Library API** product
added, and an access token. Meta does not publish a fixed token lifetime for
this use; `reel-engine` already assumes 60 days for a Meta user token and
counts it out loud (`engine/oauth.py`), and this plan reuses that posture.
Rate limit: about **200 calls per hour per token** is the figure every guide
reports; Meta's reference names the error (code 613) and not the number.
Treated below as a budget to charge before the socket, exactly like YouTube's
10,000 units.

**Terms.** Meta's Ad Library API terms govern storage and reuse of what the
endpoint returns. Nobody in this session read them in full. Before the first
corpus record is committed, a human reads them and decides whether the record
holds the creative text verbatim or only what was derived from it (section
8, decision 6). The corpus is in a private repository either way.

### 2.3 What "best performing" can honestly mean

`reel-engine`'s outlier is not a popular video but one a channel's own audience
treated differently: views over the median of that channel's other videos in
the same run. There is no view count here, so the same idea is re-pointed at
what the archive does expose:

| Signal | Field arithmetic | Why it means anything |
|---|---|---|
| **Longevity** | `today - ad_delivery_start_time` for an active ad; `stop - start` for a finished one, in days | Advertisers kill what does not convert. An ad still running after eight weeks is the one number in the archive that an advertiser's own money has voted on. This is the primary signal. |
| **Reach** | `eu_total_reach`, and reach per day running | Reach is spend-correlated, and spend follows results. Weaker than longevity on its own (a launch can buy reach for a week), stronger combined with it. |
| **Variants** | count of ads from the same `page_id` whose first creative body or link title match, in the same run | A page running six versions of one hook is scaling it. Seen live in the Fyxer probe. |
| **Outlier ratio** | an ad's reach-per-day over the **median** of the OTHER ads from the same page in the same run | The reel loop's own definition, unchanged: a page that reaches 50k with every ad has no outliers; the page whose median is 3k and whose one ad did 60k has something worth reading. Needs the page's other ads, which `search_page_ids` returns in the same call. |

Two things this cannot do, said now so nobody expects them later. It cannot
rank ads across pages by absolute reach without rewarding whoever spends most;
the per-page median is what stops that. And it cannot see a click. **The only
CTR in this whole design is our own**, from our own ad account, in section
3.12 - and that is the strongest evidence the loop will ever hold, stronger
than anything the reel loop can read for a competitor.

---

## 3. The mapping, stage by stage

For each stage: what carries over verbatim, what changes, and what is decided
here rather than left to review. **The module names below are the ones that
were built**, updated from the `ads_`-prefixed names this document first
proposed - see the decisions block after section 8. The contracts sketched in
section 4 were settled in `docs/CONTRACTS.md`, which is the authority on what
each module reads and writes; section 4 is kept as the record of what was asked
for.

### 3.1 Seeds: `research/seeds.yaml`

Hand-edited and committed, like `reel-engine`'s own `research/seeds.yaml`.
Four blocks:

```
pages:      who we watch, by Facebook page id. origin competitor | icp-adjacent.
            The id is the number in the Ad Library UI's URL for that page, or
            the page_id the MCP probe returns - it is NOT the page name. A wrong
            id is caught for one call before anything is learned from it.
queries:    keyword searches, each with the countries and language it runs in.
            Danish and Lithuanian words for the market ("regnskab", "bogholder",
            "buhalteris", "apskaita"), English for the category ("AI email
            assistant"). A bare query is icp-adjacent, as on YouTube.
countries:  the default ad_reached_countries - DK and LT. A competitor page may
            be given its own list, because a US or UK competitor does not run
            in DK and will not appear at all unless the country it does run in
            is asked for.
own:        OUR page id and OUR ad account id. Ships blank, and blank is a
            valid state: engine/discover.py validates its shape at load and
            engine/feedback.py is its only reader, writing page_id "" into an
            own record rather than guessing. engine/measure.py never opens
            this file - the ad ids pinned into queue/launched/<segment>.json
            are what say which ads are ours.
```

Carried over: the loader's whole posture - validate everything at load, before
a call is spent; refuse an unknown origin; refuse a duplicate; name the fix in
every message.

### 3.2 Discover: `engine/discover.py`

Carried over verbatim in shape: the `Quota` class (budget 200, charged before
the socket, `QuotaExceededError` carrying the numbers), the single `_http`
seam, `transport=` injection so every test is offline, `candidate()` as the one
place the record shape is written, and `add_outlier_ratios()` grouped per page.

What changes:

- **One call per ten seeded pages** (`search_page_ids`), one call per query per
  country list, paginated only as far as the budget allows. A run over ten
  competitor pages and six queries is under twenty calls; the arithmetic is in
  section 5.
- **`ad_delivery_date_min`** set to the window (`--days`), because the run
  wants what a page is running now, not its archive. Inactive ads inside the
  window still matter: a finished ad has a measured `stop - start`.
- **Metrics are** `eu_total_reach`, `days_running`, `active`, `variants`,
  `media_type`, `publisher_platforms`, `languages`, `countries`. `variants` is
  computed here, once, over the run's own results per page.
- **`outlier_ratio`** is reach per day over the page's median reach per day.
  `NO_BASELINE` stays 0.0 for a page with no other ad in the run.
- **Id prefix** `fb-<library id>`; platform `meta-ad`.

Nothing here fetches a snapshot, and the test for it is `test_discover.py`'s
socket-explosion test, re-pointed: run the seeds-only path, then run a
discovery whose transport stub returns snapshot URLs, and assert no request was
ever made to `facebook.com/ads/library/?id=`.

### 3.3 Analyse: `engine/analyse.py`

Two paths, and the split is the design decision.

**Text path, batched.** An ad's copy is a few hundred characters. Twelve of
them fit in one prompt, and rule 3 in section 1.2 says a batch of things that
only have to be read is one call. So the default is **one model call per
batch** of up to N candidates (start at 12), returning one JSON object per ad,
keyed by id, with the same refusal shape (`{"refuse": ...}` per ad, not per
batch). A batch whose reply is short an id, or truncated, raises: a half-batch
would be counted as evidence. This alone cuts a research week from ~14 model
calls to ~3, against a free tier that is 20 a day per model - the single most
binding limit in `docs/COST.md`.

What the text path extracts is what a copywriter reuses against a different
product, not a summary: the **hook** (first sentence, word count, device label
from the same short vocabulary the reel prompt uses so patterns can be counted
across both corpora), the **structure** as an ordered label list with no
timings (`hook > problem > proof > offer > cta`), the **offer** (free trial,
demo, guarantee, price, none), the **proof** type (testimonial, number, logo,
none), the **CTA** (button type from the link caption, plus the ask in words),
the **objections** the copy answers, the **language** and whether the copy is
native or translated-sounding, and the **word count**.

**Media path, manual-seed only.** When a concept needs the video's mechanics -
the on-screen text, the cut rhythm, what the first two seconds show - the
operator opens `ad_snapshot_url` in a browser and saves the creative by hand to
`research/media/fb-<id>.mp4` (or `.jpg`). The existing `engine/model.py`
local-file part then inlines it, up to 20MB, and the reel prompt's video
mechanics are read on top of the text analysis. **There is no code path that
fetches a snapshot, and there is no place to add one** - this is the Instagram
seam, byte for byte, and the analysis prompt says in the record which path
produced it (`analysis.creative.kind`: `text-only` or `local-file`).

Carried over: `_first_json_object`, the refusal handling, `SkippedCandidate`
versus `AnalysisError`, provenance stamped under `analysis` after the model's
own keys, validation before return.

### 3.4 Corpus: `engine/corpus.py`

A copy of `reel-engine/engine/corpus.py` with a different `REQUIRED_NESTED`,
not an import
of it: the reel corpus requires `transcript`, `pacing` and timed `structure`,
and a text ad has none of those. Everything else is identical - one file per
record at `research/corpus/meta-ad-<id>.json`, sorted keys, trailing newline,
strict top level, permissive `analysis`, duplicate ids refused, `ORIGINS` =
`competitor | icp-adjacent | own`. The two repositories keep their own corpus;
nothing reads across.

### 3.5 Learn: `engine/learn.py`

Zero model calls, AST-proved, `MIN_SUPPORT = 2`, ordered by `(kind, device)`,
ids from that order, `generated_at` from the corpus. The kinds change:

| Kind | Device | Slots (for the description's medians) |
|---|---|---|
| `hook` | the device label | hook word count |
| `length` | `words:0-19` / `20-49` / `50-99` / `100-199` / `200+` | word count |
| `structure` | `shape:hook>problem>offer>cta` and `section:<label>` | position in the order |
| `cta` | the button type | - |
| `offer` | `free-trial`, `demo`, `guarantee`, `price`, `none` | - |
| `proof` | `testimonial`, `number`, `logo`, `none` | - |
| `objection` | the normalised objection text | - |
| `longevity` | `days:0-6` / `7-27` / `28-59` / `60-119` / `120+` | days running |
| `ctr` (own ads only, from measure) | `ctr-pct:0-0.4` / `0.5-0.9` / `1.0-1.9` / `2.0+` | the CTR |

The pattern record carries `median_days_running` and `median_reach` where the
reel one carries `median_views`, and `n` as before. The `ctr` kind is the
`retention` kind's twin: absent is silent, present-but-unreadable is reported,
and a null is never a zero. The band edges are a first guess and are the one
thing here to revisit after the first live corpus.

### 3.6 Concepts: `engine/concepts.py`

One call, N concepts, every concept citing a pattern id that exists and a
segment id from the backlog. Two additions to the record: `placement`
(`reels-9x16`, `feed-4x5`, `static-1x1`) so the writer knows whether a video
is being asked for, and `offer` (one of the learned offer devices, or `none`).
`needs_numbers` stays and stays a JSON boolean.

**The backlog.** The concepts need the same ranked segments the reel loop
uses. `campaign-site` documents that the campaign repositories are cloned as
siblings and reach across by relative path, and this repository's own README
already reads `../outreach-engine/queue/acc-dk.csv`. So the default is to read
`../reel-engine/queue/backlog.md` with a copy of that repository's
`engine/backlog.py` parser,
and to refuse by name if the sibling is absent. Decision 4 in section 8 is
whether to copy the table instead.

### 3.7 Score: `engine/score.py`

The same five dimensions and the same weights. `pattern_evidence` reads `n`
against `EVIDENCE_FULL_N = 3` and `median_days_running` on a log scale with a
ceiling at 120 days, in place of views. `claims_survivability` runs the claims
gate over the hook (section 3.8). `icp_fit` is the segment's lookup share, as
now. `novelty` compares against `creative/*.json` and the live queue. One
editorial call scores the batch. `_spread` picks winners across segments first
and then across placements, so three winners are three ads and not three
videos for one trade.

### 3.8 Write and gate: `engine/write.py`, `engine/gate.py`

The writer produces **two files from one concept**:

1. `queue/proposed/<segment>.json` - the ad copy, in the shape
   `creative/capacity.json` already has: `primary_text`, `headline`,
   `description`, `cta`, `destination`, per language, plus `concept_id`,
   `pattern_ids` and `placement`. The Danish and Lithuanian fields are written
   as `NEEDS_NATIVE_PROOFREAD` unless a native has signed them off - the model
   does not get to declare copy native.
2. For a `reels-9x16` or `feed-4x5` placement, a **`reel-engine` content
   JSON** beside it, written against `reel-engine`'s own guide and gated by
   `reel-engine`'s own build. The concept's hook is the reel's hook. The ad's
   video is a reel; nothing new is rendered here.

**The claims gate has to be one gate.** Today `engine/gate.py` is five regexes
and `claims/evidence.json` is keyed by claim id; `reel-engine`'s policy is a
number regex that also matches number words ("one", "half", "twice"), a
per-field hash attestation, and a hard build failure. The reel policy is the
stronger one and it is the one a video creative will be gated by anyway, so
this repository adopts it: port `NUM_RE`, `evidence_key`, `spoken` and the
evidence file format, keep the five regexes as additional named checks
(`customer_count`, `percentage_claim` are worth keeping by name), and migrate
`claims/evidence.json` to the hash format with the five verified product facts
carried over. Decision 5 in section 8.

The editorial rubric for an ad has four rules, in the gate's own shape:

1. No unsupportable promise - the latency and accuracy constructions
   `reel-engine` already lists, verbatim.
2. The offer named in the copy is one this business actually makes
   (`docs/ICP-BRIEF.md`'s table: design partner, standard, the 30-day
   guarantee) - checked from a table, not judged.
3. The hook names a moment in that trade's week, not a generic complaint.
4. Nothing in the copy claims a customer, a logo or a testimonial exists.

Rule 2 is structural and free; the other three are the one editorial call.

### 3.9 Render: `reel-engine`, unchanged

`reel-engine`'s own `python -m engine.cli <content.json> --out <ad>.mp4` for
the video and the
still-frame path for a static. `reel-c`, `reel-s` and `reel-d` are 9:16 for
Reels and Stories placements; `reel-b` is 4:5 for feed. The ad's workflow
checks out the sibling repository and calls its CLI; `ad-engine` holds no
renderer and installs no Chromium of its own. Meta's placement specs (9:16 at
1080x1920, 4:5 at 1080x1350) are exactly the two aspects that exist.

### 3.10 Approve: `engine/approval.py`, copied

The same two taps on the same label, with the stages renamed for what they
mean here:

```
queue/proposed/   copy gated, awaiting approval          stage:copy
queue/built/      creative rendered, awaiting launch     stage:creative
queue/launched/   live in Ads Manager, ad ids pinned     -
queue/rejected/   parked drafts
```

The decision half is pure and copies over; the GitHub transport copies over;
the issue body shows the copy and, for a video, the still `reel-engine` shot.

### 3.11 Launch: manual first, Marketing API second

**Phase 1 is a human.** The second `go` moves the job to `queue/built/` and
the issue says: upload this MP4 and this copy in Ads Manager, then paste the
ad id back with `python -m engine.approval launch --segment <id> --ad <ad
id>`. That
pins the id into the job under `ads`, the twin of the reel job's `videos` map
- the guess is made once, by a human, and every later measurement is an exact
lookup.

**Phase 2 is the Marketing API**, and it is a write: upload the video, create
the creative, create the ad **paused**, and let a human flip it on. That needs
`ads_management` on our own account and is the one step in this whole design
that can spend money, so it stays behind a human tap and is built last.

### 3.12 Measure: `engine/measure.py`

Our own ads, read from our own ad account through the Marketing API insights
edge, by pinned ad id. What comes back is real: `impressions`, `reach`,
`clicks`, `ctr`, `cpc`, `spend`, `video_p25_watched_actions` through
`video_p100`, `video_thruplay_watched_actions`, `actions` and
`cost_per_action_type`. Hook rate (3-second plays over impressions) and hold
rate (thruplays over 3-second plays) are derived in the module and say so.

Same shape as `reel-engine/engine/measure.py`: nothing launched costs nothing,
and the token is read through a copy of that repository's `engine/oauth.py`
with its day-40 warning and day-60 refusal. What was built reads
`/{ad_id}/insights` **one pinned ad at a time** rather than fifty at a time:
the batched account-level form needs `own.ad_account_id` and a second URL shape
nobody has verified, and one call a week per launched ad is not a surface worth
guessing at. Whether a
System User token from Business Manager (which does not expire) is acceptable
here is the first thing to check when the account is wired - it would delete
the calendar entry.

### 3.13 Feedback: `engine/feedback.py`

Zero model calls. We wrote the copy, so the hook, structure, offer and CTA are
read off the job file verbatim; the CTR and hook rate come from the
measurement; the record is written with origin `own`, `model: none
(authored)`, and `analysis.derived_from.note` saying which fields were read
rather than judged. An ad with zero impressions is skipped, not written.

**This is where the ad loop is better than the reel loop.** A competitor's ad
contributes longevity; our own ad contributes a click-through rate. The `ctr`
kind in learn counts only our own ads, exactly as `retention` counts only our
own reels - and a hook device that appears in three long-running competitor
ads *and* in our own best-CTR ad is the strongest citation this system can
write.

---

## 4. Contracts

The reel loop's contracts C1-C5, re-stated for ads. Ids are prefixed so nothing
downstream can confuse a reel record with an ad record.

### C1' - corpus record, `research/corpus/meta-ad-<id>.json`

```json
{"schema": 1, "id": "fb-961046237012883", "platform": "meta-ad",
 "url": "https://www.facebook.com/ads/library/?id=961046237012883",
 "channel": "Balance - Your AI Powered Accountants",
 "origin": "icp-adjacent",
 "fetched_at": "2026-09-22T06:04:11Z",
 "metrics": {"eu_total_reach": 0, "days_running": 0, "active": true,
             "variants": 1, "media_type": "VIDEO",
             "publisher_platforms": ["facebook", "instagram"],
             "languages": ["da"], "countries": ["DK"],
             "page_id": "1007614045762121"},
 "analysis": {
   "copy": {"primary_text": "...", "headline": "...", "description": "...",
            "cta_type": "LEARN_MORE", "words": 0},
   "hook": {"words": 0, "text": "...", "device": "question"},
   "structure": ["hook", "problem", "offer", "cta"],
   "offer": {"type": "none", "text": ""},
   "proof": {"type": "none", "text": ""},
   "cta": {"type": "learn-more", "text": "..."},
   "objections": ["..."],
   "creative": {"kind": "text-only"},
   "outlier_ratio": 0.0},
 "model": "gemini-3.6-flash"}
```

`origin` is `competitor | icp-adjacent | own`. `platform` is `meta-ad` and
nothing else in this repository. `page_id` lives under `metrics` because the
top level is closed.

### C2' - candidate record (in memory, discovery to analysis)

```json
{"id": "fb-...", "platform": "meta-ad", "url": "...", "channel": "...",
 "origin": "...", "metrics": {"eu_total_reach": 0, "days_running": 0,
 "active": true, "variants": 1, "media_type": "VIDEO",
 "publisher_platforms": [], "languages": [], "countries": [],
 "page_id": "..."}, "copy": {"primary_text": "...", "headline": "...",
 "description": "...", "cta_type": "..."}, "outlier_ratio": 0.0}
```

`copy` travels on the candidate because the text path needs it in the prompt;
it is copied into `analysis.copy` by the analysis step.

### C4' - concept record

```json
{"id": "a01", "segment": "payroll-bureaus", "angle": "...", "hook": "...",
 "pattern_ids": ["q03"], "placement": "reels-9x16", "offer": "guarantee",
 "needs_numbers": false}
```

### C5' - `research/patterns.json`

```json
{"schema": 1, "generated_at": "...", "corpus_size": 0,
 "patterns": [{"id": "q03", "kind": "longevity", "device": "days:60-119",
   "description": "...", "evidence": ["fb-..."],
   "median_days_running": 0, "median_reach": 0, "n": 0}]}
```

Pattern ids are `q..` so a concept can never cite a reel pattern by accident.

### C6' - measurement row, `research/measurements.json`

```json
{"segment": "payroll-bureaus", "ad_id": "...", "campaign_id": "...",
 "launched_at": "...", "measured_at": "...", "window_days": 7,
 "metrics": {"impressions": 0, "reach": 0, "clicks": 0, "ctr": 0.0,
             "cpc": 0.0, "spend": 0.0, "plays_3s": 0, "thruplays": 0,
             "results": 0, "cost_per_result": 0.0},
 "derived": {"hook_rate": 0.0, "hold_rate": 0.0}}
```

---

## 5. The cost ledger for the ad half

Every row is a free allowance. The invariant `docs/COST.md` states for
`reel-engine` holds for everything in this document **except one line, which is
outside it by definition**: the ad spend itself. Research, writing, rendering,
approving and measuring cost nothing. Running the ad costs whatever the
campaign budget says, and nothing in this design requires an ad to run for the
research half to work.

| Surface | Allowance | Load, weekly | Arithmetic or measured | If exceeded |
|---|---|---|---|---|
| **Ad Library API** | ~200 calls/hour per token (reported, not published); free | 1 call per 10 seeded pages + 1 per query per country list + pagination. 10 pages, 6 queries, 2 pages each: **~14 calls**. Measure adds 0. | Arithmetic on the documented parameters. Never called live. | Error 613, never a charge. A `Quota(200)` charged before the socket refuses the call that would exceed it. |
| **Marketing API insights** (own account) | Free; rate-limited per ad account by Meta's business-use-case formula | 1 call per 50 pinned ads, once a week. **0 with nothing launched.** | Arithmetic. | HTTP 429 or an error body, never a charge. Not retried. |
| **Gemini** (free tier, per model per project) | **20 requests a day per model** - measured in `reel-engine` from the 429 that killed propose run 26 | Research: 1 batched analysis call per 12 ads + 1 concepts + 1 editorial = **~3**. Write: up to 2 per concept per attempt (write, gate). | Arithmetic on the batch size. The reel loop's research day spends up to 14; batching text is what makes room for both loops on one key - **or the ad loop gets its own AI Studio key and its own 20**, which is free. | 429, resets midnight Pacific. Not retried, by design. |
| **GitHub Actions minutes** | 2,000/month, private repo; `reel-engine` projects ~284 | research ~2m (no browser), propose ~5m, build ~8m (the `reel-engine` render), measure ~2m: **~17m a week, ~75/month** | Estimate; the `JOB_STARTED` stamp reports the real figure on the first run. | Stops, does not bill, while the spending limit is $0. |
| **Actions artifacts** | 500MB | one MP4 per ad, 14-day retention | Same as the reel ledger | Cut retention. |
| **Meta developer app** | Free | - | - | - |
| **Ad spend** | **Not in this ledger.** | - | - | The only money in the design, and it is a campaign decision behind a human tap, never a research cost. |

---

## 6. What a human has to do before the first live run

In order, with what each one unblocks.

1. **Identity verification and a token.** `facebook.com/ID` with a government
   id (one to three business days), a Meta developer app with the Ad Library
   API product, a token. Secret: `META_ACCESS_TOKEN`; variable:
   `META_TOKEN_ISSUED` as `YYYY-MM-DD` (one pair for both Meta APIs - see the
   decisions block after section 8), the same shape
   `engine/oauth.py` keeps for Instagram, for the same reason - the date must
   be visible beside the token or the countdown cannot be kept honest.
   *Unblocks discovery.*
2. **Page ids for the seed file.** Open each competitor and ICP-adjacent page
   in the Ad Library UI and read the id out of the URL, or take it from the
   MCP probe's `page_id`. Starting list from this session's probe and
   `reel-engine`'s seeds: Fyxer, Jace AI (both may run nowhere in the EU -
   check before seeding, a page that returns nothing costs a call every week),
   Balance, GoSimple, and the Danish and Lithuanian accounting-software pages
   (Dinero, e-conomic, Billy, Rivile - unverified, chosen as examples of the
   kind). *Unblocks a corpus with a per-page baseline.*
3. **Read the Ad Library API terms** and take decision 6 in section 8 on what
   the corpus record stores. *Unblocks committing records.*
4. **An access token for our own ad account**, read-only (`ads_read`) for
   measure. Check whether a System User token is accepted. *Unblocks measure;
   nothing before it needs this.*
5. **The native check.** Every Danish and Lithuanian field stays
   `NEEDS_NATIVE_PROOFREAD` until a human replaces it. This is a gate in the
   approval flow, not a model's opinion. *Unblocks launching in either
   market.* (Already recorded in this repository's README as an open item.)
6. **The pixel** on `doviloop.dev`. Not needed for anything in this document;
   needed for the retargeting audience this repository already lists as
   blocked. Recorded here so it is not mistaken for a research blocker.

---

## 7. Phasing

Each phase is independently useful and stops cleanly, in the spirit of
`reel-engine/docs/STRATEGY.md`'s "stop at any point". Costs are model calls per weekly run
and are ceilings.

| Phase | Builds | Done when | Model calls |
|---|---|---|---|
| **A. Discover** | `research/seeds.yaml`, `engine/discover.py` with `Quota`, the offline test suite with a stub transport and the no-snapshot socket test, `--dry-run` | A dry run prints the plan and the call count; the first live call with a real token prints the field set section 2.2 could not confirm. | 0 |
| **B. Corpus and learn** | `engine/corpus.py`, `engine/analyse.py` (text path, batched), `engine/learn.py` with the AST test, `research.yml` weekly | `research/patterns.json` is committed with at least one pattern supported by 2+ ads, and an unchanged corpus rewrites identical bytes. | ~1 |
| **C. Concepts and score** | `engine/concepts.py`, `engine/score.py`, `engine/fanout.py` writing `research/selection.json` | Three selected concepts, each citing a pattern that traces to named ads with days-running under it, with a scorecard for all twelve. | ~3 |
| **D. Write, gate, approve** | `engine/write.py`, the ported claims policy in `engine/gate.py` and the migrated `claims/evidence.json`, `engine/approval.py` copied, `propose.yml` opening one issue per concept with `reel-engine`'s still | A concept becomes gated copy in `queue/proposed/` plus a content JSON `reel-engine` builds without error, and a `go` moves it. | up to 6 per concept |
| **E. Build and manual launch** | a `build.yml` that checks out `../reel-engine` and renders; `engine.approval launch --ad` pinning the id | An MP4 and a still for one approved concept, and a job in `queue/launched/` carrying an ad id a human pasted. | 0 |
| **F. Measure and feed back** | `engine/measure.py`, the copied `engine/oauth.py`, `engine/feedback.py`, `measure.yml` an hour before research | One launched ad has a C6' row and an `own` corpus record with a CTR band, and the next sweep's patterns cite it. | 0 |
| **G. Marketing API launch** | write path: upload, creative, ad created paused | Optional, last, behind a human tap. | 0 |

Phase A through C is the "scrape the best performing ads, structure them" half
the request asked for, and it runs with no ad account, no pixel and no spend.

---

## 8. Open decisions

Put to Dovy, with a recommendation each.

1. **Home.** This repository (recommended, section 0) versus a `meta-ad`
   platform inside `reel-engine`. The latter would reuse `corpus.py` and
   `learn.py` by import but would force timed transcripts onto text ads or
   loosen the reel schema, and would put a Meta transport into a repository
   whose tests assert it has none.
2. **The performance proxy.** Longevity as primary with reach-per-day as the
   outlier numerator (recommended), or reach as primary. Longevity is the
   number an advertiser's own money voted on; reach is the number their budget
   bought.
3. **Text-only by default, media by hand.** Recommended. The alternative -
   fetching snapshots - is a scrape of a rendered page whose terms nobody here
   has read, and it is the exact seam `reel-engine` refuses for Instagram.
4. **The backlog.** Read `../reel-engine/queue/backlog.md` as a sibling
   (recommended; the ICP is one list and two copies drift), or copy the table.
5. **One claims policy.** Port `reel-engine`'s (recommended) and migrate
   `claims/evidence.json`. The two formats cannot both be the truth about what
   this business may claim in public.
6. **What the corpus stores.** Verbatim creative text under `analysis.copy`, or
   only the derived fields plus the ad id and snapshot URL. Depends on the
   terms in section 6 step 3. The derived-only record is enough for learn; the
   verbatim one is what a writer would quote.
7. **A second AI Studio key for this repository.** Free, and it doubles the
   daily headroom rather than sharing 20 calls a day per model with the reel
   sweep on the same Monday morning.
8. **Competitor countries.** A UK or US competitor that never reaches DK or LT
   is invisible under the default country list. Seeding them with their own
   countries widens `icp-adjacent` to "a different market's ads about the same
   category", which is honest as long as the record says which countries it
   reached - and it does.

---

## 8a. Decisions taken 2026-09-18

Section 8 put eight decisions to Dovy. Six of them were taken the same day and
the loop was built against them, in one pass, by a fan-out of builders working
from `docs/CONTRACTS.md`. This block is the record of what was chosen and what
it cost; where a decision differs from the recommendation above, this block
wins and section 8 is the argument that led here.

**1. Home: this repository.** Decision 1, as recommended. The research half
lives in `ad-engine`. `reel-engine`'s corpus schema is untouched, its tests
still assert it has no Meta transport, and the two repositories share nothing
at run time except the renderer - which `build.yml` reaches by checking the
sibling out, once, when a video is actually being shot.

**2. The backlog is a copy, kept in sync by a tool.** Decision 4, **against**
the recommendation. The ICP is one ranked list and `reel-engine` owns it, but
reading `../reel-engine/queue/backlog.md` at run time would mean the weekly
research cron needs `REEL_ENGINE_TOKEN` - a second repository's credential -
to read one markdown table. A free, read-only sweep should not be able to fail
on a credential it has no other use for. So `queue/backlog.md` is a copy with a
header saying so, `engine/backlog.py` reads it locally, and
`tools/sync_backlog.py` rewrites the rows from the sibling when a checkout has
both: `--check` exits 1 with a diff on drift, and refuses (exit 2) rather than
guessing when the table or the markers are wrong. The tool runs in `build.yml`,
which already holds the token, and nowhere else. Two copies drift; a tool that
says so is the price of a cron that cannot fail on a token.

**3. One claims policy, and it is `reel-engine`'s.** Decision 5, as
recommended. `engine/gate.py` keeps its five named regexes and its
`check()`/`check_creative()` surface - the eight tests that were here first
still pass, unedited - and gains the number policy ported verbatim from
`reel-engine/reel/build.py`: `CARDINALS`, `MULTIPLIERS`, `NUM_RE`, `spoken()`
and `evidence_key()`, so a number word ("one", "half", "twice") is a number and
a hash of field-and-text is what attests it. `claims/evidence.json` now carries
three sections rather than one: the original `claims` untouched, an
`attestations` map (empty on purpose - no ad has yet needed a number), and an
**offers table**:

| Offer | Status | What may be said |
|---|---|---|
| `guarantee` | verified | if the drafts are not good enough to send, they do not pay and keep the knowledge base |
| `design_partner` | verified | design-partner terms for the first firms in |
| `demo` | verified | a call can be booked |
| `free_trial` | **UNVERIFIED** | no self-serve trial exists; revenue is switched off in the product |

The offer is checked from that table and not judged, which is rule 2 of the
editorial rubric turned into a lookup: `engine/concepts.py` will not write a
concept on an unverified offer, `engine/write.py` refuses one before it builds
a prompt, and `gate.structural()` refuses a job carrying one - three places,
one table, no model call. The other three rubric rules are the single editorial
call.

**4. Text-only analysis by default, batched; media by hand.** Decision 3, as
recommended, plus the batching rule 1.2/3 argues for. `engine/analyse.py` reads
up to `BATCH_SIZE = 12` ads in **one** model call, keyed by id, with a per-ad
`{"refuse": ...}` escape and a batch-level refusal if the reply is short an id
or truncated - half a batch would be counted as evidence. A candidate with a
hand-saved file at `research/media/<id>.<suffix>` gets its own call with the
file attached. **There is no code path that fetches a snapshot and no place to
add one**: `tests/test_analyse.py` AST-parses the module, forbids every
transport import, and asserts the source contains neither `snapshot_url` nor
any `ads/library` string other than the Library URL prefix the record's `url`
is built from. A default sweep is 2 analysis calls, not 24.

**5. One token pair for both Meta APIs.** Not a section 8 question; it came up
while wiring. `META_ACCESS_TOKEN` (secret) and `META_TOKEN_ISSUED` (repository
variable, `YYYY-MM-DD`) are read by `engine/oauth.py` and by nothing else, and
they serve **both** reads: the Ad Library archive for strangers' ads and the
Marketing API insights edge for our own. The names this document first proposed
- `META_AD_LIBRARY_TOKEN` and its `_ISSUED` twin - were dropped: two secrets
for one token is two things to rotate and two ways for the date to go stale,
and the second read needs no second credential, only `ads_read` on our own ad
account granted to the same token's user. The countdown is unchanged: warns
from day 40 of 60, refuses past 60 before any socket, and `python -m
engine.oauth --status` exits nonzero inside the band. `docs/SECRETS.md` has the
minting steps and the rotate-both-in-one-visit rule.

**6. The `ads_` prefix is dropped.** The modules mirror `reel-engine`'s names
exactly - `discover`, `analyse`, `corpus`, `learn`, `concepts`, `score`,
`fanout`, `write`, `measure`, `feedback`, `approval`, `oauth`, `backlog`,
`model`, `gate` - rather than `ads_discover`, `ads_analyse` and the rest.
There is no reel module in this repository to collide with, so the prefix
bought nothing and cost the one thing that matters when two repositories are
read side by side: an operator who knows where a thing lives over there knows
where it lives here, and a diff between the two is a diff about behaviour
rather than about names. Section 3 and section 7 above have been updated to
the real names. The record shapes keep their primed ids (C1', C2', ...) in
section 4 because those genuinely differ from the reel ones; `docs/CONTRACTS.md`
carries the versions the modules were actually built against.

### What was NOT decided

- **Decision 6, what the corpus stores**, is still open and still waits on
  Meta's Ad Library API terms, which nobody has read. The corpus as built
  stores the creative text verbatim under `analysis.copy`, because a writer
  quotes it and `research/corpus/` is a private repository - but that is the
  default, not a ruling, and narrowing it later is a change to
  `engine/discover.py`'s `candidate()` and one field of the record.
- **Decision 7, a second AI Studio key**, is still open. It is free and it is
  the first lever if a Monday that runs both loops ever hits the 20-a-day
  ceiling. `docs/COST.md` prices the collision.
- **Decision 2 (longevity primary) and decision 8 (competitor countries)** were
  taken as recommended and needed no argument: `outlier_ratio` is reach-per-day
  over the page's own median, the per-page baseline is what stops absolute
  reach rewarding whoever spends most, and `research/seeds.yaml` gives any page
  or query its own country list, with the record saying which countries the ad
  reached.
- **Phase G, the Marketing API launch path**, is not built and is not started.
  Launching is a human in Ads Manager pasting an ad id back through
  `engine.approval launch`, exactly as phase E says.

### What the first live run still has to prove

Nothing here has met a live credential. Every test is offline, every transport
is injected, `research/corpus/` holds only its `.gitkeep`, and neither
`research/patterns.json` nor `research/measurements.json` has been written
once. Section 9 below is unchanged and still correct, and `docs/SECRETS.md`'s
"before you trust the cron" is the order to check it in.

---

## 9. What this document did not verify

- **No call was made to `ads_archive`** with a real token. The field set for a
  commercial EU ad is Meta's reference page and the DSA guides; the first live
  call in phase A is the proof, and the ambiguous targeting fields in section
  2.2 are the ones to look at.
- **200 calls per hour** is the figure every secondary source reports and
  Meta's reference does not print. The `Quota` budget is a parameter so a
  measured figure replaces it in one line.
- **The token lifetime** is not published for this use. 60 days is assumed
  from `reel-engine`'s Instagram experience, and the countdown makes a wrong
  assumption loud rather than silent.
- **Meta's Ad Library API terms** on storing and committing returned data were
  not read in this session. Decision 6 waits on them.
- **Whether a System User token can read insights** for measure without a
  60-day rotation.
- **The band edges** in section 3.5 are a first guess with no corpus behind
  them.
- **The Marketing API insights field names** listed in 3.12 are from memory of
  the API and need checking against the reference before phase F.
