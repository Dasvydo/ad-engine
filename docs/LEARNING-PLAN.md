# What "learning" means here

This project runs because the operator wants the reps — pixel, audiences,
creative testing, attribution — knowing ads are the weakest of the three
channels for this ICP. That is a legitimate reason and it is not relitigated
here. But "we're doing it to learn" is only honest if *learning* is defined in
advance, with numbers, before there is a dashboard to rationalise against.

So: every question this campaign can answer, the metric that answers it, what a
result would have to look like to act on, and — for each — what it cannot tell
you no matter how good it looks.

---

## The two constraints that shape everything below

**1. Revenue is switched off.** `TEST_MODE` plus two `BYPASS_*` flags mean
traffic can reach a conversation but not a payment. So:

- There is no cost-per-acquisition. There is no ROAS. There is no
  conversion rate, because no conversion exists.
- The deepest honest funnel step is **a conversation started**.
- Any Ads Manager column containing the word *purchase* or *value* is either
  empty or wrong. If it is not empty, someone implemented a `Purchase` event
  that fires on a transaction that did not happen — see
  `docs/PIXEL-INSTALL.md` §4, and remove it.

**2. The volume is tiny and mostly not fixable.** ~700–800 firms, ~2,000
contacts, a €13/day launch budget. Most statistical questions are simply out of
reach, and the useful move is knowing *which* ones in advance rather than
discovering it in a monthly review.

---

## The sample-size reality, stated once

The creative A/B — `capacity` vs `hours` — is the brief's highest-value
question. Here is exactly how much of it Meta can answer.

To detect a CTR difference of **1.0% → 1.5%** (a 50% relative lift, which is a
*large* effect) at 95% confidence and 80% power, a two-proportion test needs
about **7,750 impressions per arm**. Smaller differences get expensive fast:
1.0% → 1.2% needs ~42,700 per arm. A 1.0% → 2.0% doubling needs ~2,300.

| Ad set | Impressions/arm available | Powered for the A/B? |
|---|---|---|
| `as-broad-interest-dk` + `-lt` combined | ~15,000–40,000 per month, depending on CPM (€8 → 15k, €3 → 40k) | **Yes**, for a ≥50% relative difference |
| `as-outreach-list` | ~7,500–10,000 impressions/month per arm — but across only ~1,000 *reachable people* | **No** |
| `as-site-retargeting` | Unknown, small | No |

The outreach-list row is the important one, and the impression count is a trap.
Seven thousand impressions spread over a thousand people is each person seeing
each arm seven times. A significance test assumes independent observations;
seven repeated exposures to the same accountant are one observation with noise
on it. The effective sample is the **people**, ~1,000 per arm, against the
~7,750 the test needs.

**So the only place the creative A/B is powered is `broad-interest` — the one
audience that is definitionally not the ICP.** The audience that is right cannot
power a test; the test that can be powered is on the wrong people. This is not a
budgeting problem and more money does not fix it: the ICP is 700–800 firms.

The consequence is a decision, not a complaint: **the definitive `capacity` vs
`hours` read comes from `outreach-engine`**, where the arms are per-recipient,
language is free, and the volume exists. Meta can corroborate a direction. It
cannot settle the question, and a Meta result pointing the other way from
outreach should not overturn outreach.

---

## Question by question

### Q1 · Will Meta even match a B2B list? — **the first result, and it is free**

| | |
|---|---|
| **Metric** | Custom-audience match rate, and reported audience size, after uploading `queue/aud-outreach.csv` |
| **Where** | Ads Manager → Audiences, on the `ca-outreach-list-hashed` row |
| **Cost** | €0. No campaign has to run. |
| **Act on it if** | Matched size **< 1,000** → the entire account-based premise of this repo does not clear Meta's delivery floor. |
| **Cannot tell you** | Anything about whether the ICP is right. Only whether Meta can find them. |

This is the single highest-information, lowest-cost thing in the project and it
should happen before anything else that costs money.

Expect it to be worse than you think. Custom-audience match rates on **work**
email addresses are commonly 20–50%, because people do not sign up to Facebook
with `firstname@accountingfirm.dk`. 2,000 uploaded rows at a 35% match is ~700
matched people — *below* the floor, even though the CSV cleared it. The row
count in `engine/audience.py`'s warning is a necessary condition, not a
sufficient one.

**If it comes in short**, in order of preference: add phone number columns from
`outreach-engine` if it has them (phone matches better than work email); add any
personal-email column; combine every vertical and both countries, which
`audiences/outreach-list.json` already requires; and only then fall back to
using the list as a **lookalike seed** (100-person minimum), accepting that a
lookalike built from a weak B2B seed in two small countries is a different and
much vaguer thing than the audience you meant to build.

### Q2 · Does the pixel collect fast enough to be worth retargeting?

| | |
|---|---|
| **Metric** | Daily unique visitors reaching the pixel post-consent; growth curve of `pixel-all-visitors-90` |
| **Where** | Events Manager → Overview; Ads Manager → Audiences (size) |
| **Act on it if** | Audience **< 1,000 after 60 days** → `as-site-retargeting` never launches this quarter, and that is a finding, not a failure. Reallocate its €5/day or bank it. |
| | Consent-accept rate **< 30%** → the pool is capped by the banner, not by traffic, and more ad spend will not fix it. |
| **Cannot tell you** | Whether retargeting *works*. Only whether it can be attempted. |

### Q3 · Does `capacity` beat `hours`?

| | |
|---|---|
| **Metric** | Outbound CTR (link clicks ÷ impressions). *Outbound*, not all-clicks — all-clicks counts reactions and profile taps. |
| **Where** | Broad-interest ad sets only, DK and LT pooled, ad-level breakdown |
| **Act on it if** | One arm leads by **≥50% relative** (e.g. 1.0% vs 1.5%) on **≥7,750 impressions per arm**. Below either threshold, record the number and change nothing. |
| **Cannot tell you** | Whether the ICP prefers it. These are not ICP people — that is the entire point of Q5's checklist. A win here says the *sentence* works on a lay audience. |

A result of "capacity leads by 0.2 points" after two weeks is noise and must be
written down as noise. The commonest failure mode of a small ad test is not a
wrong conclusion, it is a confident one.

### Q4 · Does the creative hold attention? — **the best-powered question here**

| | |
|---|---|
| **Metric** | Hook rate (3-second video plays ÷ impressions); hold rate (ThruPlay ÷ 3-second plays); the 25/50/75/95% retention curve |
| **Where** | Ad level, every ad set |
| **Act on it if** | Hook rate **< 20%** → the first three seconds fail and nothing downstream matters; recut in `reel-engine`. A **≥10-point** gap between arms is worth acting on. |
| **Cannot tell you** | Whether anyone will buy. Retention measures the edit, not the offer. |

This is the one question small budgets answer well, because it is measured per
impression, the effects are large, and it needs no conversion. If this project
teaches exactly one thing, it will probably be this one — and it transfers
directly to `reel-engine`, which is a channel with real reach.

### Q5 · What does it cost to reach this ICP on Meta at all?

| | |
|---|---|
| **Metric** | CPM on `as-outreach-list` vs CPM on the broad-interest ad sets; delivered reach ÷ matched audience size; frequency |
| **Act on it if** | Custom-audience CPM **> 3×** broad CPM → the small-audience premium is real and now quantified; that number is an input to whether Meta is ever worth running against a list this size. |
| | Reach plateaus **< 60%** of matched size → Meta cannot actually deliver to the list even when it matches it, which is a harder stop than a low match rate. |
| **Cannot tell you** | Whether the impressions did anything. Reach is delivery, not effect. |

### Q6 · Does traffic from each source behave differently once it lands?

| | |
|---|---|
| **Metric** | Sessions, session duration, pages/session, pricing-page rate — **split by `utm_term`** (which carries the ad set name) |
| **Where** | Site analytics, **not** Ads Manager |
| **Act on it if** | Outreach-list and retargeting traffic look **statistically indistinguishable from** broad-interest traffic → either the list is not who you think it is, or `advantage_custom_audience` got left on and Meta is serving outside the list. **Check that setting first, before concluding anything about the ICP.** |
| **Cannot tell you** | Intent. A 4-minute session from a curious student looks like a 4-minute session from a managing partner. |

### Q7 · Does any of it start a conversation?

| | |
|---|---|
| **Metric** | `Lead` events, and — separately and more reliably — actual inbound enquiries with a Meta UTM on first touch |
| **Act on it if** | Nothing numeric. **Expect zero.** One to three conversations is an anecdote, and treating an anecdote as a rate is how a €390/month experiment turns into a €4,000/month one. |
| **What is actually valuable** | The *content* of any conversation that does happen — which framing they repeat back, whether they raise Outlook, auto-send, or EU hosting unprompted. That is qualitative evidence about the offer, and it is worth more than the count. |
| **Cannot tell you** | Anything about willingness to pay. They could not pay if they tried; revenue is off. |

### Q8 · Free mechanics, no hypothesis needed

Placement breakdown (Feed vs Reels vs Stories vs Audience Network), device,
hour-of-day, DK vs LT cost difference, and the shape of Meta's own delivery
behaviour on a tiny audience. Nobody needs to predict these in advance. Read
them monthly, write down what surprised you, and let them inform the next round.
This is most of the "reps" the project exists for.

---

## `broad-interest` results validate craft, not ICP

`audiences/broad-interest.json` already carries the warning. Here is the
procedure that makes it enforceable.

Meta interest targeting cannot isolate this ICP. "Accounting" as an interest
catches students, software shoppers, bookkeeping hobbyists, and people who
follow an accounting meme page — not twelve-person Danish firms. And the ad sets
in `campaign/structure.json` **exclude** the outreach list and the site
visitors, so a broad-interest converter is, by construction, someone not on the
ICP list.

**Before any broad-interest result is described as validating anything, answer
all seven of these about each actual converter:**

1. Is the submitted email at a **company domain** at all — or a free mailbox?
2. Is the firm in `outreach-engine`'s list? *If yes, the exclusion failed.* Stop
   and check whether `advantage_custom_audience` or detailed-targeting expansion
   is on, because that would invalidate every other reading in this document.
3. NACE **69.20, 82.11, or 66.22**?
4. **10+ people writing client email**? (Gate G4)
5. Microsoft 365 / Outlook? (Gate G1, G2)
6. **No in-house development team**? (Gate G6 — the walk-away)
7. Denmark or Lithuania?

Fail any of 3–7 and the honest write-up is: *"the ad converted someone. It was
not the ICP."* That is a real and useful finding — it means the craft works —
and it is a different sentence from *"our ICP responds to Meta ads,"* which this
ad set is structurally incapable of demonstrating.

The one genuinely interesting outcome would be **repeated** conversions from a
consistent segment nobody targeted. That is not ICP validation either; it is a
prompt to go re-check whether the ICP is drawn too narrow — a question for the
locked brief and the canonical `ICP_LOCKED.md`, not something to fix by editing
an ad set.

---

## Comparisons that are invalid, however tempting

- **CTR on `cmp-aircover` vs CTR on `cmp-response`.** Different objectives.
  Meta optimises reach in one and link clicks in the other; the first is
  *supposed* to have a worse CTR. Comparing them measures the objective setting,
  not the audience.
- **Anything against an industry benchmark.** Published B2B SaaS benchmarks come
  from campaigns with conversion events, real budgets, and audiences three
  orders of magnitude larger.
- **"Learning Limited."** Every ad set here will show it, permanently. It is a
  description of the volume, not a diagnosis of the setup, and chasing it out of
  the dashboard means abandoning the account-based structure that is the only
  reason Meta is usable at all.
- **Quality / engagement / conversion rate rankings.** Meta suppresses these
  below volume thresholds this project will not reach.
- **Week-over-week anything**, at these numbers. Read monthly.

---

## Stopping rules, written down now

Set before the data exists, so they are not negotiated afterwards.

| Condition | Then |
|---|---|
| Matched custom audience < 1,000 and no fallback recovers it (Q1) | Do not launch `cmp-aircover`. The account-based premise fails at Meta's floor. Write it up; the €0 spent is the whole point. |
| Pixel audience < 1,000 at 60 days (Q2) | `as-site-retargeting` does not launch this quarter. |
| Hook rate < 20% across every ad after 10,000 impressions (Q4) | Stop spending and recut in `reel-engine`. Budget spent on creative nobody watches for three seconds buys nothing. |
| One full month, all questions Q1–Q6 answered, zero conversations (Q7) | **Expected.** Not a stopping condition. The learning objectives were met; that was the deal. |
| Spend has risen above the declared ceiling in `campaign/structure.json` without a written reason | Stop. The project's justification is learning, and learning has a fixed price. |

---

## Where the numbers come from

| Number | Source | Not from |
|---|---|---|
| Impressions, reach, frequency, CPM, CTR, video retention | Ads Manager | — |
| Match rate, audience size | Ads Manager → Audiences | — |
| Sessions, page depth, pricing views | Site analytics, split by UTM | Ads Manager's click count, which will not agree and does not have to |
| Conversations | The inbox and the calendar | `Lead` event counts alone |
| Anything with a currency symbol beyond spend | **Nowhere. It does not exist yet.** | Any dashboard that offers one |

Review monthly, not weekly. Write the answer to each question down — including
"still no signal", which is a legitimate and common answer — and keep the write-up
next to this file so the second month can disagree with the first.

**Nothing measured here may become a public claim without an entry in
`claims/evidence.json`.** A campaign that finally produces a number is exactly
the moment someone wants to put that number in an ad. Run `python -m engine.cli
check` and let the gate decide.
