# BLOCKED

Batch E, `campaign/e-ads`. Every item here was hit, logged, and worked around.
Nothing stopped the batch.

Format: what was missing, what it blocks, what unblocks it, and how long that
takes Dovy.

---

## 1. Meta Ad Library is unreachable from this session

**What happened.** Three routes tried, all failed:

```
$ curl -sS -A "<chrome UA>" "https://www.facebook.com/ads/library/?q=Fyxer"
http=403  size=481

$ curl -sS -A "<chrome UA>" "https://www.facebook.com/ads/library/async/search_ads/?q=Fyxer"
http=403  size=481

# headless Chromium, same proxy
Page.goto: net::ERR_CONNECTION_RESET at https://www.facebook.com/ads/library/?...

$ curl -sS "https://graph.facebook.com/v21.0/ads_archive?search_terms=fyxer&ad_reached_countries=US"
{"error":{"message":"An unknown error has occurred.","type":"OAuthException","code":1,...}}
```

The Graph endpoint is reachable and returns real API errors, so the block is not
network. `ads_archive` requires an access token and a verified identity, which is
a secret this session does not have and is not allowed to use.

**What it blocks.** The spec's strongest intended research signal: "ads that have
been running a long time are ads that work". No competitor ad was seen, so no
objection in `research/objections.md` is ranked by ad longevity.

**Workaround taken.** Objections were sourced from durable public objection
surfaces instead: security pages, FAQ pages, comparison pages and named dated
negative reviews. Every objection says how strong its evidence is, and
`research/objections.md` states in its own words which ones are thinner.

**What unblocks it.** Dovy opens `facebook.com/ads/library` in a normal browser,
searches Fyxer, Superhuman and Jace, and notes which angle the longest-running
ads lead with. **About 10 minutes.** Whichever objection those ads lead with
should be promoted to the top of the creative rotation in
`campaigns/structure.md`.

---

## 2. G2, Capterra (Fyxer listing) and Reddit are bot-blocked

```
g2.com/products/fyxer-ai/reviews          -> HTTP 403
capterra.com/p/10015399/Fyxer-AI/reviews/ -> HTTP 404
reddit.com/r/Accounting/search.json       -> HTML, not JSON
old.reddit.com/search.json                -> HTTP 302
```

**What it blocks.** Buyer-stated objections in the buyer's own words, which is
exactly what negative reviews are best for.

**Workaround taken.** Trustpilot was reachable and supplied five named, dated
reviews, three of them one-star. The Conversifi listing on Capterra loaded. The
gap is visible in `research/objections.md`: objection 4 has no buyer quote at
all and says so.

**What unblocks it.** Dovy opens the G2 Fyxer and Superhuman pages in a browser
and reads the 1 and 2 star reviews. **About 15 minutes**, and it would firm up
objections 2 and 4.

---

## 3. The ROI figures conflict with the repo's own claims gate

**The conflict.** `00-START-HERE.md` lists as available proof: "verified ROI
figures (~9x ROI, ~EUR 400/month saved, ~40-day payback)".
`claims/evidence.json` in this repo says the opposite, in writing:

- `hours_saved`: UNVERIFIED. "No measured customer outcome exists. The pricing
  page's '10 hours a month' is a modelled estimate, not an observation."
- `percentage_claim`: UNVERIFIED. "No measured percentage outcome of any kind
  exists."
- `customer_count`: UNVERIFIED. "Zero closed customers as of 2026-08-31."

Both cannot be true. The gate also carries an explicit warning that an investor
flagged public measurable promises with nothing behind them as real exposure for
a company with no liability cap and no insurance.

**What Batch E did.** Followed the gate. No ROI number, no percentage, no
time-saving figure and no customer count appears in any of the 8 creatives or
any of the 6 copy variants. All 6 variants pass `python -m engine.cli check`.

**What it blocks.** Creative `s07-roi`, which the spec asked to build on the ROI
figures, is instead built on the *shape* of the arithmetic without asserting an
outcome. It invites the reader to run the numbers on their own firm rather than
claiming a result. It is a weaker ad than a number-bearing one would be.

**What unblocks it.** One answer from Dovy: where do 9x, EUR 400/month and
40-day payback come from? If they are the revenue model spreadsheet
(`DoviLoopRevenueModel` in Drive has "Value delivered per seat / month: 400" and
an "ROI multiple to client" column, both flagged in the sheet itself as
assumptions to verify), then they are a **model**, not a measurement, and the
gate is right to block them. In that case the ad can still say "run it on your
own numbers" but must never say "9x".

If instead a real customer measurement exists somewhere I could not see, add it
to `claims/evidence.json` with the source, flip the status to `verified`, and
the number-bearing variant becomes writable in about 20 minutes.

**Do not simply flip the flag to unblock the copy.** The whole point of the gate
is that this is the moment when that happens.

---

## 4. No DoviLoop logo asset exists in this repo

**What is missing.** `references/brand-lock.md` requires the interlocking L-D
monogram as a backgroundless transparent PNG. There is no image file in this
repo and none was found in Google Drive.

**What it blocks.** The monogram does not appear on any of the 16 rendered
creatives.

**Workaround taken.** Every creative carries the **wordmark** instead, typeset
exactly to the brand lock: "Dovi" in teal `#2A6C7C` and "Loop" in orange
`#E96C32`, DM Sans regular, sitting directly on the layout with clear space, no
tile or container. That is an approved lockup form in the brand lock.

**What unblocks it.** Drop `creative/static/assets/logo.png` (transparent) into
the repo and re-run `python -m creative.static.render all`. The renderer already
looks for that path and places the mark to the left of the wordmark when it
exists. **About 2 minutes** once the file is to hand.

---

## 5. No image-generation model in this session, so no photographic beds

**What is missing.** `hm-static-ad-generator` defaults to hybrid mode: a model
generates a photographic or illustrative bed, and the brand-critical type layer
is typeset over it. There is no Nano Banana Pro, Higgsfield or equivalent image
call available here.

**What it blocks.** The bed half of hybrid mode. Nothing else. The typesetting
half runs, and is proven in `AUDIT.md` section 2.

**Workaround taken.** All 8 creatives are built as typeset editorial layouts on
solid brand grounds, which is fully inside the brand lock, plus product-realistic
Outlook draft cards drawn in CSS where a creative needs concrete proof. A written
Nano Banana Pro bed prompt is committed for every creative in
`creative/static/beds/`, each following the skill's Mode A scaffold.

**What unblocks it.** Dovy runs the eight bed prompts through Nano Banana Pro,
saves the results as `creative/static/beds/sNN.png`, and re-runs the renderer.
The layouts already accept a bed image behind the type. **About 20 minutes** for
all eight, and it is optional. The typeset-only versions are shippable as they
stand.

---

## 6. No Meta account, no pixel, no ad account, so no live Insights call

**What is missing.** Meta Business account, ad account id, pixel id, and a system
user access token. None exist and none may be created here.

**What it blocks.** The live run of `report/pull_ad_stats.py`. Also the
`site-retargeting` audience that `audiences/site-retargeting.json` already
flagged as blocked before this batch started, and every audience in
`campaigns/structure.md` that depends on the pixel.

**Workaround taken.** `report/pull_ad_stats.py` is written against the real
Insights response shape, runs clean in `--dry-run` mode against
`report/fixtures/insights_sample.json`, and is covered by tests. `.env.example`
lists every variable it needs, with no secret values.

**What unblocks it.** Dovy's own wiring checklist: create the Meta Business
account and pixel, install the pixel on both domains per
`campaigns/pixel-install.md`, then set `META_AD_ACCOUNT_ID` and
`META_ACCESS_TOKEN` in `.env`. **About 20 minutes**, and it is already on the
checklist in `00-START-HERE.md`.

---

## 7. `campaign_db.py` does not exist in this session (Batch B dependency)

**What is missing.** Batch B owns `campaign_db.py` in the `campaign-ledger` repo,
which this session cannot see or write to. It is the module that
`report/pull_ad_stats.py` is supposed to call `snapshot_ad_stats` on.

**What it blocks.** Nothing, by design.

**Workaround taken.** The import is defensive. `report/pull_ad_stats.py` tries
`from campaign_db import snapshot_ad_stats`, and on `ImportError` falls back to a
local shim in `report/ledger_shim.py` that writes the same rows to a JSONL file
and logs loudly that the ledger is not connected. The code runs and the tests
pass with or without Batch B. The seam is documented in `RUN-REPORT.md`.

**What unblocks it.** Put `campaign_db.py` on the `PYTHONPATH` when the ledger
repo lands. **About 1 minute.** No code change needed on this side.

---

## 8. The campaign brief and the repo brief disagree on price and destination

Not a blocker, recorded so nobody has to rediscover it. Full table in `AUDIT.md`
section 5.

- Price: brief says $89/seat + $500 setup, `docs/ICP-BRIEF.md` says $49/$99 with
  $750 onboarding. Batch E followed the campaign brief and put **no price in any
  creative**, so nothing shipped breaks either way.
- Destination: brief says `teams.doviloop.dev`, the repo's two pre-existing
  creatives point at `doviloop.dev`. All new copy uses `teams.doviloop.dev`. The
  two old files were left alone.

**What Dovy should do.** Decide which brief is canonical and update the loser.
**About 5 minutes.**
