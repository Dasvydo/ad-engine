# Run state: ads research loop
Started: 2026-09-18
Last updated: 2026-09-18
Status: executing
Domain profile: software

## Original request

> So, now that you already have this infrastructure build for scraping the best
> performing reels, structuring them, copy their scripts, generating a video,
> etc. Now I need to do the same just that for Ads, so i need to scrape best
> performing Ads (thru Ad Library). I need you to analyse whats already done,
> learn what is the actual procedure/infrastructure, scope how could it be
> re-applied the same way just that for ads.
>
> (Then: "If you have a clear idea on how to clone and build it exactly for the
> Meta Ads use case, then simply scope and build.")

This file was written after the build, on request, because the work was
orchestrated directly rather than through this skill and therefore had no task
table to count. Every row below was set from the tree and the run journals, not
from memory. Where a row says `landed` rather than `verified`, that is the
honest state and not a formatting choice.

## Mission brief

GOAL: `ad-engine` runs the loop `reel-engine` runs - discover what is already
working in the market, count what repeats, write the next thing from that
evidence, gate it, get a human's approval, ship it, measure it, and feed the
result back as evidence - with the Meta Ad Library where the YouTube Data API
sits and our own ad account's click-through rate where retention sits.

DONE WHEN: a weekly sweep reads real ads, a concept traces to named ads with
days-running under it, a human taps `go` twice, an ad runs, and its measured
click-through rate becomes a pattern the next sweep can cite. The monthly bill
for everything except the ad spend itself is $0.00.

CONSTRAINTS: zero cost - every service inside a published free allowance, no
card attached anywhere. Every test offline: no key, no token, no socket. The
Ad Library is read through its API and nothing else - no snapshot page is
fetched, no creative is downloaded, nothing is scraped. No number reaches a
public ad without an attestation. Nothing leaves the repository until a human
has tapped `go` twice. `docs/ICP-BRIEF.md` never reaches a model prompt.

OUT OF SCOPE: rendering (that is `reel-engine`'s, called across the seam and
never reimplemented); any write to Meta - creating, editing, pausing or paying
for an ad; `outreach-engine`; the existing `engine/audience.py` and
`audiences/*.json`; the Meta pixel; and translating Danish or Lithuanian copy,
which a native speaker signs off and a model never claims to have written.

## Tasks

| ID | Title | Wave | Status | Attempts | Verdict | Deliverable | Owns |
|----|-------|------|--------|----------|---------|-------------|------|
| T1 | Scope the reel loop re-applied to ads | 0 | verified | 1 | PASS | e9cfa60 | docs/AD-RESEARCH-SCOPE.md |
| T2 | Fix the build contracts and the skeleton | 0 | landed | 1 | - | e168b98 | docs/CONTRACTS.md, requirements.txt, pytest.ini |
| T3 | Model provider and the test stub | 1 | landed | 1 | - | 1581594 | engine/model.py, tests/stubs.py |
| T4 | Corpus store, one file per analysed ad | 1 | verified | 1 | PASS | 1581594 | engine/corpus.py |
| T5 | Segment backlog and its sync tool | 1 | landed | 1 | - | 1581594 | engine/backlog.py, tools/sync_backlog.py |
| T6 | Meta token, aged and refused past sixty days | 1 | landed | 1 | - | 1581594 | engine/oauth.py |
| T7 | Ad Library discovery behind a quota ledger | 1 | verified | 1 | PASS | 1581594 | engine/discover.py, research/seeds.yaml |
| T8 | Claims gate, attestations and the offers table | 1 | verified | 1 | PASS | 1581594 | engine/gate.py, claims/evidence.json |
| T9 | Batched analysis, twelve ads to a call | 2 | verified | 1 | PASS | 1581594 | engine/analyse.py |
| T10 | Pattern counting, zero model calls | 2 | verified | 2 | PARTIAL to PASS | 1581594, 4a4ff5d | engine/learn.py |
| T11 | Approval: stages, labels, the two taps | 2 | verified | 1 | PASS | 1581594 | engine/approval.py |
| T12 | Concepts, twelve in one call, every one cited | 3 | verified | 1 | PASS | 1581594 | engine/concepts.py |
| T13 | Five-dimension score, measured outranking judged | 3 | verified | 1 | PASS | 1581594 | engine/score.py |
| T14 | Measure our own launched ads | 3 | verified | 1 | PASS | 1581594 | engine/measure.py |
| T15 | Feed a measured ad back as evidence | 3 | verified | 1 | PASS | 1581594 | engine/feedback.py |
| T16 | Write the ad copy and the reel sidecar | 4 | verified | 2 | PARTIAL to PASS | 1581594, 4a4ff5d | engine/write.py |
| T17 | Fan-out: the sweep, composed end to end | 4 | verified | 1 | PASS | 1581594 | engine/fanout.py |
| T18 | Propose a gated job from a selected concept | 5 | verified | 2 | PARTIAL to PASS | 1e32872, 4a4ff5d | engine/propose.py |
| T19 | The seven workflows | 5 | verified | 2 | PARTIAL to PASS | 1e32872, 4a4ff5d | .github/workflows/ |
| T20 | README, cost ledger, secrets | 5 | verified | 2 | PARTIAL to PASS | 1e32872, 4a4ff5d | README.md, docs/COST.md, docs/SECRETS.md |
| T21 | End-to-end pipeline test | 6 | verified | 1 | PASS | 4a4ff5d | tests/test_pipeline.py |
| T22 | Seam audit and the fixes it confirmed | 6 | verified | 1 | PASS | 4a4ff5d | (cross-cutting) |
| T23 | GitHub setup: labels, secrets, variables, $0 limit | 7 | held on Dovy - about 20 minutes in repository settings | 0 | - | four labels, three secrets, one variable | (GitHub settings) |
| T24 | Meta identity verification and an Ad Library token | 7 | held on Dovy - a government id, then one to three business days | 0 | - | META_ACCESS_TOKEN, META_TOKEN_ISSUED | (Meta developer app) |
| T25 | Page ids for the seed file | 7 | held on Dovy - about 30 minutes reading ids out of the Ad Library UI | 0 | - | research/seeds.yaml pages | research/seeds.yaml |
| T26 | Read the Ad Library API terms, settle what the corpus stores | 7 | held on Dovy - decision 6 in the scope | 0 | - | a decision recorded in the scope | docs/AD-RESEARCH-SCOPE.md |
| T27 | A read-only token for our own ad account | 7 | held on Dovy - and check whether a System User token avoids the sixty-day clock | 0 | - | the measure half of META_ACCESS_TOKEN | (Meta business settings) |
| T28 | Native Danish and Lithuanian proofread | 7 | held on Dovy - every da and lt field ships as NEEDS_NATIVE_PROOFREAD | 0 | - | signed-off copy | creative/ |
| T29 | First live ads_archive call: confirm the field set | 8 | blocked on T24 | 0 | - | the TODO(integration) block in discover closed or corrected | engine/discover.py |
| T30 | First live sweep: a real corpus and real patterns | 8 | blocked on T24, T25 | 0 | - | research/corpus/, research/patterns.json | research/ |
| T31 | First live insights call: confirm the field names | 8 | blocked on T27 | 0 | - | the TODO(integration) block in measure closed or corrected | engine/measure.py |
| T32 | Re-band learn's edges against the real corpus | 9 | blocked on T30 | 0 | - | corrected LENGTH/LONGEVITY/CTR edges | engine/learn.py |
| T33 | First full loop: propose, build, launch, measure, feed back | 9 | blocked on T23, T28, T30, T31 | 0 | - | one ad live and one own corpus record | (cross-cutting) |
| T34 | Marketing API write path, ad created paused | 10 | held - external write, deliberately last | 0 | - | engine/launch.py | engine/launch.py |

## Contracts

| ID | Producer | Consumers | Interface | Honored |
|----|----------|-----------|-----------|---------|
| C1 | T7 | T9 | Candidate record (C2 in docs/CONTRACTS.md) | yes - tests/test_pipeline.py |
| C2 | T9 | T4, T10, T13 | Corpus record (C1), platform meta-ad | yes - tests/test_pipeline.py |
| C3 | T10 | T12, T13, T18 | research/patterns.json, ids q01.. | yes, with one caveat: ids are positional, so a regeneration can reassign them. Recorded in engine/learn.py |
| C4 | T12 | T13, T16 | Concept record, placement and offer | yes - tests/test_pipeline.py |
| C5 | T16 | T19 (build.yml), reel-engine | The reel selection sidecar must satisfy reel-engine's own load_selection | yes - audited at T22 against the sibling's source |
| C6 | T14 | T15 | Measurement row (C6), nulls never zeros | yes - tests/test_pipeline.py |
| C7 | T5 | reel-engine's queue/backlog.md | The five segment ids must exist in both | yes today, byte for byte. `tools/sync_backlog.py --check` is what keeps it true |

## Hard stops

| ID | Category | Status | Resolved by |
|----|----------|--------|-------------|
| HS1 | Auth - a Meta access token, and the identity verification behind it | held | T24, T27. Dovy only; no agent can complete an identity check |
| HS2 | External writes - any call that creates, edits or pays for an ad | held | T34, and it is built last on purpose |
| HS3 | External reads - the first live call to either Meta API | held | T29, T31. Cheap and reversible, but they spend a real token and the first response is the thing being checked |
| HS4 | Main branch - nothing here has been merged to main | held | a pull request from claude/busy-bohr-wanqmv, on request |
| HS5 | Publishing copy - no ad ships until a human has tapped `go` twice | cleared - this one never needs clearing | the two-tap approval is the architecture, not a gate on this run. Listed so nobody adds a second one |

## Assumptions made unattended

| When | Task | Decision | Alternative not taken |
|------|------|----------|----------------------|
| scope | all | Home is `ad-engine`, not a `meta-ad` platform inside `reel-engine` | Widening reel-engine's corpus schema to hold text ads, and putting a Meta transport in a repository whose tests assert it has none |
| scope | T7 | Longevity is the primary performance proxy, reach per day the numerator | Reach alone, which rewards whoever spends most |
| scope | T9 | Text analysis batched twelve to a call | One call per ad, as reel-engine does for video - twenty-four calls against a free tier of twenty a day |
| scope | T5 | The backlog is copied locally and synced by a tool | Reading reel-engine's file across the repository boundary, which would make the weekly cron need a second repository's token |
| scope | T8 | One claims policy - reel-engine's, ported | Keeping ad-engine's five-regex gate as a second, looser standard |
| T22 | T10 | Pattern ids stay positional; the docstring was corrected to say so | Content-derived ids, which would break the contract, the worked examples and two tests |

## Verification log

| Task | Attempt | Verdict | Gaps | Action |
|------|---------|---------|------|--------|
| T1-T21 | 1 | see below | - | Eight seam auditors traced values across module boundaries rather than reviewing modules, because the defect this design produces is a field with a writer and no reader |
| all | 1 | 25 findings raised | - | Two independent skeptics per finding, told to refute. Twelve did not survive |
| T10 | 2 | PARTIAL to PASS | The determinism rule claimed pattern ids survive a regeneration; adding two ads moved thirteen of thirteen | Docstring corrected to the condition it actually holds under, measurement pinned by a test |
| T16 | 2 | PARTIAL to PASS | The reel sidecar took its aspect from the concept, not the approved job, so --placement moved the ad and not its creative | Sidecar now built from the gated job |
| T19 | 2 | PARTIAL to PASS | build.yml published a selection path then re-derived it in shell; two tests matched pinned numbers against the comments naming them | Path consumed and path traversal refused; tests read the command, proved by mutating both workflows |
| T20 | 2 | PARTIAL to PASS | SECRETS omitted build.yml for the model key; META_GRAPH_VERSION was documented as a variable no workflow passed | Both corrected; a test fails if either Graph step stops mapping the variable |
| T3, T5, T6 | 1 | LANDED, NOT VERIFIED | No seam audit read these three. Their own suites pass - 77, 36 and 73 tests - but nobody independent has checked them | See the risk note below |

**Objective check, run at 4a4ff5d:** `python -m pytest -q` - 1,618 passed, no key,
no token, no socket. Clean working tree, local and remote at the same commit.

## Coherence audit

Run at T22 as part of the seam audit rather than as a separate phase. The
integration test `tests/test_pipeline.py::test_the_whole_loop` is its standing
form: it walks a candidate from a stubbed Ad Library response through discovery,
analysis, the corpus, learning, concepts, scoring, writing, the gate, all three
approval stages, a launch, a measurement and the feed-back, and ends by
asserting that a click-through-rate pattern appears which a later concept could
cite. That assertion is what makes the loop a loop rather than a line.

**The one thing it cannot prove** is the seam that crosses into `reel-engine`,
because that needs a checkout, a browser and a rendered MP4. It was audited by
reading both sides - every flag `build.yml` passes against the sibling's own
argument parser, and the sidecar document against the sibling's own loader -
and the five segment ids exist in both backlogs today. The first real proof is
T33.

**Not audited:** T3, T5 and T6. `engine/oauth.py` is the one worth naming,
because it is the module that handles the access token and counts its age, and
it is the only credential-handling code here that no independent pass has read.
