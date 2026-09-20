# ad-engine (batch E) — session report

Branch `claude/campaign-build-status-9j9194`, from a clean clone, 2026-09-09.
No credential was used and no Meta API was called. `pull_ad_stats.py` was run
only with `--dry-run`.

## Verified

Everything below is a number this session actually observed, not an expectation.

| what I ran | what it returned |
|---|---|
| `pip install -r requirements.txt` | Pillow 12.3.0, pytest 9.1.1. First attempt died on a PyPI `ReadTimeoutError`; succeeded on retry with `--timeout 120 --retries 5`. |
| `python3 -m pytest tests/ -q` (before the sibling clone) | **106 passed, 9 skipped** |
| `python3 -m pytest tests/ -q` (after) | **115 passed** |
| `python3 -m pytest tests/test_ledger_contract.py -q` | **10 passed, 0 skipped** — see Found #1, the brief said 13 |
| `python3 -m creative.static.vet` | **16 renders checked, 0 failing**, exit 0 |
| `python3 -m engine.cli check` over `creative/copy/*.json` | **6 of 6 PASS**, nothing rejected |
| `python3 -m engine.cli check` over the whole `creative/` tree | **16 of 16 PASS**, exit 0 |
| `python3 report/pull_ad_stats.py --dry-run` | 8 raw rows collapsed to 5, **spend EUR 22.75**, clicks 53, leads 2, exit 0, nothing written |

### The cross-repo seam is real, not skipped

The 9 skips above were exactly `tests/test_ledger_contract.py`, all with
`campaign-ledger is not checked out beside this repo`. Cloned it as a true
sibling and checked out the matching branch:

```
/home/user/ad-engine        <- this repo
/home/user/campaign-ledger  <- claude/campaign-build-status-9j9194
```

`_campaign_db_path()` looks for `ROOT.parent/campaign-ledger/src/campaign_db.py`,
which now exists, so the module fixture imports Batch B's real client by file
path. No `CAMPAIGN_DB_PATH` override was needed and none was set. After the
clone the suite reports **0 skips**, so no assertion in this report rests on a
green skip.

### a. Static creatives — all 8, both ratios

All 16 renders PASS. Nothing to escalate before spend: no wrong dimensions, no
off-cream background, no amber over the 3.0% ceiling, no cool/blue drift, no
content inside the 18px edge band, no em/en dash, no third typeface.

The font check ran for real rather than being skipped — `check_fonts()` launched
headless Chromium and confirmed via `document.fonts.check()` that both Playfair
Display and DM Sans loaded, which is the one failure a human eye reliably
misses. That check has never been runnable from a clean clone before (Found #2).

### b. Claims gate — nothing rejected

All 6 copy variants and all 8 static specs pass. The gate rejected nothing, so
there is no blocked copy for the founder to rewrite.

**How the gate currently treats the 9x ROI figure (parked decision P-1).** I
changed no claim and no evidence entry. Probed with throwaway strings:

| string put to `gate.check()` | verdict |
|---|---|
| `Get 9x ROI on every seat.` | **BLOCK** — twice, on `9x` and on `ROI` |
| `9x return on investment.` | **BLOCK** |
| `Pays for itself in 40 days.` | **BLOCK** |
| `Saves 400 EUR a month per seat.` | **BLOCK** (as `hours_saved`) |
| `A worked example: 9x ROI on every seat.` | PASS |
| `Our model suggests 9x on every seat.` | PASS |
| `This is not a measurement. 9x ROI.` | PASS |

So the gate does hold the line the 2026-09-06 decision describes: `roi_model` is
`UNVERIFIED`, and a multiple, a payback period or a money-saved figure only gets
through when the ad itself carries one of the seven `allowed_if_framed_as`
phrases. No shipped creative asserts 9x — `s07-your-own-numbers` deliberately
hands the reader the sum instead of the answer. The arithmetic behind 9x is not
mine to re-open and I did not touch it; it stays parked as P-1.

One caveat on *why* s07 passes, which is not the reason it looks like: Found #3.

### c. Ad-stats path — both 2026-09-08 defects are still fixed

Verified against the committed fixture, offline.

**Defect 1 — `creative_content_id` must be `None` for a non-UUID label.** Still
fixed, in `content_id_for_ledger()`:

| label | returns |
|---|---|
| `v5-pilot` | `None` |
| `teams_q4_v3_outlook_static` | `None` |
| `v1-glance` | `None` |
| `''`, `None` | `None` |
| `3f2504e0-4f89-11d3-9a0c-0305e82c3301` | passes through unchanged |

All 8 transformed rows and all 5 ledger rows carry `creative_content_id = None`,
so nothing that would fail `uuid references campaign.content (id)` reaches the
insert. The labels are not lost — all six survive on `AdStatRow.utm_content`
(`teams_q4_v3_outlook_static`, `v1-glance`, `v2-voice`, `v3-outlook`,
`v4-europe`, `v5-pilot`) and print in the dry-run table.

Note the guard is `content_id_for_ledger()`, not the similarly named
`creative_content_id()` — the latter is the ad-name parser and still returns the
raw label by design. I checked the wrong one first; they are one letter apart in
intent and worth not confusing.

**Defect 2 — sum to the ledger's grain before writing.** Still fixed. 8
ad-level rows aggregate to 5 rows on `(campaign_name, ad_set_name,
captured_on)`, and the 5 are unique on that key. Three keys each carried two ad
rows:

- `teams_q4_retargeting / as1_video_viewers / 2026-09-23`
- `teams_q4_retargeting / as2_site_visitors / 2026-09-23`
- `teams_q4_retargeting / as3_format_test / 2026-09-23`

Raw total **22.75 EUR**; aggregated total **22.75 EUR** — it reaches the ledger
intact. Had the raw rows been handed to `snapshot_ad_stats` and upserted, the
replace-on-conflict would have left **13.97 EUR**, losing **8.78 EUR (39%)**
with no error. Both figures match the brief exactly.

## Produced

- `requirements.txt` — declares `playwright`, and corrects the stale test count
  in its comment (89 → 115, with the skip caveat). Commit `2a6a7f4`.
- `SESSION-REPORT.md` — this file.
- `../campaign-ledger` — sibling clone required by the contract tests. Outside
  this repo, not committed, and it must exist for `tests/test_ledger_contract.py`
  to do anything.

No creative, claim, audience, campaign doc or engine module was modified.

## Found

**1. The contract suite has 10 tests, not the 13 the brief expected.**
`pytest --collect-only` lists exactly 10 test functions in
`tests/test_ledger_contract.py`, there is no parametrisation, and all 10 pass
with 0 skips. The full-suite count of 115 matches the brief precisely, so this
looks like a stale number in the brief rather than three missing tests — but I
cannot prove that from inside this repo, and if three assertions were dropped
somewhere they would be invisible exactly the way the two 2026-09-08 defects
were. Worth one look from whoever wrote the 13.

**2. `vet.py` imported playwright and nothing installed it.** The documented path
— `pip install -r requirements.txt`, then `python -m creative.static.vet` — died
on `ModuleNotFoundError: No module named 'playwright'` before checking a single
creative. So the font-substitution check, the one item on the list a human eye
cannot audit, has never run from a clean clone. Fixed in `2a6a7f4` by declaring
the dependency. This is the only code-adjacent change I made.

**3. The claims gate scans internal fields as if they were ad copy — in both
directions.** This is the one worth the founder's time.

`check_creative()` walks every key except those starting with `_` and
`hypothesis`. But only `eyebrow`, `headline`, `subline` and `card.rows[]` are
ever rendered onto an image (`render.build_html`) or shown to a reader. So
`maps_to`, `job` and `note` — pure internal routing notes — are gated as though
a stranger on Instagram would read them. Measured across the tree: `maps_to` on
14 of 16 creatives, `job` on 8, `note` on 1, all scanned; the copy variants use
`_note`, which *is* correctly skipped.

That produces a false positive and a real loophole, and in `s07` the two cancel:

```
s07 as committed .................... PASS
s07 with the `note` key removed ..... BLOCK
    'return on investment' -> roi_model UNVERIFIED
```

s07's rendered copy is entirely clean and number-free. It trips the gate on
`maps_to: "direct value: the return on investment angle, written to pass the
claims gate"` — an internal label — and is then cleared because its internal
`note` happens to contain the framing phrase "a model". Two fields no reader
will ever see argue with each other, and the verdict lands on PASS by luck.

The loophole that follows is the more serious half, and it directly contradicts
`gate.check()`'s own docstring ("That framing phrase has to be in the ad itself,
not in a note, because the reader never sees notes"):

```
{"headline": ["9x ROI on every seat."],
 "note": "internal: this is a model, not a measurement"}      -> PASS

{"headline": ["9x ROI on every seat."],
 "note": "internal: reviewed by Dovy"}                        -> BLOCK
```

An unverifiable 9x in a headline is unblocked by framing sitting in a field the
reader never sees. That is precisely the outcome the 2026-09-06 decision was
written to prevent, and it is the failure mode this repo exists to stop.

**No shipped creative is affected today.** I re-gated all 16 against
reader-visible fields only, and every one passes both ways — the verdicts are
all correct, the *reasoning* under s07 is not. The exposure is latent: it bites
the first time someone puts a number in a headline and an honest explanation in
a note.

I did not fix it. The fix is small — have `check_creative()` walk only the
rendered fields, or rename `note`/`maps_to`/`job` to `_`-prefixed like the copy
variants already do — but either changes what the gate passes and blocks, on the
one control standing between a modelled number and a public ad, and it sits
directly against parked decision P-1. That is the founder's call, not mine.

**4. P-6 untouched, and confirmed still true from this side.**
`campaigns/pixel-install.md` already records that Audience 3 ("Pricing section
viewers, 90 days"), ranked highest-intent in `structure.md`, filters on a
`ViewContent` carrying `content_name: 'pricing'` that campaign-site never sends
— the only `ViewContent` it does send carries `demo_video`. I neither applied
the two-line `LocalePage.tsx` patch nor edited that file. Worth restating for
priority: the doc also notes `VITE_META_PIXEL_ID` is unset, so the pixel is
inert and nothing fires today regardless — P-6 costs nothing until the pixel is
switched on, and must be settled before it is.

**5. Audience 2 is blocked upstream.** `engine.cli plan` reports
`site-retargeting` (priority 2, the cheapest useful spend) as BLOCKED: the Meta
pixel is not installed on either domain. Reporting only — this is not mine to
act on.

**6. Environment note for anyone reproducing the vet run.** `playwright` must
match the Chromium build it drives. This container ships build 1194 at
`/opt/pw-browsers`; pip installs 1.62.0 by default, which expects 1234 and fails
with `Executable doesn't exist`. `playwright==1.56.0` matches 1194 and the vet
run above used it. I left `requirements.txt` unpinned deliberately — the
constraint is the local browser, not the repo — and did not run
`playwright install`.

## Blocked

- **Nothing in the assigned task was blocked.** All of 1, 2a, 2b and 2c ran to
  completion and every number above was observed.
- **Joining spend back to a specific creative.** Every ledger row writes
  `creative_content_id = NULL`, correctly. Fixing that needs a real
  `campaign.content.id` to look labels up against, which this repo has no way to
  reach — see `BLOCKED.md`. Until then `v_content_perf` cannot attribute spend
  per creative, only per ad set per day.
- **One ad is named off-convention** and cannot be joined even once ids exist:
  `teams_q4_v3_outlook_static`, against the expected
  `campaign | utm_content | creative-ratio`. Renaming it lives in Ads Manager,
  which is out of scope here.
- **The live write path is unproven against real Postgres, by design.** The
  contract test binds against Batch B's real signature, which is the strongest
  check available without credentials, but only an actual insert proves the uuid
  column behaves as expected. That needs Supabase access this session correctly
  does not have and did not ask for.
- **Six parked decisions, P-1 to P-6, remain the founder's.** None was acted on.
  P-1 (the 9x figure) is reported above as the gate currently treats it; Found #3
  should be read alongside it, since it changes how much that gate can be
  trusted to enforce whatever P-1 decides.
- **Found #1 (10 tests vs 13)** needs whoever wrote the brief to confirm the
  expected number. I cannot settle it from inside this repo.
