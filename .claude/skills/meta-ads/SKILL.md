---
name: meta-ads
description: Run, read or change DoviLoop's Meta ads through the Meta Ads MCP connector. Use when asked to pull ad performance, build a report, investigate a spend or frequency change, write or vary ad copy, brief a creative, launch or pause anything, or check whether an ad is safe to ship. Also use before writing any DoviLoop ad copy, even when Meta is not mentioned.
---

# Meta ads — DoviLoop

**This account is not a normal ad account. Read this before touching anything.**

- ~750 firms in the whole addressable market. The custom audience is ~2,000 people.
- **Zero customers. Zero purchase events. ROAS does not exist here** and never will
  until a design partner signs.
- Meta needs ~50 optimisation events per ad set per week to leave the learning
  phase. This account will never supply that. **Meta will not optimise — it will
  just spend.** Every judgement is yours, not the algorithm's.
- Purpose is **account-based air cover over outreach**, not prospecting. The ads
  exist so a named firm has seen DoviLoop before the email lands.

Advice tuned for ecommerce — ROAS targets, creative-volume flywheels, winner
detection by spend share, 2-standard-deviation conversion alerts — is wrong here.
Do not import it.

---

## Hard rules

**1. No claim ships unless it is evidenced.**
Read `references/claims.md` before writing or varying any ad copy. Every factual
assertion must resolve to a `verified` entry there.

**⚠️ `engine/gate.py` will not save you.** It is five regexes hunting for digits.
`"Save ten hours a month"`, `"Cut your reply time in half"` and
`"Most firms see faster turnaround"` all pass it clean and are all unverifiable.
Reason about the **claim**, not the digit. Run the gate as a backstop, never as
the check:

```bash
python -m engine.cli check
```

**1b. Pre-hash before upload.** The audience tools accept raw PII and hash it
server-side. Do not use that path. Run `python -m engine.cli audience` first and
upload the hashed output, so the raw list never leaves the machine.

**2. Never split the audience.**
It clears Meta's 1,000-person delivery floor *only* with both countries and all
three verticals combined (`audiences/outreach-list.json`). Splitting by country,
by vertical, or into multiple ad sets breaks delivery entirely. One campaign, one
ad set, two ads.

**3. Frequency is the primary metric.** Not ROAS, not CPA, not CTR. On a
2,000-person audience reach saturates in days and frequency climbs hard. Check it
first, every time, before anything else.

**4. Confirm before every write.** Show the exact parameters, wait for an explicit
yes. Applies to creating, updating, unpausing, budget changes and audience edits.
The connector creates things **paused** — never unpause without being asked to.

**5. Never invent a number.** If a metric was not returned, say it was not
returned. "I didn't check" is an acceptable answer. A plausible-sounding figure
is not.

---

## Context guardrails

Reports here are small. Keep them small.

- `limit=10` on any listing call. Expand only when asked.
- `time_range="last_7d"` by default. Warn before pulling anything longer — a
  multi-month pull is slow and mostly noise on this spend level.
- Format returned JSON into a markdown table before reasoning over it. Never
  paste raw connector JSON into a reply.

---

## What the connector cannot do

Do not attempt these, and do not claim to have done them:

| | |
|---|---|
| ~~Create or manage audiences~~ | **CORRECTED 2026-09-16 — it can.** `ads_create_custom_audience` (subtype `CUSTOM`) then `ads_update_custom_audience_users`. Still build the file with `python -m engine.cli audience <csv>` first and pass pre-hashed values, so raw PII never leaves the machine |
| B2B targeting | Does not exist on any Meta surface. This is why the custom audience exists at all |
| ~~Read creative assets~~ | **CORRECTED — it can.** `ads_get_ad_preview`, `ads_get_ad_images`, `ads_get_ad_videos`, `ads_get_creatives`, plus upload tools |
| Competitor research | **`ads_library_search` exists.** Earlier docs said no |
| Anomaly detection | **`ads_insights_anomaly_signal` is native** — no need to hand-build the videos' detector |
| A/B testing | `ads_experiment_abtest_*` — relevant to the `capacity` vs `hours` arms |

---

## Routing

| Task | Read |
|---|---|
| Writing or varying ad copy | `references/claims.md` — **mandatory** |
| Daily / weekly report, alerts, what to watch | `references/operating-loop.md` |
| Launching for the first time, or setting anything up | `docs/META-ADS-RUNBOOK.md` |
| Why the setup is shaped this way | `docs/META-MCP-SETUP.md`, `docs/META-MCP-MAP.md` |
| What may be claimed, canonical | `claims/evidence.json` |

`references/claims.md` is generated. After editing `claims/evidence.json`:

```bash
python scripts/sync_skill_claims.py
```
