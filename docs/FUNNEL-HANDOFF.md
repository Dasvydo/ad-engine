# FUNNEL-HANDOFF — the contract between the ad and the page

> Written 2026-09-16. Self-contained: assumes no prior conversation and no
> access to the other repo. Everything marked **measured** was run on that date;
> everything else says plainly that it was not.

The funnel is **Meta ad → landing page → qualifier form → booking**. Two repos
own the two halves and they have to agree on three things: **where the click
lands**, **what the URL says about itself**, and **what the page sends back to
Meta**. This file is that agreement.

| Half | Repo | Owns |
|---|---|---|
| The ad | `ad-engine` | audiences, creative, claims gate, destination URLs |
| The page | `campaign-site` | landing page, consent, pixel, UTM capture, lead payload |

---

## ⛔ Blocker 1 — there is no stable destination URL

**Nothing is safe to put in an ad yet.** This is the first job, and it blocks the
ad regardless of the Facebook Page or the payment method.

### What the hosts actually do — measured 2026-09-16

| Request | Result |
|---|---|
| `https://teams.doviloop.dev/` | **301** → `http://doviloop.dev` — server `openresty`, IPs `207.207.210.107` / `.229`, which are **not Vercel** |
| `http://doviloop.dev` | 308 → `https://doviloop.dev/` |
| `https://doviloop.dev/` | 307 → `https://www.doviloop.dev/` |
| `https://www.doviloop.dev/` | 200 · `<title>DoviLoop — The inbox assistant that runs on your knowledge</title>` — **the product site** |
| `https://campaign-site-azure.vercel.app/` | 200 · `<title>DoviLoop for teams</title>` — **the campaign page** |

Three hops, one of them plain `http`, landing on the wrong page. `openresty` on
non-Vercel IPs means `teams` is a **registrar URL-forward**, not a Vercel domain.

The failure mode is the nasty one: it returns 200, so a link checker passes it.
Every paid click would land on the product homepage — no qualifier, no pixel, no
UTM capture, different offer, different price.

**Do not put `teams.doviloop.dev` in an ad until the forward is removed.**

### Why the `.vercel.app` URL is not a workaround

`vercel.app` is on the Public Suffix List. Meta verifies domains at **eTLD+1**
and will not verify an eTLD+2, so `campaign-site-azure.vercel.app` can never be
a verified domain — no Aggregated Event Measurement, and the ad shows a URL that
reads as staging. (Meta Business Help `321167023127050`; consistent with Vercel's
own public-suffix troubleshooting. Read, not tested against a live Business
Manager — **unverified in practice**.)

### The fix — founder, ~10 min plus DNS propagation

1. Delete the URL-forward on the `teams` record at the DNS provider for `doviloop.dev`.
2. Vercel → the `campaign-site` project → **Settings → Domains → Add** → `teams.doviloop.dev`.
3. Add `CNAME  teams  →  cname.vercel-dns.com`. Not an A record. No Cloudflare
   orange cloud on first issuance or the TLS challenge fails.
4. Wait for green in Vercel; the certificate is automatic.
5. Load `/`, `/da`, `/lt` on the custom domain.

Already written up in full at `campaign-site/README.md` §4.

### One code change that must follow the DNS change

`campaign-site/src/LocalePage.tsx:26` pins

```ts
const SITE_ORIGIN = 'https://campaign-site-azure.vercel.app';
```

and that origin is written into `canonical`, `og:url` and every `hreflang`
alternate. Once `teams.doviloop.dev` serves the page, flip this to
`https://teams.doviloop.dev` and redeploy — otherwise the ads point at one origin
while the page declares another.

### Domain to verify in Business Manager

**`doviloop.dev`** — the apex, not `teams.doviloop.dev`. Verification at eTLD+1
covers the subdomain.

---

## ⛔ Blocker 2 — the UTM convention, which is not actually free to choose

Pick it before the first ad or attribution is guesswork. **But most of it is
already decided by code that exists.**

`campaign-site/src/lib/attribution.ts` → `resolveSource()` maps the incoming UTMs
onto a coarse enum, and that enum is the `source` field of the lead payload the
n8n side and the ledger read. Send UTMs it does not recognise and every paid lead
files itself as `direct`.

### The convention

```
https://teams.doviloop.dev/<locale>?utm_source=meta&utm_medium=paid_social&utm_campaign=<market>-<audience>&utm_content=<creative_id>
```

| Parameter | Value | Why it is not free |
|---|---|---|
| `<locale>` | *(empty)* = en · `da` · `lt` | The only three routes — `campaign-site/src/App.tsx`. Anything else redirects to `/`. |
| `utm_source` | literal `meta` | Matched at `attribution.ts:107` to derive `source: 'ad'`. `facebook` and `instagram` also match. |
| `utm_medium` | literal `paid_social` | Also matched at `attribution.ts:107`. Belt and braces: either one alone is enough. `cpc` and `paid` also match. |
| `utm_campaign` | `<market>-<audience>` | e.g. `dk-outreach-list`, `lt-outreach-list`, `dk-retargeting`, `global-broad-interest`. `<audience>` is an `audiences/<id>.json` id. |
| `utm_content` | the `creative/<id>.json` id | `capacity` or `hours`. **This is the A/B split key** — it is what separates the two arms in PostHog. Nothing else does. |

Optional, when an English page is served to a DK or LT audience:
`&market=dk` · `&market=lt` — read by `resolveMarket()`, `attribution.ts:150`.

Also available: `&source=ad` overrides the derivation outright. Reserved for
outreach links; ads should not need it.

### Two constraints that will bite if ignored

- **Exactly four UTM fields exist.** `campaign-site/src/lib/contract.ts:31` defines
  `source`, `medium`, `campaign`, `content` and nothing else. A fifth parameter —
  `utm_term`, or a Meta macro like `{{ad.id}}` in the URL-parameters field — is
  read by nothing, reaches neither the payload nor PostHog, and silently
  disappears. Do not build reporting on one.
- **First touch wins for the session.** UTMs are captured on first load and held
  in `sessionStorage` under `dl_utm` (`attribution.ts:46`). An ad click keeps the
  credit even if the visitor wanders to pricing and comes back on a bare URL.

---

## ✅ What the page already gives Meta — nothing to rebuild

**Verified 2026-09-16** by running `npm run verify:consent` in `campaign-site`:
23 assertions, all PASS, `CONSENT GATE HOLDS`. (Previously read but not executed;
this is now an executed result.)

| Pixel event | Fires on | Where |
|---|---|---|
| `PageView` | pixel init, after consent | `src/lib/pixel.ts:73` |
| `ViewContent` · `content_name: 'pricing'` | dwell-gated pricing view | `src/LocalePage.tsx:127` |
| `Lead` | qualifier submitted | `src/LocalePage.tsx:149` |
| `Schedule` | booking link clicked | `src/LocalePage.tsx:157` |

The gate, proven by that test: before a choice, no script is injected, `window.fbq`
is undefined, no cookie is written. Declining keeps it that way. Accepting loads
it exactly once. Global Privacy Control is honoured as a decline and the notice
never appears.

**It needs one thing:** `VITE_META_PIXEL_ID` set in the Vercel project, then a
redeploy. With it empty the pixel is completely inert — deliberate, for EU consent
reasons. See `campaign-site/.env.example` §5.

---

## Still founder-only, unchanged

- Create the Facebook Page.
- Add a payment method to the ad account.
- Create the pixel in Events Manager, then paste its ID into Vercel as
  `VITE_META_PIXEL_ID` and redeploy.
- Verify `doviloop.dev` in Business Manager.
- Remove the `teams` URL-forward and add the domain in Vercel (Blocker 1).

---

## Misalignments found on 2026-09-16

Four. The first three are fixed in this change; the fourth is flagged, not settled.

1. **Creative pointed at the wrong site.** `creative/capacity.json` and
   `creative/hours.json` both carried `"destination": "https://doviloop.dev"` —
   the product site, which 307s to `www` and has no qualifier, no pixel and no
   UTM capture. `campaign-site/src/LocalePage.tsx:22` asserts *"The ad-engine repo
   was repointed at the deployment on 2026-09-14"*. **It was not.** `ad-engine`
   has a single commit dated 2026-08-31. **Fixed** — both files now carry a
   `destination` block with the three locale URLs and the UTM contract above.

2. **`audiences/site-retargeting.json` described a pixel that does not exist
   where it said.** It was blocked on "pixel not installed on doviloop.dev". The
   pixel is built, consent-gated and tested — on the **campaign site**, needing
   only the env var. Still true: nothing is on `www.doviloop.dev`, so the
   retargeting pool sees campaign traffic only until the pixel also goes on the
   product site (`campaign-site/.env.example` §5 says it should). **Corrected.**

3. **An audience referenced from the page did not exist.** `LocalePage.tsx:129`
   names *"ad-engine's audience 3 (pricing viewers, 90 days)"* as the reason the
   `ViewContent` event exists. Audience 3 in this repo is `broad-interest`; no
   pricing-viewer audience was ever here, so the event was firing into nothing.
   **Added** as `audiences/pricing-viewers.json`.

4. **Three repos state three different prices.** Not settled here — it is a
   founder decision, and an ad must not disagree with the page it lands on.
   - `ad-engine/docs/ICP-BRIEF.md` — $49/seat design partner, $99/seat standard
   - `campaign-site/BLOCKED.md` — "89 USD per seat per month plus 500 USD setup", recorded as a decision of 2026-09-06
   - the product repo's `CLAUDE.md` — Individual $20/mo, Teams $44/mo

   The landing page renders one of these. Settle it before spend starts.

---

## The order of operations

Nothing below can be skipped by doing a later step first.

1. Remove the `teams` URL-forward · add the domain in Vercel · `CNAME`. *(founder, ~10 min + DNS)*
2. Flip `SITE_ORIGIN` in `campaign-site/src/LocalePage.tsx:26` · redeploy.
3. Create the pixel · set `VITE_META_PIXEL_ID` in Vercel · redeploy. *(founder)*
4. Verify `doviloop.dev` in Business Manager. *(founder)*
5. Let the pixel collect. `site-retargeting` and `pricing-viewers` have nobody in
   them until it does, and both need a head start on the ads.
6. Settle the price disagreement (misalignment 4).
7. Native proofread of `da` and `lt` creative — every non-English field in
   `creative/*.json` still reads `NEEDS_NATIVE_PROOFREAD`, and the same caveat is
   open on the landing copy (`campaign-site/BLOCKED.md` §6).
8. `python -m engine.cli check` must pass. Then ads.
