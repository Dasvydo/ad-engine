# ad-engine — Claude Code context

Meta ads for DoviLoop. This file is a router and is re-read every turn, so it
stays short.

## Before you touch ad copy

**Read `.claude/skills/meta-ads/references/claims.md`.** DoviLoop has zero
customers and zero measured outcomes. Every factual assertion in an ad must
resolve to a `verified` entry in `claims/evidence.json`, or it does not ship.

⚠️ **`engine/gate.py` is a backstop, not the check.** It is five regexes hunting
for digits. `"Save ten hours a month"`, `"Cut your reply time in half"` and
`"Most firms see faster turnaround"` all pass it clean and are all unverifiable.
Reason about the claim, not the digit. Run it anyway:

```bash
python -m engine.cli check
```

## Where things are

| | |
|---|---|
| `docs/META-ADS-RUNBOOK.md` | **A-to-Z.** Vocabulary, account setup, pixel, launch, operating loop. Start here if anything is unclear |
| `docs/META-MCP-SETUP.md` | What the Meta MCP connector can and cannot do, and why |
| `docs/META-MCP-MAP.md` | The same thing as three diagrams |
| `.claude/skills/meta-ads/` | The skill. Loads the above on demand; also packageable for Claude Desktop |
| `docs/ICP-BRIEF.md` | Who we sell to and how to talk about it. Locked 2026-08-31 |
| `claims/evidence.json` | Canonical: what may be claimed |

## Commands

```bash
python -m engine.cli plan                    # audiences in priority order, with blockers
python -m engine.cli check                   # claims gate over creative/
python -m engine.cli audience <src.csv>      # hash an outreach list into a Custom Audience
python scripts/sync_skill_claims.py          # regenerate the skill's claims copy
python scripts/sync_skill_claims.py --check  # fail if it is stale
```

## Standing facts

- **~750 firms total.** The custom audience is ~2,000 people. It clears Meta's
  1,000 floor **only** with both countries and all three verticals combined —
  **never split it**. One campaign, one ad set, two ads.
- **No ROAS, no CPA, no conversion optimisation.** Meta wants ~50 events per ad
  set per week to leave the learning phase; this account will never supply that.
  Meta will not optimise, it will just spend. **Frequency is the primary metric.**
- **The connector cannot create or manage audiences.** `outreach-list` is a manual
  Ads Manager upload, every time. There is no tool and there is no workaround.
- **Two creative arms only**: `capacity` (untested, recommended) and `hours`
  (control). They mirror outreach-engine's arms deliberately — same variable,
  two channels. Do not add a third.
- Danish and Lithuanian copy in `creative/*.json` is still
  `NEEDS_NATIVE_PROOFREAD`. It is not ready to ship.

## Build rules

1. Never write a number into ad copy that does not resolve in `evidence.json`.
2. Never split the custom audience.
3. Never unpause a campaign without being asked to. The connector creates paused;
   keep it that way until a human says otherwise.
4. Never report a metric that was not returned. "I didn't check" is a valid answer.
5. Ecommerce ad advice does not apply here. Flag it and move on, do not adapt it
   silently.
