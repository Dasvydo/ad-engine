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

## 4. Which means: three ads is correct, for a reason that is not testing

| Goal | Right ad count | Available here? |
|---|---|---|
| A statistically valid creative winner | — | **No. Not at any count.** |
| A real CPM for this market | 1 is enough; 3 costs nothing extra | **Yes** |
| Funnel validation, click → page → UTM → pixel | 1 is enough | **Yes** |
| Directional read on which objection lands | 3 | **Yes, roughly** |

CPM is measured at ad-set level regardless of how many ads sit under it, so
splitting three ways costs the CPM reading **nothing**. And the directional
objection read — which `structure.md` calls *"the single most valuable output"* —
needs three angles to exist at all.

Three ads it is. Not as a test. As three probes sharing one CPM measurement.

---

## 5. Why all three must launch in the same moment

Mechanical, not stylistic. In 2026 the learning phase resets on: targeting change,
**creative addition**, optimisation-event change, bid-strategy change, and any
budget change over 20%. **Pausing an ad set also resets it.**

- Add a fourth ad in week two → the ad set re-enters learning, and the first two
  weeks of delivery history stop counting.
- Pause the "loser" on day three → same reset, plus you have thrown away the only
  ad that was accumulating a comparable sample.

Each reset is reported to cost roughly 5-15% of the following week's performance.
On a 14-day run you cannot afford one.

---

## 6. The procedure

**Before launch**
1. Exclude **Audience Network** — ad-set level if still available, otherwise
   account-level. Leave every other Advantage+ placement on.
2. Settle the three open questions: the **lane** (never-leaves-Outlook / voice /
   guarantee), **AI disclosure** on the statics, **Instagram account** id.
3. Build all three ads **paused**. Run `python -m engine.cli check` first.

**Launch**
4. Unpause all three in the same minute, then the ad set, then the campaign.
5. Leave the budget where it is — campaign-level CBO, one ad set, so CBO has
   nothing to misallocate between.

**The next 14 days**
6. **Touch nothing.** No pausing, no adding, no budget edits, no targeting tweaks.
7. Read nothing before day 7. Day 3 is noise.

**Reading it**
8. **CPM** — the number this campaign exists to buy. Open the **country breakdown
   every time**: Lithuania is cheaper, Meta will skew delivery there, and the
   blended figure will quietly be Lithuania's.
9. **Link CTR per ad** — ranks the three angles. Directional only. Never quote it
   as significant.
10. **Frequency** — expected to stay low here. It is the primary metric for the
    ~2,000-person custom audience, *not* for broad DK+LT geo. Do not apply that
    rule to this campaign.

**Do not measure:** cost per lead, which creative converts, whether Meta is a
viable channel. `structure.md`: *"noise wearing a number's clothes."*

---

## 7. If you want an actual creative test later

You need roughly **EUR 10-12/day minimum** for a traffic objective before element
testing (headline, CTA, format) means anything — and practitioner guidance for
link-click objectives sits at USD 25-50/day per ad set. At that point the order is:
concept first (which angle), element second (which execution of the winning angle).
Never element-test an angle you have not yet confirmed.
