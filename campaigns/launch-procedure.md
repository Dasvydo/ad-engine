# Launching the three ads — the procedure, and the arithmetic behind it

Written 2026-09-21. Account state read live, not recalled.

---

## 1. What is actually configured right now

| | Read live 2026-09-21 |
|---|---|
| Campaign `120252014714500563` | `OUTCOME_TRAFFIC`, **DKK 35.00/day**, Highest volume, PAUSED |
| Ad set `120252014715910563` | `LINK_CLICKS` / billed on `IMPRESSIONS`, DK+LT, 30-60 hard (`advantage_audience: 0`), PAUSED |
| Ads | **zero** |
| Account | ACTIVE, payment method attached, **zero delivery-blocking errors** |

DKK 35/day = **EUR 4.69/day**. That single number governs everything below.

---

## 2. The finding that should change the build

**Audience Network is enabled on the live ad set**, and so is its `rewarded_video`
position. Read live from `targeting.effective_publisher_platforms`:

```
facebook · instagram · audience_network · threads
effective_audience_network_positions: classic, rewarded_video
```

30 placement surfaces in total, including Marketplace, Search, right-hand column
and notifications.

This matters more than any split-testing question. Independent ad-fraud analyses
put Audience Network invalid-traffic rates several times those of the Facebook or
Instagram feed, and `rewarded_video` pays people to interact — a click there is
someone collecting a reward in a mobile game, not a Danish office manager.

`campaigns/structure.md` already said to turn Audience Network off. The live ad set
has it on. **This is the single highest-value fix before launch**, because at
EUR 4.69/day junk clicks are a far bigger threat than statistical power.

⚠️ **Do not go fully manual.** Current practitioner guidance is to stay on
Advantage+ placements and exclude *only* Audience Network — restricting placements
without cause tends to raise cost per result. This supersedes `structure.md`'s
"manual placements" instruction.

⚠️ **Time-sensitive.** Meta is removing ad-set-level placement controls through
2026 on a staggered rollout with no published cut-off. If the ad-set exclusion is
already gone on this account, use the **account-level** placement control, which
survives the change.

---

## 3. The arithmetic. Read this before designing any test

Impressions DKK 35/day buys, at a range of plausible CPMs, split three ways:

| CPM (EUR) | impressions/day | per ad | clicks/ad/day @ 1% CTR |
|---|---|---|---|
| 4 | 1,173 | 391 | 3.9 |
| 8 | 586 | 195 | 2.0 |
| 12 | 391 | 130 | 1.3 |
| 20 | 235 | 78 | 0.8 |

Impressions **per ad** needed to call a winner (two-proportion test, α .05, power .80):

| Difference being detected | Impressions per ad |
|---|---|
| CTR 0.8% vs 1.2% | **9,712** |
| CTR 1.0% vs 1.5% | 7,750 |
| CTR 1.0% vs 2.0% | 2,319 |
| CTR 1.0% vs 3.0% | 769 |

Days to a statistically callable result on the realistic 0.8%-vs-1.2% bar:

| CPM (EUR) | Days | Spend to get there |
|---|---|---|
| 4 | 25 | EUR 117 |
| 8 | 50 | EUR 233 |
| 12 | 75 | EUR 350 |
| 20 | **124** | EUR 583 |

**Conclusion: statistical significance is unreachable on any sane timeline.**
Not because three ads is the wrong number — because EUR 4.69/day is the budget.
Dropping to two ads moves 124 days to 83. Still unreachable.

So the question is not *"how do I run a valid test."* It is
*"what do I want to learn, given a valid test is not available at any ad count."*

---

## 4. Two findings that decide the structure

### (a) Meta will not split the ad set evenly. It concentrates.

Meta does **not** divide ad-set budget across the ads under it. It predicts from
early signals and concentrates, **routinely giving one ad over 90% of spend**.

So "one ad set, three ads" does not run three ads. It runs whichever ad Meta
liked in the first few hours, plus two that never get a sample. That is not a
weak test — it is no test, and it silently discards two of the three angles.

### (b) A 25% gap between ads is what *identical* ads produce

Jon Loomer ran **three identical ad sets** — same creative, same targeting, same
optimisation. The top one got **25% more conversions than the bottom**. Meta's own
reported confidence that the winner would repeat: **59%**.

Put those together and the ranking you will see after 14 days is, at this volume,
noise with a label on it. https://www.jonloomer.com/results-identical-ad-sets/

Backstop from the literature: Lewis & Rao (*QJE* 2015), 25 large field
experiments — median ROI confidence interval **over 100 percentage points wide**.
Below a certain scale the information is not purchasable at any price a rational
advertiser would pay.

---

## 5. Real CPMs, and what they actually buy

| Source | CPM (USD) | Date |
|---|---|---|
| Lithuania | **$6.51** | 2026-07 |
| Denmark | **$8.74** | 2026-07 |
| Traffic objective, all industries | $8.94 | Q1 2026, US |
| Denmark, all-industry median | $16.02 | Jul 2025–May 2026 |

⚠️ The **spread between sources for Denmark ($8.6–$16) is wider than the DK–LT
gap**. Treat any single figure as low confidence. Every source is an ad-tech
vendor with a commercial incentive and none publish sample sizes.

**Lithuania is ~25% cheaper than Denmark.** Delivery will skew there and the
blended CPM will read as Lithuania's. The country breakdown is not optional.

At a blended CPM of ~$7.29 (65% LT / 35% DK), DKK 35/day buys:

- **~739 impressions/day** total · **~246 per ad** across three
- **~6 link clicks/day** at a realistic 0.8% cold B2B link CTR
- **14 days per ad = ~3,449 impressions, ~28 clicks — 36% of the significance bar**

⚠️ **Q4 seasonality.** Global Meta CPM rose **+28.7%** from July to November 2025.
Launching in late September means costs climb under you for the whole run.
At +30% the same budget buys 568 impressions/day, and the days-to-significance
figure goes from 39 to **51**.

**Benchmark for reading the result:** cold B2B **link** CTR of 0.6–1.0% is normal.
Below 0.5% is a creative problem, not bad luck.

---

## 6. The structure this forces

### The tool that solves the concentration problem

Meta ships a **Creative Test** in Ads Manager, separate from the A/B Test. It runs
**inside one active ad set and spends near-evenly across the ads**, Highest Volume
bidding only. https://www.facebook.com/business/help/1423851372208214

That is the precise fix for §4(a). Use it, and "one ad set, three ads" becomes a
real three-way delivery instead of Meta picking one. No ABO split needed, and
consolidation — which is still Meta's official guidance — is preserved.

⚠️ **Correction to earlier advice in this session.** I said Meta's A/B Test tool
is for structural questions only and does not cover creative. Meta's own docs say
creative **is** explicitly supported. The reason to avoid it here is different and
still decisive: **the A/B Test splits your audience**, which doubles the
under-delivery risk at this spend. Meta's own listed fix is "increase your budget"
or "broaden your audiences". https://www.facebook.com/business/help/1738164643098669

### The number that matters most

Meta publishes exactly one numeric budget rule, and it uses link clicks as its
example: **"your daily budget should be at least 10 times the average cost of your
performance goal."** https://www.facebook.com/business/help/666335734044063

DKK 35/day = USD 5.39, so it complies only if **CPC ≤ USD 0.54 (DKK 3.50)**.

| CPC benchmark | Meta's rule needs | vs DKK 35 |
|---|---|---|
| Traffic objective, all industries $0.70 | USD 7.00/day = **DKK 45** | 1.3x short |
| Europe, all objectives $1.18 | USD 11.80/day = **DKK 88** | 2.5x short |
| B2B / SaaS $2.94 | USD 29.40/day = **DKK 219** | 6.3x short |

**DKK 35/day sits below Meta's own stated minimum for this objective**, by
somewhere between 1.3x and 6x depending on which CPC you land on. This is not a
practitioner opinion — it is Meta's published guidance, and it is checkable
against your own CPC in week one.

**If there is one change worth making before launch, it is the budget**, not the
creative structure. DKK 50-90/day puts you inside Meta's own rule for a realistic
European CPC. At DKK 35 you are running under-delivered by the platform's own
definition, and "Learning Limited" is the expected steady state — which Meta is
explicit is *"not a penalty… an indication that your budget isn't being spent
effectively."* https://www.facebook.com/business/help/269269737396981

### What significance would cost

Unreachable regardless: 39 days at the blended CPM, 51 with Q4 inflation, 26 days
even at two ads. The budget question above is about *delivery quality*, not about
buying significance — significance is not for sale here at any price you would
rationally pay (Lewis & Rao).

### Recommendation

**One ad set. Three ads. Run them through the Creative Test tool.** Keep CBO as
it is — with a single ad set, Meta says CBO vs ad-set budgets is a no-op
("best suited for campaigns with at least 2 ad sets"). Raise the budget if you
can; DKK 50+ is the first meaningful improvement available.

⚠️ Note the tension, and accept it knowingly: Meta's official line is **"decrease
ads per ad set, but maintain diverse creative assets per ad set"** — fewer ad
objects, diversity inside them. Three separate ads is a deliberate trade against
that guidance, and the Creative Test tool is the documented way to buy it back.
https://www.facebook.com/business/help/2720085414702598

---

## 6b. Why all three must start together, and nothing may be touched

Mechanical, not stylistic. In 2026 the learning phase resets on: targeting change,
**creative addition**, optimisation-event change, bid-strategy change, any budget
change over 20% — and **pausing**.

- Add a fourth ad in week two → the ad set re-enters learning, prior history stops
  counting.
- Pause the "loser" on day three → per §4(b) you would have paused an ad set
  statistically indistinguishable from the one that "won".

Read only on **whole 7-day boundaries**, so the weekday mix stays constant.
Meta's own split-test tool enforces a 3–14 day window and practitioners put the
reliable floor at 7 days.

---

## 7. The procedure

**Before launch**
1. Exclude **Audience Network** — ad-set level if still available, else account level.
   Leave every other Advantage+ placement on.
2. Leave CBO as is (no-op on one ad set). **Raise the budget to DKK 50-90/day if you can** — Meta's own 10x rule.
2b. Set the three ads up as a **Creative Test**, so spend is even instead of concentrated on one.
3. Settle the lane, the AI disclosure, and the Instagram account id.
4. Build paused. Run `python -m engine.cli check` first.

**Launch**
5. Unpause all three ads in the same minute. Adding one later is a
   "significant edit" by Meta's definition and resets learning.

**The next 14 days**
6. **Touch nothing.** No pausing, no adding, no budget edits.
7. Read at day 7 and day 14 only. Whole weeks, never partial.

**What to read**
8. **CPM, with the country breakdown open.** This is what the spend buys.
9. **Link CTR per angle.** Directional. A gap under ~50% means nothing (§4b).
10. **Gross failure only** — zero clicks in 3,000 impressions is a real signal.
11. **Qualitative** — comments, shares, which objection provokes a reaction.
    At this volume this is worth more than the CTR table.

**Never quote:** cost per lead, which creative converts, whether Meta works for
DoviLoop. `structure.md`: *"noise wearing a number's clothes."*

---

## 8. If you want an actual creative test later

You need roughly **EUR 10-12/day minimum** for a traffic objective before element
testing (headline, CTA, format) means anything — and practitioner guidance for
link-click objectives sits at USD 25-50/day per ad set. At that point the order is:
concept first (which angle), element second (which execution of the winning angle).
Never element-test an angle you have not yet confirmed.
