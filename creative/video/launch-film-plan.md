# Launch-film plan: InboxSolved, restructured

Written 2026-10-04. Three inputs:
- the founder's `DoviLoop_InboxSolved_v3.mp4`, made with Da Vinci + Seedance and now at `flow-savvy-automations/video/sources/`;
- Tim Scheuer's LinkedIn post and his YouTube video `wdZIE2jCPFg` (transcript pasted 2026-10-04);
- the kit that video points to, `github.com/timscheuerai/launch-video-kit` (MIT). I read its README through a summary and did not clone it.

The structure is the house 8-beat structure from the `doviloop-video-ad` skill. Every line was checked against `claims/evidence.json`.

Tags: **(verified)** checked in a file or a frame today · **(estimate)** my arithmetic · **(unverified)** not checked.

## 1. What is wrong with v3 (verified, from its frames)

| Problem | Where in v3 | Why it reads generic |
|---|---|---|
| **The props change between cuts** | 0–2 s: an open silver laptop at the left, screen facing camera. 15–16 s: a dark MacBook, logo facing camera, in front of Anna. 18–20 s: that MacBook moves to the centre. 9–11 s: Mark points at a third laptop | There are ten regenerated shots of one two-person table, so every difference reads as an error. This is the "computers flip" |
| **Two AI voices in dialogue** | The whole film | Lip-sync drifts and the scene has to be regenerated for every line. The kit's rule is one narrator for the whole film |
| **Cheap photoreal stock office** | Every AI shot | Nothing says insurance broker, Denmark or Lithuania. The kit says stylised beats cheap photoreal, and Tim makes his AI footage look deliberate with a vintage grade |
| **The product is tiny and brief** | Mock cards for 0.5 s, 1.6 s, 2.3 s and 1.2 s | A whole window at thumbnail size says nothing. Push into the one part the voice names |
| **The dialogue explains instead of showing** | "It's in your inbox and knows our stuff" | Features are talked about. There's no moment and no tension |
| **The audience is named last** | "Brokers." at 20.7 s | A broker should know the ad is for them in the first second |
| **It makes claims it can't back** | "Try it free for 14 days", an "Approve ✓" button that doesn't exist, "Quotes 13 / Claims 8" | `free_trial` is UNVERIFIED (`evidence.json:187`) |

My earlier rebuild (`flow-savvy-automations` `0f4965d`) fixed only the last row. The generic look needs new footage and a new structure.

## 2. What the two sources say, combined

| Rule | Source |
|---|---|
| Build one body and many hooks. The motion graphics are the slow part, so build them once | Video 00:07:29 · kit's hook-plus-body template |
| Use one emotional register per hook: pain, nostalgia or humour | Video 00:06:12, 00:06:46, 00:07:15 |
| Hook, then cut to the brand **on the music drop**, then the body | Kit README (summary) |
| Body beats: `name` (logo punches in on the drop, tagline writes on), `hero` (full-frame words), `product` (real screen, camera pushes in), `blocks` (features land, then close into one), `switch` (a card that turns), `end` (lockup) | Kit README (summary) |
| One narrator. A second voice breaks it | Kit README (summary) |
| Stylised over cheap photoreal. A consistent visual signature | Kit · video 00:06:20, 00:07:07 |
| Type lands on its word | Kit README (summary) |
| Make the first version type-only and free. Swap in real voice and footage once the story works | Kit README (summary) |
| Show frames before a full render | Kit README (summary) |
| 30–60 s | Kit README (summary) |

## 3. The structure: three hook modules, one fixed body, about 38 s

The 8 beats from `doviloop-video-ad`, mapped onto the kit's beat types. Beats 1–3 change per hook. Beats 4–8 are built once.

| # | Beat (your skill) | Kit beat | s | Narrator line, sized at ~2.5 words/s | On screen | Built with | Claim |
|---|---|---|---|---|---|---|---|
| 1 | Hook with pain | hook | 4–5 | per hook module, §4 | stylised AI shot | Seedance / Higgsfield | none |
| 2 | Connector | hero | 3 | per hook module | full-frame type | code | none |
| 3 | Beat the substitutes | switch | 4 | per hook module | card: "Paste your policies into a chatbot. Again." | code | none |
| — | the drop | | | | music drop, cut | | |
| 4 | Product intro | name | 3 | "Meet DoviLoop. The inbox assistant that knows your business." | logo punches in, tagline writes on | code | `own_knowledge_base` |
| 5 | Objection: "generic AI" | product | 7 | "A client asks what's covered. The reply is already drafted, in Outlook, from your own policies." | real draft in Outlook. Camera pushes into the grounded sentence and its source | real screen + code camera | `stays_in_outlook`, `own_knowledge_base` |
| 6 | Proof + transformation | product | 5 | "In your own words. And if it doesn't know, it asks you." | draft → the Needs-you question | real screen + code | `per_person_voice`. **"it asks you": not in evidence.json** ⚠️ |
| 7 | Colleague + proof | blocks | 4 | "Inside Outlook. On European servers. Grounded in your documents." | four blocks land on their words, then close into one | code | `stays_in_outlook`, `eu_hosted`, `own_knowledge_base` |
| 7b | (control) | switch | 3 | "Nothing sends until you read it." | card turns: "Nothing sends" → "until you read it" | code | `never_auto_sends` (exact safe phrasing) |
| 8 | Offer + CTA | end | 4 | "Brokers, see it on your own inbox." | lockup, button, teams.doviloop.dev | code | `offers.demo` |

- **Beat 6, social proof:** there is none, because there are zero customers. The product screen is the proof (skill rule).
- **Beat 7, "UGC colleague":** shown, not voiced. A second voice breaks the one-narrator rule.
- **End card:** add "Design-partner terms for the first firms in" if you want urgency (`offers.design_partner`, verified).

## 4. Three hook modules (beats 1–3), one register each

All claim-free: they're story premises, not product claims, and contain no numbers. Number words count too (`attestations` in evidence.json).

**H1 Pain, "Same question"**
- Shot: a broker's desk at dusk, letters stacking up as a metaphor. No screens.
- Type overlay: "What does my home insurance actually cover?", repeating.
- Narrator:
  - "Brokers. You've answered this one more times than you can count."
  - "Same question. Same answer. Every day."
  - "And the chatbot? It doesn't know your policies. So you paste them in. Again."

**H2 Nostalgia, "Back in the day"** (Tim's vintage register)
- Shot: a 1970s insurance office, a broker pulling a paper file. Grainy, warm.
- Narrator:
  - "Remember when a client question meant pulling the paper file?"
  - "It still does. The file just moved into your inbox."
  - "And no chatbot has read it."

**H3 Humour, "On holiday"**
- Shot: an empty chair, a "Back Monday" note on the screen bezel (the screen is off), a cold coffee.
- Narrator:
  - "Every brokerage has that colleague who knows every policy by heart."
  - "This week, she's on holiday."
  - "So everyone else is guessing. Or pasting policies into a chatbot."

Testing: run one variable per test (`CLAUDE.md`, "one variable per test"). The three hooks are the variable; the body stays identical.

## 5. Shooting rules that stop the "flip"

1. Two AI shots per hook module at most, and none in the body. v3 had ten of the same setup.
2. **No screens in AI frames** (skill rule). If a laptop must appear, it's closed, the same model, named in every prompt, and comes from the same start still.
3. Image-to-video from **one start still per setup**. Every cut of that setup starts from it.
4. Apply one look to every shot, e.g. "16 mm film, warm grade, soft grain". This makes AI footage look deliberate and hides small artifacts.
5. No lip-sync. The narrator sits on top, so nobody on screen has to talk.
6. Text, captions and UI are always code, never generated.

## 6. Order of work, costed in your time

| Step | What | Cost |
|---|---|---|
| 1 | Type-only body plus hook H1 as type, scratch narrator (edge-tts, as reel-engine uses) and a scratch bed, in Remotion (`flow-savvy-automations/video`, already set up). Stills first, then render | $0, about half a day (estimate) |
| 2 | Watch it. Fix the story. Only then spend credits | — |
| 3 | AI shots for the hooks: up to 2 per module, 6 in total | Your skill's figure: ~100–130 Da Vinci credits per Seedance Fast clip, so about 600–800 for 6 (estimate). Higgsfield is on the free plan with 16.25 credits, which isn't enough |
| 4 | One real narrator, music with a drop at the hook → body cut, mix | — |
| 5 | Export 9:16, plus 4:5 or 1:1 | minutes |

The product beats need a **broker** sample tenant recorded on screen. The final demo is a SaaS sample ("€49/month") and would read as DoviLoop's price. Until there's a broker recording, the coded broker screens in `flow-savvy-automations/video/src/compositions/ads/parts.tsx` stand in.

Tim's kit could do steps 1 and 4: brand from URL, word-aligned type, free audio path. It would also be a third renderer next to reel-engine and Remotion. My call: borrow its beat types and rules, and build in Remotion.

## 7. Open decisions (yours)

1. Which hook to build first: H1, H2 or H3.
2. "And if it doesn't know, it asks you." The Needs-you loop exists in the product and is shown in your own demo, but it isn't in `evidence.json`. Add an entry, or cut the line.
3. "Chatbot" or "ChatGPT". Your skill's default names ChatGPT; this plan uses the generic word.
4. EN first. DA/LT need a native proofread (`CLAUDE.md`).
