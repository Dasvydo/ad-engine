# Video for ads: a cutting spec, not a shoot

**No separate ad video gets shot.** The spec is explicit about this and it is the
right call at this budget: three weekly English reel masters already exist in
`reel-engine`, they are already on brand, and paying to produce parallel ad
footage for a campaign spending under EUR 500 a month would cost more than the
media.

So the ad video is a **cut**, not a production. Every week, the three English
masters from Batch D get trimmed to 15 seconds with a harder call to action and
exported at 9:16 and 1:1.

This document is that cutting spec. It is written to be executed by whoever
holds Batch D's masters, because this repo does not have them.

> **Not executed here.** `ffmpeg` is not installed in this session and Batch D's
> masters do not exist in this repo, so none of the commands below were run.
> They are written against the standard filter syntax and the file naming Batch
> D uses. Treat them as a recipe to check once, not as verified output. Logged
> in BLOCKED.md.

---

## What comes out

Per weekly master, two files:

```
creative/video/out/<master-id>-ad15-9x16.mp4    1080 x 1920, 15s
creative/video/out/<master-id>-ad15-1x1.mp4     1080 x 1080, 15s
```

Three masters a week means six ad cuts a week. That is more creative than a
EUR 500 budget can read, which is fine: rotate two at a time and keep the rest
in the library. See `campaigns/structure.md` for why more creative than the
budget can measure is a trap rather than an advantage.

Skip 4:5 for video. Meta will letterbox 9:16 into the feed and 1:1 covers the
feed placement properly, so a third export buys nothing.

---

## The 15 second structure

A reel master is built to hold attention for 30 to 60 seconds and earn a follow.
An ad has to earn a click from someone who was scrolling past. Same footage,
different job, so the cut is not simply the first 15 seconds of the master.

| Seconds | What is on screen | Why |
|---|---|---|
| 0.0 to 2.0 | **The hook, hard cut in.** No logo, no build up, no establishing shot. Start on the strongest sentence in the master, even if it sits at 0:22 in the original. | This is retargeting, so the viewer has met DoviLoop before. They do not need an introduction, they need a reason to go back. |
| 2.0 to 6.0 | **The objection, named.** One line from `research/objections.md`. The one this cut is for. | An ad that names the thing the viewer was privately worried about outperforms an ad that lists features. |
| 6.0 to 11.5 | **The proof.** The screen recording beat from the master: an Outlook drafts folder, a real subject line, a draft opening. | The brand lock prefers concrete real content over abstract AI visuals. The drafts folder is the product. |
| 11.5 to 15.0 | **The hard CTA and end card.** | See below. |

Two rules that matter more than the timings:

1. **Cut on the sentence, not on the clock.** If the proof beat lands at 11.8
   seconds, let the CTA run 3.2 seconds. Never clip a word to hit 15.0.
2. **The first frame has to work with the sound off.** Most of these plays are
   silent. Burn the hook line in as a caption on frame one.

---

## The harder CTA

The reel masters end soft, because a reel is asking for attention and a follow.
An ad is asking for a click, and the retargeting audience has already had the
soft version.

| | Reel master ending | Ad cut ending |
|---|---|---|
| Line | "More at doviloop.dev" | "Book a call. Two weeks, set up by us." |
| Duration | 2 to 3 seconds | 3.5 seconds, held |
| Card | Wordmark, calm | End card from the static renderer, one amber word |
| Ask | Implicit | Explicit and singular |

Only one ask. No "follow us and book a call".

### End card

Reuse the static pipeline instead of designing a second system. Render the end
card at video size with the same fonts, hex and amber discipline:

```bash
# a 9:16 end card, using the same typeset layer as the statics
python -m creative.static.render s05-two-weeks --ratio 4x5
# then pad 1080x1350 to 1080x1920 on the brand cream, or add a 9:16 entry
# to RATIOS in creative/static/render.py, which is a two line change
```

The end card must carry the wordmark and must not carry a button. A button on a
video frame is not tappable and the brand lock forbids it on statics for the
same reason.

---

## The three cuts, and which objection each carries

Batch D produces one master per lane per week (Higgsfield, HyperFrames, Dovy on
camera). Assign objections rather than letting all three carry the same message:

| Lane | Objection it carries | Hook line to cut to at 0:00 |
|---|---|---|
| Dovy on camera | 5, what happens if it does not work out | "Two weeks. We set it up. Then you decide." |
| Screen recording lane | 3, we are not moving out of Outlook | "There is no second screen. It is your drafts folder." |
| Third lane | 1, it will send something wrong | "Nothing goes out until someone reads it. Reading it takes four seconds." |

Objections 2 and 4 stay with the statics. Five objections across three weekly
cuts would spread the spend too thin to read anything.

---

## The commands

Written for whoever has the masters. Adjust the in-points per master.

```bash
# 1. Cut the 15 second edit from the master, keeping the audio in sync.
#    -ss before -i seeks fast; re-encode because a copy cut lands on a keyframe.
ffmpeg -ss 00:00:22.4 -i master.mp4 -t 15 \
  -c:v libx264 -crf 18 -preset slow -c:a aac -b:a 128k \
  cut15.mp4

# 2. 9:16, from a 16:9 or 9:16 master. Cover, never stretch.
ffmpeg -i cut15.mp4 -vf \
  "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1" \
  -c:v libx264 -crf 20 -preset slow -pix_fmt yuv420p -c:a aac -b:a 128k \
  -movflags +faststart out-ad15-9x16.mp4

# 3. 1:1.
ffmpeg -i cut15.mp4 -vf \
  "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080,setsar=1" \
  -c:v libx264 -crf 20 -preset slow -pix_fmt yuv420p -c:a aac -b:a 128k \
  -movflags +faststart out-ad15-1x1.mp4

# 4. Append the end card as a 3.5 second still, matching the video's fps.
ffmpeg -loop 1 -t 3.5 -i endcard-9x16.png -f lavfi -t 3.5 -i anullsrc \
  -c:v libx264 -crf 20 -pix_fmt yuv420p -r 30 -c:a aac endcard.mp4
ffmpeg -f concat -safe 0 -i list.txt -c copy final-ad15-9x16.mp4
```

If step 4 fails on a stream mismatch, the usual cause is a different fps or
sample rate between the cut and the end card. Re-encode both to 30fps and 48kHz
rather than trying to concat with `-c copy`.

---

## Safe zones, because Meta crops

- **9:16:** keep every burned-in caption inside the middle 1080 x 1420. Meta's
  UI covers roughly 250px at the top and 250px at the bottom in Reels
  placements, and a caption that lands under the CTA bar is a caption nobody
  reads.
- **1:1:** keep type 90px in from every edge, matching the static padding.
- Burn captions in. Do not rely on Meta's auto captions for an ad, they are
  generated per viewer and can miss on accented Danish and Lithuanian names even
  when the audio is English.

---

## Naming, so reporting can join back

`report/pull_ad_stats.py` joins spend back to creative through
`utm_content`, and Meta's ad name is what the export shows. Use the same id in
all three places:

```
ad name in Ads Manager   teams_q4 | v5-pilot | dovy-cam-ad15-9x16
utm_content              v5-pilot
file                     dovy-cam-ad15-9x16.mp4
```

If the ad name and `utm_content` drift apart, the report still runs and the
numbers are still right, but nobody can tell which cut earned them, which is the
only thing this campaign is actually buying.
