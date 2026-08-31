# ad-engine

Meta ads for DoviLoop. Audiences, creative, and a gate that stops unverifiable
claims reaching a public ad.

Sibling to `reel-engine` and `outreach-engine`; all three work from the same
locked brief in `docs/ICP-BRIEF.md`.

```
audiences/<name>.json   who      targeting specs, ranked by priority
creative/<variant>.json the words  ad copy, one per A/B arm
claims/evidence.json    the truth  what may be claimed, and what may not
engine/                 the code   audience build, claims gate, export
```

---

## Quick start

```bash
python -m engine.cli plan                                  # audiences + blockers
python -m engine.cli check                                 # claims gate over creative
python -m engine.cli audience ../outreach-engine/queue/acc-dk.csv --out queue/aud.csv
```

## The targeting problem, and the answer

This ICP is **~700–800 firms**. Meta cannot target "Danish accounting firms with
10+ staff" — that targeting does not exist — and a 750-company audience is far
below what its optimiser needs.

**So stop asking Meta to do the targeting.** `outreach-engine` already produces
the exact list. Upload it hashed as a Custom Audience and Meta becomes
account-based air cover over outreach, not a prospecting channel:

> ~750 firms × 2–3 contacts ≈ **2,000 people**, comfortably over Meta's 1,000
> minimum — but only with both countries and all three verticals combined. A
> single-vertical slice will under-deliver.

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

Currently allowed, because each is a verifiable product fact: never auto-sends ·
never leaves Outlook · EU-hosted · answers from the firm's own documents · a
voice profile per person.

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

## Known state

- **Meta pixel is not installed on doviloop.dev.** `site-retargeting` cannot be
  built until it is, and it needs to start collecting well before ads run or
  there will be nobody in it. **Do this first — it costs nothing and it is the
  only audience that compounds.**
- **Revenue is switched off** in the product (`TEST_MODE` plus two `BYPASS_*`
  flags). Traffic can arrive and convert to a conversation, but not to a payment.
- Danish and Lithuanian creative is drafted, **not native-checked**.

## Why this runs at all

The brief argues ads are the weakest of the three channels for this ICP, and
that stands. It runs anyway, deliberately: the operator wants the reps —
pixel, audiences, creative testing, attribution — and that is a legitimate
reason. **Judge it on what it teaches, not on pipeline.** Cold outreach is where
the pipeline should come from.
