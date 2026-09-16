# Meta ads — A to Z

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

> For someone who has not run Meta ads before. Written 2026-09-16.
> Every step is grounded in this repo's own specs. Where a number depends on your
> account and I do not have it, I say so rather than guessing.
>
> **Menu labels in Meta's UI move around.** Paths below are the route, not a
> promise about today's wording. If a label has changed, the shape is still right.

---

# Part 0 — The vocabulary

Nine words. Everything else is built from these.

| Word | What it actually is |
|---|---|
| **Business Manager** (business.facebook.com) | The container that *owns* everything else — your ad accounts, Pages, pixels, and who has access to them. Not itself a place ads run. Make this first |
| **Page** | A Facebook page. Ads run *from* a Page — there is no such thing as an ad with no Page behind it. You need one for DoviLoop |
| **Ad account** | Where money is spent. Has an ID like `act_123456789`. Lives inside Business Manager |
| **Pixel** (a "dataset" in Events Manager) | A snippet of JavaScript on your website. It tells Meta which people visited which pages. Two uses: building retargeting audiences, and measuring conversions |
| **Custom Audience** | A list of specific people. Either uploaded by you (emails, hashed) or built from pixel traffic. **This is the only way to reach your ICP** |
| **Campaign → Ad Set → Ad** | The three-level hierarchy. Campaign holds the *objective*. Ad Set holds the *audience, placements, schedule and usually the budget*. Ad holds the *image/video and the words* |
| **CPM** | Cost per 1,000 impressions. The price of being seen. Market-driven, not something your creative controls much |
| **Reach vs Impressions vs Frequency** | Reach = unique people. Impressions = total views. **Frequency = impressions ÷ reach** = how many times the average person saw it |
| **Learning phase** | Meta's optimiser needs roughly 50 conversion events per ad set per week to stabilise. Below that it never learns |

**The one that decides everything for you: learning phase.** You will never hit
50 events a week. So Meta will not optimise your ads — it will simply spend the
budget. Every decision a normal advertiser delegates to the algorithm, you make
yourself. This is not a problem to fix; it is the shape of a 2,000-person
audience, and the setup below is built around it.

**And: ROAS is meaningless here.** Return On Ad Spend = revenue ÷ spend. You have
no revenue from ads and `claims/evidence.json` records zero closed customers. Any
guide, video or tool that centres ROAS is describing a different business. Ignore
that part of it.

---

# Part 1 — Accounts and plumbing

Roughly an afternoon. Nothing here depends on anything else in this document.

### 1.1 Business Manager
business.facebook.com → create a business. Real legal name, real address.

### 1.2 A Facebook Page for DoviLoop
You cannot run ads without one. It does not need an audience or posts — it needs
to exist, have the logo, and be owned by the Business Manager (not your personal
profile). Business settings → Accounts → Pages → Add.

### 1.3 Ad account
Business settings → Accounts → Ad accounts → Add → Create. Set currency and
timezone **carefully — neither can be changed later.** EUR, Europe/Vilnius.

### 1.4 Payment method
Billing → add a card. Expect a small authorisation charge.

### 1.5 Accept Custom Audience terms
**Easy to miss and it blocks Part 4 entirely.** Business settings → somewhere
under Audiences / Data sources, there is a one-time Custom Audience Terms of
Service to accept. You cannot upload a customer list until you have.

### 1.6 Record the ad account ID
It looks like `act_123456789`. You will paste it into Claude constantly, and the
numeric ID resolves far more reliably than the account name.

> **Not applicable to you:** Special Ad Categories (credit, employment, housing,
> politics). Those force restricted targeting. B2B software is not one — leave it
> unset.

---

# Part 2 — The pixel

**Do this first, before anything else in this document.** Not because it is
urgent to use, but because it is a *clock*. It does nothing the day you install
it. It only becomes useful after it has been quietly collecting for weeks.
`audiences/site-retargeting.json` is blocked on exactly this, in its own
`blocked_on` field.

### 2.1 Create it
Events Manager → Data sources → Connect → Web. Copy the ID — 15 or 16 digits.

### 2.2 Put it in Vercel
`campaign-site/.env.example` §5 documents this. The variable is
`VITE_META_PIXEL_ID`, currently empty. Set it in the Vercel project under
Settings → Environment Variables, for **both Production and Preview**, then
redeploy. Empty means the pixel is completely inert — no script, no request, no
cookie. That is deliberate, not broken.

### 2.3 Put the same pixel on doviloop.dev too
`.env.example` says this explicitly and it matters: with the pixel only on the
campaign page, your retargeting audience contains people who saw the campaign
page and nobody else. The product site is where most of your traffic already is.

### 2.4 Understand what EU consent does to it
`campaign-site` gates the pixel behind consent, and `scripts/verify-consent.mjs`
proves it: no script, no `window.fbq`, no image pixel until the visitor accepts.

**So your retargeting pool will be smaller than your actual traffic — by a lot.**
That is correct behaviour and legally necessary. Do not "fix" it. Just do not be
surprised when the audience looks thin.

---

# Part 3 — Connect Claude

Ten minutes.

### 3.1 Add the connector
Claude → Customize → Connectors → **+** → Add custom connector.

- URL: `https://mcp.facebook.com/ads` — exactly, no trailing slash
- Name: anything
- Then Facebook Login, then choose which business portfolios Claude may see

### 3.2 It is in open beta
Not every advertiser has access. A connection that succeeds but returns no data
is a queue position, not a bug. Nothing below is wasted if this is where you land
— come back to it.

### 3.3 Set permissions the careful way
Set **everything to "needs approval"** on first connect. As each read-only tool
fires and you see what it does, promote that one to "always allow".

**Never promote anything that writes.** Budget changes, status changes, creating
or unpausing — those stay manual approvals permanently. The cost of a wrong click
here is money.

⚠️ **Do not rely on "creates paused" as your safety net.** It is a default, and
an activate tool exists. Your approval prompt is the real control.

⚠️ **Decline the financial/billing scope** if Meta's OAuth screen offers scope
tiers (reported by a secondary source; unverified — you will see the real screen
before I do). Nothing Claude does for you needs it.

### 3.4 Prove it works
> List every ad account I have access to, and say which ones are MCP-enabled.

Then give it your `act_` number and ask for yesterday's spend. If that returns,
you are connected.

### 3.5 Turn the skill on
The skill in `.claude/skills/meta-ads/` loads all of the above automatically in
Claude Code. For Claude Desktop — where you will actually run the connector —
zip that folder and upload it under Customize → Skills.

---

# Part 4 — The audience

**This is the part Claude cannot do.** The connector has no audience tool. It
will always be you, by hand, in Ads Manager.

### 4.1 Build the file
```bash
python -m engine.cli audience ../outreach-engine/queue/acc-dk.csv --out queue/aud.csv
```
Every field is SHA-256 hashed after normalisation, per Meta's spec, so the raw
list never leaves your machine. The command warns you if the result is too small.

### 4.2 Upload it
Ads Manager → Audiences → Create → Custom Audience → Customer list. Upload the
hashed CSV. Meta will match some fraction of it — **match rates well under 100%
are normal**, not a sign you did it wrong.

### 4.3 The rule that matters
> **Never split this audience.**

`audiences/outreach-list.json` is explicit: ~2,000 people clears Meta's 1,000
delivery floor **only** with both countries and all three verticals combined. Cut
it by country, by vertical, or across two ad sets and delivery breaks.

Your instinct will be to split — everyone's is, and in a normal account it would
be right. Here it is the single most expensive mistake available.

### 4.4 Optional: hold some back
If you want to know whether the ads did anything, hold ~20% of firms out of the
upload and later compare outreach reply rates between the two groups. That is the
only real test this channel can pass or fail.

It leaves ~1,600 people — still over the floor, but thin. Check the row count the
build command prints before committing to it.

---

# Part 5 — Creative and copy

### 5.1 Two arms, no more
`creative/capacity.json` and `creative/hours.json`. They mirror outreach-engine's
arms on purpose, so both channels test the same variable. `capacity` ("more
clients, same team") is the one `docs/ICP-BRIEF.md` calls the highest-value thing
to test. A third arm splits attention you do not have.

### 5.2 Reuse before generating
`creative/capacity.json` points at `reel-engine` for video and stills. Use those
first. HiggsField is connected and can generate, but generation is for when reuse
runs out — not the default.

### 5.3 The claims gate — the part that actually protects you
DoviLoop has no customers and no measured outcomes. That is precisely the state
in which someone writes "save 10 hours a week" because it sounds right. An
investor specifically flagged that exposure: a public measurable promise with
nothing behind it, from a company with no liability cap and no insurance.

```bash
python -m engine.cli check
```

**The gate is five regexes and it will not save you.** Measured on 2026-09-16:

```
BLOCK  "Save 10 hours a month"
BLOCK  "Trusted by 200 firms"
BLOCK  "Reply 40% faster"
PASS   "Save ten hours a month"        ← spelled out, no digit
PASS   "Cut your reply time in half"
PASS   "Most firms see faster turnaround"
PASS   "Save hours every week"
```

Four unverifiable claims pass clean. The gate hunts for a **digit**. Anything
spelled out in words, or phrased as a vague comparative, is invisible to it.

**What you may say** (each a verifiable product fact): it never auto-sends · it
never leaves Outlook · it runs in Europe · it answers from the firm's own
documents · a voice profile per person. Full list in `claims/evidence.json`.

### 5.4 Danish and Lithuanian are not ready
Every non-English field in `creative/*.json` says `NEEDS_NATIVE_PROOFREAD`.
Machine-translated B2B copy reads wrong to a native speaker in a way that costs
you credibility with exactly the buyer you want. This is a real blocker, not a
nicety.

---

# Part 6 — The launch

### 6.1 Structure
**One campaign. One ad set. Two ads.** That is the whole thing.

| Level | Setting | Why |
|---|---|---|
| Campaign | Objective: **Awareness / Reach** | You are buying *being seen by named firms*, not clicks. Conversion objectives need ~50 events/week you will never have |
| Campaign | Budget at ad set level (ABO) | With one ad set the distinction is academic; ABO is simpler to reason about |
| Ad set | Audience: `outreach-list`, whole | Never split. See 4.3 |
| Ad set | **Frequency cap: ~1 impression per 3–5 days** | The Reach objective lets you set this. It is your single most important control |
| Ad set | Placements: automatic | Restricting placements starves an already-small audience |
| Ad | Two: `capacity` and `hours` | The A/B |

**Why Reach and not Traffic:** Traffic optimises toward whoever clicks. On 2,000
B2B people that means Meta finds the same three habitual clickers and shows them
your ad forever. Reach spreads across the list, which is the entire point of air
cover. Traffic is defensible if growing the retargeting pool matters more to you
— but that pool will be tiny either way.

### 6.2 What to spend
The arithmetic, since guessing is how people waste money here:

```
impressions needed = audience × target frequency
monthly cost       = (impressions ÷ 1000) × CPM

2,000 people × 3 exposures/month = 6,000 impressions = 6 × CPM
```

So your monthly spend is **roughly six times your CPM**. If CPM is €10 that is
€60/month. If it is €30, €180.

**I do not know your CPM.** It depends on Denmark and Lithuania, on your
placements, and on who else is bidding for those people — and I have not measured
it. Read it from your own data after week one and recompute.

**The point:** this is a small-budget channel *by construction*. The audience
physically cannot absorb more. If you find yourself spending four figures a month
here, something is wrong — most likely you are reaching people outside the list.

### 6.3 Before you turn it on
The mechanical half of this list is a command. It exits non-zero if anything
blocks. The rest of the list is yours to check.

```bash
python -m engine.cli preflight --audience queue/aud-outreach.csv
```

**It is red today, and both red lines are correct answers rather than bugs:**

- **native copy** — `da` and `lt` are still `NEEDS_NATIVE_PROOFREAD` (5.4). Goes
  green when a native speaker has read them, or you ship English only.
- **audience blockers** — `site-retargeting` is blocked on a pixel that is not on
  doviloop.dev (2.1), so that audience cannot be built and would have nobody in
  it if it could. Goes green when the pixel is live and `blocked_on` comes off
  the spec.

Two red lines mean this account is not ready to launch. That is true, so the
command says so. **A preflight that went green today would be lying to you.**

It also prints what it *cannot* check rather than letting a green run imply
completeness: whether the copy reads true against `evidence.json`, the frequency
cap, the budget arithmetic, whether the pixel is collecting, and whether outreach
is actually running.

- [ ] `python -m engine.cli check` passes
- [ ] You have read the copy yourself against `claims/evidence.json` — the gate is not enough
- [ ] `da` / `lt` proofread by a native speaker, or you are running English only
- [ ] Audience uploaded whole, not split
- [ ] Frequency cap set
- [ ] Budget matches the arithmetic above
- [ ] Pixel live and already collecting
- [ ] Outreach is actually running — air cover over nothing is just cover

---

# Part 7 — The operating loop

Detail in `.claude/skills/meta-ads/references/operating-loop.md`. The short form:

**Every time you look:** frequency first, everything else second.

| Frequency (7d) | Do |
|---|---|
| under 2 | nothing |
| 2–3 | nothing — working as intended |
| 3–4 | rotate to the other arm |
| over 4 | cut budget or pause — the list has seen it |

**Weekly:** week-over-week on spend, reach, frequency, CPM, link clicks. Flag
moves over 30%.

**Do not read lead counts as signal.** Single digits per week is noise. Four one
week and one the next is not a 75% drop, it is two small numbers. Log, do not act.

**Monthly:** which arm carried more spend and clicks. State plainly when the
sample is too small to call — it usually will be.

---

# Part 8 — Gotchas on a fresh account

Things that surprise everyone the first time:

- **New ad accounts carry low spending limits** and sometimes get auto-flagged.
  Appeals are usually resolved but can take days. Do not schedule a launch tightly.
- **Business verification** may be requested before some features unlock.
- **Custom audience match rate is never 100%.** Half is normal. Not your fault.
- **A rejected ad is normal.** Request review; the automated pass is aggressive.
- **Currency and timezone are permanent.** Set at account creation, never changeable.
- **The connector creates things paused** — but that is a *default*, not a
  guardrail. An activate tool exists (`ads_activate_entity`, per a secondary
  source), so Claude can unpause too. The thing actually protecting you is
  keeping every write tool on "needs approval". Do that and keep it that way.

---

# Part 9 — The order

**Today, because it is a clock:** Part 1 (accounts) → Part 2 (pixel). Then the
pixel collects while you do everything else.

**Any afternoon after that:** Part 3 (connect Claude) → Part 5 (creative and
proofreading) → Part 4 (build the audience).

**When the pixel has weeks behind it and outreach is running:** Part 6 (launch).

**Then forever:** Part 7.

The only thing where delay costs you weeks instead of hours is the pixel.
Everything else waits without penalty.
