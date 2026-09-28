# Gotchas - things that already bit this account

Each one: the symptom you'll see, what's actually happening, the fix. Dated,
because Meta changes.

## Ads stuck at WITH_ISSUES: "Page Backed Instagram profile is being created" (2026-09-22)

- **Symptom:** `effective_status: WITH_ISSUES`, and `ads_get_errors` says the Page
  Backed Instagram profile is still being created. It never finishes: two ads
  sat like this for six days.
- **Cause:** the ad set has Instagram (or Threads) placements, and no Instagram
  account is linked (`ads_get_ig_accounts` → `[]`), so Meta tries to invent an IG
  identity from the Page.
- **Fix:** Facebook-only placements (the ad set was switched on 2026-09-28), or
  link a real IG account. Threads uses the Instagram identity, so it goes too.

## You can't edit an ad's link, copy or disclosure

Creatives are immutable. Changing any of them means a new creative plus a new ad.
The ad set keeps its settings.

## `ads_get_creatives` doesn't return `link_url` for these ads

Link ads are stored as Page posts (`object_type: SHARE`). The destination sits in
the post spec, which the read tool doesn't return. Prove the destination from
the rendered preview with `scripts/preview_destination.py`.

## The caption shows the raw tracking string

Without `display_link`, the ad's caption reads
`doviloop.dev/?utm_source=meta&utm_medium=paid&utm_ca…`. Set
`display_link: "doviloop.dev"`. It only changes the text shown, not where the
click goes, and it's fixed once the creative exists.

## Meta writes a description you didn't (2026-09-28)

- **Symptom:** the preview shows a line under the headline that nobody wrote.
  On 2026-09-28: *"DoviLoop drafts replies to your client emails from what your
  business knows, in Outlook or Gmail. You press send. Free for 14 days, then €29
  per seat a month."*
- **Cause:** with no `description` on the creative, Meta pulls the destination
  page's meta description, which here includes a price.
- **Fix:** always set `description` explicitly, and run it through the claims gate
  like any other copy. `preview_destination.py` prints what the ad will show.

## The apex redirects

`https://doviloop.dev/` → 307 → `https://www.doviloop.dev/`. Put the `www` URL in
the ad so every paid click skips a hop.

## Upload paths

- `ads_creative_upload_media` with `upload_source: URL` is the path. On 2026-09-22
  it answered "gradually rolled out" for this account. If it still does, images
  can go straight into `image_url` on the creative, but video cannot.
- `LOCAL_FILE`, `ads_creative_upload_local_image` and
  `ads_finalize_local_ad_image_upload` drive an interactive upload app this CLI
  doesn't have. Don't use them.
- `ads_get_ad_preview_screenshot` is app-only. Don't call it.
- Video encodes asynchronously. Wait for ready before building the creative.

## Draft mode

`ads_create_ad` can stage the ad as a `DRAFT` instead of creating it `PAUSED`. A
draft publishes with `ads_activate_entity` + `object_ids`, and **publishing makes
it ACTIVE immediately**, so publishing a draft is the launch itself.

## The permission check blocks creating and launching ads (2026-09-28)

Claude Code's auto mode refused `ads_create_ad` as a real-world transaction. The
setup allowlists the build tools and leaves `ads_activate_entity` and
`ads_update_entity` behind a prompt, so launching always takes his tap. If a call
is still refused, name it and stop. Don't retry through a different tool.

## Retired ads - never reactivate

These point at `teams.doviloop.dev`, the landing page retired on 2026-09-28:
`120252098516600563` (v3-outlook), `120252098517200563` (v4-europe),
`120252098517410563` (v2-voice). They stay paused.

## Budget concentration

Meta puts well over half an ad set's spend on one ad. At DKK 35/day three ads is
already the ceiling. A fourth doesn't get tested, it just restarts learning.

## No pixel on the destination (2026-09-28)

`www.doviloop.dev` doesn't load pixel `1584074833462346`. Ads Manager shows
clicks, CPC, CPM, reach and frequency, but not landing page views or leads. Report
those as "not measured". Re-check with `scripts/verify_destination.py --pixel`.
