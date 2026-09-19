# Claims — what DoviLoop may and may not say in an ad

> GENERATED from `claims/evidence.json` by `scripts/sync_skill_claims.py`.
> Do not hand-edit. Re-run the script after changing evidence.json.

## The rule

Every factual assertion in ad copy must resolve to a `verified` entry below.
If it does not, it does not ship. There is no 'probably fine'.

## ✅ Verified — safe to claim (5)

### `never_auto_sends`
Product behaviour. Drafts are written to the Outlook drafts folder; no send call exists on the draft path.

Safe phrasings:
- Nothing sends until you read it
- It never sends on its own
- You approve every send

### `stays_in_outlook`
Microsoft Graph API writes into the user's existing mailbox. No separate client, no inbox migration.

Safe phrasings:
- It never leaves Outlook
- Inside the inbox you already use

### `eu_hosted`
Supabase project and n8n instance both hosted in the EU. GDPR compliant.

Safe phrasings:
- Runs on European servers
- Your data stays in Europe

### `own_knowledge_base`
kb_vectors retrieval is per-tenant and grounded in documents the firm supplies.

Safe phrasings:
- Answers from your own fees, deadlines and policies
- Grounded in your documents, not the internet

### `per_person_voice`
WF9 builds a voice profile per mailbox from that person's sent mail.

Safe phrasings:
- In each person's own words

## ⛔ Blocked — never claim (7)

### `hours_saved`
**Why blocked:** No measured customer outcome exists. The pricing page's '10 hours a month' is a modelled estimate, not an observation.

**Note:** Do NOT put a time-saving number in an ad. No customer backs it, and a measurable public claim with nothing behind it is the exposure an investor specifically warned about.

### `customer_count`
**Why blocked:** Zero closed customers as of 2026-08-31. Three prospects, none closed.

**Note:** No 'trusted by N firms', no logos, no testimonials until design partners sign and agree.

### `percentage_claim`
**Why blocked:** No measured percentage outcome of any kind exists.

**Note:** Any percentage in an ad needs a measurement behind it. There is none yet.

### `money_saved`
**Why blocked:** No measured customer outcome exists. The campaign landing page renders '430 USD saved per month, for each person' - that figure is assumed hours at a mid-level salary, converted from euros, and the page says so in the same block ('These are a model, not a measurement' / 'Never yet checked against a real customer').

**Note:** Do NOT echo the landing page's money figure into an ad. The page carries its own disclosure in the same eyeline; an ad carries none, and a figure lifted out of its disclosure is exactly the unbacked public promise an investor warned about. See docs/FUNNEL-HANDOFF.md. UNIFIED 2026-09-18: this began as a hard block, written before roi_model was visible on claude/campaign-build-status-9j9194. The founder's rule of 2026-09-06 is the one that governs - a modelled figure MAY appear when the same ad says in plain words that it is a model or a worked example, because the reader sees the framing and never sees a note. Two rules on one subject is how one of them gets ignored, so these now share roi_model's escape.

### `roi_multiple`
**Why blocked:** No measured return exists. The landing page computes its multiple at runtime from the modelled saving, a ten-person firm and the active tier price (campaign-site/src/components/Numbers.tsx:98). It is arithmetic over an assumption, not an observation - and it moves whenever the price moves.

**Note:** Covers 'Nx', 'pays for itself' and 'N times over'. Same rule as money_saved: the page may state it with its disclosure attached, an ad may not state it at all. UNIFIED 2026-09-18: this began as a hard block, written before roi_model was visible on claude/campaign-build-status-9j9194. The founder's rule of 2026-09-06 is the one that governs - a modelled figure MAY appear when the same ad says in plain words that it is a model or a worked example, because the reader sees the framing and never sees a note. Two rules on one subject is how one of them gets ignored, so these now share roi_model's escape.

### `price`
**Why blocked:** Confirmed by Dovy on 2026-09-06: 89 USD per seat per month plus 500 USD one-off setup. Supersedes the 49/99 USD and 750 USD figures that were in docs/ICP-BRIEF.md.

**Note:** Do not put a price in an ad until the founder settles which model is true. The safe_phrasings below are the per-seat wording and stay recorded, but CONTESTED means no writer may use them yet.

### `roi_model`
**Why blocked:** Decision 2026-09-06: the ~9x ROI, ~400 EUR per month saved per seat and ~40-day payback figures are outputs of a model, not measurements. The model assumes an amount of time saved per seat and costs it at a salary. No customer has been measured.

**Note:** An ROI multiple, a payback period or a money-saved figure may appear in an ad ONLY if the same ad says in plain words that it is a model or a worked example. Never present it as an outcome. If the ad does not carry one of the framing phrases in allowed_if_framed_as, the gate blocks it.

## ⚠️ The gate does not catch everything

`engine/gate.py` is five regexes looking for digits. These all pass it
clean and are all still unverifiable claims. Catching them is *your* job,
not the script's:

- 'Most firms see faster turnaround'

The pattern: the gate hunts for a **digit**. A claim spelled out in words,
or phrased as a vague comparative, is invisible to it. Reason about the
*claim*, not the digit.
