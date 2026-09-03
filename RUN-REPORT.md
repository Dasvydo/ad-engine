# RUN REPORT, Batch E, ad-engine

Branch `campaign/e-ads`. Six commits, nothing pushed. Run 2026-09-03,
unattended. No question asked, nothing waited on, nothing launched, nothing
spent, no database touched, no secret written to any file.

---

## What was built

| Deliverable | Where | State |
|---|---|---|
| Phase 0 audit | `AUDIT.md` | Written before any other file changed |
| Five sourced objections | `research/objections.md` | 5 of 5 traced to named public competitor sources |
| 8 static creatives, 1:1 and 4:5 | `creative/static/out/` | 16 PNGs, rendered, all pass the brand check |
| The static pipeline itself | `creative/static/render.py`, `vet.py` | The typeset half of `hm-static-ad-generator`, which shipped no code |
| Bed prompts for the generative half | `creative/static/beds/` | 8 Nano Banana Pro prompts, unrun |
| 6 copy variants | `creative/copy/` | Primary text, headline, description. Gate green, no em dashes |
| Video cutting spec | `creative/video/cut-spec.md` | Written, not executed. No video shot, by design |
| Campaign build sheet | `campaigns/structure.md` | Hand-buildable in about 20 minutes |
| Pixel install, both domains | `campaigns/pixel-install.md` | With the PostHog mapping |
| Reporting hook | `report/pull_ad_stats.py` + fixture + shim | Clean dry run, 78 tests pass |
| Blockers | `BLOCKED.md` | 8 entries, each with the unblock and how long it takes |

Existing work was extended, not flattened. `audiences/`, `claims/`,
`docs/ICP-BRIEF.md`, `engine/gate.py`, `engine/audience.py` and both original
creatives are untouched. The one change to existing code is one line in
`engine/cli.py`: `check` now recurses into `creative/` so the new copy is gated
by the same rules as the old.

---

## The QA gate, line by line

Every line reported honestly, including what I could not verify.

### `research/objections.md` has 5 objections, each traced to a real competitor source, none invented

**Pass, with a stated caveat.** Five objections, eleven public sources opened in
this session, listed with URLs and outcomes in the file itself. Buyer quotes are
named and dated: Tom Allason, Damian Biondo, Martin Becker, Kellie
Bauer-Simpson, Scott, David E.

The caveat is in the file, not hidden here. **Meta Ad Library could not be
reached** (403 on the web, connection reset in headless Chromium, OAuth error on
the Graph endpoint, which needs a token this session is not allowed to have). So
the spec's intended strongest signal, ad longevity, is absent. G2 and Reddit were
also blocked. `research/objections.md` names which objections rest on thinner
evidence: objection 4 has no buyer quote at all, objection 2 leans on a review of
an adjacent product, and objection 5's quotes all come from one company.

Also reported rather than papered over: of the four companies the brief named
for the teardown, only **Fyxer** is a competitor for this ICP. MasterInbox sells
cold-email deliverability, Conversifi sells LinkedIn outreach automation, and no
AI email assistant called Alta exists in this category. Rather than force
objections out of companies that sell something else, the set was widened to the
products this ICP would actually shortlist. The reasoning is in the file.

### 8 static creatives render at both ratios, brand-locked

**Pass.**

```
$ python -m creative.static.render all
16 files -> creative/static/out/    (8 ids x {1x1, 4x5})

$ python -m creative.static.vet
16 renders checked, 0 failing
```

`vet.py` is `references/vetting-checklist.md` turned into code. Per render it
checks: the background is exactly `#FFF0E5` or `#1D1816` (the yellow test), amber
is present and covers under 3% of the frame, no cool or blue pixels beyond the
deliberate teal in the wordmark, nothing within 18px of any edge, correct
dimensions, no em dash, no third typeface, and that Playfair Display and DM Sans
actually loaded rather than silently falling back to a system serif.

Two real bugs were caught by that check and fixed rather than shipped: three
amber dots on one card (amber is a single signal, not a list marker), and the
wordmark clipped off the bottom edge of two square renders.

Five map to the five objections (`s01` to `s05`), three are direct value
(`s06` Outlook-native, `s07` the ROI angle, `s08` writes-in-your-voice).

**What I could not verify:** whether these actually stop a scroll. That needs the
campaign. And a human should still eyeball the line breaks; `vet.py` explicitly
says which items it does not cover.

### 6 copy variants written, no em dashes

**Pass.**

```
$ python -m pytest -q
78 passed

$ python -m engine.cli check
PASS on all 16 specs (6 copy variants, 8 statics, 2 pre-existing arms)
```

No em dashes and no en dashes, checked by test, not by eye. All English. Every
variant carries the exact UTM from the spec and points at `teams.doviloop.dev`.
Headlines are 26 to 34 characters and descriptions 18 to 31, so none truncates in
feed. Casual, plain verbs, no "unlock", no "supercharge", no "in today's
fast-paced".

**One thing I found and deliberately did not change:** the pre-existing
`creative/capacity.json` contains an em dash in its live English primary text.
It is a pre-campaign A/B arm that may already be running, so changing an arm's
copy mid-test seemed worse than reporting it. **Two minute fix if Dovy wants it.**

### `campaigns/structure.md` is executable by hand in under 20 minutes

**Pass, with an honest correction to the plan.** The build itself is four steps:
audiences, one campaign, three ad sets, six ads, with every setting written out
including the ones that quietly ruin small accounts (campaign budget
optimisation off, Audience Network off, detailed targeting expansion off).

The document says plainly, in its first section and again in its metrics table,
that **under EUR 500 with cold traffic this cannot produce statistically clean
results in six weeks. It produces direction, and the honest read is which
creative gets clicked, not which one converts.** That is not softened anywhere.
The arithmetic is shown: about 45 clicks a week per ad set at the learning-phase
threshold, and a handful of lead events across the entire run.

It also contains a correction the spec did not ask for but the campaign needs:
**every retargeting audience is empty today.** The pixel is not installed and the
reels start posting the same week the window opens. Launching paid on 8 September
spends money against pools of nobody. The document recommends installing the
pixel now, letting the pools fill for two weeks, and running four weeks of paid
from around 22 September instead. That costs less and measures more.

### Pixel instructions cover both domains

**Pass.** `campaigns/pixel-install.md` covers `teams.doviloop.dev` (with the
Next.js and Vercel specifics, including the SPA route-change `PageView` and the
preview-deployment guard) and `doviloop.dev`, on one shared pixel rather than
two. Consent gating is treated as mandatory, not optional, because Denmark and
Lithuania both require opt-in and the campaign already flags Danish marketing law
as stricter than the rest of the EU.

Two standard events, `ViewContent` and `Lead`, with the anti-patterns called out:
fire `ViewContent` on intersection rather than page load, fire `Lead` on the
success response rather than the button click. Advanced Matching is off on
purpose: sending client-adjacent PII to Meta from a product that sells European
data sovereignty would be an own goal.

**What I could not verify:** the PostHog event names. Batch A owns them and this
session cannot see that repo. The mapping table is marked **proposed** and needs
one reconciliation pass. The three routing outcomes (`qualified`,
`gmail_on_request`, `too_small`) are taken verbatim from the shared contract in
`00-START-HERE.md`, so those at least cannot drift.

### `pull_ad_stats.py` runs clean against fixtures

**Pass.**

```
$ python report/pull_ad_stats.py --dry-run
8 rows  spend EUR 22.75  clicks 53  leads 2
DRY RUN, nothing written to campaign.ad_stats.
```

The fixture is shaped exactly like `GET /act_<id>/insights?level=ad&time_increment=1`
and deliberately includes an off-convention ad name, so the test proves that a
mislabelled ad still produces a row with a warning rather than being dropped.

**What I could not verify: the live call has never run.** No Meta account exists.
`fetch_insights` and `build_url` are written against Meta's documented response
shape; `build_url` is tested, `fetch_insights` is not, because testing it would
require the credential. Logged as BLOCKED.md entry 6.

### Branch `campaign/e-ads`, nothing pushed

**Pass.** `git log origin/main..HEAD` is six local commits. No `git push` was run
at any point. No remote branch was created.

---

## The Batch B seam, documented

Batch B owns `campaign_db.py` in the `campaign-ledger` repo, which this session
cannot see or write to. `report/pull_ad_stats.py` handles that in two places:

1. **The import is defensive.** It tries `from campaign_db import
   snapshot_ad_stats` and falls back to `report/ledger_shim.py` on `ImportError`,
   logging loudly that the ledger is not connected. The shim writes the same rows
   to `report/out/ad_stats.jsonl`, validates the column set, and refuses any
   column that is not in `campaign.ad_stats`.

2. **The call adapts to a signature this side has never seen.** Batch B may have
   written `snapshot_ad_stats` to take a row dict, a list of rows, or the columns
   as keyword arguments. `_write_row` inspects the signature and calls it the
   right way. All three shapes are covered by tests.

Row shape uses Batch B's exact column names and nothing else:
`campaign_name`, `ad_set_name`, `creative_content_id`, `captured_on`,
`spend_eur`, `impressions`, `clicks`, `leads`. `id` is left to the database. A
test asserts the dataclass fields equal that list exactly, so a rename here fails
loudly instead of silently on integration day.

`creative_content_id` is the join back to a creative. Meta Insights does not
return `utm_content`, so it is parsed out of the ad name using the convention in
`campaigns/structure.md`: `teams_q4 | v5-pilot | s05-two-weeks-4x5`.

**To connect it:** put the ledger repo on `PYTHONPATH`. No code change on this
side. **About 1 minute.**

---

## What was skipped, and why

| Skipped | Why |
|---|---|
| Any ad video production | The spec says use Batch D's masters. Shooting parallel ad footage for a campaign under EUR 500 a month would cost more than the media. `creative/video/cut-spec.md` is the cutting spec instead. |
| Running the ffmpeg commands in the cut spec | `ffmpeg` is not installed in this session and Batch D's masters are not in this repo. The commands are a recipe to verify once, not verified output. Said plainly at the top of that file. |
| Generative image beds | No image model is callable here. The eight bed prompts are written to the skill's Mode A scaffold and committed. The creatives ship as typeset editorial layouts, which is inside the brand lock. |
| The DoviLoop monogram on the creatives | No logo PNG exists in the repo or in Drive. Every creative carries the wordmark instead, typeset to the brand lock ("Dovi" teal, "Loop" orange, DM Sans regular, sitting directly on the layout). |
| Any ROI number in any ad | The campaign brief calls the ROI figures verified; `claims/evidence.json` says no customer outcome has ever been measured and that an investor flagged exactly this exposure. Followed the gate. BLOCKED.md entry 3. |
| A Meta API integration | The spec asks for a hand-built campaign and it is right. Automation at this spend costs more than it saves. |
| Lookalike audience | Needs 100 seeds minimum. There will not be 50 form submitters in six weeks. Documented and left unused, exactly as the spec asks. |
| Touching the product Supabase, any migration, any auth | Forbidden, and not needed. |

---

## What Dovy has to do

Ordered by what unblocks the most. Total about **65 minutes**, of which 20 is the
campaign build the spec estimated and the rest is wiring that was already on the
checklist in `00-START-HERE.md`.

| # | Task | Time | Why it matters |
|---|---|---|---|
| 1 | **Install the pixel on both domains.** `campaigns/pixel-install.md`, steps 1 to 6. | **25 min** | Do this today, before anything else. Every audience in the campaign is empty until it has been collecting for two weeks. It costs nothing and it is the only piece that compounds. |
| 2 | **Answer the ROI question.** Where do 9x, EUR 400 a month and 40-day payback come from? Either add the source to `claims/evidence.json` and flip the status, or confirm they are a model and stay out of ads. | **5 min** | Unlocks a stronger `s07` creative. Do not simply flip the flag; the gate exists for this exact moment. BLOCKED.md entry 3. |
| 3 | **Open the Meta Ad Library in a browser.** Search Fyxer, Superhuman, Jace. Note which angle the longest-running ads lead with. | **10 min** | The one research input I could not get. Whichever objection those ads lead with should go to the top of the creative rotation. |
| 4 | **Build the campaign.** `campaigns/structure.md`, steps 0 to 3. Around 22 September, not 8 September. | **20 min** | The audiences have to exist first, which is why step 1 is today and this is in three weeks. |
| 5 | Decide which brief is canonical on price and destination, and update the loser. | **5 min** | `00-START-HERE.md` says $89 + $500 setup and `teams.doviloop.dev`; `docs/ICP-BRIEF.md` says $49/$99 and `doviloop.dev`. No shipped creative depends on it, but the next person will trip on it. |
| Optional | Drop a transparent `logo.png` into `creative/static/assets/`, re-run the renderer. | 2 min | Adds the monogram to all 16 creatives. |
| Optional | Run the eight bed prompts through Nano Banana Pro, save to `creative/static/beds/`, re-render. | 20 min | Turns typeset-only creatives into full hybrid ones. The typeset versions are shippable as they stand. |
| Optional | Reconcile the PostHog event names with Batch A. | 10 min | Only matters for audience 3, the pricing viewers. |

Read `BLOCKED.md` alongside this. Every entry names what unblocks it and how
long it takes.

---

## The one thing worth arguing with

`campaigns/structure.md` recommends **not launching on 8 September** and running
four weeks from around 22 September instead. That is a departure from the
campaign window in the brief, made because retargeting against an audience that
does not exist yet is spending for the sake of the calendar. If you disagree,
the fix is one line: launch on 8 September with `as1` only and add the other two
ad sets when the pools fill. Do not launch all three against empty audiences.

And the honest frame from the repo's own README still holds after six weeks of
work on it: **judge this on what it teaches, not on pipeline.** By the end of
October you will know which of five objections makes an accountant stop
scrolling, for about EUR 450. That answer is worth more in outreach subject lines
and on the landing page than the clicks are.
