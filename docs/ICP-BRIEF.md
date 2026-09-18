# ICP + Offer brief

> ICP locked 2026-08-31, offer repriced 2026-09-17. Shared by three projects: **reel-engine** (this repo),
> **outreach-engine**, **ad-engine**. Canonical source lives in
> `flow-savvy-automations/docs/handoff/ICP_LOCKED.md` + `OFFER_LOCKED.md`.
> This is the working copy — if the two disagree, the canonical one wins.

---

## Who

**Accounting & bookkeeping · administrative (outsourced back-office) · insurance
brokers — 10+ people writing client email, on Microsoft 365, in Denmark and
Lithuania.**

| Vertical | NACE | DK firms | LT firms | At 10+ seats |
|---|---|---|---|---|
| Accounting & bookkeeping | 69.20 | 4,882 | ~9,823 | ~525 |
| Administrative / back-office | 82.11 | 1,793 | ? | ~90+ |
| Insurance brokers | 66.22 | 448 | 105 licensed | ~75 |

Roughly **700–800 firms** total at 10+ seats. Ample for outreach against a
5–10 customer target; too thin for paid ad optimisation.

## Gates

| # | Gate |
|---|---|
| G1 | Outlook **preferred** — Gmail workable but carries an unverified-app screen and a 100-user lifetime cap |
| G2 | Email is the primary client channel |
| G3 | **Recurring questions have stable, documentable answers** |
| G4 | 10+ people writing client email |
| G5 | No regulatory bar on AI client comms |
| G6 | **No in-house development team** — build-vs-buy; they'll think they can build it |
| G7 | Below the data-sovereignty procurement threshold |

**G3 is this repo's own content rule.** `reel/CONTENT-GUIDE.md` step 2 requires the
three questions be *lookups, not judgement calls*. Same test. A segment that fails
the reel gate would also fail as a customer.

**Walk away from:** in-house developers · under 10 seats · tech/SaaS companies ·
clinics and patient data · enterprise with procurement.

## Offer

**Repriced 2026-09-17.** The per-seat design-partner rate below this line is dead;
it was never founder-stated and it contradicted the flat fee the campaign page
sells. The live offer is two flat packages, and the only place either price may be
written down is `campaign-site/src/lib/offer.ts`. The costing behind them is in
`flow-savvy-automations/docs/economics/OFFER.md`.

| | Desk | Firm |
|---|---|---|
| Price | **$149/mo**, whole firm | **$199/mo**, whole firm |
| Mailboxes covered | up to 10 | up to 20 |
| Drafts per month, pooled | 5,000 | 10,000 |
| Setup | $500, waived for the first 5 firms | $500, waived for the first 5 firms |

Flat, not per seat: the bill does not move when the firm hires. At 20 people that
is under $10 a head. **Above 20 people it is a custom quote** — past that a flat
fee stops being generous and starts being careless, and WF4's polling window tops
out near 52 mailboxes across all customers anyway.

**The five founding places are real capacity, not a device.** WF4 polls every 60s
at ~0.8s per mailbox; at 70% headroom that is ~52 mailboxes in total. The trade is
the setup fee waived, never a lower monthly fee, so the price a reader sees does
not depend on when they read it.

**Delivered:** we build the knowledge base (fees, deadlines, checklists,
engagement and policy terms) · a voice profile per person · 90-minute kickoff
workshop · monthly tune-up · new hires free inside the coverage.

**Guarantee:** if DoviLoop does not put 150 usable drafts into the team's Outlook
in the first 30 days, that month is free. Counted from n8n execution records, so
the customer tracks nothing, and set well under what the smallest covered firm is
expected to produce.

## How to talk about it

**Not "hours saved."** The ROI arithmetic was never the objection — a prospect said
so directly: *"what do I make per hour? That's not the issue."*

**Say "capacity":** take on more clients without adding headcount.
Accounting-specific hook: **seasonal surge** — the inbox triples at year-end and
you cannot hire for eight weeks. Quality angle for audit and insurance:
**consistency** — a junior answers like a senior.

### Three true things, currently unstated in all copy

1. **It never leaves Outlook.** Buyer-stated: *"a lot of apps do similar things,
   but then you have to move away… it's what you're used to, you continue doing
   that, we just do a little prep work for you."*
2. **It never auto-sends.** Buyer-stated: *"I like that it doesn't auto-send,
   because that would be a big no-no for me."*
3. **It runs in Europe.** Data sovereignty is currently the biggest driver in
   European buying — a reason to buy, not a hurdle.

## Language

Danish for DK, Lithuanian for LT. Both ship in the product, so the outreach
language and the product language match. No US competitor will localise for these
two markets — this is the most defensible thing on the board.

## Two things that are proposals, not decisions

Flagged so no project treats them as settled:

- **The "capacity" framing** — reasoned from the prospect rejecting the ROI lever,
  but untested in market. **Highest-value thing to A/B first.**
- **The $149 / $199 flat packages** — founder-decided 2026-09-17, costed against
  measured unit costs, but never yet put in front of a buyer. Both clear the fixed
  monthly bill inside the capacity the polling window allows; neither has been
  tested for whether a DK firm reads $149 as cheap or as suspect.
- **Every competitor price the offer argues against.** Fyxer, Superhuman and
  Copilot rates came off pricing round-ups, not vendor pages. `claims/evidence.json`
  marks `competitor_price` and `rivals_charge_per_seat` UNVERIFIED and the gate
  blocks any ad that names a rival or characterises their billing. Read each rate
  at source, record the URL and date, then flip them.
- **doviloop.dev still sells Managed at $89/seat** — $890 for the 10-person firm
  this offer charges $149. Both pages are live. Deliberately left standing while
  there are no customers; revisit before real traffic hits both.
