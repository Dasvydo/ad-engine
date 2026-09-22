# Meta Ads — one-page cheat sheet

For someone who has never run an ad. Every number here was read live on
2026-09-21, not remembered. Full reasoning: `campaigns/launch-procedure.md`.

---

## 1. The whole system is three nested boxes

```
CAMPAIGN  →  how much money, and what for
   └─ AD SET  →  who sees it, where, when
        └─ AD  →  the picture and words a human actually sees
```

One campaign holds ad sets. One ad set holds ads. That's it. Everything in Ads
Manager is a setting on one of these three.

**Yours: boxes 1 and 2 exist and are paused. Box 3 is empty. That's the only gap.**

---

## 2. Vocabulary — one line each

| Word | Means |
|---|---|
| **Impression** | Your ad appeared on a screen once |
| **Reach** | How many *different* people saw it |
| **Frequency** | Impressions ÷ reach. How often one person sees it |
| **CPM** | Cost per 1,000 impressions. *The price of attention* |
| **Link click** | Someone tapped through to your site |
| **Link CTR** | % of viewers who clicked. *Ranks your creative* |
| **CPC** | Cost per click. *Tells you if your budget is right-sized* |
| **Objective** | What you tell Meta to optimise for. Yours: **Traffic** |
| **Placement** | Where the ad shows (FB feed, IG reels, …) |
| **Learning phase** | Meta's first ~50 results, while it works out who to show it to |
| **Learning Limited** | Meta saying *"your budget is too small to learn"* |
| **CBO** | Meta sets budget across ad sets. No-op if you have only one |

---

## 3. Your account, by the numbers

| | |
|---|---|
| Ad account | `620456015062432` · currency **DKK** · min DKK 6.46/day |
| Campaign | `120252014714500563` — Traffic, **DKK 35/day**, PAUSED |
| Ad set | `120252014715910563` — Link clicks, DK+LT, age 30–60, PAUSED |
| Ads | **zero** |
| Facebook Page | `1294387330427112` (DoviLoop) |
| Pixel | `1584074833462346` — live since 2026-09-12 |
| Destination | `https://teams.doviloop.dev/` |

---

## 4. Launch checklist

- [ ] **Turn OFF Audience Network** in the ad set's placements.
      It is currently ON. It shows your ad inside mobile games; those clicks are
      accidents and reward-farming. Leave every other placement on.
- [ ] **Consider raising the budget to DKK 50–90/day.** See §6.
- [ ] Build **three ads**, each = one image + copy + the link above.
- [ ] Run `python -m engine.cli check` before shipping any copy.
- [ ] Turn on **all three ads in the same minute**, then the ad set, then the campaign.
- [ ] **Do not touch anything for 14 days.**

---

## 5. What to watch, and what good looks like

Only three numbers matter.

| Number | Bad | Normal | Good |
|---|---|---|---|
| **Link CTR** | under 0.5% | 0.6 – 1.0% | over 1.5% |
| **CPM** | over $16 | **LT $6.51 · DK $8.74** | under $6 |
| **CPC** | over DKK 8 | DKK 4–6 | under DKK 3.50 |

⚠️ **Always open the country breakdown.** Lithuania is ~25% cheaper, so Meta
sends most of your budget there. The single blended CPM on screen is basically
Lithuania's price wearing a DK+LT label.

**Ignore:** cost per lead, conversions, ROAS. At this budget they are noise.

---

## 6. Meta's own budget rule

> *"Your daily budget should be at least 10 times the average cost of your
> performance goal."* — Meta Business Help Centre

Your goal is link clicks. So: **daily budget ≥ 10 × CPC.**

DKK 35/day = USD 5.39, so it only complies if **CPC ≤ DKK 3.50**.

| If your CPC turns out to be | Meta's rule wants |
|---|---|
| $0.70 (best case, traffic objective) | DKK 45/day |
| $1.18 (European average) | DKK 77/day |
| $2.94 (B2B software) | DKK 191/day |

**Check your real CPC in week one, then decide.** This is the single most
useful thing the first week tells you.

---

## 7. Five rules you must not break

1. **Never add an ad to a live ad set.** Meta counts it as a "significant edit"
   and throws away everything it learned. Launch all three together.
2. **Never pause an ad to pick a winner.** Same reset, and you have thrown away
   your only comparable sample.
3. **Never change budget by more than 20% mid-run.** Same reset.
4. **Never read results before day 7.** Meta spreads budget across the week and
   can spend 175% of daily on one day. Whole weeks only.
5. **Never claim a number that is not in `claims/evidence.json`.** The gate is
   five regexes; it will not catch a plausible-sounding lie.

---

## 8. What to say to Claude

You don't need the dashboard. Type these:

```
Show me the last 7 days
Break the CPM down by country
Which of the three ads has the best link CTR?
Is anything rejected or blocked?
What's my CPC, and does it clear Meta's 10x rule?
```

**Ask on day 7. Then day 14. Not before** — day 3 is noise, and checking makes
you want to fiddle, and fiddling resets the learning.

Claude never turns anything on, off, or changes a budget without you saying so.

---

## 9. The three traps

| Trap | Reality |
|---|---|
| *"Ad A beat Ad B by 25%, so A wins"* | Someone ran three **identical** ad sets; the best beat the worst by 25%. A gap under ~50% is noise. |
| *"Meta will split my budget across three ads"* | It won't. It picks one early and gives it **over 90%** of spend. |
| *"Learning Limited means I did something wrong"* | Meta: *"it isn't a penalty — it's an indication that your budget isn't being spent effectively."* Expected at DKK 35/day. |

---

## 10. What this campaign can and cannot tell you

**Can:** the real CPM in DK and LT · whether the funnel works end to end ·
roughly which objection provokes a reaction · gross failure.

**Cannot:** which ad is best · cost per lead · whether Meta works for DoviLoop.

Six weeks and EUR 700 cannot answer the last one. Judge this on what it
teaches, not on pipeline.
