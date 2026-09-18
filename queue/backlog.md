# Segment backlog (a copy)

**The table below is a copy of `reel-engine/queue/backlog.md`, not the
original.** The ICP is one ranked list and `reel-engine` owns it. This
repository keeps a copy rather than reading `../reel-engine` at run time so
that the weekly research cron needs no second repository's token: checking the
sibling out inside Actions would cost `REEL_ENGINE_TOKEN` just to read one
markdown table, and a free, read-only sweep should not be able to fail on a
credential it has no other use for. The one workflow that genuinely needs the
sibling - `build.yml`, which renders - is the one that holds that token.

Do not edit the rows here. Edit them in `reel-engine`, then run

    python tools/sync_backlog.py            # rewrite the block below from ../reel-engine
    python tools/sync_backlog.py --check    # exit 1 and print the diff if the two drift

The block between the `backlog:begin` and `backlog:end` markers is owned by
that tool and rewritten whole; everything outside the markers is this file's
own prose. Two copies drift, which is why `--check` exists and why the rows
are never hand-edited on this side.

`engine/backlog.py` takes the highest-ranked segment that has no job in
`queue/proposed`, `queue/built` or `queue/launched`. Rank is intent, not a
queue position. A draft parked in `queue/rejected/` deliberately does **not**
count as used: it never passed the gate, so its segment stays here and gets
picked again.

The rows are scoped to the locked ICP in `docs/ICP-BRIEF.md`: accounting and
bookkeeping, outsourced back-office, insurance brokers - 10+ people writing
client email, Microsoft 365, Denmark and Lithuania. A segment belongs in the
table only if its three questions are lookups, not judgement calls; that is
the same test as gate G3 in the brief, and the reason is the same on both
sides - a knowledge base has to be able to answer the mail.

> ⚠️ **Every pipe-delimited row in this file is parsed as data** by
> `engine/backlog.py`, anywhere in the file, and a malformed one raises. Keep
> prose as prose, and never write a table outside the markers: the sync tool
> refuses a row it finds there, because no rewrite of the block could make the
> local table equal the source.

<!-- backlog:begin -->
| rank | id | trade | questions | note |
|---|---|---|---|---|
| 1 | accountants | Accountants | deadline, receipts, mileage | reframed: `allowance` mixes lookups with judgement ("can I claim the laptop?" needs business-use %), and the gate rejected it twice - though the same tags passed twice before, so the rubric samples |
| 2 | payroll-bureaus | Payroll bureaus | payslip, holiday, tax-code | strongest lookup profile of the set - all three are a record fetch, none is an opinion |
| 3 | bookkeepers | Bookkeeping firms | invoice, vat, receipt | distinct audience from accountants in DK/LT: bogholder vs revisor, buhalteris vs auditorius |
| 4 | admin-firms | Outsourced back-office firms | invoice, scope, document | NACE 82.11 - they run admin for other businesses, so their inbound is structurally high |
| 5 | audit-firms | Audit firms | deadline, document, fee | inside NACE 69.20 with accountants; keep separate because the inbox reads differently |
<!-- backlog:end -->
