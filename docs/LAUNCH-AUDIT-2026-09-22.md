# LAUNCH AUDIT — 2026-09-22

Written against the **live** system, not against this repo's docs. Every line marked
**measured** was run on 2026-09-22 between 13:13 and 13:25 UTC. Everything else says
plainly that it was not checked.

The funnel under audit, in the founder's words: *ad → click → landing page → browse →
fill in the form → book a calendar event*, with the result readable in **both** Supabase
and Meta Ads Manager.

---

## Status, updated 2026-09-22 after the fixes landed

`campaign-site@18cbaeb` is live on `campaign/a-site`. Re-verified against the
production site, both viewports:

| | Was | Now |
|---|---|---|
| **M2** duplicate PageView | 2 per pageload, one `noscript=1` | **beacon gone** ✅ |
| **M3** `ViewContent` on a phone | could not fire, ceiling 0.494 vs a 0.50 gate | **fires** ✅ |
| **M3** `ViewContent` on desktop | fired | still fires ✅ |
| **M1** PostHog | silently dropping every event | **still dropping** — needs an EU key |

The dwell still discriminates, checked at 390x844: a scroll straight past does
not fire, a 900ms glance does not fire, stopping on the price does.

⚠️ **M1 was deliberately not "fixed" by moving the host.** All three locales tell
the visitor, inside the consent dialog, that PostHog is hosted in the EU. Pointing
the ingest host at US to make the key work would make that sentence false at the
moment consent is asked for. `npm run verify:posthog` now fails either way round -
a key that does not resolve at the configured host, or a host outside the EU while
the copy still promises EU. The decision is the founder's: a new PostHog project on
EU cloud (keeps the copy true), or staying on US and rewriting the consent copy in
en, da and lt.

**B1, B2, M4, M5 and M6 below are unchanged and still open.**

---

## 0. Verdict

**The funnel works end to end. Two things block delivery and three corrupt measurement.**

A real lead submitted through the live page on a phone-sized viewport reached n8n, was
accepted, and came back `"stored": true` with a `lead_id`. The booking link resolves to a
real Google Calendar appointment page. The Meta pixel is live and receiving.

What is not true is that you can *read* the result. PostHog is silent, Meta's PageView is
double-counted, and the pricing-intent event cannot fire on a phone — which is where
essentially all of this traffic will land.

---

## 1. Method

| What | How it was checked |
|---|---|
| Landing page | Real Chromium, 390×844 mobile UA, navigated to the **actual ad destination URL** |
| Pixel | Every request to `facebook.com/tr` intercepted and its `ev=` / `noscript=` read |
| Lead pipeline | A real form submission; the POST body and the n8n response body captured |
| Booking | The rendered `href` followed to its final URL |
| PostHog | The project key probed against both EU and US ingest and config endpoints |
| Meta objects | Read back through the connector: campaign, ad set, ads, creatives, errors, dataset |
| Ad destination | Extracted from the **rendered ad preview**, not from this repo's JSON |
| Videos | `ffprobe`-equivalent on both files, plus frame extraction and safe-zone overlay |

Test lead written to Supabase — **delete it**: company `ZZ-DELETE-ME Claude launch audit`,
email `qa-audit@zz-delete-me-claude.example`, `lead_id` `eb0f97f7-4cdb-4795-8c26-fd9e6daa1218`.

---

## 2. ✅ Completed and verified

### The click lands correctly
- `https://teams.doviloop.dev/?utm_source=meta&utm_medium=paid&utm_campaign=teams_q4&utm_content=v3-outlook`
  → **HTTP 200, no redirect chain**, title `DoviLoop for teams…`. **Measured.**
- The UTM string is **live inside the ad object** — pulled from the rendered preview, not
  from `creative/copy/*.json`. `utm_content` carries the variant id, so spend joins back
  to a creative.
- FUNNEL-HANDOFF Blocker 1 (the Porkbun wildcard forward) is **closed**. The doc still
  reads as if it were open.

### The page
- Renders correctly at 390×844. Consent notice, hero, fit check, result screen all intact.
- Page height 9,367px. Fit check reachable, two-step form works.

### Consent gate
- **Nothing fires before a choice.** Zero requests to `facebook.com/tr` pre-consent. **Measured.**
- On Accept, `fbevents.js` injects and `fbq.loaded === true`.

### Lead → Supabase
- POST to `https://viniflow-u57383.vm.elestio.app/webhook/campaign/qualifier` → **200**.
- Response: `{"ok":true,"outcome":"qualified","stage":"qualified","lead_id":"…","deduped":false,"shows_booking":true,"nurture_started":false,"stored":true}`
- The webhook **validates the contract** — an empty body is rejected with a per-key problem list.
- ⚠️ `"stored": true` is n8n's claim. The Supabase row was **not** read back directly; this
  audit has no Supabase credentials. Treat storage as verified-by-contract, not verified-by-query.

### Booking
- `VITE_BOOKING_URL` **is set**: `https://calendar.app.google/BzZ7TXZNiuoRZeAy7`
  → 200, resolves to a real Google Calendar appointment schedule. **Measured.**
- The confirmation screen renders "Pick a time" as a real link, not the mailto fallback.

### Meta objects
| Object | Id | State |
|---|---|---|
| Campaign `DoviLoop · EN traffic · DK+LT` | `120252014714500563` | PAUSED · `OUTCOME_TRAFFIC` · CBO **DKK 35/day** · Highest volume |
| Ad set `DK+LT · 30-60 · broad geo · link clicks` | `120252014715910563` | PAUSED · `LINK_CLICKS`/`IMPRESSIONS` · WEBSITE |
| Ad `v3-outlook` | `120252098516600563` | PAUSED · **WITH_ISSUES** |
| Ad `v4-europe` | `120252098517200563` | PAUSED · clean |
| Ad `v2-voice` | `120252098517410563` | PAUSED · **WITH_ISSUES** |

- Targeting intact: DK+LT, ages 30–60 hard (`advantage_audience: 0`), geo-only.
- `publisher_platforms`: facebook, instagram, threads. **Audience Network is gone.**
- Pixel/dataset `1584074833462346` is receiving: PageView, ViewContent, Lead, Schedule.

---

## 3. ⛔ Blocks delivery — fix before turning anything on

### B1 · Two of three ads cannot deliver — Page-Backed Instagram Profile

`ads_get_errors`, read twice ten minutes apart, both times:

> `Fail to create Page Backed Instagram Profile: Page Backed Instagram profile is being created. Please try again later.`

On `120252098516600563` (v3-outlook) and `120252098517410563` (v2-voice). `v4-europe` is clean.

**Why.** The ad set includes Instagram placements. No Instagram account is linked to the
account (`ads_get_ig_accounts` → `[]`), so Meta tries to auto-create a Page-Backed
Instagram Account from the DoviLoop Page to carry the Instagram identity. That creation is
asynchronous and has not completed.

**Three ways out, in order of preference:**
1. **Link a real Instagram business account** to the DoviLoop Page in Business Settings.
   Best outcome — the ads get a real IG identity instead of a shadow profile.
2. **Wait and re-check.** PBIA creation usually completes by itself. Costs nothing but time,
   and it has already been pending for at least ten minutes.
3. **Drop Instagram from the ad set's placements.** Removes the need for a PBIA entirely.
   Cheapest unblock, smallest reach.

Turning the campaign on while two ads are `WITH_ISSUES` means the whole DKK 35/day lands on
`v4-europe` alone, and the three-way objection test never happens.

### B2 · Neither video exists in Meta

`ads_get_ad_videos` → `[]`. The two files are on disk only. Nothing to add to an ad yet.
See §5 for whether they should go in at all.

---

## 4. ⚠️ Launch-safe, but the numbers will lie

### M1 · PostHog is dead — wrong cloud region

The project key resolves on **US** cloud. The page is configured for **EU**.

| Probe | EU | US |
|---|---|---|
| `/flags/?v=2` | **401** | **200** |
| `…-assets.i.posthog.com/array/<key>/config` | **404** | **200** |

**Measured**, both. In the browser the page throws two 404s and a 401 on every load.

`VITE_POSTHOG_HOST` **is not set in Vercel** (only four vars are: `VITE_POSTHOG_KEY`,
`VITE_META_PIXEL_ID`, `VITE_BOOKING_URL`, `VITE_LEAD_WEBHOOK_URL`). So `env.ts` falls back
to its default, `https://eu.i.posthog.com`, and every event is dropped.

**Everything in `analytics.ts` is going nowhere** — `page_view`, `demo_desk`,
`pricing_view`, `form_start`, `form_step`, `form_submit`, `qualified_shown`,
`too_small_shown`, `booking_click`. That is the entire on-page funnel. Meta will tell you
clicks; only PostHog was going to tell you what happened between the click and the form.

**Two fixes, and the choice is yours** because they mean different things:
- Set `VITE_POSTHOG_HOST=https://us.i.posthog.com` in Vercel and redeploy. Two minutes.
  Analytics starts working today. EU visitor analytics then sits on US infrastructure.
- Or create the project on PostHog **EU** cloud and swap the key. Slower, keeps the EU
  data-residency posture the consent copy and `.env.example` both assume.

Note also: `VITE_POSTHOG_KEY` is scoped to **production only**, not preview. Preview
deployments have no analytics at all.

### M2 · Every PageView is counted twice

Intercepted on one page load, one pixel id:

```
facebook.com/tr?…&ev=PageView&noscript=1     ← the <noscript> fallback
facebook.com/tr?…&ev=PageView                ← the real fbq call
```

`pixel.ts` builds the `<noscript>` fallback with `document.createElement('img')` and sets
`img.src` on it. Setting `.src` on an element created in a live document **fires the
request immediately**, before it is ever parked inside `<noscript>`. So the fallback meant
for visitors without JavaScript fires for every visitor *with* JavaScript.

Neither carries an `event_id`, so Meta has nothing to dedupe on. **Landing page views,
and every ratio built on them, read ~2× high.**

The fallback is dead weight anyway: if the loader ran, JavaScript is on.

### M3 · `ViewContent` can never fire on a phone

`Price.tsx` fires the Meta `ViewContent` through an `IntersectionObserver` with
`threshold: 0.5` on the whole `#price` band, plus a dwell timer.

Measured peak `intersectionRatio`, scrolling the full page in both directions and then
dwelling 12s:

| Viewport | `#price` height | Peak ratio | Gate needs ≥ 0.5 |
|---|---|---|---|
| **390×844 (phone)** | 1,705px | **0.494** | ❌ **impossible** |
| 1440×900 (desktop) | 1,316px | 0.684 | ✅ fires |

It is not a timing problem, it is arithmetic: a target taller than the viewport can never
exceed `viewport ÷ target`. 844 ÷ 1705 = 0.495.

The ad set targets DK+LT 30–60 on feed placements, which is overwhelmingly mobile. So the
pricing-viewer retargeting pool — this repo's audience 3 — **will not be built from paid
traffic at all**. The dataset's existing `ViewContent` counts are desktop sessions.

Fix is one of: observe a short sentinel element inside the band instead of the band itself,
or drop the threshold to something a phone can reach (~0.35 with the dwell kept).

### M4 · `Schedule` means "clicked the booking link", not "booked"

`pixelTrack('Schedule')` fires on `onBookingClick`. Google Calendar never reports back, so
a click that ends in nothing still counts. Fine as an intent signal — just do not read
Ads Manager's Schedule count as calls in the diary.

`Schedule` events **are** arriving (2 today, per the dataset). Verified from Meta's own
event stats, **not** by clicking it in this audit.

### M5 · The ad's visible link caption shows the raw UTM string

The preview renders the caption as `doviloop.dev/?utm_source=meta&utm_medium=paid&utm_ca…`.
It works, it just reads like a tracking link. Meta has a **Display link** field that
overrides the caption without touching the destination. Cosmetic, one field per ad.

### M6 · `promoted_object` is not set on the ad set

No pixel is declared on the ad set and no `attribution_spec` is present. For a
`LINK_CLICKS` traffic objective this is **not** a blocker — the pixel is connected at the
account level and reporting still works. Worth knowing before anyone reads a conversion
column and wonders why it is thin.

---

## 5. The two videos

**Neither is in Meta.** Both are technically clean.

| | **Ad C — 4:5** | **Ad D — 9:16** |
|---|---|---|
| Resolution | 1080×1350 | 1080×1920 |
| Duration | 6.00s | 6.00s |
| Video | H.264 High, yuv420p, 30fps, 299 kb/s | H.264 High, yuv420p, 30fps, 549 kb/s |
| Audio | AAC LC stereo 48kHz · mean −21.5 dB, peak −3.1 dB | AAC LC stereo 48kHz · mean −19.5 dB, peak −3.0 dB |
| Size | 377 KB | 564 KB |
| Meta spec | ✅ within every limit | ✅ within every limit |

**Ad C (4:5)** — a six-second Outlook demo. Inbox with three unread → "Draft ready" badges
appear → the draft expands and types itself → Send is clicked. Headline locked across every
frame: *"Your replies are **drafted** before 9am"*. Trust bar along the bottom: *Works
inside Outlook · Sounds like you · You hit send*.

**Ad D (9:16)** — a split-screen contrast. Left, a dark inbox with chaotic floating labels
(*Urgent!! · Re: Re: Re: · Any update?*) and a rising unread count. Right, the same list
gone clean with "Draft ready" on every row, closing on *"Every reply drafted"* and the
DoviLoop wordmark.

**Safe zones, measured with the Stories/Reels UI bands drawn over the frames:** Ad D's
content sits entirely between y=268 and y=1536 — clear of both the 14% top band and the
20% bottom band. Correctly composed. One decorative floating chip clips the top band in
the opening second; transient, not content.

### Which format

They are not alternatives. They are different placements, and your ad set has both enabled.

- **4:5 (1080×1350) is the one that matters.** It is the tallest ratio Facebook and
  Instagram **feed** will serve, so it takes the most screen height without cropping. Your
  ad set's delivery mass is feed — `mobilefeed`, `desktopfeed`, `instagramstream`. At
  DKK 35/day, feed is where the money goes. **Lead with Ad C.**
- **9:16 (1080×1920) is for Stories and Reels only.** Full-bleed, no letterbox.
- Best practice is to put **both on one ad** with placement customisation, so each
  placement serves its native ratio. Without that, Meta crops the 4:5 into the 9:16 slot and
  either pillarboxes it or eats the headline.

### What is weak in both

- **Six seconds leaves no room for a CTA beat.** Neither video ends on an ask. For
  `LINK_CLICKS` this costs less than it would elsewhere — the click comes from the
  Learn More button, not the video — but Ad C in particular ends mid-gesture on "Send"
  with no end card and no logo. Ad D closes properly.
- **Both read fine muted**, which is right: feed autoplays silent and all the information
  is on-screen text. The audio is present and correctly levelled if anyone unmutes.

### Should video go in at launch — no

You have three statics built and paused. Adding two videos makes five ads in one ad set at
DKK 35/day. Meta concentrates the overwhelming majority of an ad set's spend on a single
ad; five ads means four starve and you learn nothing about any of them. Every creative
added after launch also resets the learning phase.

**Pick three and launch three.** If you would rather test video than the third objection,
that is a **swap**, not an addition — drop one static, add Ad C. Video generally beats
static on cold Meta traffic, so this is a defensible trade. What is not defensible is
running five.

---

## 6. Launch order

Nothing below changes a status. Statuses stay the founder's.

1. **Clear B1.** Link an Instagram account, or wait for the PBIA, or drop Instagram
   placements. Re-read `ads_get_errors` until all three ads are clean.
2. **Decide M1.** US host in Vercel (fast) or EU project (correct posture). Redeploy.
3. **Decide M2 and M3.** Both are small edits in `campaign-site`. ⚠️ Production deploys
   from branch **`campaign/a-site`** — a fix on any other branch will not reach the live
   site.
4. **Delete the test lead** named in §1.
5. **Decide the two still-open Meta questions**: `self_ai_disclosure` (never set on the
   founder's behalf — it cannot be changed after the fact, only rebuilt) and Instagram.
6. **Then** turn on: three ads → ad set → campaign, in that order, same minute, so all
   three start together.
7. Leave it alone for 14 days. Adding an ad, pausing an ad, or moving the budget more than
   20% each reset learning.

## 7. Corrections to standing docs

- `docs/FUNNEL-HANDOFF.md` Blocker 1 reads as open. It is **closed** — `teams.doviloop.dev`
  serves the campaign page directly, 200, no redirect.
- `campaign-site/BLOCKED.md` entry 4 says all five environment variables are empty. Four of
  them are now set in Vercel. `VITE_POSTHOG_HOST` is the one that is not, and that is M1.
- `campaign-site/.env.example` still says `teams.doviloop.dev` 301s to the product site and
  names the `.vercel.app` URL as canonical. Both are stale.
