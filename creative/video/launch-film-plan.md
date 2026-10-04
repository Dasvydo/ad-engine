# Launch-film plan: "Already written", v5 script

Updated 2026-10-04. Founder's direction, in order:
1. v3's storyline is the direction, not the script.
2. Make it more intense and dramatic.
3. Merge it with the founder's reference script, which he liked: keep its staging and most of its lines, and make the logic hold.
4. **Not broker-only**: any team that answers the same client emails, showing how seamless DoviLoop is.

Earlier inputs:
- `DoviLoop_InboxSolved_v3.mp4`, in `flow-savvy-automations/video/sources/`;
- Tim Scheuer's post and video `wdZIE2jCPFg`;
- his kit, `github.com/timscheuerai/launch-video-kit` (MIT). I read its README through a summary and did not clone it.

Every spoken line was checked against `claims/evidence.json`.

## 1. What was merged, and why

| From | Kept | Changed, and why |
|---|---|---|
| Founder's reference script | The staging of every beat; the lines in beats 2–6; the CTA line; the "realization lands" moment | **Beat 7 logic:** Anna's own drafts appeared *before* she asked "Could it write like me?" and before she had DoviLoop. Now it's question → answer → time cut → her inbox |
| | | "A hundred times" → "too many times". A number in an ad line needs evidence (`attestations`) |
| | | End card "AI-powered replies" → **"AI-drafted replies"**, so the "nothing sends on its own" promise survives the tagline |
| | | It had no offer. Added the verified one: "See it on your own inbox" (`offers.demo`) |
| v4 draft | "Already written" curiosity hook, "Nope" twist, "It learns from your sent emails" | — |
| v3 | The colleague at the next desk; the coffee | The coffee becomes a visual rhyme: Mark's in frame 1, Anna's in the last shot |
| Generalising | — | The recurring client question is **"which documents do you need from me?"**. It reads true for accounting, back-office and insurance alike. No "Brokers" line, no insurance props |

## 2. Where the intensity comes from

- **Sound arc:** pings pile up with a ticking clock → **hard silence** when Anna sees Mark's screen → **music drop** on the product → silence again while the cursor hovers over Send → release on the click → swell at her realization.
- **Camera arc:** tight handheld chaos → still, calm Mark → whip into a full-frame product → slow push-ins → a macro on the cursor → Anna turns to camera.
- **Rhythm:** shots of 1.5 s or less in beat 1; drafts landing *on the beat* in beat 4; a held pause in beat 6.
- **Visual rhyme:** the calm coffee moves from Mark to Anna.

## 3. The script: 8 beats, about 50 s

AI shots are singles from one locked still per character, with no screens in frame. Every screen, caption and the end card are code. The "AI-generated dramatization" label goes on every AI shot.

### 1. HOOK, 0–4 s
Tight and handheld. Anna digs through old emails, opens a document, copies, starts typing.
PING: the same client question lands again: *"Quick question: which documents do you need from me?"* PING. PING. The pings pile up. A clock ticks.
She glances right. **Hard silence.** Mark, coffee in hand. On his screen the same question has just landed, and the reply is already written.
> **ANNA:** "Wait. Why is your reply already written?"

### 2. CONNECTOR, 4–10 s
Mark takes another sip.
> **MARK:** "Because I've answered it too many times."
> **ANNA:** "And you don't start from scratch?"
> **MARK:** "Not anymore."

### 3. SUBSTITUTES, 10–15.5 s
> **ANNA** (eyes on his screen): "ChatGPT?"
> **MARK:** "No."
> **ANNA:** "So no pasting all the context in?"
> **MARK:** "It already knows it."

Anna leans in.

### 4. PRODUCT, 15.5–23 s
Mark turns his screen toward her.
> **MARK:** "It's DoviLoop. It lives right inside Outlook."

**MUSIC DROP.** Whip into a full-frame product sequence (code): an email lands and the draft appears underneath it. Another email, another draft. Each lands on the beat. Effortless.

### 5. OBJECTION, 23–29.5 s
> **ANNA:** "Okay, but AI replies always sound like a robot."
> **MARK:** "Read it."

Slow push-in on the draft: the right details from the company's own documents, natural wording, Mark's usual sign-off.
> **ANNA** (quietly): "That actually sounds like you."

### 6. TWIST, 29.5–36 s
> **ANNA** (pointing at Send): "And it just sends it?"
> **MARK:** "Nope."

Macro: the cursor hovers over Send. Hold. **Silence.**
> **MARK:** "Nothing goes out until I read it."

He changes one word. Click. Sent.

### 7. PROOF, 36–44 s
> **ANNA:** "Could it write like me?"
> **MARK:** "It learns from your sent emails."

Time cut, morning light, no caption. Anna's own inbox. An email lands. Before she types, a draft appears under it: her phrasing, her tone, her sign-off. Slow push on her face. The realization lands. She reads it and sends.

### 8. CTA, 44–48 s
Anna picks up her coffee, Mark's move from beat 1, and turns to camera.
> **ANNA:** "Maybe it's time to stop answering the same questions from scratch."

### END CARD, 48–51 s
**DoviLoop** · *AI-drafted replies, right where you work.* · button **See it on your own inbox** · **teams.doviloop.dev** · small: "Nothing sends until you read it."

## 4. Claims check, every spoken or printed line

| Line | Key |
|---|---|
| "…your reply already written?" / "Not anymore." | drafts are written to the Outlook drafts folder (`never_auto_sends` evidence) |
| "It already knows it." | `own_knowledge_base` |
| "It lives right inside Outlook." / "right where you work" | `stays_in_outlook` |
| "That actually sounds like you." / "It learns from your sent emails." | `per_person_voice` (voice profile built from each person's sent mail) |
| "Nothing goes out until I read it." / "Nothing sends until you read it." | `never_auto_sends` |
| "See it on your own inbox" | `offers.demo` |
| "ChatGPT?" "No." | not a claim about ChatGPT. **Your call** whether to name the brand |

No numbers, no free trial, no price, and no team claim.

## 5. Variants

- **Cold-open hook (beat 1 swap):** black screen, a single ping, then a flood of them. Type on screen: *"Same question. Again."* Anna, under her breath: "Not again." Then her glance and the hard silence, as above.
- **30 s cut:** beats 1, 4, 5, 6, 8 and the end card.
- **15 s retargeting cut:** beat 6 plus the end card (`creative/video/cut-spec.md` structure).

## 6. Production

- **AI clips:** singles only, one locked still each for Anna and Mark, image-to-video start frame, native voice per line. About 10–12 clips, merging adjacent lines per skill rule. That's about 1,000–1,500 Da Vinci credits at the skill's ~100–130 per Seedance Fast clip (estimate).
- **Code:** the product sequence, the pings and the clock, captions, the cursor macro and the end card. Starting points are in `flow-savvy-automations/video/src/compositions/ads/parts.tsx`.
- **Next (skill step 3):** the two locked stills, then the Seedance prompts and upload map.

EN first. DA/LT need a native proofread (`CLAUDE.md`).
