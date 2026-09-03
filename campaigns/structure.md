# The campaign, built by hand in Ads Manager

Retargeting only. English only. Under EUR 500 a month.

This is a build sheet, not an API integration. At this spend, automating Meta
would cost more to build and maintain than the media it manages. Everything
below is clicks in Ads Manager, and the whole build is about 20 minutes once the
audiences exist.

---

## Read this before you build it

**Under EUR 500 a month against cold traffic, this campaign cannot produce
statistically clean results in six weeks. It will not tell you which creative
converts. It produces direction, and the honest read is which creative gets
clicked.**

That is not pessimism, it is arithmetic. Meta's optimiser leaves the learning
phase at roughly 50 optimisation events per ad set per week. At EUR 6.50 a day
an ad set spends about EUR 45 a week. Even at a friendly EUR 1.00 per link
click that is about 45 clicks, which is barely at the threshold for **clicks**
and nowhere near it for **leads**. A booked discovery call at this ICP is a
handful of events across the entire six weeks. You cannot A/B test on a handful
of events. Anything the dashboard tells you about cost per lead in October will
be noise wearing a number's clothes.

So here is what to actually take from it:

| Signal | Trustworthy at this spend? |
|---|---|
| Which creative gets clicked, and which gets ignored | **Yes.** Clicks accumulate fast enough to rank creative. |
| Which objection people respond to | **Yes, roughly.** This is the single most valuable output, and it feeds the outreach scripts and the landing page, which are where the pipeline actually comes from. |
| Whether video or static earns more attention | **Yes, roughly.** |
| Cost per lead, by ad set | **No.** Not enough events. |
| Which creative converts to a booked call | **No.** Do not let anyone quote this number. |
| Whether Meta is a viable channel for DoviLoop | **No.** Six weeks and EUR 700 total cannot answer that. |

The repo's own README already said the honest thing and it still stands: judge
this on what it teaches, not on pipeline. Cold outreach is where the pipeline
should come from.

---

## The thing that will actually break this

**Every audience below is empty today.**

Retargeting needs a pool, and the pools are built by the pixel and by reel
views. The pixel is not installed. Batch D's reels start posting the same week
the campaign window opens. Meta will not deliver to a custom audience under
about 1,000 people, and a 90-day site audience built from a landing page that
went live yesterday has nobody in it.

So do not launch paid on 8 September. Do this instead:

| When | What |
|---|---|
| **Now, today** | Install the pixel on both domains. See `pixel-install.md`. It costs nothing and it is the only thing here that compounds. |
| 8 to 21 September | Reels post, outreach runs, traffic lands on `teams.doviloop.dev`. Pools fill. Spend nothing on ads. |
| **Around 22 September** | Check audience sizes in Ads Manager. If video viewers is over 1,000, build the campaign below. |
| 22 Sept to 19 Oct | Four weeks of paid, roughly EUR 450. |

Four weeks of paid against a real audience beats six weeks of paid against an
empty one, and it costs less. If the pools are still tiny on 22 September, run
one ad set instead of three rather than splitting nothing three ways.

---

## The 20 minute build

### Step 0, once: the audiences (Audiences, not Ads Manager)

Build these first. The campaign takes two minutes once they exist and cannot be
built at all before.

| # | Audience | How to build it | Notes |
|---|---|---|---|
| 1 | **Video viewers 50%, 180 days** | Create audience > Custom > Video > "People who watched at least 50% of your video" > select all reels on the page and the IG account > 180 days | The best audience here. Someone who watched half a reel about drafting client email is qualified in a way no interest targeting can match. |
| 2 | **Site visitors, 90 days, minus leads** | Custom > Website > All visitors > `teams.doviloop.dev` > 90 days. Then Exclude > people who triggered `Lead` | Excluding form submitters matters. Paying to retarget someone who already booked is the most common way small budgets get wasted. |
| 3 | **Pricing section viewers, 90 days** | Custom > Website > Events > `ViewContent` where `content_name` equals `pricing` > 90 days | Fed by the PostHog to pixel mapping in `pixel-install.md`. Highest intent pool, and it will also be the smallest. |
| 4 | **IG and FB engagers, 365 days** | Custom > Instagram account, and again for Facebook page > "Everyone who engaged" > 365 days | Cheap filler. Keep it as an expansion audience, not a headline one. |
| 5 | **Lookalike from form submitters** | Custom > Website > `Lead` event > then Create lookalike, 1% | **Documented and unused.** A lookalike needs 100 seeds minimum and behaves badly under about 500. There will not be 50 form submitters in six weeks. Build it when there are, not before. |

Exclude audience 2's leads from every ad set, not just its own.

### Step 1: the campaign

```
Campaign name      teams_q4_retargeting
Objective          Traffic
Budget             At campaign level: no. Use ad set budgets.
Advantage campaign budget   OFF
Special ad category         None
```

**Objective is Traffic, not Leads or Conversions, and this is deliberate.**
A Conversions campaign optimising for `Lead` at EUR 16 a day will get about two
events a week, never exit learning, and deliver badly to a tiny audience. A
Traffic campaign optimising for link clicks gets enough events to actually
learn, and clicks are the only thing this budget can measure honestly anyway.
Optimising for a signal you cannot generate is the classic way small accounts
burn their budget on Meta's exploration phase.

Set **Ad set budgets**, not campaign budget optimisation. CBO will pour almost
everything into whichever ad set is cheapest, which at this size means the
comparison you are running quietly stops existing.

### Step 2: three ad sets

Same settings on all three unless the table says otherwise.

```
Optimisation       Link clicks
Bid strategy       Highest volume (no cost cap)
Placements         Manual: Facebook feed, Instagram feed, Instagram reels,
                   Facebook reels. Turn OFF Audience Network and
                   Messenger, they eat budget at this size for junk clicks.
Locations          Denmark, Lithuania, United States
Age                28 to 65+
Language           Leave empty. The audience is already defined by the
                   retargeting pool; a language filter shrinks it further.
Detailed targeting expansion   OFF. It undoes retargeting.
Schedule           Run continuously
```

| Ad set | Audience | Daily budget | Monthly |
|---|---|---|---|
| `as1_video_viewers` | Audience 1, exclude leads | EUR 6.50 | EUR 195 |
| `as2_site_visitors` | Audience 2 (already excludes leads) | EUR 6.50 | EUR 195 |
| `as3_format_test` | Audiences 1 + 3 + 4 combined, exclude leads | EUR 3.00 | EUR 90 |
| **Total** | | **EUR 16.00** | **EUR 480** |

The first two get enough to have a chance of clearing learning. The third is the
static versus video slice and is deliberately small, because it is the question
you can most afford to answer roughly.

Do not add a fourth ad set. Four ad sets at EUR 4 a day each is four ad sets
that all stay in learning forever.

### Step 3: the ads

Two ads per ad set. Two, not six. Six creatives on EUR 6.50 a day means each one
gets EUR 1 a day, which measures nothing.

| Ad set | Ad A | Ad B |
|---|---|---|
| `as1_video_viewers` | `v5-pilot` copy + `s05-two-weeks` static, 4:5 | `v1-glance` copy + `s01-glance` static, 4:5 |
| `as2_site_visitors` | `v3-outlook` copy + `s03-no-new-app` static, 4:5 | `v4-europe` copy + `s04-where-it-lives` static, 4:5 |
| `as3_format_test` | `v2-voice` copy + `s02-how-you-write` static, 1:1 | `v2-voice` copy + the 15 second video cut, 1:1 |

`as3` holds the copy constant and changes only the format, which is the only way
that comparison means anything.

Per ad:

```
Format           Single image, or single video for the format test
Primary text     paste from creative/copy/<variant>.json  -> primary_text
Headline         same file -> headline
Description      same file -> description
Call to action   Learn more
Website URL      https://teams.doviloop.dev/?utm_source=meta&utm_medium=paid
                 &utm_campaign=teams_q4&utm_content=<variant-id>
Ad name          teams_q4 | <variant-id> | <creative-id>-<ratio>
```

The URL in every copy file already has the right UTM baked in. Copy it from the
`destination` field rather than typing it, because one wrong `utm_content` makes
that ad invisible in the report.

Upload the 4:5 image and let Meta crop for feed, or upload 1:1 separately per
placement. Both ratios are in `creative/static/out/`.

### Step 4: leave it alone

Seven days minimum before touching anything. Editing an ad set restarts its
learning phase, and at EUR 6.50 a day an ad set that keeps restarting learning
never leaves it. This is the single most common way a small Meta budget produces
nothing.

---

## What to look at, and when

| When | Look at | Act if |
|---|---|---|
| Day 3 | Delivery only. Is it spending? | An ad set has spent under EUR 5 in 3 days. That means the audience is too small. Merge it into another rather than raising the budget. |
| Day 7 | CTR (link click through rate) per ad | An ad is under 0.5% CTR while another is over 1.5%. Pause the loser, do not replace it yet. |
| Day 14 | CTR by objection. Which of the five is landing? | One objection is clearly ahead. Tell Batch A and Batch D. That is the real product of this campaign. |
| Day 21 | Frequency | Frequency over 4. The pool is exhausted. Widen to audience 4 or pause. |
| Day 28 | Everything | Write down which creative got clicked. Do not write down a cost per lead. |

Run `python report/pull_ad_stats.py` daily once the account exists so the numbers
land in the ledger rather than only in Meta's UI, which does not keep the daily
grain you will want in November.

---

## What to do with the answer

The point of this is not the ads. It is that in four weeks you will know, with
usable confidence, which of the five objections makes an accountant stop
scrolling. That answer is worth more in outreach subject lines and on the
landing page than the clicks themselves, and it costs about EUR 450 to buy.

Feed it back into `research/objections.md` as a note under the winning
objection, and tell Batch A and Batch D.
