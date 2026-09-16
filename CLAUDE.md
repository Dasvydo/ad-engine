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
- **Live account**: `620456015062432` ("Dovydas Vinickis"), MCP-enabled, ACTIVE,
  **currency DKK** (permanent), **no payment method**, **no Business Manager**
  (`business_id` empty — it is a personal ad account). Min daily budget DKK 6.46.
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
- **Blocking a live ad:** no payment method, and **no Facebook Page** — an ad's
  creative needs a `page_id`, and there is no create-page tool. Both are founder-only.
- **Two creative arms only**: `capacity` (untested, recommended) and `hours`
  (control). They mirror outreach-engine's arms deliberately — same variable,
  two channels. Do not add a third.
- Danish and Lithuanian copy in `creative/*.json` is still
  `NEEDS_NATIVE_PROOFREAD`. It is not ready to ship.

## Build rules

1. Never write a number into ad copy that does not resolve in `evidence.json`.
2. Never split the custom audience.
3. Never unpause a campaign without being asked to. The connector creates paused;
   keep it that way until a human says otherwise.
4. Never report a metric that was not returned. "I didn't check" is a valid answer.
5. Ecommerce ad advice does not apply here. Flag it and move on, do not adapt it
   silently.
