---
name: meta-ad-launch
description: >-
  Take ad files Dovy drops into the chat (images, videos) all the way to live
  DoviLoop ads on Meta: inspect every file, build creatives and ads paused, prove
  each one passed (no errors, preview renders, destination and tracking links
  correct), get his go, launch, then push performance checkpoints to his phone.
  Use whenever he attaches or uploads ad images or videos, says launch these,
  swap these in, put these live, new creatives, new ad, asks whether the ads are
  live, approved or stuck, or asks how the ads he launched are doing - even if he
  never says Meta, campaign or ad set. Copy and claims questions on their own
  belong to meta-ads.
---

# Meta ad launch: drop → live → checkpoints

Dovy drops files. You take them to live ads and then keep watch. Every phase ends
in something he can check, and **nothing spends until he taps approve** on the
launch prompt.

This skill is the pipeline. The rules it runs under live in `../meta-ads/`:
read its `SKILL.md` hard rules, and `references/claims.md` before any copy goes
into a creative. Where either file names an ID or a structure, **the live account
wins** - read it, because both files drift.

---

## Setup (check once per session)

**Permissions.** Build tools run freely because they create paused objects and
spend nothing: `ads_creative_upload_media`, `ads_create_creative`, `ads_create_ad`.
Launch tools always prompt, and **that tap is his go**: `ads_activate_entity` and
`ads_update_entity` - the second can set `status: ACTIVE` and move the budget, so
it is a launch tool too. Never allowlist either. If a build call is refused by
the permission check, name the tool, point him at `/permissions`, and stop.
Never route around a refusal with a different tool.

**Account, as of 2026-09-28 - re-read live before trusting:**

| | |
|---|---|
| Ad account | `620456015062432` (DKK) |
| Page | `1294387330427112` - DoviLoop |
| Running campaign | `120252014714500563` - `OUTCOME_TRAFFIC`, budget on the campaign, DKK 35/day |
| Running ad set | `120252014715910563` - DK+LT, 30-60 hard, **Facebook only** |
| Destination | `https://www.doviloop.dev/` - the `www` host. The apex 307s to it, and `teams.doviloop.dev` was retired on 2026-09-28 |
| UTM template | `utm_source=meta&utm_medium=paid&utm_campaign=teams_q4&utm_content=<variant>` |
| Pixel | `1584074833462346` - **not installed on www.doviloop.dev** as of 2026-09-28 |

Generate one `client_conversation_id` per conversation and reuse it on every
Meta call.

---

## The pipeline

Run the phases in order. Post one short line per phase as you finish it - he
wants to watch it move, not read a wall at the end:

```
✅ 1 Intake - 2 files, copy = v4-europe, replaces v2-voice
✅ 2 Inspected - both 4:5, feed-ready (sheets checked)
⚠️ 4 Pre-flight - ad set has Instagram, no IG account → Facebook-only (your ok?)
```

### 1 · Intake

Work out what each file is for, then ask for what is missing **in one message**:

- **Copy.** An existing variant from `creative/copy/<id>.json` is reused verbatim.
  New copy goes through phase 3.
- **Which live ads it replaces.** The swap rule: at most 3 ads live in the ad set.
  At DKK 35/day Meta puts most of the spend on one ad, so a fourth ad learns
  nothing and every added creative restarts learning.
- **Destination**, if it isn't the homepage.
- **AI disclosure: always ask, never infer.** *"Was any of this made or edited with
  an AI image or video tool?"* Yes → `self_ai_disclosure: OPT_IN`, no → `OPT_OUT`.
  No answer → omit it, and say it's blank in the go message. It **cannot be changed
  after the creative exists**, and in the EU it's his legal declaration, not yours.

### 2 · Inspect every file

```bash
python .claude/skills/meta-ad-launch/scripts/inspect_media.py <files...> --out <dir>
```

The script prints specs (size, ratio, duration, codec, audio level) and writes a
contact sheet per video plus a safe-zone overlay for anything 9:16. **Open and look
at every image it writes.** The script measures; you judge what is on screen,
whether the headline reads with the sound off, and whether text crosses the
Stories UI bands.

| Ratio | Goes to | Note |
|---|---|---|
| 4:5 (1080×1350) | Feed - the main placement at this budget | Lead with it |
| 1:1 | Feed | Loses height against 4:5 |
| 9:16 (1080×1920) | Stories, Reels | Keep text out of the top 14% and bottom 20% |
| 16:9, 1.91:1 | In-stream, right column | Weak in mobile feed |

Report per file: ratio → placement, what happens on screen, anything wrong.

### 3 · Copy and claims

Existing variant: take the body and headline verbatim from its JSON. New copy:
`../meta-ads/references/claims.md`, then `python -m engine.cli check` as a
backstop only. **Text burned into the image or video is copy too**: "drafted
before 9am" in a video is a claim and needs evidence like any headline.

### 4 · Pre-flight the account (read-only)

1. **Read live**: campaign, ad set (status, budget, `targeting.publisher_platforms`),
   every ad (`status`, `effective_status`), `ads_get_errors` on all of them,
   `ads_get_ig_accounts`.
2. **Placements vs linked accounts.** If `publisher_platforms` has `instagram` or
   `threads` and there is no IG account, new ads stick at `WITH_ISSUES`
   (*"Page Backed Instagram profile is being created"*) **indefinitely**. On
   2026-09-22 it held two ads for six days. Threads uses the Instagram identity
   too. Fix before building: go Facebook-only (a targeting write, so ask) or have
   him link an IG account.
3. **Swap plan.** New ads + the ones staying live ≤ 3. Name which ads retire. With
   7+ days of data, propose the lowest link CTR. Without it, ask him.
4. **Destination check:**
   ```bash
   python .claude/skills/meta-ad-launch/scripts/verify_destination.py "<url with UTMs>" --pixel 1584074833462346
   ```
   It must return 200 with no redirect hop, and the UTMs must survive. It also
   records whether the pixel is present - if not, the reports say "not measured",
   never "0".
5. **Hosting the files.** Meta has to fetch the media from a public URL (this CLI
   cannot drive the connector's local-file upload app). Copy each file into
   `creative/drops/<YYYY-MM-DD>/`, commit, push, and use
   `https://raw.githubusercontent.com/Dasvydo/ad-engine/<branch>/<path>`.
   The repo is public, so the file is public before launch. Say so once.

### 5 · Build - everything paused

1. **Upload**: `ads_creative_upload_media`, `upload_source: URL`,
   `media_type: IMAGE|VIDEO`. Video encodes asynchronously: poll `ads_get_ad_videos`
   until it reads ready, never build on `processing`. If the tool says it isn't
   available to this account, images can go straight in as `image_url` on the
   creative. Video has no fallback, so stop and say so.
2. **Creative**: `ads_create_creative` with `page_id`, `image_hash` or `video_id`
   (video also needs a thumbnail image), `link_url` (the `www` host + UTMs),
   **`display_link: "doviloop.dev"`** (otherwise the caption prints the raw UTM
   string), `message`, `headline`, **`description`** (always set it: left out,
   Meta pulls the destination's meta description onto the ad - on 2026-09-28 that
   put *"€29 per seat a month"* under an ad nobody had written a price into),
   `call_to_action_type`, and `self_ai_disclosure` per phase 1. The description is
   copy, so it goes through phase 3. Name it `<variant> | <file-stem> | <host> <date>`.
3. **Ad**: `ads_create_ad` in the ad set with `{"creative_id": ...}`, named
   `teams_q4 | <variant> | <file-stem>`. It can come back `PAUSED` or `DRAFT`
   (draft mode) - record which, because a draft publishes straight to ACTIVE.

**Creatives are immutable.** A wrong link, copy or disclosure means a new creative
and a new ad. There is no edit.

### 6 · Verify - prove it, don't assume it

For every new ad:

- `ads_get_errors` → must be empty. An error either gets fixed or gets explained
  before the go. Never carry one into it.
- `ads_get_ad_preview` (with `ad_id`; if the ad is too fresh, `creative_id`) → give
  him the `preview_url` as a clickable link.
- The destination Meta will actually send people to:
  ```bash
  python .claude/skills/meta-ad-launch/scripts/preview_destination.py "<preview_url>" --expect "<intended url>"
  ```
  Meta's creative read does not return `link_url` for these ads, so the rendered
  preview is the only first-hand proof of where the click goes. The script also
  prints the button, caption, headline and **description as they will actually
  show** - read the description, Meta may have filled it in.

Then one table: ad id, name, status, errors, destination ✓/✗, preview link.

### 7 · The go

Send exactly this shape, then wait:

```
Ready to launch - nothing is spending yet.

New ads (paused, verified):
• v4-europe · 4:5 · → www.doviloop.dev ✓ · no errors · [preview](…)
Retiring (will pause): v2-voice
Budget unchanged: DKK 35/day · DK+LT · 30-60 · Facebook only
AI disclosure: OPT_OUT (you said no AI) | blank (not answered)
Checkpoints I'll push to your phone: +2h, +24h, day 3, day 7, day 14

Tap approve on each launch prompt to go.
```

On his go, in this order: **pause the retiring ads → activate the new ads →
activate the ad set if paused → activate the campaign last** if paused, so the
whole set starts at the same moment. Then re-read every status and report it.
`IN_PROCESS` / in review is normal and takes minutes to 24 hours. If a launch call
is refused, stop, say which one, and don't retry another way.

### 8 · Checkpoints - push to his phone

At go time, schedule one-shot Routines (`create_trigger` with `run_once_at`,
`create_new_session_on_fire: true`, `notifications: {push: true}`, the Meta
connector) at **+2h, +24h, day 3, day 7, day 14**. Each prompt stands alone:

> Use the meta-ad-launch skill. Checkpoint <X> for the launch of <date>: ads
> <ids>, ad set <id>, campaign <id>. Report per references/checkpoints.md.

If there are no scheduling tools, say so and list the five times so he can ask.
What each checkpoint reads, and the report format: `references/checkpoints.md`.

---

## Never

- **Spend without his tap.** Build freely, launch only on approve.
- **Guess the AI disclosure.** Ask, and omit it if he doesn't answer.
- **Report a number that wasn't returned.** No pixel means "not measured", not 0.
- **Run a fourth ad.** Swap, don't add.
- **Change a live test in its first 14 days** unless he asks for a swap. Adding an
  ad, pausing one, a targeting change, or moving the budget more than 20% each
  restart Meta's learning.

What bit us before, with symptoms and fixes: `references/gotchas.md`.
