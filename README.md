# ad-engine

Meta ads for DoviLoop. Audiences, creative, and a gate that stops unverifiable
claims reaching a public ad.

> **Campaign-wide documents live in `campaign-n8n/ops/`.** This repo is one of six
> batches; the status of all of them, the setup guide for a new machine, the
> decisions taken and what is still waiting on a human are kept together there:
>
> | File | What |
> |---|---|
> | `ops/STATUS.md` | audit of all six batches |
> | `ops/NEW-PC-SETUP.md` | clone, install and prove every repo from scratch |
> | `ops/DECISIONS.md` | what was decided, why, and how to reverse it |
> | `ops/NIGHT-RUN.md` | the current task plan and its live status |
> | `ops/HANDOFF.md` | what to pick up next |
>
> The six repos must be cloned as **siblings under one parent directory** -
> several tools reach across them by relative path, and this repo's own contract
> tests locate `campaign-ledger` that way.


Sibling to `reel-engine` and `outreach-engine`; all three work from the same
locked brief in `docs/ICP-BRIEF.md`.

```
audiences/<name>.json   who        targeting specs, ranked by priority
creative/<variant>.json the words  ad copy, one per A/B arm
claims/evidence.json    the truth  what may be claimed, and what may not
engine/                 the code   audience build, claims gate, export

research/objections.md  the why    five competitor-sourced objections
creative/copy/          the words  six campaign copy variants
creative/static/        the images the typeset ad pipeline, 8 creatives x 2 ratios
creative/video/         the cut    how to cut reel-engine masters to 15s ads
campaigns/              the build  Ads Manager build sheet and pixel install
report/                 the numbers daily Meta Insights into campaign.ad_stats
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

---

## The teams_q4 campaign (Batch E, Sept to Oct 2026)

The repo above is the pre-campaign account-based layer. On top of it sits a
**retargeting** campaign for `teams.doviloop.dev`, under EUR 500 a month,
English only in all three markets.

```bash
python -m engine.cli check                 # claims gate, now recurses into creative/
python -m creative.static.render all       # 8 creatives x 2 ratios -> creative/static/out/
python -m creative.static.vet              # the brand lock, as an automated check
python report/pull_ad_stats.py --dry-run   # Meta Insights -> campaign.ad_stats, on a fixture
python -m pytest -q
```

Read in this order:

1. **`research/objections.md`** first. Everything else is downstream of it. Five
   objections for accounting, insurance and housing admin, each traced to a
   named public competitor source rather than invented.
2. `campaigns/structure.md` to build the campaign by hand in about 20 minutes.
3. `campaigns/pixel-install.md` before anything else actually happens, because
   every audience is empty until the pixel has been collecting for two weeks.
4. `BLOCKED.md` and `RUN-REPORT.md` for what is missing and what Dovy has to do.

### Three things about this campaign that are easy to get wrong

- **It measures clicks, not conversions.** At EUR 16 a day there are not enough
  lead events to compare ad sets on cost per lead. `campaigns/structure.md` says
  this at length and does not soften it.
- **The claims gate governs every word.** No time saving figure, no percentage,
  no customer count appears in any of the six copy variants or the eight
  creatives. Dovy confirmed on 2026-09-06 that the ROI figures are a model,
  not a measurement, so the gate's call stands. A modelled figure may appear
  only in an ad that says so itself; see `BLOCKED.md` entry 3 and
  `claims/evidence.json`.
- **No ad video gets shot.** `creative/video/cut-spec.md` is a cutting spec for
  reel-engine's weekly English masters, trimmed to 15 seconds with a harder CTA.

## The ledger seam

`report/pull_ad_stats.py` writes one `campaign.ad_stats` row per ad set per day
through Batch B's `campaign_db.snapshot_ad_stats`. The import is defensive
(`report/pull_ad_stats.py:86`): while `campaign_db` is not importable it falls
back to `report/ledger_shim.py`, which writes the same row shape to
`report/out/ad_stats.jsonl` and says loudly that the ledger is not connected.
That fallback is why this repo was testable before Batch B landed; it is not a
substitute for the ledger.

`campaign_db.py` lives in the sibling `campaign-ledger` repo. Put its `src` on
the Python path to write to Postgres instead of JSONL:

```bash
export PYTHONPATH=/path/to/campaign-ledger/src
python report/pull_ad_stats.py --date 2026-09-08
```

`campaign_db.py` reads `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` itself. This
repo holds neither, and never connects to Supabase directly - its own
`.env.example` carries only the Meta credentials.

The column list in `report/ledger_shim.py` is fixed by Batch B's schema:
`campaign_name`, `ad_set_name`, `creative_content_id`, `captured_on`,
`spend_eur`, `impressions`, `clicks`, `leads`. `id` is generated by the
database and is never written from here.

Unlike the other two engines, this suite is unaffected by `PYTHONPATH` -
**89 passed** either way, and `tests/test_ad_stats.py` is **13 passed** against
the real client. Both verified 2026-09-08.

Batch F's `WF-C6` invokes this every Friday as
`cd <ad_engine_repo> && python3 report/pull_ad_stats.py --date <yesterday>`.

## Why this runs at all

The brief argues ads are the weakest of the three channels for this ICP, and
that stands. It runs anyway, deliberately: the operator wants the reps —
pixel, audiences, creative testing, attribution — and that is a legitimate
reason. **Judge it on what it teaches, not on pipeline.** Cold outreach is where
the pipeline should come from.
