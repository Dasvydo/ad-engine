# Launch-film plan: "Already written", v4 story draft

Updated 2026-10-04. Founder's direction: **v3's storyline is the direction, not the script.** Push the story further, then make the pictures tell it, inside the house 8-beat structure.

Inputs:
- `DoviLoop_InboxSolved_v3.mp4` (Da Vinci + Seedance), in `flow-savvy-automations/video/sources/`;
- Tim Scheuer's LinkedIn post and video `wdZIE2jCPFg`;
- his kit, `github.com/timscheuerai/launch-video-kit` (MIT). I read its README through a summary and did not clone it.

Every line was checked against `claims/evidence.json`. Tags: **(verified)** checked today · **(estimate)** my arithmetic · **(unverified)** not checked.

## 1. v3's story, line by line: what holds and what doesn't

| v3 line | Problem | v4 move |
|---|---|---|
| "Wait. Why is your inbox... done?" | Good curiosity. But "done" implies he's faster, a time-saving claim nobody has measured | Keep the curiosity, point it at what the product really does: replies **already written** |
| "I stopped answering the same questions myself." | Gives the premise away at once, with no tension | Mark explains *why* (same questions), not *what* |
| "ChatGPT? I still paste our policies in every time." | Good, a real substitute pain | Keep it, and give Mark a punchline: "Mine already knows them." |
| "Try DoviLoop. It's in your inbox and knows our stuff." | Reads like an ad, not like a colleague | "It's called DoviLoop. It lives in Outlook." Then show it |
| "Generic AI replies?" → "Our prices, our policies, your tone." | Answers with a feature list | Anna is sceptical ("sounds like a robot"). Mark: "Read it." Proof on screen |
| "So I just... check and send?" → "Yep." | Weak twist | Turn it into the buyer's real fear, auto-send, and answer it with "Nope" (`ICP-BRIEF.md:84`, buyer-stated) |
| "Works for the whole team. One knowledge base." | A feature recap. "Whole team" isn't in evidence.json | "Could it write like me?" → "It learns from your sent emails." Her own draft appears |
| "Brokers. Try it free for 14 days." | No such trial (`free_trial` UNVERIFIED) | "Brokers. See it on your own inbox." (`offers.demo`) |

**What changes overall:**
- Objections now come from Anna's scepticism, not from exposition.
- Every claim gets a moment on screen.
- The ending is her conversion, not a feature list.

## 2. Rules taken from Tim's post, video and kit

- **One body, swappable hooks.**
- **One emotional register.** Here: sceptical humour.
- **Cut to the product on the music drop.**
- **Push into the one part of the screen the line names.**
- **A deliberate look over cheap photoreal.**
- **Type lands on its word.**
- **A free version first, look at frames, then spend.**

## 3. Visual spine

Frame 1 is the story with the sound off: Anna **buried** (the same client question, pinging), Mark beside her **calm**, his drafts waiting.

The product takes the full frame on the drop. The last frame rhymes with the first: Anna now as calm as Mark was.

## 4. The script: 8 beats, about 33 s

Lines are sized at ~2.5 words/s, with no em dashes and no numbers.

| # | Beat | s | Line | We see | We hear | Built | Claim |
|---|---|---|---|---|---|---|---|
| 1 | Hook | 0–3 | **Anna:** "Wait. Why are your replies already written?" | Her screen: "Quick question: what does my policy actually cover?" lands again. She looks over: Mark sips coffee, his drafts waiting | ping, ping, ping | AI + code | drafts: product behaviour |
| 2 | Connector | 3–5.5 | **Mark:** "Because they're the same questions every day." | He shrugs. On her screen the same question stacks up, client after client | one more ping | AI + code | none |
| 3 | Beat the substitutes | 5.5–10 | **Anna:** "ChatGPT? I still paste our policies in every time." **Mark:** "Mine already knows them." | A sped-up copy-paste loop on her side. Mark taps his temple | keyboard clatter, then a beat of silence | AI + code | `own_knowledge_base` |
| 4 | Product intro | 10–14 | **Mark:** "It's called DoviLoop. It lives in Outlook." | He turns his screen → **full frame, on the drop**: a client email arrives and the reply is already there, "[Draft] · not sent" | **music drop** | AI + code UI | `stays_in_outlook` |
| 5 | Objection | 14–18.5 | **Anna:** "AI replies always sound like a robot." **Mark:** "Read it. Our policy. My words." | Push-in: the covered items light up with their source, "Home Basic policy"; then his sign-off | two soft hits | code UI | `own_knowledge_base`, `per_person_voice` |
| 6 | Twist: the real fear | 18.5–23 | **Anna:** "And it just sends that?" **Mark:** "Nope. Nothing goes out until I read it." | He changes a word, then presses Send himself | silence, then a clean send | code + AI | `never_auto_sends` |
| 7 | Proof, for her | 23–27.5 | **Anna:** "Could it write like me?" **Mark:** "It learns from your sent emails." | The same question, now a draft in *her* style, signed Anna | music lifts | code UI | `per_person_voice` (evidence: voice profile built from each person's sent mail) |
| 8 | Offer + CTA | 27.5–30.5 | **Anna**, to camera, coffee now: "Brokers. See it on your own inbox." | Calm. A visual rhyme with Mark in frame 1 | music resolves | AI | `offers.demo` |
| + | End card | 30.5–33.5 | none | Logo · "The inbox assistant that knows your business." · button "See it on your own inbox" · teams.doviloop.dev · small "Nothing sends until you read it." | sting | code | `offers.demo`, `never_auto_sends` |

Social proof: there is none, because there are zero customers. The product moments are the proof (skill rule).

## 5. Hook modules (beats 1–2 swap; beats 3–8 stay identical)

| Hook | Register | Lines |
|---|---|---|
| H1 | curiosity | as above |
| H2 | humour, to camera | **Anna:** "If another client asks what's covered, I'm moving to Spain." **Mark**, off screen: "Or stop typing the same answers." |

Run the hooks as one test: the hook is the only variable.

## 6. How it gets shot without the "flip"

1. **Singles, not two-shots.** One front-facing still each for Anna and Mark (v3's faces as reference). Every clip is image-to-video from that still, start frame only, with native voice.
2. **No screens in AI frames.** Screens, captions and the end card are code (`flow-savvy-automations/video/src/compositions/ads/parts.tsx` has the draft card, send and end card already).
3. **One look**: a warm, filmic grade. Broker props, such as policy binders.
4. **Clips**, with adjacent lines merged per skill rule and cut in the edit:
   - Anna: (1) hook, (2) ChatGPT line, (3) the robot, sends-that and write-like-me lines in one clip, (4) CTA.
   - Mark: (1) same-questions + knows-them, (2) DoviLoop + read-it, (3) nope + learns.
   - That's **7 clips**, about 700–900 Da Vinci credits at the skill's ~100–130 per Seedance Fast clip (estimate).

## 7. Open decisions (yours)

1. Tone: this draft is sceptical humour. Push funnier, more dramatic or more serious?
2. Which hook leads: H1 or H2.
3. "ChatGPT" named, or "a chatbot".
4. Then skill step 3: the stills, the Seedance prompts and the upload map.

EN first. DA/LT need a native proofread (`CLAUDE.md`).
