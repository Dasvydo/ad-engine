# Meta pixel install, both domains

One pixel, two domains. `teams.doviloop.dev` is the campaign landing page
(Batch A). `doviloop.dev` is the product site, and it matters here because the
qualifier redirects firms under 10 seats there, and because a 90 day site
audience built from both domains is roughly twice the size of one built from
either.

Nothing in this document contains a secret. `<PIXEL_ID>` is a public identifier
that appears in page source on every site that uses one, but it does not exist
yet, so it is a placeholder until Dovy creates the Meta Business account.

> **Do this before anything else in the campaign.** Every audience in
> `structure.md` is empty until the pixel has been collecting for two weeks. It
> costs nothing and it is the only piece of this that compounds.

---

## 1. Create it

Meta Business Suite > Events Manager > Connect data sources > Web > Meta Pixel.
Name it `doviloop-web`. Copy the ID.

One pixel across both domains, not two. Two pixels means two half-sized
audiences and two sets of numbers to reconcile, and there is no upside at this
scale.

---

## 2. Base code, both domains

Goes in `<head>` on every page of both sites.

```html
<!-- Meta Pixel -->
<script>
!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,
document,'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '<PIXEL_ID>');
fbq('track', 'PageView');
</script>
<noscript><img height="1" width="1" style="display:none"
  src="https://www.facebook.com/tr?id=<PIXEL_ID>&ev=PageView&noscript=1"/></noscript>
<!-- End Meta Pixel -->
```

### On `teams.doviloop.dev` (Next.js on Vercel, Batch A)

Put it in `app/layout.tsx` with `next/script` and `strategy="afterInteractive"`,
not in a `useEffect`. Then set `NEXT_PUBLIC_META_PIXEL_ID` in Vercel project
settings so the id is not hardcoded across environments, and guard it so preview
deployments do not pollute the audiences:

```tsx
{process.env.NEXT_PUBLIC_VERCEL_ENV === "production" &&
  process.env.NEXT_PUBLIC_META_PIXEL_ID && <MetaPixel />}
```

A single-page app also has to fire `PageView` on client-side route changes,
because the base snippet only fires on hard loads. Hook it to the router.

### On `doviloop.dev`

Same snippet, same id, whatever the current stack allows. If it is a hosted
site builder, use its "custom head code" or "third party scripts" field. If
there is a Google Tag Manager container already, add it there instead of in the
template, and skip step 2 entirely for that domain.

---

## 3. Consent, because this is Denmark and Lithuania

Do not fire the pixel before consent. The ePrivacy directive as implemented in
Denmark and Lithuania requires opt-in for non-essential tracking, and Denmark
enforces it more actively than most of the EU. The campaign brief already notes
that Danish marketing law is stricter than the rest of the EU on unsolicited
commercial contact; the cookie rules follow the same instinct.

Practically:

```js
// only after the visitor has accepted marketing cookies
fbq('consent', 'grant');
```

Initialise the pixel with `fbq('consent', 'revoke')` immediately after
`fbq('init', ...)`, and grant on acceptance. Nothing is sent to Meta in the
meantime and no queued event is lost.

Expect this to cost 20 to 40 percent of the audience. That is the correct
tradeoff and it is not negotiable. Plan the audience sizes in `structure.md`
knowing the pools fill slower than raw traffic suggests.

---

## 4. The two standard events

Only two. A long list of events at this spend is a long list of numbers nobody
will read.

### `ViewContent`, fired when the pricing section is actually seen

```js
fbq('trackCustom', 'ViewContent', {
  content_name: 'pricing',
  content_category: 'teams_landing'
});
```

Fire it from an IntersectionObserver when the pricing block has been at least
50% visible for 2 seconds, not on page load. Firing on load makes every visitor
a "pricing viewer" and destroys the only high-intent audience in the account.

```js
const el = document.querySelector('#pricing');
let sent = false, timer;
new IntersectionObserver(([e]) => {
  if (e.isIntersecting && !sent) {
    timer = setTimeout(() => { sent = true; fbq('track','ViewContent',
      { content_name:'pricing', content_category:'teams_landing' }); }, 2000);
  } else clearTimeout(timer);
}, { threshold: 0.5 }).observe(el);
```

### `Lead`, fired on a successful qualifier submit

Fire on the success response, not on the button click. A click that fails
validation is not a lead, and counting it makes the exclusion audience in
`structure.md` exclude people who never got through.

```js
fbq('track', 'Lead', {
  content_name: 'qualifier',
  content_category: routing_outcome   // 'qualified' | 'gmail_on_request' | 'too_small'
});
```

Passing the routing outcome is what makes it possible later to exclude the
`too_small` firms from retargeting without excluding the good ones. Do not pass
the email, the company name, the phone number or anything else from the payload.
Advanced Matching is off. The audiences here are small and behavioural, hashed
matching buys nothing, and sending client-adjacent PII to Meta from a product
that sells data sovereignty would be an own goal.

---

## 5. How these map to Batch A's PostHog events

Batch A owns PostHog. This repo cannot see that code, so the mapping below is
**proposed** and needs one reconciliation pass when both branches land. Both
tools should fire off the same call site so they cannot drift.

| Moment on the page | PostHog event (proposed) | Meta pixel event | Feeds |
|---|---|---|---|
| Any page load or route change | `$pageview` (automatic) | `PageView` | Audience 2, site visitors 90 days |
| Pricing block 50% visible for 2s | `pricing_section_viewed` | `ViewContent` with `content_name: 'pricing'` | Audience 3, pricing viewers 90 days |
| Qualifier submitted successfully | `qualifier_submitted` with `team_size`, `email_client`, `role`, `market`, `locale` and the `utm` object | `Lead` with `content_category` = routing outcome | The exclusion on audiences 1, 2 and 3, and the ledger's `insert_lead` |
| Booking link clicked | `booking_link_clicked` | none | PostHog only. Not worth a pixel event at this volume. |
| Under 10 seats, redirected to pricing | `too_small_redirect` | `Lead` with `content_category: 'too_small'` | Lets a future campaign exclude them |

Wrap both in one function so a change to one cannot silently skip the other:

```ts
export function trackQualifierSubmit(outcome: RoutingOutcome, payload: Qualifier) {
  posthog?.capture('qualifier_submitted', { outcome, ...safeFields(payload) });
  window.fbq?.('track', 'Lead', { content_name: 'qualifier', content_category: outcome });
}
```

The three routing outcomes are fixed by the shared contract in
`00-START-HERE.md`: `qualified`, `gmail_on_request`, `too_small`. Use those exact
strings in both systems so the ledger, PostHog and Meta all agree.

**The one thing to reconcile:** if Batch A has already named the pricing event
something else, keep Batch A's name and change the table above. PostHog is the
system of record for behaviour; the pixel exists only to build audiences.

---

## 6. Verify both domains

Do all four. This takes about ten minutes and it is the difference between a
working account and four weeks of quietly broken audiences.

1. **Meta Pixel Helper** (Chrome extension). Load each domain. Expect one pixel,
   one `PageView`, no duplicate ids, no errors.
2. **Events Manager > Test Events.** Paste each domain's URL, then walk the real
   path: land, scroll to pricing, wait, submit the qualifier with a test entry.
   You should see `PageView`, then `ViewContent`, then `Lead`, in that order,
   from both domains.
3. **Domain verification.** Business Settings > Brand Safety > Domains. Add
   `doviloop.dev` and `teams.doviloop.dev`. Verify with the DNS TXT record,
   which is the least fragile of the three methods and works for both at once if
   you verify the apex.
4. **Aggregated Event Measurement.** Events Manager > Aggregated Event
   Measurement > Configure Web Events, per verified domain. Rank them:

   ```
   1  Lead
   2  ViewContent
   3  PageView
   ```

   Without this, iOS traffic reports almost nothing and a meaningful slice of a
   Danish audience is iOS. It takes two minutes and it is the step people skip.

---

## 7. What to do when it is wrong

| Symptom | Cause, nearly always |
|---|---|
| Pixel Helper shows two `PageView` events | The snippet is in both the template and GTM. Remove one. |
| `ViewContent` fires on every visit | It is on page load instead of on intersection. |
| No events at all from `teams.doviloop.dev` | Consent gate never granted, or the Vercel env guard is excluding production because `NEXT_PUBLIC_VERCEL_ENV` is unset. |
| Audience stuck at "below 1000" for weeks | Normal at this traffic level. Do not launch ads against it. See the timing table in `structure.md`. |
| Events show in Test Events but not in the audience | Audiences take up to 24 hours to populate, and a 90 day window only counts people who visited after install. Wait a day before worrying. |
