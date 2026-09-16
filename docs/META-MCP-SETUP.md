# Meta Ads MCP — setup, and what actually transfers from the videos

> ## ⛔ CORRECTED 2026-09-16 — read before trusting this file
>
> The connector was connected for real and its tool list read. **Three claims
> below are wrong:**
>
> - **"Cannot create or manage audiences"** — false. `ads_create_custom_audience`
>   + `ads_update_custom_audience_users` do the hashed customer-list upload.
> - **"Creative assets not accessible / contradictory"** — false. `ads_get_ad_preview`,
>   `ads_get_ad_images`, `ads_get_ad_videos`, `ads_get_creatives` all exist.
> - **"No competitor research"** — false. `ads_library_search` exists.
>
> Still true: **no B2B firmographic targeting**. Nothing in the tool list provides it.
>
> Live account: `620456015062432`, MCP-enabled, **DKK**, no payment method, no
> Business Manager. See `CLAUDE.md` for current state.

> Written 2026-09-16 from two YouTube transcripts (Meta MCP walkthrough; "Claude +
> Facebook Ads FULL COURSE" by the Moonlighters) checked against this repo and
> against Meta's current connector docs.
>
> **The videos are an ecommerce playbook.** Their example account: $102k spend,
> 5,539 purchases, 3.2x ROAS. This repo's `README.md` already concluded the
> opposite for our ICP — Meta is *account-based air cover over outreach, not a
> prospecting channel*. Most of the video mechanics need conversion volume that
> does not exist here. Section 3 is the part that survives.

---

## 1. The setup — verified

| | |
|---|---|
| **Endpoint** | `https://mcp.facebook.com/ads` — exact, no trailing slash |
| **Status** | Open beta. Not every advertiser has access; a connected account with no data is a queue position, not a bug |
| **Surface** | 29 Marketing API tools: performance reporting · campaign management · catalog · signal diagnostics |
| **Write safety** | Campaigns/ad sets/ads created by the agent land **paused** — a default, not a guardrail: an activate tool (`ads_activate_entity`) reportedly exists. Budget increases and material targeting changes need per-action human approval. **The approval prompt is the real control** |
| **Requires** | Meta Business Manager with admin access + a paid Claude tier |

**⚠️ The URL in the video transcripts is garbled** (`mcp.fasads.com/ads`). No such
domain appears in any current source. Do not paste it.

**claude.ai / Desktop:** Customize → Connectors → `+` → Add custom connector →
paste the endpoint → name it → Add. Then Facebook Login, then pick which business
portfolios Claude may see.

**Claude Code:**
```bash
claude mcp add --transport http meta-ads-official https://mcp.facebook.com/ads
```
This is client-side MCP compatibility, not a Meta-listed integration. Meta's own
terminal route is a separate CLI binary.

**Permissions — do this the video's way, it is correct.** Set every tool to
*needs approval* on first connect. Promote only the read-only insight tools to
*always allow* once you have seen each one fire. Never promote anything that
writes: budget edits, status changes, creative pushes.

**First prompt, to prove the connection:** ask it to list every ad account you
have access to and call out which are MCP-enabled. Account **numbers** resolve
faster than account names.

---

## 2. Two things the MCP cannot do — and they are our two priorities

This is the finding that matters. Checked against `audiences/*.json`.

**❌ No audience creation or management.** Documented limitation. Our
priority-1 audience is `outreach-list` — the hashed Custom Audience built by
`python -m engine.cli audience <outreach.csv>`. The MCP cannot upload it, cannot
read it, cannot refresh it. That stays a manual Ads Manager upload, forever, or
until Meta adds the tool. *The single most important object in this repo is
outside the agent's reach.*

**❌ No B2B targeting features.** Also documented. Consistent with
`engine/audience.py`'s premise: Meta has no "Danish accounting firm, 10+ staff"
targeting. Nothing about the MCP changes that.

**⚠️ Creative assets — contradiction, unresolved.** One 2026 write-up lists ad
creative (images, videos, previews) as *not* exposed, text fields only. The
second video plainly shows Claude reading an ad's image and describing it
(~35:44). Both cannot be true. **Five-minute test:** connect, then ask it to pull
your top-spending ad *and show you the creative*. If it renders the image, the
video's creative flywheel is live for you. If it returns only copy, the whole
"iterate the winner with Higgsfield" loop needs the image fetched by hand first.
Unverified either way — I did not test it, you have no ad account connected yet.

---

## 3. What survives, rebuilt for a B2B account with no purchase events

The videos build three things. Two of them break here.

### Winner detection — **breaks**
Their rule: an ad above target ROAS *and* carrying >5% of campaign spend.
We have no ROAS, no purchases, and zero customers (`claims/evidence.json` →
`customer_count: UNVERIFIED`). Nothing to rank on.

**Replace with:** rank on the only events that will exist — qualified lead
(10+ seats reaching the booking page) and, above it, landing-page engagement
from PostHog. `campaign-site/src/lib/env.ts` already carries `posthogKey`
alongside `metaPixelId`; PostHog is the honest source because the pixel is
consent-gated in the EU and will systematically under-report. Expect single-digit
lead events per week. That is below any statistical test — read it as a log, not
a signal.

### Anomaly detection at 2 standard deviations — **breaks on conversions, works on delivery**
Two SDs over a metric that fires 3 times a week is noise.

**Replace with:** alert on the metrics that *do* have volume — spend, CPM,
reach, and above all **frequency**.

> **Frequency is the metric that will kill this account, and the videos treat it
> as secondary.** The audience is ~2,000 people
> (`audiences/outreach-list.json`: ~750 firms × 2–3 contacts). Meta's optimiser
> wants ~50 conversions per ad set per week to leave the learning phase (Meta's
> published threshold; not re-verified here) — we will never supply that, so it
> never optimises, it just spends. On a 2,000-person pool even a small daily
> budget saturates reach within days and frequency climbs hard.
>
> **The one alert worth building first:** frequency over a 7-day window, against
> a ceiling you pick before launch. Everything else is nice to have.

### Creative flywheel — **survives, but sourced differently**
Their loop: winner → AI variants → relaunch, ~100 assets/week. Ours cannot be
volume-driven, and every variant must clear `engine/gate.py` before it ships.

**What holds:**
- Higgsfield MCP is **already connected on this account** (verified this session).
  The image-generation half of the video needs no new setup.
- `creative/capacity.json` points at `reel-engine` for video and stills —
  reuse before generating. Two arms only (`capacity` untested/recommended vs
  `hours` control), deliberately matching outreach-engine's arms.
- **Hard rule: `python -m engine.cli check` runs over every AI-generated variant
  before it reaches Ads Manager.** The gate exists precisely because a model
  asked for "punchy ad copy" will invent a percentage. The video's workflow has
  no equivalent guard and will happily write one.

### Reporting + scheduling — **survives unchanged**
The daily/weekly scheduled report is the genuinely portable part, and the cheapest.
Two caveats from the videos, both correct: give it business context or the analysis
is worthless (video 2 shows it calling profitable weeks "structurally unprofitable"
because it had no margin data), and the video's own closing warning stands — keep a
human filter on spend.

---

## 4. Prerequisites — none of which involve Claude

Nothing above can run until these land. In order:

1. **A Meta Business Manager + ad account exists.** No `act_` ID appears anywhere
   in `ad-engine`, `campaign-site` or `flow-savvy-automations`. Assume it does not
   exist yet.
2. **`VITE_META_PIXEL_ID` is filled in Vercel.** Currently empty
   (`campaign-site/.env.example` §5). While empty the pixel is fully inert — no
   script, no request, no cookie.
3. **The same pixel goes on `doviloop.dev`, not just the campaign page.**
   `.env.example` says so explicitly, and `audiences/site-retargeting.json` is
   `blocked_on` exactly this. Priority-2 audience, and **it must start collecting
   weeks before any ad runs or there is nobody in it.**
4. **PostHog reconnected.** It currently reads `needs_reconnect` on this account,
   and it is the conversion source of truth.
5. **`da` and `lt` copy proofread.** Every non-English field in
   `creative/*.json` is still `NEEDS_NATIVE_PROOFREAD`.

**Item 3 is the long pole.** The pixel is a clock — it does nothing until it has
been running for weeks. Everything else can be done in an afternoon.

---

## 5. `Varnan-Tech/meta-ads-skill` — assessed, do not install

Read in full 2026-09-16 (6 files, 240K, last commit **2026-04-21**).

**It does not drive the official connector.** It orchestrates a *different*
server — `Varnan-Tech/Meta-Ads-MCP`, self-hosted — which needs your own Meta
Developer App, `FB_APP_SECRET` in a local `.env`, a Python auth server on
`localhost:8000` and a SQLite token DB. Nothing to do with
`mcp.facebook.com/ads`. Its last commit **predates Meta's connector launch
(2026-04-29)**, which explains the whole thing: it was written before the
official route existed.

**Four concrete problems:**

1. **The tool names don't match.** Its guardrails name `get_campaigns`,
   `get_insights`, `analyze_campaigns`, `search_interests`,
   `estimate_audience_size`, `clear_database`, `reset_database`. Those belong to
   the third-party server. Install this skill, connect Meta's official MCP, and
   every instruction points at tools that are not there — it will not fail
   loudly, it will just mislead.
2. **`scripts/auth_check.py` is a stub.** `token_valid = False`, hardcoded,
   checked against nothing. It always prints "No valid access token found". It is
   a print statement wearing a function's clothes.
3. **`scripts/formatters.py` is ~50 lines of naive f-strings** and is wrong for
   our data. No pipe-escaping, so an ad named `Capacity | DK` breaks the table.
   No unit handling, so Meta's `daily_budget` — returned in **minor units** —
   renders €50 as `5000`.
4. **The templates are ecommerce templates.** ROAS, Revenue, "Lookalike 1% of
   recent purchasers", "weekend flash sale". Same mismatch as the videos, for the
   same reason. See §3.

**Security, if you were ever tempted:** it asks for `ads_management` — write
scope on the ad account — held by a self-hosted server, and exposes
`clear_database` / `reset_database` as agent-callable tools. It also cannot run
in a Claude Code cloud session at all: `localhost:8000` does not exist here and
the container is ephemeral. Desktop-only, on your own machine.

### What is worth stealing from it

Three things, and they are good:

- **Hub-and-spoke shape.** `SKILL.md` as a thin router, detail in `references/`,
  loaded only when needed. Sound skill architecture, worth copying exactly.
- **Two context guardrails the videos completely lack:** cap listings at
  `limit=10` and default insights to `last_7d`. Video 2's author admits a 52-week
  pull costs ten minutes of waiting — this is the fix.
- **Explicit parameter display + confirmation before any state-changing call.**
  Same instinct as the videos' "needs approval", written down as a rule.

### Recommendation

Don't install it. **Write our own**, same shape, pointed at the official
connector's 29 tools, with one rule no off-the-shelf skill can have:

> Any ad copy — written, rewritten or AI-generated — runs through
> `python -m engine.cli check` before it reaches Ads Manager. No exceptions.

That is the guardrail that matters here, because `claims/evidence.json` exists
precisely to stop a model inventing a percentage, and every generic media-buyer
skill on the internet is tuned to write exactly that percentage.

---

## 6. Sources

Repo: `README.md` · `engine/audience.py` · `claims/evidence.json` ·
`audiences/outreach-list.json` · `audiences/site-retargeting.json` ·
`creative/capacity.json` · `../campaign-site/.env.example` ·
`../campaign-site/src/lib/env.ts`

External, fetched 2026-09-16:
- <https://www.getpassionfruit.com/blog/meta-ads-claude-mcp-what-it-actually-does> — 29 tools, the limitation list, paused-by-default
- <https://adadvisor.ai/blog/mcp-facebook-com-ads-official-meta-setup> — endpoint, exact-paste warning
- <https://www.markifact.com/blog/meta-ads-mcp-claude-code> — the `claude mcp add` form
- <https://www.jonloomer.com/meta-ads-ai-connectors-claude/> — **not read, 403**

Skill repo read locally at `/home/user/varnan-tech/meta-ads-skill` @ `1826822`:
`README.md` · `meta-ads-skill/SKILL.md` · `references/workflows.md` ·
`references/report_templates.md` · `scripts/auth_check.py` · `scripts/formatters.py`
