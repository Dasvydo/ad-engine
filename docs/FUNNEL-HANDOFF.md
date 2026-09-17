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

### Who is actually serving it — measured 2026-09-17

| Lookup | Answer |
|---|---|
| `doviloop.dev` NS | `salvador` · `curitiba` · `maceio` · `fortaleza` `.ns.porkbun.com` |
| `teams.doviloop.dev` CNAME | **`pixie.porkbun.com`** → `207.207.210.107` / `.229` |
| TLS on the teams host | Let's Encrypt, `CN=doviloop.dev`, SAN `*.doviloop.dev` |

`pixie.porkbun.com` is **Porkbun's URL-forwarding host**. So this is not a
misconfigured DNS record to repoint — it is a URL Forward entry in the Porkbun
control panel, and it has to be deleted there. The wildcard certificate is why
the hop is silent: it terminates TLS correctly and then 301s, which is what makes
a link checker pass it.

### The fix — founder, ~15 min plus propagation

Order matters. Porkbun creates the forwarding record itself, so a hand-written
CNAME for the same host will collide with it until the forward is gone.

**1 · Delete the URL forward.**
Porkbun → *Domain Management* → `doviloop.dev` → **URL Forwarding**. Find the row
for the `teams` subdomain and delete it.

**2 · Confirm the record actually went.**
Same domain → **DNS Records**. There should now be no `teams` record at all. If an
`ALIAS` or `CNAME` pointing at `pixie.porkbun.com` is still listed, delete it by
hand — the forward's record occasionally outlives the forward.

Check from a terminal:

```
curl -sS "https://dns.google/resolve?name=teams.doviloop.dev&type=CNAME"
```

`pixie.porkbun.com` must be gone from the answer. Porkbun's default TTL is 600s,
so allow ten minutes (default not re-verified — **unverified**).

**3 · Add the domain in Vercel.**
Vercel → the **campaign-site** project → *Settings* → *Domains* → **Add** →
`teams.doviloop.dev`. Vercel then shows the record it wants. Use the value it
prints, not one from memory: it has been issuing per-project CNAME targets rather
than the old shared `cname.vercel-dns.com` for some time.

**4 · Create that record at Porkbun.**
DNS Records → Add:

| Type | Host | Answer | TTL |
|---|---|---|---|
| `CNAME` | `teams` | *(whatever Vercel printed)* | 600 |

A subdomain takes a real `CNAME`; Porkbun's `ALIAS` type is for the apex and is
not needed here.

**5 · Wait for the certificate.**
The domain goes green in Vercel on its own, usually under two minutes once DNS
has propagated. Nothing to click.

**6 · Prove it end to end.**

```
curl -sS -o /dev/null -w "%{http_code} %{url_effective}\n" -L https://teams.doviloop.dev/
curl -sS https://teams.doviloop.dev/ | grep -o "<title>[^<]*</title>"
```

Expected: **`200`**, no redirect chain, and the title **`DoviLoop for teams`**.
If the title says *"DoviLoop — The inbox assistant that runs on your knowledge"*
you are still landing on the product site and the forward is not gone.

Then check all three routes load on a hard refresh — `/`, `/da`, `/lt`. The SPA
rewrite in `vercel.json` already covers them.

**7 · Only now, the origin.**
Set `VITE_SITE_ORIGIN=https://teams.doviloop.dev` in the Vercel project and
redeploy. See the next section for why this is last rather than first.

### One setting that must follow the DNS change

The page declares its own origin in `canonical`, `og:url` and every `hreflang`
alternate. Meta scrapes `og:url` to build the ad's link preview, so an ad pointing
at one origin while the page names another is a mismatch visible **inside the ad**.

It was a literal in `campaign-site/src/LocalePage.tsx:26`. As of 2026-09-17 it
reads `VITE_SITE_ORIGIN`, defaulting to the same deployment URL — **behaviour
today is unchanged**. On cutover set

```
VITE_SITE_ORIGIN=https://teams.doviloop.dev
```

in the Vercel project and redeploy. No code edit, no rebuild from a branch.

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

## The ad-set matrix

One row per ad set. `<creative_id>` is `capacity` or `hours`; both run in every
ad set, because the arm is the variable being tested.

| Ad set | Audience | Lands on | `utm_campaign` | Extra |
|---|---|---|---|---|
| Outreach list, combined | `outreach-list` | `/` (en) | `global-outreach-list` | — |
| Retargeting · DK | `site-retargeting` | `/da` | `dk-retargeting` | — |
| Retargeting · LT | `site-retargeting` | `/lt` | `lt-retargeting` | — |
| Pricing viewers · DK | `pricing-viewers` | `/da` | `dk-pricing-viewers` | — |
| Pricing viewers · LT | `pricing-viewers` | `/lt` | `lt-pricing-viewers` | — |
| Broad interest (practice) | `broad-interest` | `/` (en) | `global-broad-interest` | — |

Full form, every time:

```
https://teams.doviloop.dev/da?utm_source=meta&utm_medium=paid_social&utm_campaign=dk-retargeting&utm_content=capacity
```

`&market=` exists as an override for when an ad set knows a market the page
cannot infer from its locale (`resolveMarket()` reads it). **No row above uses
it.** The two English rows are both mixed-country audiences, so there is no
single true value to send, and tagging one country would be a false label on
every lead from the other. Those leads carry `market: global`, which is the
honest answer — `utm_campaign` still says which audience they came from.

### Why the top-priority audience has no DK and LT rows — decided 2026-09-17

**You cannot both language-split the outreach audience and keep it targetable.**

`audiences/outreach-list.json` states the list is ~2,000 people — ~750 firms at
2–3 contacts — and clears Meta's 1,000 floor *"only with both countries and all
three verticals combined. A single-vertical slice will under-deliver."* Splitting
it into a DK ad set and an LT ad set is exactly that slice.

**Decision: one combined ad set on the English page.** Founder, 2026-09-17,
choosing delivery over localisation on this audience. The rejected alternative was
two ad sets at `/da` and `/lt` with `utm_campaign` of `dk-outreach-list` and
`lt-outreach-list`, accepting under-delivery in exchange for native-language
landing pages.

The cost is real and worth naming: the ICP brief calls Danish and Lithuanian copy
*"the most defensible thing on the board"*, and this is the one audience that
cannot use it. **If this ad set under-performs, language is a live hypothesis for
why** — and it is the one variable the ad set is structurally unable to test. Do
not read a flat result here as a verdict on the `capacity` / `hours` arms without
saying that out loud.

The two pixel audiences have no such problem: they are built from page traffic,
which already arrives language-sorted by which locale route it landed on. DK and
LT native copy still matters there, and those rows use it.

(The 1,000 figure is this repo's own assertion in `outreach-list.json`. Not
re-checked against Meta's current documented minimum — **unverified**.)

### What the decision unblocks

Both day-one ad sets — `outreach-list` and `broad-interest` — now land on the
English page with English creative. **Neither is blocked on the Danish and
Lithuanian proofread**, which was previously sequenced ahead of the first ad.
The proofread still gates the four `/da` and `/lt` rows, and those are blocked on
the pixel collecting anyway, so it is no longer on the critical path.

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

## The claims seam — fixed 2026-09-17

The ad copy passed the claims gate. **The page behind the click had never been
scanned**, and to a reader — or a regulator — the two are one unit.

### The gate was catching the wrong phrasings

Probed with nine strings. Five passed that should not have, including **both
figures the landing page actually renders**:

| Probe | Was | Now |
|---|---|---|
| `430 USD saved per month, for each person` | PASS | BLOCK · `money_saved` |
| `12x time saved, against what the firm pays` | PASS | BLOCK · `roi_multiple` |
| `Worth 4,300 USD a month to a ten person firm` | PASS | BLOCK · `money_saved` |
| `Pays for itself twelve times over` | PASS | BLOCK · `roi_multiple` |
| `Cuts your email time in half` | PASS | BLOCK · `hours_saved` |
| `Saves 10 hours a month` | BLOCK | BLOCK |
| `89 USD per month for the whole firm` | PASS | **PASS** — a price is a fact, not a claim |

Word order was the whole defect: `saves?\s+\d` needs save-then-digits, and the
page writes digits-then-saved. The gate blocked the phrasings nobody writes and
passed the two a buyer is actually shown. `money_saved` and `roi_multiple` are now
entries in `claims/evidence.json`, both UNVERIFIED.

### The page is allowed to say it. An ad is not.

`python -m engine.cli check --landing ../campaign-site/src/content` scans the
landing copy. Its findings are **advisory and do not fail the run**, deliberately:
the page states its modelled figure with *"These are a model, not a measurement"*
and *"Never yet checked against a real customer"* in the same eyeline. An ad
carries no disclosure, so the same figure lifted into one is the unbacked public
promise an investor warned about.

Current result: `en.ts`, `da.ts`, `lt.ts` all report the `430 USD saved` claim.
Creative: both arms PASS.

### One thing no static scan can see

The return multiple is **computed at runtime** from the modelled saving, a
ten-person firm and the active tier price. It never appears as a literal in any
content file, so `--landing` cannot report it and never will. It is on the page
regardless. Treat `roi_multiple` as live whether or not a scan mentions it.

## Still founder-only, unchanged

- Create the Facebook Page.
- Add a payment method to the ad account.
- Create the pixel in Events Manager, then paste its ID into Vercel as
  `VITE_META_PIXEL_ID` and redeploy.
- Verify `doviloop.dev` in Business Manager.
- Delete the `teams` URL Forward at **Porkbun** and add the domain in Vercel (Blocker 1).

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

4. **Price — OUT OF SCOPE. Do not reconcile it.** The founder is actively
   working out the right number as of 2026-09-17. Three repos currently state
   three different prices; that is known, and it is his call, not a drift to be
   tidied up by whoever reads this next.

   Two consequences to be aware of rather than act on:
   - The landing page's return multiple is computed from the active tier price
     (`campaign-site/src/components/Numbers.tsx:98`), so **the multiple moves when
     the price moves**. Nothing to do; just do not treat a figure read off the
     page today as stable.
   - An ad and its landing page must not state different prices. Since no
     creative states a price at all, nothing is currently exposed — and the gate
     deliberately still allows a bare price (`test_a_bare_price_is_not_a_claim`)
     so that stays true when one is added.

---

## The order of operations

Nothing below can be skipped by doing a later step first.

1. Delete the `teams` URL Forward at Porkbun · add the domain in Vercel · `CNAME`.
   *(founder, ~15 min + propagation — full runbook under Blocker 1)*
2. Set `VITE_SITE_ORIGIN=https://teams.doviloop.dev` in Vercel · redeploy. No
   code change — it was a literal until 2026-09-17 and is now a variable.
3. Create the pixel · set `VITE_META_PIXEL_ID` in Vercel · redeploy. *(founder)*
4. Verify `doviloop.dev` in Business Manager. *(founder)*
5. Let the pixel collect. `site-retargeting` and `pricing-viewers` have nobody in
   them until it does, and both need a head start on the ads.
6. `python -m engine.cli check --landing ../campaign-site/src/content` must pass
   on the creative. **Then the first ads** — `outreach-list` and `broad-interest`,
   both English, both on `/`.
7. Native proofread of `da` and `lt` — every non-English field in `creative/*.json`
   still reads `NEEDS_NATIVE_PROOFREAD`, and the same caveat is open on the landing
   copy (`campaign-site/BLOCKED.md` §6). Gates only the four `/da` and `/lt` ad
   sets, which step 5 is holding regardless. **Off the critical path since the
   decision of 2026-09-17.**

Price is deliberately absent from this list. See misalignment 4.
