# ad-engine

Meta ads for DoviLoop. Audiences, creative, and a gate that stops unverifiable
claims reaching a public ad.

Sibling to `reel-engine` and `outreach-engine`; all three work from the same
locked brief in `docs/ICP-BRIEF.md`.

```
audiences/<name>.json    who        targeting specs, ranked by priority
creative/<variant>.json  the words  ad copy, one per A/B arm
campaign/structure.json  the shape  campaigns, ad sets and ads, declared not clicked
claims/evidence.json     the truth  what may be claimed, and what may not
engine/                  the code   audience build, claims gate, structure validation
docs/PIXEL-INSTALL.md    blocked    how to install the pixel on doviloop.dev
docs/LEARNING-PLAN.md    the point  which metric answers which question, and what counts
```

---

## Quick start

```bash
python -m engine.cli plan                                  # audiences + blockers
python -m engine.cli check                                 # claims gate over creative
python -m engine.cli audience ../outreach-engine/queue/acc-dk.csv --out queue/aud.csv
python -m engine.cli campaign                              # structure tree + validation
python -m engine.cli claims                                # every gate pattern, and what it asserts
```

## The targeting problem, and the answer

This ICP is **~700–800 firms**. Meta cannot target "Danish accounting firms with
10+ staff" — that targeting does not exist — and a 750-company audience is far
below what its optimiser needs.

**So stop asking Meta to do the targeting.** `outreach-engine` already produces
the exact list. Upload it hashed as a Custom Audience and Meta becomes
account-based air cover over outreach, not a prospecting channel:

> ~750 firms × 2–3 contacts ≈ **2,000 rows**, over Meta's 1,000 minimum — but
> only with both countries and all three verticals combined. A single-vertical
> slice will under-deliver.

Rows are not people, though. Meta matches uploaded work email addresses to
Facebook accounts poorly, so the *matched* audience can land under the floor
even when the CSV clears it. That match rate is the first thing this project
measures and it costs nothing — see `docs/LEARNING-PLAN.md` Q1.

Audiences are ranked accordingly: `outreach-list` (1), `site-retargeting` (2),
`broad-interest` (3, kept for practice rather than results).

All PII is SHA-256 hashed after normalisation, per Meta's spec, so the raw list
never leaves this machine.

## The claims gate

**Ads make public factual assertions. This repo refuses to ship ones nothing
backs.** `claims/evidence.json` records what may be claimed; `engine/gate.py`
scans copy for measurable assertions and blocks any that aren't verified.

Currently blocked, deliberately:

| Claim | Why |
|---|---|
| Any time-saving number | No customer outcome exists. The pricing page's "10 hours" is a model, not an observation. |
| "Trusted by N firms", logos, testimonials | Zero closed customers as of 2026-08-31. |
| Any percentage | Nothing has been measured. |
| Any price | The $49 design-partner rate is a proposal in the brief, never founder-stated. |
| Best / leading / #1 / the only X that | No market analysis exists. |
| Faster / better than | No benchmark against anything has been run. |
| 2x, twice as fast, half the time | A time-saving claim expressed as a ratio. |
| Error-free, never wrong, always accurate | An LLM drafting client email. This is the worst-exposure claim on the board. |
| Instantly, set up in 5 minutes | Onboarding builds the knowledge base first. It is not instant, by design. |
| SOC 2, ISO 27001, certified, "GDPR compliant" | None exists. EU hosting is not GDPR compliance. |
| Guaranteed, risk-free, money-back | The 30-day guarantee is real in the brief and has never been operated. Broadcasting it to two countries is a different instrument from offering it in a call - a human decision, not a default. |
| Trusted by / loved by / case study / star ratings | Social proof with no number in it is still social proof. |

Currently allowed, because each is a verifiable product fact: never auto-sends ·
never leaves Outlook · EU-hosted · answers from the firm's own documents · a
voice profile per person.

The gate is deliberately biased toward false positives: a blocked line that was
fine costs one rewrite, a claim that slips through costs a liability. Numbers
written as words are caught, and so are Danish and Lithuanian spellings — though
detection in both is a backstop, not coverage. **A native reviewer is the last
line for da/lt copy, not the gate.**

**Unblock a claim by adding evidence, never by loosening a pattern.** An
evidence entry is a reviewable record of a decision someone made; a regex edit
unblocks every future ad silently.

This is not pedantry. An investor specifically warned that a public measurable
promise with nothing behind it is real exposure for a company with no liability
cap and no insurance.

## Creative

Two variants, matching outreach-engine's arms so both channels test the same
variable:

| Variant | Framing |
|---|---|
| `capacity` | More clients, same team — **recommended, untested** |
| `hours` | Stop re-typing the same reply — **control** |

The `hours` arm deliberately carries **no number**, so it tests the framing
rather than smuggling in a metric the gate would block.

Video and stills come from `reel-engine` — reuse those renders rather than
commissioning new creative.

## Campaign structure

`campaign/structure.json` declares the whole account — two campaigns, four ad
sets, twelve ads — so it is reproducible rather than clicked together once in
Ads Manager. `python -m engine.cli campaign` renders it and checks it against
the rest of the repo: audience refs, creative refs, priorities, the claims gate,
unproofread locales, and that nothing is set to anything but `PAUSED`.

| Campaign | Objective | Why separate |
|---|---|---|
| `cmp-aircover` | Awareness / reach | Air cover over outreach. Success is *coverage of a known list*, not clicks. Optimising for clicks on 2,000 people makes Meta find the click-happy 5% and hammer them. |
| `cmp-response` | Traffic / link clicks | Retargeting and interest. Conversion optimisation needs ~50 events per ad set per week; this project will not see 50 in a quarter, so it would sit in Learning Limited forever. |

Ad sets carry the audience priority: `as-outreach-list` (1), `as-site-retargeting`
(2, blocked on the pixel), `as-broad-interest-dk` / `-lt` (3).

Three settings that are **on by default in Ads Manager and must be off**, each
of which silently defeats something this repo depends on:

- **Advantage custom audience** — expansion serves outside the uploaded list.
  The list *is* the targeting; expansion turns account-based air cover back into
  the broad prospecting that cannot work here.
- **Advantage detailed targeting** — makes the interests you set a suggestion,
  so a result cannot be attributed to the targeting you chose.
- **Advantage+ creative** — a *claims gate* issue, not a performance one.
  Standard enhancements can reword primary text. Copy reaching the public
  without passing `engine/gate.py` is what this repo exists to prevent.

## What this is supposed to teach

`docs/LEARNING-PLAN.md` sets it out per question, with thresholds fixed before
the data exists. The two facts that shape all of it:

**Revenue is off**, so there is no CPA, no ROAS, and no conversion rate. The
deepest honest funnel step is a conversation started.

**The A/B that can be powered is on the wrong people.** Detecting a 1.0% → 1.5%
CTR difference needs ~7,750 impressions per arm. Only `broad-interest` can
supply that — and its results validate craft, not ICP. `as-outreach-list` reaches
~1,000 people; seven repeated impressions to the same accountant are one
observation with noise on it, not seven. **So the definitive `capacity` vs
`hours` read comes from `outreach-engine`**, where volume exists and language is
free. Meta can corroborate a direction; it cannot settle the question.

The best-powered question here is whether the creative *holds attention* — hook
rate and retention curve, measured per impression, with large effects. That
answer transfers straight to `reel-engine`.

## Known state

- **Meta pixel is not installed on doviloop.dev.** `site-retargeting` cannot be
  built until it is, and it needs to start collecting well before ads run or
  there will be nobody in it. **Do this first — it costs nothing and it is the
  only audience that compounds.** Instructions: `docs/PIXEL-INSTALL.md`.
  Meta's copy-paste snippet is wrong for this site twice over — it fires before
  consent in two GDPR jurisdictions, and it records one PageView ever on a
  single-page React app.
- **Nothing here is live.** No campaign, ad set or ad has been created and no
  money is committed. Budgets in `campaign/structure.json` are proposals. A
  human launches.
- **The custom-audience match rate is the first result, and it is free.** Work
  email addresses match to Facebook accounts poorly — commonly 20–50%. 2,000
  rows at 35% is ~700 matched people, *below* Meta's 1,000 floor even though the
  CSV cleared it. Upload and read the number before spending anything.
- **Revenue is switched off** in the product (`TEST_MODE` plus two `BYPASS_*`
  flags). Traffic can arrive and convert to a conversation, but not to a payment.
- Danish and Lithuanian creative is drafted, **not native-checked**.

## Why this runs at all

The brief argues ads are the weakest of the three channels for this ICP, and
that stands. It runs anyway, deliberately: the operator wants the reps —
pixel, audiences, creative testing, attribution — and that is a legitimate
reason. **Judge it on what it teaches, not on pipeline.** Cold outreach is where
the pipeline should come from.
