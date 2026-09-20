# ad-engine — Claude Code context

Meta ads for DoviLoop. This file is a router and is re-read every turn, so it
stays short.

## Before you touch ad copy

**Read `.claude/skills/meta-ads/references/claims.md`.** DoviLoop has zero
customers and zero measured outcomes. Every factual assertion in an ad must
resolve to a `verified` entry in `claims/evidence.json`, or it does not ship.

⚠️ **`engine/gate.py` is a backstop, not the check.** It is five regexes hunting
for digits. `"Save ten hours a month"`, `"Cut your reply time in half"` and
`"Most firms see faster turnaround"` all pass it clean and are all unverifiable.
Reason about the claim, not the digit. Run it anyway:

```bash
python -m engine.cli check
```

## Where things are

| | |
|---|---|
| `docs/META-ADS-RUNBOOK.md` | **A-to-Z.** Vocabulary, account setup, pixel, launch, operating loop. Start here if anything is unclear |
| `docs/META-MCP-SETUP.md` | What the Meta MCP connector can and cannot do, and why |
| `docs/META-MCP-MAP.md` | The same thing as three diagrams |
| `.claude/skills/meta-ads/` | The skill. Loads the above on demand; also packageable for Claude Desktop |
| `docs/ICP-BRIEF.md` | Who we sell to and how to talk about it. Locked 2026-08-31 |
| `claims/evidence.json` | Canonical: what may be claimed |

## Commands

```bash
python -m engine.cli plan                    # audiences in priority order, with blockers
python -m engine.cli check                   # claims gate over creative/
python -m engine.cli preflight               # runbook 6.3 launch checklist; non-zero if blocked
python -m engine.cli preflight --audience <built.csv>   # ...and size-check the built audience
python -m engine.cli audience <src.csv>      # hash an outreach list into a Custom Audience
python scripts/sync_skill_claims.py          # regenerate the skill's claims copy
python scripts/sync_skill_claims.py --check  # fail if it is stale
```

## Standing facts

- **~750 firms total.** The custom audience is ~2,000 people. It clears Meta's
  1,000 floor **only** with both countries and all three verticals combined —
  **never split it**. One campaign, one ad set, two ads.
- **No ROAS, no CPA, no conversion optimisation.** Meta wants ~50 events per ad
  set per week to leave the learning phase; this account will never supply that.
  Meta will not optimise, it will just spend. **Frequency is the primary metric.**
- **The connector CAN create and populate audiences** — `ads_create_custom_audience`
  (subtype `CUSTOM`) then `ads_update_custom_audience_users`. Verified against the
  live tool list 2026-09-16. ⚠️ Earlier docs in this repo said the opposite; they
  were wrong and are corrected.
  **Still pre-hash locally** with `python -m engine.cli audience`: the MCP tool will
  hash raw PII server-side, but `engine/audience.py` exists so the raw list never
  leaves this machine. Pass the already-hashed values — 64-char hex passes through
  unchanged.
- **Live account**: `620456015062432` — renamed **"DoviLoop Ads"**, MCP-enabled,
  ACTIVE, **currency DKK** (permanent), min daily budget DKK 6.46.
  ✅ **A payment method is attached** (read live 2026-09-19; it said "none" until
  then). ⚠️ `business_id` is still empty — the **DoviLoop** business portfolio
  exists and owns the Page and the pixel, but **not** this ad account: Meta
  refuses the claim until it has billed a first real payment, not merely seen a
  card. Retry after the first invoice. Until then there is no
  Business-Settings → Domains screen for this account, so `doviloop.dev` cannot
  be verified and Aggregated Event Measurement is unavailable. Neither gates a
  `LINK_CLICKS` campaign.
- **Pixel / dataset `1584074833462346`** — named "DoviLoop teams campaign",
  **owned by the DoviLoop business**, receiving events since 2026-09-12, and
  connected to the ad account. The pixel audiences are blocked on *time*, not
  on wiring.
- **Destination is live**: `https://teams.doviloop.dev/` serves the campaign page
  on `/`, `/da` and `/lt`, no redirects, own certificate. Cut over 2026-09-18 by
  adding a `teams` CNAME that beats the `*.doviloop.dev` wildcard; nothing was
  deleted. ⚠️ This supersedes the `_decisions` entry of 2026-09-14 in
  `claims/evidence.json`, which named the `.vercel.app` deployment URL as
  canonical because the subdomain then 301'd to the product site.
- **Live on the account (2026-09-16, ALL PAUSED, nothing spending):**
  campaign `120252014714500563` "DoviLoop · EN traffic · DK+LT" — `OUTCOME_TRAFFIC`,
  CBO DKK 35/day · ad set `120252014715910563` — `LINK_CLICKS`/`IMPRESSIONS`,
  destination `WEBSITE`, DK+LT, ages 30-60 as a **hard** cap
  (`advantage_audience: 0`), geo-only (no interest IDs — the connector forbids
  inventing them and has no targeting-search tool). DSA beneficiary and payor
  both `DoviLoop`, founder-confirmed.
  ⚠️ **Superseded, still present:** campaign `120252014169110563` +
  ad set `120252014200110563` (`OUTCOME_AWARENESS`). Meta forbids changing a
  campaign objective, so switching to Traffic meant rebuilding. Paused and empty.
  ⚠️ **Frequency capping was lost** in that switch — it is a Reach-objective
  feature. Correct trade: the frequency warning applies to the ~2,000-person
  custom audience, not to broad DK+LT geo. It returns as the primary metric if
  the custom-audience campaign is ever built.
  **The funnel contract with `campaign-site` is `docs/FUNNEL-HANDOFF.md`** — read
  it before touching either side.
  **This is a practice campaign, not ICP validation** — English copy, broad interest.
  The number it buys is the real CPM. ⚠️ Read the **country breakdown**: LT is cheaper,
  so Meta will skew delivery there and the headline CPM will read as Lithuania's.
- **Nothing blocks a live ad any more.** The payment method landed 2026-09-19.
  What is left is the ad object itself: zero ads exist on the account.
  ⚠️ The Facebook Page claim above it was **wrong and is corrected** — read live
  2026-09-18 via `ads_get_user_pages`, the account can advertise as **`DoviLoop`,
  page_id `1294387330427112`** (two others exist: `garazasvilnius`, `All-Upper`).
  An ad creative's `page_id` is therefore available now. It remains true that no
  create-page tool exists, which is where the wrong claim came from.
- ⚠️ **"Two creative arms only" is superseded for this campaign.** It said
  `capacity` and `hours` mirror outreach-engine's arms, same variable, two
  channels — sound, and not what is going live. The founder chose the
  **objection variants** on 2026-09-19: three ads from `creative/copy/`,
  `v3-outlook` · `v4-europe` · `v2-voice`, each paired with its own static from
  `creative/static/out/`. `campaigns/structure.md` argues the case — at this
  spend the trustworthy reading is *which objection people respond to*, which
  capacity-vs-hours cannot test. The two arms stay in the repo, unused.
  The rule still holds where it counts: **one variable per test, and no third
  thing smuggled in beside it.**
- Danish and Lithuanian copy in `creative/*.json` is still
  `NEEDS_NATIVE_PROOFREAD`. It is not ready to ship — but it is **not on the
  critical path**. The founder's decision of 2026-09-17 runs the outreach audience
  as one combined ad set on the English page, because the list clears Meta's 1,000
  floor only with both countries together and so cannot be language-split. The
  proofread gates the four `/da` and `/lt` ad sets, which the pixel is holding
  anyway. `preflight` reports it without blocking; English placeholders still block.

## Build rules

1. Never write a number into ad copy that does not resolve in `evidence.json`.
2. Never split the custom audience.
3. Never unpause a campaign without being asked to. The connector creates paused;
   keep it that way until a human says otherwise.
4. Never report a metric that was not returned. "I didn't check" is a valid answer.
5. Ecommerce ad advice does not apply here. Flag it and move on, do not adapt it
   silently.
