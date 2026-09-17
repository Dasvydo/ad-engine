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
docs/FUNNEL-HANDOFF.md  the seam   where the click lands, and what comes back
```

**Read `docs/FUNNEL-HANDOFF.md` first.** It is the contract with the landing page:
the destination URL, the UTM convention that `campaign-site` already enforces in
code, and the four pixel events the page sends back. Two of its items block the
first ad.

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

Audiences are ranked accordingly: `outreach-list` (1), `site-retargeting` and
`pricing-viewers` (2), `broad-interest` (3, kept for practice rather than results).

**That minimum decided the ad-set shape.** Because the list clears 1,000 only when
both countries are combined, it cannot be split into a Danish ad set and a
Lithuanian one — that split *is* the slice the note above warns about. Decided
2026-09-17: **one combined ad set, on the English landing page.** Delivery over
localisation, on the one audience that cannot have both. The two pixel audiences
are built from page traffic and arrive already language-sorted, so they keep their
`/da` and `/lt` rows. Full matrix in `docs/FUNNEL-HANDOFF.md`.

All PII is SHA-256 hashed after normalisation, per Meta's spec, so the raw list
never leaves this machine.

## The claims gate

**Ads make public factual assertions. This repo refuses to ship ones nothing
backs.** `claims/evidence.json` records what may be claimed; `engine/gate.py`
scans copy for measurable assertions and blocks any that aren't verified.

`--landing` points the same scan at the landing page's copy, because the ad and
the page behind the click are one unit to a reader. Those findings are advisory
and do not fail the run: the page may state a modelled figure while carrying its
disclosure in the same eyeline, and an ad may not state it at all.

Currently blocked, deliberately:

| Claim | Why |
|---|---|
| Any time-saving number | No customer outcome exists. The pricing page's "10 hours" is a model, not an observation. |
| "Trusted by N firms", logos, testimonials | Zero closed customers as of 2026-08-31. |
| Any percentage | Nothing has been measured. |
| Any money-saved figure | The landing page renders one (`430 USD saved per month, for each person`). It is a model, labelled as one on the page. An ad carries no disclosure, so it may not echo it. |
| Any return multiple — `12x`, "pays for itself" | Computed on the page from that same modelled saving, and it moves whenever the price moves. |

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

- **⛔ There is no stable destination URL.** `teams.doviloop.dev` 301s to the
  product site through a Porkbun URL Forward (CNAME to `pixie.porkbun.com`), and the landing page serves from
  `campaign-site-azure.vercel.app`, which Meta cannot verify. **Nothing is safe to
  put in an ad until this is fixed.** Measured 2026-09-16 — see
  `docs/FUNNEL-HANDOFF.md`, Blocker 1.
- **The Meta pixel is built, not live.** It is installed and consent-gated on the
  campaign landing page, and its gate is tested (`npm run verify:consent`, 23/23
  PASS). It stays inert until `VITE_META_PIXEL_ID` is set in that project's Vercel
  settings and the page is redeployed. `site-retargeting` and `pricing-viewers`
  have nobody in them until then, and both need a head start on the ads. **Do this
  first — it costs nothing and they are the only audiences that compound.** No
  pixel is on `www.doviloop.dev`, so product-site traffic is in neither pool.
- **Revenue is switched off** in the product (`TEST_MODE` plus two `BYPASS_*`
  flags). Traffic can arrive and convert to a conversation, but not to a payment.
- Danish and Lithuanian creative is drafted, **not native-checked**.

## Why this runs at all

The brief argues ads are the weakest of the three channels for this ICP, and
that stands. It runs anyway, deliberately: the operator wants the reps —
pixel, audiences, creative testing, attribution — and that is a legitimate
reason. **Judge it on what it teaches, not on pipeline.** Cold outreach is where
the pipeline should come from.
