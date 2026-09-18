# AUDIT, Batch E, ad-engine

Phase 0. Written before any other file in this repo was touched.
Run date: 2026-09-03. Branch: `campaign/e-ads`. Nothing pushed.

Evidence rule for this file: every claim below names the command that produced
it and what came back. Where I could not verify something, it says so.

---

## 1. The repo as it stands

```
$ cd /home/user/ad-engine && git status
On branch campaign/e-ads
nothing to commit, working tree clean

$ git log --oneline
a214e58 Initial commit: audiences, creative, and a claims gate
```

Tree (`find . -path ./.git -prune -o -type f -print`):

```
.gitignore
README.md
audiences/broad-interest.json
audiences/outreach-list.json
audiences/site-retargeting.json
claims/evidence.json
creative/capacity.json
creative/hours.json
docs/ICP-BRIEF.md
engine/audience.py
engine/cli.py
engine/gate.py
tests/test_gate.py
```

### Does it run?

```
$ python3 -m pytest -q
........                                                        [100%]
8 passed in 0.03s

$ python3 -m engine.cli check
PASS   capacity.json
PASS   hours.json
(exit 0)

$ python3 -m engine.cli plan
[3] broad-interest       interest
[1] outreach-list        custom_audience
[2] site-retargeting     pixel_retargeting   BLOCKED: Meta pixel is not installed...
```

Yes. Python 3.11.15, pytest 9.1.1, no external dependencies. Everything in the
repo works today.

### The claims gate (found, read, respected)

`engine/gate.py` + `claims/evidence.json`. It regex-scans every rendered string
in a creative spec for measurable assertions and blocks any whose claim id is
not `verified` in `claims/evidence.json`.

Currently blocking, deliberately:

| Pattern | Claim id | Status |
|---|---|---|
| `\d+ hours`, `saves \d` | `hours_saved` | UNVERIFIED, no measured customer outcome |
| `trusted by \d`, `\d firms use` | `customer_count` | UNVERIFIED, zero closed customers as of 2026-08-31 |
| `\d+%` | `percentage_claim` | UNVERIFIED, nothing measured |

Verified and therefore usable: `never_auto_sends`, `stays_in_outlook`,
`eu_hosted`, `own_knowledge_base`, `per_person_voice`.

**This gate governs every word Batch E writes.** All new copy is run through
`python -m engine.cli check` and must pass. See "Conflicts found" below for the
one place the campaign brief and this gate disagree.

### What existing work I am extending, not replacing

- `audiences/*.json` stay as they are. They describe list-upload and interest
  targeting for a cold prospecting motion. Batch E adds a *retargeting* layer on
  top; it does not contradict them.
- `creative/capacity.json` and `creative/hours.json` stay. They are the two
  pre-campaign A/B arms and they still pass the gate. New campaign copy lands in
  `creative/copy/` so the two sets do not collide.
- `engine/gate.py` logic is unchanged. `engine/cli.py` `check` is widened from
  `creative/*.json` to a recursive glob so it also gates the new copy.

---

## 2. `hm-static-ad-generator`, does the Playwright pipeline execute?

**Yes. Verified by running it, not by reading about it.**

Skill location confirmed:

```
$ find /root/.claude/skills/synced/0f088901-...-0f340692-.../hm-static-ad-generator -type f
.../SKILL.md
.../references/brand-lock.md
.../references/nano-banana-pro.md
.../references/prompt-scaffold.md
.../references/vetting-checklist.md
```

`references/brand-lock.md` exists and was read in full. Palette, type rules,
amber-accent-only rule, logo rules, voice, and the "if it reads yellow the
background hex is wrong" test are all captured and applied.

### The open question, settled

The skill describes a hybrid mode: an image model makes the *bed*, and the
brand-critical layer (Playfair headline, exact hex, one amber accent, logo) is
typeset in HTML/CSS and screenshotted with Playwright. The skill ships **no
code** for that pipeline. It refers to a pipeline "DoviLoop already uses",
which is not in this repo and not on this machine. So the pipeline had to be
built here to be answered honestly.

What is on the machine:

```
$ python3 -m pip list | grep -i playwright
playwright         1.62.0

$ python3 -c "from playwright.sync_api import sync_playwright ..."
SCREENSHOT OK

$ p.chromium.executable_path
/opt/pw-browsers/chromium-1234/chrome-linux64/chrome
```

Chromium is preinstalled at `/opt/pw-browsers`, not at the usual
`~/.cache/ms-playwright` (that directory does not exist), which is why a naive
`ls` check would wrongly report the pipeline as dead.

Fonts are **not** on the machine:

```
$ fc-list | grep -iE "playfair|dm sans"
(no output, 59 fonts installed, all DejaVu / Liberation / Noto)
```

Google Fonts is reachable through the agent proxy, so the two brand faces are
fetched once and vendored into the repo as woff2, then base64-embedded into the
render HTML so a render needs no network:

```
$ curl -sS -o - "https://fonts.googleapis.com/css2?family=Playfair+Display..." | head
200, 8401 bytes
fonts/playfair-var.woff2  38404 bytes
fonts/dmsans-var.woff2    36932 bytes
```

Full end-to-end proof render, 1080x1350, cream ground, Playfair headline with a
single amber word:

```
$ python3 render_probe.py
playfair width 342.0  fallback serif width 316.6  -> custom font applied: True
size (1080, 1350)  bg px (255, 240, 229)
```

`(255, 240, 229)` is exactly `#FFF0E5`. The width comparison proves the embedded
Playfair is actually rasterising rather than silently falling back to a system
serif, which is the failure mode that would quietly ship off-brand type.

**Verdict: the hybrid typesetting half of the pipeline executes today and Batch
E ships all 16 creative files through it.** What does *not* execute is the
generative half: there is no image-model call available in this session, so no
photographic or illustrative "beds" were generated. All eight creatives are
therefore built as pure typeset editorial layouts on solid brand grounds, which
is inside the brand lock and needs no model. The Nano Banana Pro bed prompts are
written and committed alongside each creative so Dovy can generate beds later
and re-run the same typeset layer over them. See BLOCKED.md.

Batch D was asked the same question independently. This answer is from a real
run in this session with the output above.

---

## 3. Existing DoviLoop ad creative

**None found.**

- Repo: no image files at all. `creative/*.json` are copy specs, and both point
  at `reel-engine` renders for their visuals rather than carrying any.
- Google Drive, searched as dvinickis@gmail.com:
  - `fullText contains 'DoviLoop'` returns three folders (DoviLoop Ops,
    DoviLoop, DoviLoop Solutions) and two revenue-model spreadsheets. No ad
    creative.
  - A search for image and presentation files whose titles contain ad, creative
    or campaign returns only personal photos and one Higgsfield render
    (`hf_20260616_095031_*.png`) in the DoviLoop folder. Nothing that is an ad.

So every creative in this batch is new. Nothing was duplicated.

---

## 4. The Alta / MasterInbox / Fyxer / Conversifi teardown

**It is not on this machine and it is not in Drive. I did the research fresh.**

```
$ grep -rliE "masterinbox|conversifi|fyxer" /home/user /root /opt
/home/user/campaign-specs/E-ad-engine.md
/home/user/campaign-specs/D-reel-engine.md
/root/code/campaign-specs/D-reel-engine.md
/root/.claude/... (this session's own transcript files)
/root/.claude/uploads/... (copies of the two spec files above)
```

Every hit is a spec file that *asks* for the teardown or a transcript of this
session. No hit is a teardown.

Drive holds two adjacent but different documents, both authored October 2025 and
both secondary (analyst write-ups, not primary competitor pages):

| File | What it is | Use here |
|---|---|---|
| `fyxer_ai_competitor_analysis.docx` | Feature, pricing, security and positioning summary of Fyxer AI | Corroborating only. Cited as a dated secondary source where it agrees with a live page I checked myself. |
| `RevReply_Competitor_Analysis.docx` | Same format, different company, not in scope | Not used |
| `Alta Meeting Notes.docx`, `alta_agent_roster.svg` | Notes and a diagram about Alta | Noted as existing. Not a teardown of the four. |

Neither Drive file contains an objection teardown, neither covers MasterInbox or
Conversifi, and both predate the campaign by eleven months. `research/objections.md`
is built from live public sources checked in this session, with the Drive Fyxer
doc used only as a cross-check.

---

## 5. Conflicts found between the campaign brief and this repo

Logged here because both documents are live and a later reader needs to know
which one Batch E followed.

| Thing | `00-START-HERE.md` (campaign) | `docs/ICP-BRIEF.md` + `claims/evidence.json` (repo) | What Batch E did |
|---|---|---|---|
| Price | $89/seat/mo + $500 setup | $49 design partner / $99 standard, $750 onboarding | Followed the campaign brief. No price appears in any creative, so nothing shipped depends on it. |
| Destination | `teams.doviloop.dev` | `doviloop.dev` | Campaign brief. All new copy points at `teams.doviloop.dev` with the spec's UTM string. Old creative left pointing at `doviloop.dev`. |
| Markets | DK, LT, US/global | DK, LT | Campaign brief. Ads are English everywhere either way. |
| ROI figures | "verified ROI figures (~9x ROI, ~EUR 400/month saved, ~40-day payback)" | `hours_saved`, `percentage_claim` both UNVERIFIED, zero customers | **Followed the repo gate.** No ROI number appears in any creative or copy variant. See BLOCKED.md entry 3, this needs a one-line answer from Dovy and is the single highest-value unblock in this batch. |

The ROI conflict is the one that matters. The campaign brief calls the figures
verified; the repo says flatly that no customer outcome has ever been measured
and that an investor warned specifically about public measurable promises with
nothing behind them. Those cannot both be true. Batch E took the conservative
reading, because a wrong ad is cheap to rewrite and a wrong public claim is not.
