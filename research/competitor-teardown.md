# Competitor teardown — Meta, email-AI category

**Swept 2026-09-21** via the Meta Ad Library through the MCP connector (`ads_library_search`).
Raw: `research/corpus/2026-09-21-competitor-sweep.json`.

---

## 0. Read this before you read the numbers

The Ad Library returns, for a commercial ad:

```
id · page_id · page_name · ad_creative_link_title
ad_creation_time · ad_delivery_start_time · ad_snapshot_url · currency
```

**No impressions. No spend. No CTR. No reach.** Those fields exist only for
`POLITICAL_AND_ISSUE_ADS`. There is no "best performing competitor ad" to scrape —
not by me, not by a paid tool. Anything sold as that is inferring from the same
two signals available here:

- **Survival** — is it still running, and for how long.
- **Repetition** — how many times they cloned the same line.

Also: only the **headline** comes back, not the body copy. Full creative is behind
each `ad_snapshot_url`. Those links below are for you to click.

---

## 1. State of the category

| Page | Market | Ads ever | Active now | Newest ad | State |
|---|---|---|---|---|---|
| **Echo You** `1068016506404036` | DK, LT | 88 | **16** | 2026-09-16 | **live** |
| **Fyxer** `484462831408750` | GB, US, IE | **1,718** | 0 | 2026-06-10 | dark 102 days |
| **Jace.ai** `591862607340162` | GB, US | 446 | 0 | 2026-02-16 | dark 216 days |

Keyword sweeps, active only:

- `AI email assistant inbox` · DK+SE+NO → **5 hits**, of which **1** is a real competitor
  (Echo You). The rest are receipt scanners.
- `el paštas AI verslui` · LT → **0**.
- `email drafts Outlook AI` · DK+LT → **1**, an accounting course.

**Lithuania has no one.** The Nordics have one.

⚠️ **The uncomfortable read.** The two companies that spent the most in this category
both stopped. 1,718 ads and 446 ads, then silence. We cannot see why — moved channel,
ran out of money, found Meta doesn't convert for B2B email software. All are consistent
with the data. Treat "Meta works for this category" as **unproven**, and treat your
first spend as buying that answer rather than buying leads.

---

## 2. The structural finding — headline discipline

This is the thing worth studying.

| | Ads ever | Distinct headlines | Ads per headline |
|---|---|---|---|
| Fyxer | 1,718 | **1** | 1,718 |
| Jace.ai | 446 | 5 (+ a broken template) | ~89 |
| Echo You | 88 | 13 | ~7 |

Fyxer ran **1,718 ads on one line**: *"Your AI Email Assistant."* 49 of the 50 sampled
are that exact headline; one is blank. They did not test headlines. They fixed the
headline and varied everything else — image, audience, placement.

Jace ran 446 on five human-written lines, and **39 of 50 sampled show
`{{product.name}}` unfilled** — an Advantage+ catalog template that never resolved.
Either a misconfiguration they ran for months, or the name fills at delivery. Worth
one click to check before copying anything of theirs.

Echo You is the opposite: 13 headlines across 88 ads, launched in **29-second bursts**,
culled every ~6 days. Their whole 2026-09-10 batch is dead. The current 16 are 5 days old.

**What this means for you.** At DKK 35/day you cannot run Fyxer's play (one headline,
thousands of impressions per variant) *or* Echo You's (16 variants, cull weekly). You get
one variable, three arms, and you read frequency — which is what `campaigns/structure.md`
already says. The teardown does not change the plan; it confirms the constraint.

---

## 3. Angle inventory — click these

### Echo You (live in DK, all 16 active)

Their whole position is **consolidation**: mail and calendar, one place. Six of thirteen
headlines say it.

| Angle | Headline | Look |
|---|---|---|
| Consolidation | Email og kalender samlet ét sted | [snapshot](https://www.facebook.com/ads/library/?id=1063304842997712) |
| Consolidation | Mail og kalender. Ét sted. | [snapshot](https://www.facebook.com/ads/library/?id=937100702784392) |
| Simplicity / teams ×2 | Den enkle AI løsning til teams | [snapshot](https://www.facebook.com/ads/library/?id=2342044913298301) |
| **Press proof ×2** | Computerworld skriver om EchoYou | [snapshot](https://www.facebook.com/ads/library/?id=28483645404601660) |
| Control | Få styr på de vigtigste mails | [snapshot](https://www.facebook.com/ads/library/?id=2618586348592513) |
| Control | Få styr på din indbakke | [snapshot](https://www.facebook.com/ads/library/?id=1129762716145054) |
| Overwhelm | Din indbakke. Håndteret. | [snapshot](https://www.facebook.com/ads/library/?id=4336165009851043) |
| Overwhelm | Stop med at tjekke alt selv | [snapshot](https://www.facebook.com/ads/library/?id=1403929904417214) |
| Status / founder | Led virksomheden. Ikke indbakken. | [snapshot](https://www.facebook.com/ads/library/?id=1715183669538306) |
| Time | Mere overblik. Mindre mailtid. | [snapshot](https://www.facebook.com/ads/library/?id=2096549427892154) |
| **Number** | Brug op til 90 % mindre tid på mail | [snapshot](https://www.facebook.com/ads/library/?id=1172540888797301) |
| **Voice** | AI-svar, der lyder som dig | [snapshot](https://www.facebook.com/ads/library/?id=2904329706626267) |
| Keyword stuff ×2 | AI Email Assistant, Calendar Management Tool with Unified Inbox | [snapshot](https://www.facebook.com/ads/library/?id=1887503635990695) |

### Fyxer — the one line, 1,718 times
*Your AI Email Assistant* → [snapshot](https://www.facebook.com/ads/library/?id=768972482970136)

### Jace.ai — five lines, 446 ads
- Meet your new Inbox → [snapshot](https://www.facebook.com/ads/library/?id=4273398122912078)
- Change the way of using inbox → [snapshot](https://www.facebook.com/ads/library/?id=2396178714160576)
- A Higher Standard For Work Email 📧 → [snapshot](https://www.facebook.com/ads/library/?id=1263035382411969)
- Skip the busywork. → [snapshot](https://www.facebook.com/ads/library/?id=806500165790822)
- Your AI for Email → [snapshot](https://www.facebook.com/ads/library/?id=1355994476544038)

---

## 4. Where the white space is

Every live and dead competitor in this set sells one of three things:
**a new inbox**, **consolidation**, or **generic "AI email assistant"**.

All three ask the customer to **move**.

Nobody in the set says:

| Nobody says | DoviLoop claim | Status |
|---|---|---|
| It stays in the tool you already have | `stays_in_outlook` | **verified** |
| It answers from *your* files, not the internet | `own_knowledge_base` | **verified** |
| Nothing sends without you reading it | `never_auto_sends` | **verified** |
| Your data stays in Europe | `eu_hosted` | **verified** |

That is four verified claims sitting in unoccupied ground. It is also exactly what the
landing page already argues, so the ad and the page agree without being forced to.

**One contested square:** Echo You's *"AI-svar, der lyder som dig"* is your
`per_person_voice` (also verified). If you take the voice angle you are arguing against
a live incumbent in their own market. Winnable, but it is not white space.

**One square you must not enter:** *"Brug op til 90 % mindre tid på mail."*
`percentage_claim`, `hours_saved`, `money_saved`, `roi_multiple` are all `UNVERIFIED`
in `claims/evidence.json`. The gate will refuse it and it would be a lie. Do not match
their number. Note that Fyxer — the biggest spender here — never used one either.

---

## 5. What you may say today

**Verified claims** (`claims/evidence.json`):
- `stays_in_outlook` — "It never leaves Outlook" · "Inside the inbox you already use"
- `own_knowledge_base` — "Answers from your own fees, deadlines and policies" · "Grounded in your documents, not the internet"
- `never_auto_sends` — "Nothing sends until you read it" · "You approve every send"
- `per_person_voice` — "In each person's own words"
- `eu_hosted` — "Runs on European servers" · "Your data stays in Europe"

**Verified offers:**
- `guarantee` — "If the drafts are not good enough to send, you do not pay and you keep the knowledge base"
- `design_partner` — "Design-partner terms for the first firms in"
- `demo` — "See it on your own inbox"

**Blocked:** `hours_saved` · `money_saved` · `percentage_claim` · `customer_count` ·
`roi_model` · `roi_multiple` (all UNVERIFIED) · `price` (CONTESTED) ·
`free_trial` (UNVERIFIED — *"no self-serve trial exists"*).

⚠️ `free_trial` is blocked but the **campaign-site branch** `claude/great-bell-10ca2r`
carries four lines promising *"The first two weeks are free"*. `origin/main` does not,
and the deployed page does not. Resolve before that branch merges.

---

## 6. Open for the founder

1. Which lane — **"it never leaves Outlook"** (white space, verified, matches the page),
   **voice** (contested with a live incumbent), or **the guarantee** (risk reversal,
   nobody in the set offers one)?
2. Anything in the snapshots above that you want the ads to answer directly.
3. The `free_trial` contradiction in §5.

---

## 7. Addendum 2026-09-21 — can we get clicks or views?

Asked directly: *top 3 best performing ads for Jace and Fyxer, with clicks/views.*

### Clicks — no. Not obtainable by anyone.

Confirmed three independent ways:
1. The connector's response carries 8 fields across 8 calls. No click, CTR or impression field ever appears.
2. Meta publishes spend/impressions/demographics for `POLITICAL_AND_ISSUE_ADS` only.
3. This repo already reached the same conclusion — `engine/discover.py:12`:
   > *"There is no view count. A commercial ad in the archive carries no spend, no impressions, no clicks and nothing social."*

Any tool selling "competitor CTR" is modelling it, not reading it.

### Views — yes, as `eu_total_reach`, and both pages qualify

The EU DSA forces Meta to publish a reach figure for every ad delivered in the EU,
commercial ones included. Both ran in the EU:

| Page | EU ads (IE/DE/NL/FR/ES/IT/PL/SE/FI/DK/BE/AT) |
|---|---|
| Fyxer | **1,506** |
| Jace.ai | **331** |

So the number exists. **The MCP connector does not return it** — its field set is fixed
and reach is not in it.

### The repo was built for exactly this, and has never run

`engine/discover.py` already requests the right fields:

```
ad_delivery_stop_time · eu_total_reach · ad_creative_bodies
ad_creative_link_titles · publisher_platforms · languages
```

`ad_creative_bodies` is the **body copy** the connector withholds. `reach_per_day()`
(`discover.py:1187`) divides `eu_total_reach` by days running. The ranking model is
longevity first, reach/day as numerator, variant count as scale.

**Unblock: `META_ACCESS_TOKEN`.** With it, `python tools/first_live_call.py` is one
request that writes nothing and prints documented fields against what actually arrives.

⚠️ `FIELDS` carries `TODO(integration): UNVERIFIED AGAINST A LIVE RESPONSE`. The names
came from Meta's reference page, not a real reply. A wrong name is a 400 that names
itself. So the token makes this possible, not instant.

### Best available ranking today (proxy, not performance)

Sampled 100 of Jace's ads (50 GB/US + 50 EU). Ranked by **repetition** — how many
times they cloned the line.

| # | Jace headline | Clones in sample |
|---|---|---|
| 1 | A Higher Standard For Work Email 📧 | 6 |
| 2 | Your AI for Email | 5 |
| 3 | AI-Powered Email Assistant 👉 | 4 |
| 4 | Meet your new Inbox | 3 |
| 5 | Change the way of using inbox | 3 |
| 6 | Skip the busywork. | 2 |

`{{product.name}}` — the unfilled catalog template — is ~78 of the 100 sampled.
Jace ran 2025-12-06 → 2026-02-16, then stopped.

**Fyxer has no top 3.** One headline, *"Your AI Email Assistant"*, across every ad in
both samples. That is the finding, not a gap in the data.

This ranking says what they *committed budget to*, not what worked. Only
`eu_total_reach` ÷ days running gets closer, and that needs the token.
