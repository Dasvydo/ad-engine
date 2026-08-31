# Meta pixel installation — doviloop.dev

**Status: not installed.** This blocks the `site-retargeting` audience, which is
the only audience in this repo that compounds. Every day the pixel is not
collecting is a day of retargeting pool that cannot be recovered later.

**Do this before any spend.** It costs nothing, and a 90-day retargeting window
that starts on launch day contains nobody.

> Written for someone with access to the `doviloop.dev` repo (React + Vite,
> deployed on Vercel) and to the DoviLoop Meta Business account. This repo does
> not have access to either — these are instructions, not a patch.

---

## 0. Before you touch the code

You need three things from Meta first, in this order.

1. **A Business Portfolio** (Business Manager) that owns the ad account. If ads
   run from a personal account, the pixel and the audiences belong to a person,
   not the company. Fix this now, not after there is data in it.

2. **A dataset (pixel).** Events Manager → *Connect data sources* → *Web* →
   *Meta Pixel*. Name it `doviloop-web`. Copy the 15–16 digit ID. Meta renamed
   pixels to "datasets" in the UI; the ID and the `fbq` API are unchanged.

3. **Domain verification for `doviloop.dev`.** Business settings → *Brand safety
   and suitability* → *Domains*. Verify by DNS TXT record (Vercel: project →
   Settings → Domains → DNS records) or by the meta-tag method, which for Vite
   means adding the tag to `index.html`.

   Domain verification is not optional housekeeping. Without it you cannot
   configure Aggregated Event Measurement, and post-ATT iOS traffic — a large
   share of DK and LT mobile — will be missing or delayed in reporting. See §7.

The pixel ID is **not a secret**. It ships to every browser that loads the site.
Do not treat it as a credential; do treat it as configuration.

---

## 1. Why not just paste the snippet into `index.html`

Meta's copy-paste snippet is wrong for this site in two specific ways.

**It fires before consent.** The audience is Denmark and Lithuania. Loading a
Meta pixel and dropping `_fbp` before the visitor has consented is a GDPR
problem, and this is a company an investor has already flagged as carrying
public-facing exposure with no liability cap and no insurance. The pixel must be
injected *after* consent, not merely told about it afterwards.

**It fires PageView once, ever.** `doviloop.dev` is a single-page React app.
The base snippet's `fbq('track','PageView')` runs on the initial document load
and never again. Every client-side route change after that is invisible, which
means "visited the pricing page" — the highest-intent retargeting signal
available — never gets recorded.

Both are fixed by the module in §2.

---

## 2. The pixel module

Create `src/lib/pixel.ts`.

```ts
// Meta pixel. Loads only after consent, only in production, only on the real
// domain. Preview deploys and localhost must never reach the pixel: every
// internal pageview lands in the retargeting audience and the audience is small
// enough that a handful of them is a measurable share of it.

const PIXEL_ID = import.meta.env.VITE_META_PIXEL_ID as string | undefined;

declare global {
  interface Window {
    fbq?: ((...args: unknown[]) => void) & { callMethod?: (...a: unknown[]) => void; queue?: unknown[][]; loaded?: boolean; version?: string; push?: unknown };
    _fbq?: unknown;
  }
}

let loaded = false;

function allowed(): boolean {
  if (!PIXEL_ID) return false;
  if (!import.meta.env.PROD) return false;
  return window.location.hostname === 'doviloop.dev' || window.location.hostname === 'www.doviloop.dev';
}

/** Inject the pixel. Safe to call more than once. Call only after consent. */
export function loadPixel(): void {
  if (loaded || !allowed()) return;
  loaded = true;

  /* eslint-disable */
  // Meta's stub, verbatim in behaviour: queues calls until the real script lands.
  (function (f: any, b: Document, e: string, v: string) {
    if (f.fbq) return;
    const n: any = (f.fbq = function () {
      n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments);
    });
    if (!f._fbq) f._fbq = n;
    n.push = n; n.loaded = true; n.version = '2.0'; n.queue = [];
    const t = b.createElement(e) as HTMLScriptElement;
    t.async = true; t.src = v;
    const s = b.getElementsByTagName(e)[0];
    s.parentNode!.insertBefore(t, s);
  })(window, document, 'script', 'https://connect.facebook.net/en_US/fbevents.js');
  /* eslint-enable */

  window.fbq!('init', PIXEL_ID);
  window.fbq!('track', 'PageView');
}

/** Track a standard or custom event. No-ops if the pixel never loaded. */
export function track(event: string, params?: Record<string, unknown>): void {
  if (!loaded || !window.fbq) return;
  window.fbq('track', event, params);
}

/** Called on every SPA route change. The first PageView comes from loadPixel(). */
export function trackPageView(): void {
  track('PageView');
}
```

### Route changes

If the site uses React Router, add this once, inside the router:

```tsx
import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { trackPageView } from './lib/pixel';

export function usePixelPageViews() {
  const { pathname } = useLocation();
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; } // loadPixel() already sent it
    trackPageView();
  }, [pathname]);
}
```

The `first` guard matters. Without it the landing page records two PageViews for
every visitor, which inflates the only volume number this project has and makes
the retargeting audience look healthier than it is.

Under React 18 `StrictMode`, effects run twice in development. That is
development-only, but it means **you cannot verify event counts against
`npm run dev`** — verify against a production build (§6).

---

## 3. Consent

Wire `loadPixel()` to the consent banner's accept handler, and to nothing else:

```tsx
onAccept={() => { localStorage.setItem('consent:marketing', 'granted'); loadPixel(); }}
```

On subsequent visits, call `loadPixel()` at app start **only if** the stored
consent is `granted`.

If there is no consent banner on `doviloop.dev` today, that is the actual first
task, ahead of the pixel. Do not ship the pixel without one.

**Be clear-eyed about the cost.** Consent-gating means the retargeting audience
only ever contains the share of visitors who accept marketing cookies — in the
Nordics and the Baltics, commonly well under half. A pool that was already going
to be small gets smaller. That is the correct trade and it does not have a
workaround: firing the pixel before consent is not a growth tactic, it is an
unremediated liability on a company with no insurance.

Do not use `fbq('consent', 'revoke')` as the primary mechanism. It suppresses
sending but still loads Meta's script and touches storage. Not injecting is
cleaner and easier to defend.

---

## 4. Which events to fire — and one not to

| Event | Where | Why it exists |
|---|---|---|
| `PageView` | every route | Populates `site-retargeting`. The whole point. |
| `ViewContent` | `/pricing` | The one page whose visit means intent rather than curiosity. Build a separate, higher-intent audience from it. |
| `Lead` | contact / booking form **success** callback | The furthest down the funnel this product can currently go. |

```ts
// on the pricing route
useEffect(() => { track('ViewContent', { content_name: 'pricing' }); }, []);

// in the booking form, after the request succeeds — not on click
track('Lead', { content_name: 'design-partner-enquiry' });
```

Fire `Lead` on the **success** path only. Firing on button click counts
validation errors and network failures as leads, and at the volumes this project
will see, a handful of phantom leads is the difference between a signal and a
mirage.

### Do not implement `Purchase` or `InitiateCheckout`

Revenue is switched off in the product (`TEST_MODE` plus two `BYPASS_*` flags).
Any purchase event fired today would describe a transaction that did not happen.
That is not a harmless placeholder:

- it permanently poisons the dataset's event history, which is what any future
  conversion optimisation learns from;
- it silently creates a "purchasers" audience made of people who bought nothing;
- it produces a ROAS number in Ads Manager that is fiction, and fiction in a
  dashboard eventually gets repeated to someone.

Add these events on the same commit that turns real payments on, and not before.

---

## 5. Configuration and deployment

Add the environment variable in Vercel — project → Settings → Environment
Variables:

| Name | Value | Environments |
|---|---|---|
| `VITE_META_PIXEL_ID` | the dataset ID from §0 | **Production only** |

Two Vite-specific things that catch people:

- Only `VITE_`-prefixed variables reach client code. `META_PIXEL_ID` will be
  `undefined` in the browser and the pixel will silently never load.
- Vite **inlines** env vars at build time. Changing the value in Vercel does
  nothing until you redeploy.

Setting it on Production only is a second belt alongside the hostname check in
`allowed()`. Preview deployments then cannot fire the pixel even if the hostname
guard is later edited.

**If the site sends a Content-Security-Policy** (a `headers` block in
`vercel.json` or a meta tag), the pixel needs:

```
script-src  https://connect.facebook.net
img-src     https://www.facebook.com
connect-src https://www.facebook.com https://connect.facebook.net
```

A missing CSP entry fails silently in production and looks exactly like "the
pixel didn't install" — check the browser console for CSP violations before
debugging anything else.

---

## 6. Verify it before trusting it

Do all four. The first two pass in situations where the audience still never
fills.

1. **Meta Pixel Helper** (Chrome extension) on `https://doviloop.dev` after
   accepting consent: one pixel found, one `PageView`, no warnings.
2. **Events Manager → your dataset → Test Events**: enter the URL, click through
   the site, confirm `PageView` fires on each route change and exactly once per
   route.
3. **Consent path**: hard-refresh with storage cleared, *decline* the banner,
   and confirm in the Network tab that nothing is requested from
   `connect.facebook.net`. This is the test that actually matters legally.
4. **Preview isolation**: open the latest Vercel preview URL, accept consent,
   confirm no pixel loads.

Then, in Events Manager, watch the **Overview** tab for 48 hours. A dataset that
shows activity for a day and then flatlines usually means the pixel is on the
landing page only, or that a deploy dropped the env var.

---

## 7. Build the audiences — then wait

Once events are arriving, Ads Manager → Audiences → Create → Custom Audience →
Website:

| Audience | Rule | Window | Feeds |
|---|---|---|---|
| `pixel-all-visitors-90` | All website visitors | 90 days | `site-retargeting` ad set |
| `pixel-pricing-180` | People who triggered `ViewContent` | 180 days | seed for the higher-intent variant |

The 90 days matches `audiences/site-retargeting.json`. The 180-day pricing
audience exists because at this traffic level a 90-day intent window may never
hold enough people to serve.

Also configure **Aggregated Event Measurement** (Events Manager → dataset →
Settings → Event configuration) once the domain is verified: rank `Lead` first,
`ViewContent` second, `PageView` third. Without it, iOS conversions are dropped
rather than merely delayed.

**Then stop and let it collect.** A website custom audience under Meta's ~1,000
floor will be accepted at creation and then under-deliver or refuse to serve.
`campaign/structure.json` therefore gates the `site-retargeting` ad set on two
conditions — pixel live ≥ 30 days *and* audience size ≥ 1,000 — and the plan is
to launch the other ad sets without it rather than wait.

---

## 8. Out of scope for now

**Conversions API.** Server-side event forwarding (a Vercel serverless function
posting to Meta's `/events` endpoint with an `event_id` for deduplication)
recovers the events browser blockers and ITP drop. It is the right thing
eventually and it is not the right thing this week: it needs an access token in
server-side secrets, a deduplication scheme, and its own verification pass, and
none of that helps until the browser pixel has been collecting for a month.
Revisit when there is enough traffic for the gap to be measurable.
