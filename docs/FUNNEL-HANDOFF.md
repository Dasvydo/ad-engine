# Meta ads ↔ landing page — session handoff

> Written 2026-09-16. **Self-contained by design** — assume the reader has neither
> the originating conversation nor both repos. Lives identically in `ad-engine/docs/`
> and `campaign-site/docs/`.
>
> **Purpose.** The Meta ads side and the `campaign-site` landing page are being built
> in separate sessions. This is the contract between them: live state, what each side
> owes the other, and the constraints neither may break.

---

## 1. Live Meta state — verified against the account, not asserted

```
Ad account   620456015062432   "Dovydas Vinickis"
             MCP-enabled ✓  ACTIVE ✓  queryable ✓
             currency DKK (PERMANENT)  ·  min daily budget DKK 6.46
             NO payment method   NO Business Manager (personal account)

Campaign     120252014714500563   "DoviLoop · EN traffic · DK+LT"
             OUTCOME_TRAFFIC · CBO DKK 35/day · LOWEST_COST_WITHOUT_CAP · PAUSED

Ad set       120252014715910563   "DK+LT · 30-60 · broad geo · link clicks"
             LINK_CLICKS / IMPRESSIONS · destination WEBSITE
             DK + LT · ages 30-60 HARD cap (advantage_audience: 0)
             geo-only, no interests · DSA beneficiary+payor = "DoviLoop" · PAUSED

Pages            0   ← blocks any ad
Pixels/datasets  0   ← nothing exists on Meta's side
Custom audiences 0
Spend            0.00
```

**Superseded, still present:** campaign `120252014169110563` (`OUTCOME_AWARENESS`)
and ad set `120252014200110563`. Meta does not allow changing a campaign's
objective, so the switch to Traffic required rebuilding. Both are paused and
empty; delete them whenever.

---

## 2. What the Meta MCP can and cannot do

**Read from the live tool list, not from blog posts.** Earlier notes in `ad-engine`
claimed otherwise and were wrong; correction banners are on those files.

| Can | Cannot |
|---|---|
| Reporting, insights, benchmarks | **Create an ad account, Page, or pixel** |
| Native anomaly detection (`ads_insights_anomaly_signal`) | **Add a payment method** (regulated) |
| Create campaigns / ad sets / ads — **land PAUSED** | **B2B firmographic targeting** — does not exist on Meta at all |
| Activate and pause (`ads_activate_entity`) | **Pick interest IDs** — inventing them is forbidden and there is no targeting-search tool |
| **Create and populate custom audiences** (`ads_create_custom_audience` + `ads_update_custom_audience_users`) | Accept terms of service on a human's behalf |
| Read and upload creative (`ads_get_ad_preview`, `ads_get_ad_images`, `ads_creative_upload_image`) | |
| Ad Library search (`ads_library_search`) | |
| Pixel event config — on a pixel that already exists | |

**"Creates paused" is a default, not a guardrail** — an activate tool exists. The
real control is keeping every write tool on *needs approval* in connector settings.

---

## 3. The interface — what each side owes the other

### Landing page → Meta

| # | Owed | Status |
|---|---|---|
| L1 | **The production URL the ads point at.** `teams.doviloop.dev` **301s to `www.doviloop.dev`**; the page actually serves from `campaign-site-azure.vercel.app`. The ad needs a final, stable URL | ⛔ **unresolved — biggest open item** |
| L2 | **UTM convention** so PostHog can attribute. Nothing is agreed yet | ⛔ open |
| L3 | Confirmation the page renders correctly on mobile — nearly all Meta traffic is mobile | ⛔ unchecked |
| L4 | `VITE_META_PIXEL_ID` set in Vercel (Production **and** Preview) + redeploy | ⛔ waiting on M2 |

### Meta → landing page

| # | Owed | Status |
|---|---|---|
| M1 | A Facebook Page — blocks every ad | ⛔ founder, browser |
| M2 | A pixel ID for L4 | ⛔ founder, browser |
| M3 | Payment method | ⛔ founder, browser |

### Already built on the landing page — do not rebuild

Audited 2026-09-16 in `campaign-site`:

- **Pixel injection behind a real consent gate** (`src/lib/pixel.ts:37-84`,
  `src/lib/consent.ts`). Empty `VITE_META_PIXEL_ID` → fully inert: no script, no
  cookie, no `window.fbq`.
- **Four events already wired**: `PageView` · `ViewContent` (dwell-gated on the
  pricing band) · `Lead` (qualifier submit) · `Schedule` (booking click).
- **The gate is tested** — `scripts/verify-consent.mjs` asserts zero network, zero
  cookies and no `fbq` before consent, exactly one script after.

**So the landing page's Meta work is essentially done.** It needs the pixel ID and
a redeploy, nothing more.

---

## 4. Why the campaign is Traffic and not Leads

`OUTCOME_LEADS` optimisation needs roughly **50 conversion events per ad set per
week** to leave Meta's learning phase. This account will produce single digits.
Meta would never optimise — it would just spend, while reporting noise as signal.

`LINK_CLICKS` is honest at this volume. `LANDING_PAGE_VIEWS` would be better
quality but **requires the pixel**, which does not exist yet — worth switching to
once M2 and L4 land.

⚠️ **Frequency capping was lost in the switch.** It is a Reach-objective feature.
That was the right trade: the frequency warning in older notes was about a
**~2,000-person custom audience**, where saturation is days away. On broad DK+LT
geo the pool is millions and frequency is not the binding constraint. **If the
custom-audience campaign is ever built, frequency becomes the primary metric again.**

---

## 5. Hard constraints — do not break these

1. **Every factual claim in ad copy, a Page bio, or landing page copy must resolve
   to a `verified` entry in `ad-engine/claims/evidence.json`.** DoviLoop has zero
   customers and zero measured outcomes. An investor specifically flagged a public
   measurable promise with nothing behind it as real exposure.

   `python -m engine.cli check` is a **backstop, not the check** — five regexes
   hunting for digits. Measured 2026-09-16: `"Save ten hours a month"`,
   `"Cut your reply time in half"`, `"Most firms see faster turnaround"` and
   `"Save hours every week"` all pass clean and are all unverifiable.
   **Reason about the claim, not the digit.**

   Safe, because each is a verifiable product fact: never auto-sends · never leaves
   Outlook · EU-hosted · answers from the firm's own documents · a voice profile
   per person.

2. **Never unpause anything without the founder saying so.**

3. **Never split the custom audience** if one is built. It clears Meta's 1,000
   floor only with both countries and all three verticals combined.

4. **Never report a metric that was not returned.** "I didn't check" is valid.

5. **Read the country breakdown.** Lithuania is cheaper, so Meta skews delivery
   there. A headline CPM will effectively be Lithuania's. Denmark is the number
   that matters — it is the buildable side of the ICP.

---

## 6. Known problems that are not this funnel's fault

- **`doviloop.dev` has no consent mechanism at all**, yet already runs RB2B
  (`index.html:31-32`) and PostHog with cookies, autocapture and **session
  recording on**, to a **US host**. Pre-existing GDPR exposure. A pixel cannot
  lawfully be added there until it is fixed. `campaign-site` uses PostHog's **EU**
  host — the inconsistency is worth a deliberate decision.
- **The ICP outreach list does not exist.** `outreach-engine` can gate and export a
  list but cannot *produce* one; `segments/` holds 3 example rows with fake
  domains, `queue/*.csv` is gitignored, and the Lithuanian registry fetchers are
  deliberately unimplemented. **This is why the current campaign is broad-interest
  practice, not ICP targeting.**
- **`da` / `lt` ad copy is still `NEEDS_NATIVE_PROOFREAD`.** English-only is the
  shippable option.

---

## 7. Open decisions for the founder

| | |
|---|---|
| **The production URL** (L1) | The single biggest blocker to a working funnel |
| UTM convention (L2) | Pick one before the first ad runs, or attribution is guesswork |
| Business Manager? | Not blocking. Ad account and Page are both personal; tidier under one later |
| Delete the superseded Awareness campaign? | Paused and empty; harmless either way |

---

## 8. How to pick this up

```bash
python -m engine.cli preflight   # launch checklist; non-zero while blocked
python -m engine.cli check       # claims gate over creative/
python -m engine.cli plan        # audiences in priority order, with blockers
```

Deeper context in `ad-engine/`: `docs/META-ADS-RUNBOOK.md` (A-to-Z, vocabulary
first) · `docs/BUSINESS-MANAGER-WALKTHROUGH.md` (the click-by-click and the
ordered path to a live ad) · `docs/META-MCP-SETUP.md` and `docs/META-MCP-MAP.md`
(both carry correction banners) · `CLAUDE.md` (standing facts, re-read every turn).

**The Meta connector must be enabled in whichever session needs it.** It is a
claude.ai connector named `META_MCP` on the same account — enable it per chat.
