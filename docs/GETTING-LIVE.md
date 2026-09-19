# Getting live

Everything in this repository runs offline today: 1,757 tests, no key, no
token, no socket. What stands between that and a real ad is a short list of
things only a person can do, and this is that list, in the order that wastes
the least of your time.

`RUN-STATE.md` is the task table this mirrors. Where the two disagree, that
file is the record and this one is the instructions.

**Read this first.** Step 1 is the only step with a queue at the other end -
Meta takes one to three business days to verify an identity. Do it before you
do anything else, then fill the wait with steps 2 to 5. Getting that order
wrong costs you a working day for no reason.

---

## Step 1 - Meta identity verification (5 minutes, then 1-3 days of waiting)

**Do this first, today, whatever else you do.**

1. Open <https://www.facebook.com/ID> while logged in as the account that will
   own the app.
2. Upload a government id - passport, national id or driving licence - and
   confirm your country of residence.
3. Wait. Meta answers in one to three business days.

**Why it is first:** the Ad Library API includes political ad data, so Meta
gates the whole API behind a verified identity. Nothing that reads a stranger's
ad can happen until this clears, and no amount of preparation shortens it.

**Then, once it clears:**

4. <https://developers.facebook.com> - create an app (type: Business).
5. In the app, **Add Product** and add **Ad Library API**.
6. Generate an access token for the app, and note **today's date**.

**Unblocks:** everything in step 6, and through it the whole research half.

---

## Step 2 - A Gemini key (2 minutes)

1. <https://aistudio.google.com> - create an API key. Free, no card, no billing
   account.
2. **Check the key's Google Cloud project has no billing account attached.**
   This is the one that bites silently: with billing enabled the free tier
   stops being free and bills at paid rates, with no 429 and no warning. With
   no billing account the failure is a 429 that resets on its own.

**Unblocks:** every model call - analysis, concepts, scoring, writing, the
editorial gate.

---

## Step 3 - A read token for reel-engine (3 minutes)

The ad's video is a reel, and reels are rendered by the sibling repository.
`build.yml` checks it out, so it needs to be able to read it.

1. GitHub **Settings > Developer settings > Personal access tokens >
   Fine-grained**.
2. Resource owner `Dasvydo`, repository access **only** `Dasvydo/reel-engine`.
3. Repository permissions: **Contents: Read**. Nothing else.

**Unblocks:** the creative half. Without it a copy-only ad still works and a
reel ad fails at checkout.

---

## Step 4 - Put steps 2 and 3 into the repository (10 minutes)

```bash
bash tools/setup_github.sh --check     # what is missing, changes nothing
bash tools/setup_github.sh             # create the labels, prompt for each value
```

It creates the four labels the approval flow needs (`go`, `no`, `stage:copy`,
`stage:creative`), and prompts for each secret with the input hidden so no
value reaches your shell history. Leave `META_ACCESS_TOKEN` blank for now -
step 6 sets it.

It needs the `gh` CLI, authenticated with admin on the repository.

---

## Step 5 - The spending limit (1 minute)

<https://github.com/settings/billing> - confirm the Actions spending limit is
**$0**.

This is the single setting that turns the $0.00 claim in `docs/COST.md` from a
claim into a guarantee. At zero, an Actions overage **stops runs** instead of
billing for them. Everything else in that ledger is a free allowance whose
failure mode is a refusal; this is the only one that could become an invoice.

---

## Step 6 - When the token arrives (5 minutes)

**Set both of these in the same visit.** A fresh token with a stale date warns
for no reason; a stale token with a fresh date never warns at all.

1. `META_ACCESS_TOKEN` - Actions > **Secrets**. The token from step 1.6.
2. `META_TOKEN_ISSUED` - Actions > **Variables**. A different tab, on purpose:
   a date is not a credential, and the countdown needs it *visible* so you can
   check a rotation against it. A secret is write-only once saved, so set there
   it can never be verified again.

Then prove it works, locally, with one call:

```bash
export META_ACCESS_TOKEN=...
python tools/first_live_call.py
```

That makes **one** request and prints every field this repository asks for
against what actually arrived. Three things in the code are marked
`TODO(integration): UNVERIFIED AGAINST A LIVE RESPONSE`, and this answers two
of them. Paste the whole ad it dumps into the commit that closes the TODO, so
the next reader sees evidence rather than a summary.

Optionally, and it spends real calls on purpose:

```bash
python tools/first_live_call.py --rate-limit
```

`HOURLY_BUDGET_CALLS = 200` is what every guide reports and Meta's own
reference does not print. This measures it.

**Unblocks:** the weekly sweep, and with it steps 7 onward.

---

## Step 7 - The first sweep (10 minutes, mostly waiting)

**Actions > research > Run workflow**, with `dry_run` ticked. It spends
nothing and reports what a real run would do and cost.

Then run it again without `dry_run`. It commits three things:
`research/corpus/` (one file per analysed ad), `research/patterns.json` (what
repeats, counted), and `research/selection.json` (three concepts, each citing
patterns that trace to named ads).

The thirteen pages in `research/seeds.yaml` already carry real ids read off
live responses on 2026-09-18, so there is nothing to fill in first.

**What to look at afterwards:** whether the band edges in `engine/learn.py`
actually separate anything. They are a first guess made with no corpus behind
them, and the first real corpus is what corrects them. A band holding every ad
is a band saying nothing.

---

## Step 8 - Native copy (an hour of a native speaker's time)

**Twelve strings**, across two creative variants:

| File | Fields |
|---|---|
| `creative/capacity.json` | `primary_text`, `headline`, `description` - each in `da` and `lt` |
| `creative/hours.json` | the same six |

Each currently reads `NEEDS_NATIVE_PROOFREAD`. That placeholder is deliberate
and load-bearing: the claims gate accepts it as "not written yet" and refuses
to treat it as copy, so a machine translation can never reach a live ad by
accident. **A model does not write these and does not get to declare them
native.** `creative/example-job.json` also carries six placeholders and is
correct as it stands - it is the worked example the writer imitates, not copy
that ships.

Constraints the translator needs: the headline is under 40 characters, the
description under 60, and no number or number-word may appear in any of them
unless it is attested in `claims/evidence.json`. Nothing currently is.

**Unblocks:** running an ad in either market. Everything before this works
without it.

---

## Step 9 - The measure token (5 minutes, and only once an ad has run)

**First, fill the `own:` block** in `research/seeds.yaml`. It ships blank, and
blank is not an error - `engine/feedback.py` writes a record with `page_id ""`
and channel `"own"`, which is true rather than guessed. But a corpus of our own
ads that cannot name the page it ran from is worth less every week, so fill it
before the first launch rather than after:

```yaml
own:
  page_id: "<digits from the Ad Library URL for the DoviLoop page>"
  page_name: DoviLoop
  ad_account_id: act_<digits from Ads Manager>
```

`page_id` is validated as all-digits on load and is **not** the page name;
read the number out of the Ad Library URL for the page. `ad_account_id` is
recorded for the operator's benefit - `engine/measure.py` deliberately never
reads it, because the ad ids pinned into `queue/launched/<segment>.json`
already say which ads are ours.


`engine/measure.py` reads our own ads' click-through rate, which is the
strongest evidence this loop will ever hold. It needs `ads_read` on the ad
account - the same `META_ACCESS_TOKEN`, with that scope added, or a separate
one.

**Worth checking while you are there:** whether a **System User** token from
Business Manager is accepted. A System User token does not expire, which would
delete the sixty-day rotation from your calendar permanently. Nobody here has
tested it.

Then, on a launched ad:

```bash
python -m engine.measure --dry-run     # calls, prints, writes nothing
```

**Unblocks:** the loop closing - a measured click-through rate becoming a
pattern the next sweep can cite.

---

## Step 10 - The one decision, whenever you get to it

**Read the Ad Library API terms** at
<https://www.facebook.com/ads/library/api> and settle decision 6 in
`docs/AD-RESEARCH-SCOPE.md`: whether a corpus record stores a stranger's
creative text verbatim, or only what was derived from it.

The page refuses automated fetch, so this one genuinely needs your browser.

**What the code does today, and why it is the safer default anyway:**
`analysis.copy` holds the creative text verbatim, in a **private** repository,
and nothing republishes it. Every secondary source agrees that research,
journalism and internal marketing insight are permitted uses, and that the
prohibitions are on republishing misleadingly and on profiling individuals -
neither of which this does. **That is secondary sourcing, not the terms**, so
it is a recommendation and not a finding.

If the terms turn out to be narrower, the change is small: drop
`analysis.copy` from the record and keep the derived fields plus the ad id and
snapshot url. Learning works either way; only the ability to quote a
competitor's line back to a writer is lost.

---

## What is deliberately not on this list

**The Marketing API write path** - creating an ad from the repository rather
than by hand. It is `T34` in `RUN-STATE.md`, it is the only thing here that
could ever spend money, and it is scoped last on purpose. Today `engine/
approval.py launch` records an ad id that a person pasted, and nothing in this
repository writes to Meta at all.

**The Meta pixel on doviloop.dev.** It blocks the retargeting audience this
repository already lists as blocked. It blocks nothing in the research loop.

---

## The short version

| Do now, in this order | Time | Unblocks |
|---|---|---|
| 1. Identity verification at facebook.com/ID | 5 min + 1-3 days | everything |
| 2. Gemini key, no billing account | 2 min | every model call |
| 3. Fine-grained PAT for reel-engine | 3 min | the creative |
| 4. `bash tools/setup_github.sh` | 10 min | the workflows |
| 5. Spending limit at $0 | 1 min | the cost guarantee |

That is about **20 minutes of your time**, and then the calendar does the rest.
Steps 6 and 7 follow the moment Meta answers. Steps 8, 9 and 10 are not
urgent - nothing before them needs them.
