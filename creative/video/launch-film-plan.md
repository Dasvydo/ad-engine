# Launch-film plan: "The calm desk", v3's storyline turned into a real ad

Updated 2026-10-04, after the founder's direction: **keep v3's storyline, not its footage**, and make the pictures tell that story inside the house 8-beat structure.

Inputs:
- `DoviLoop_InboxSolved_v3.mp4` (Da Vinci + Seedance), in `flow-savvy-automations/video/sources/`;
- Tim Scheuer's LinkedIn post and video `wdZIE2jCPFg`;
- his kit, `github.com/timscheuerai/launch-video-kit` (MIT). I read its README through a summary and did not clone it.

Every line was checked against `claims/evidence.json`. Tags: **(verified)** checked today · **(estimate)** my arithmetic · **(unverified)** not checked.

## 1. What stays from v3, and what fails

**Stays: the story.** A broker is drowning in the same client questions. Her colleague at the next desk is suspiciously calm. She asks why, he shows her, she pushes back, he answers, she tries it. That is the right story, and it's v3's.

**Fails: how it's told** (verified from v3's frames):

| Problem | Where |
|---|---|
| The props change between cuts: there are ten regenerated shots of one two-person table | Silver laptop on the left at 0–2 s → dark MacBook facing camera at 15–16 s → centred at 18–20 s |
| It's told, not shown: two people talk at a table, and the pictures barely change | Whole film |
| The product is tiny and brief, so the climax is missing | Mock cards for 0.5–2.3 s |
| The hook is a generic office, and brokers are named last | "Brokers." at 20.7 s |
| Claims it can't make | "Free for 14 days" (`free_trial` UNVERIFIED, `evidence.json:187`), a fake "Approve" button, made-up counts |

## 2. Rules taken from Tim's post, video and kit

- **One body, swappable hooks.** Build the expensive part once.
- **One emotional register.** Here: envy plus humour, the "why are you so calm?" colleague.
- **Cut to the product on the music drop.**
- **Push into the one part of the screen the line names.** Never show the whole window small.
- **A deliberate look over cheap photoreal.**
- **Type lands on its word.**
- **Make a free version first, look at frames, then spend.**

## 3. The visual idea: a split screen that resolves

Frame 1 is the story with the sound off: **top half Anna, buried; bottom half Mark, coffee, calm.** Same office, same moment.

The ad ends when Anna's half looks like Mark's did: a visual rhyme. Everything between is the product, full frame, on the drop.

## 4. The script: 8 beats, about 31 s

Lines are sized at ~2.5 words/s, with no em dashes and no numbers. "AI" = a single-character shot from one locked still. "Code" = Remotion.

| # | Beat | s | Line | We see | We hear | Built | Claim |
|---|---|---|---|---|---|---|---|
| 1 | Hook | 0–2.5 | **Anna:** "Wait. Why is your inbox... done?" | Split. Top: identical client emails slam onto Anna's side ("What does my home insurance cover?"), she's frazzled. Bottom: Mark leans back, coffee. Line burned in big on frame 1 | pings stacking fast on top, quiet below | AI ×2 + code | none |
| 2 | Connector | 2.5–5 | **Mark:** "I stopped answering the same questions myself." | Mark shrugs, sips. Top half: the same question lands again. Ping | one ping, bed low | AI + code | dramatization, labelled |
| 3 | Beat the substitutes | 5–8.5 | **Anna:** "ChatGPT? I still paste our policies in every time." | Anna's half takes the frame: a sped-up copy-paste loop (policy, paste, price list, paste) | keyboard clatter, sped up | AI + code | none (her workflow) |
| 4 | Product intro | 8.5–12.5 | **Mark:** "Try DoviLoop. It's in your inbox and knows our stuff." | Mark spins his laptop toward camera → whip → **full frame, on the drop**: a client email arrives and the reply is already there, "[Draft] · not sent", in Outlook | whoosh, **music drop** | AI + code UI | `stays_in_outlook`, `own_knowledge_base` |
| 5 | Objection | 12.5–16.5 | **Anna:** "Generic AI replies?" **Mark:** "Our prices. Our policies. Your tone." | Push-in on the draft: the covered items light up with a source chip, "Home Basic policy"; the sign-off is hers | three soft hits, one per word | code UI | `own_knowledge_base`, `per_person_voice` |
| 6 | Proof + transformation | 16.5–20 | **Anna:** "So I just... check and send?" **Mark:** "Yep." | Her cursor changes one word and presses Send in Outlook. Split returns: **her half is now calm**, the pings stop | silence, then a clean send | code + AI | `never_auto_sends` |
| 7 | Colleague + proof | 20–24 | **Mark:** "One knowledge base. Everyone's own words." | Three drafts side by side, each signed by a different colleague, all linked to one knowledge-base chip | music lifts | code UI (real recording later) | `own_knowledge_base`, `per_person_voice` |
| 8 | Offer + CTA | 24–28 | **Anna**, to camera, calm, coffee now: "Brokers. See it on your own inbox." | She steps toward camera; the office behind her is calm | music resolves | AI | `offers.demo` |
| + | End card | 28–31 | none | Logo · "The inbox assistant that knows your business." · button "See it on your own inbox" · teams.doviloop.dev · small "Nothing sends until you read it." | sting | code | `offers.demo`, `never_auto_sends` |

- **Social proof:** there is none, because there are zero customers. The product is the proof (skill rule).
- **v3's "Works for the whole team":** replaced by beat 7's line, which says the same thing with only verified claims. "Whole team" is not in evidence.json.

## 5. Hooks that swap in front of the same body (beat 1 only)

| Hook | Register | Line |
|---|---|---|
| H1 | envy, curiosity | "Wait. Why is your inbox... done?" (above) |
| H2 | pain, humour, to camera | **Anna:** "If another client asks what's covered, I'm moving to Spain." |
| H3 | direct callout | **Mark**, to camera: "Brokers. Your clients keep asking the same things. Watch." |

Run them as one test: the hook is the only variable.

## 6. How it gets shot without the "flip"

1. **Singles, not two-shots.** One front-facing still each for Anna and Mark (v3's faces as reference). Every line is image-to-video from that still, start frame only, with native voice. Same still, same props, natural jump cuts.
2. **No screens in AI frames.** Every screen, caption, split and the end card are code.
3. **One look across both**: warm, filmic grade, shallow depth of field. Specific props: policy binders, not a stock glass office.
4. **Clips, merged per skill rule:**
   - Anna: (1) hook, (2) ChatGPT line, (3) "Generic AI replies?" + "check and send?" in one clip, cut in the edit, (4) CTA.
   - Mark: (1) tease + intro, (2) "Our prices…" + "Yep.", (3) knowledge-base line.
   - That's **7 clips**, about 700–900 Da Vinci credits at the skill's ~100–130 per Seedance Fast clip (estimate).
   - Higgsfield has 16.25 credits on the free plan, which isn't enough.
5. **Coded parts already exist**: the draft card, paste loop, send and end card in `flow-savvy-automations/video/src/compositions/ads/parts.tsx`. They need the split screen, kinetic captions and push-ins added.

**Free test first (Tim's kit rule):** an animatic of this exact structure, cut from v3's own clips cropped to faces in the split, plus the coded screens. That's $0 and about 1–2 h (estimate), and lets you judge pace and story before any credits.

## 7. Open decisions (yours)

1. Approve or edit the lines in §4. Next is skill step 3: the stills, then the Seedance prompts and upload map.
2. Which hook leads: H1, H2 or H3.
3. "ChatGPT" named, or "a chatbot".
4. Free animatic first, or straight to stills.

EN first. DA/LT need a native proofread (`CLAUDE.md`).
