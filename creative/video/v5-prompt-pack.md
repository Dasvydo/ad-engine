# v5 "Already written": photo prompts, Seedance clip prompts, upload map

Script: `launch-film-plan.md` (v5). This pack covers skill steps 3–5 of `doviloop-video-ad`; step 6 is the edit, which I do once the clips come back.

Rules followed:
- **Characters** are always filmed alone, one locked photo each.
- **Every clip** starts from a photo (image-to-video, start frame only), with the character's own voice.
- **No screen** is ever generated. Every screen, caption, ping, cursor and the end card are built in code.
- **No negative prompt** (Seedance rule).
- **Prompt style:** one flowing present-tense paragraph, props named, one motion per clip.

## 0. Order of work

1. Make the 3 photos (§2) and check faces and props. **Stop and fix here.** Every clip inherits them.
2. Test clip **A1** on the cheapest model first.
3. Generate the rest in priority order (§5).
4. Send me the clips. I cut them, add the coded screens, captions, the "AI-generated dramatization" label and sound.

## 1. Locked anchors: paste exactly, every time

**Anna:** a woman in her late thirties with a straight, shoulder-length blonde bob, wearing a camel-brown chunky knit crew-neck sweater over a white collared shirt, with small gold hoop earrings.

**Mark:** a man in his late thirties with short tousled ginger hair and a short ginger beard, wearing a navy button-up overshirt over a charcoal t-shirt.

**Anna's voice:** "Her voice: a woman in her late thirties, warm and clear, slightly low, natural conversational pace, light Northern European accent in English."

**Mark's voice:** "His voice: a man in his late thirties, calm, warm, unhurried baritone, light Northern European accent in English."

**The look, afternoon** (beats 1–7a): "Modern Scandinavian office, late-afternoon light through tall windows, warm desk lamps, colleagues softly out of focus, 35mm film look, subtle grain, natural skin tones."

**The look, morning** (beats 7b–8): "The same modern Scandinavian office, early morning, soft cool window light, calm and quiet, 35mm film look, subtle grain, natural skin tones."

**Face references** (`refs/`, cropped from v3):

| File | Use |
|---|---|
| `ref_anna_threequarter.png` | Anna looking right, for S1 |
| `ref_anna_front.png` | Anna facing the camera, for S3 |
| `ref_mark_threequarter.png` | Mark looking left, for S2 |
| `ref_mark_front.png` | Mark's face, as a second reference |

## 2. Photos (Da Vinci Image, 9:16, attach the face reference)

**S1 `still_anna_desk.png`** (attach `ref_anna_threequarter.png`)
> Vertical 9:16 photograph. Eye-level medium close-up of Anna, [ANNA ANCHOR], seated at her office desk, body turned three-quarters toward the right of frame as if a colleague sits just out of frame right, eyes looking off-camera right, a slight stressed frown. Her open laptop sits low in the left of frame with its silver back toward the camera, so its screen is not visible; a printed document and a pen beside it. [AFTERNOON LOOK] Photorealistic, unretouched skin, no text, no logos, no visible screens.

**S2 `still_mark_desk.png`** (attach `ref_mark_threequarter.png` and `ref_mark_front.png`)
> Vertical 9:16 photograph. Eye-level medium close-up of Mark, [MARK ANCHOR], seated at the neighbouring desk, leaning back slightly, body turned three-quarters toward the left of frame as if a colleague sits just out of frame left, eyes looking off-camera left, a calm, faintly knowing half-smile. He holds one white ceramic coffee mug in his right hand at chest height. His open laptop sits low in the right of frame with its silver back toward the camera, so its screen is not visible. [AFTERNOON LOOK] Photorealistic, unretouched skin, no text, no logos, no visible screens.

**S3 `still_anna_front.png`** (attach `ref_anna_front.png`)
> Vertical 9:16 photograph. Eye-level medium shot of Anna, [ANNA ANCHOR], standing in the office facing the camera directly, holding one white ceramic coffee mug in her right hand at chest height, relaxed confident half-smile, eye contact with the lens. A tidy desk and a colleague softly out of focus behind her. [MORNING LOOK] Photorealistic, unretouched skin, no text, no logos, no visible screens.

**Optional:**
- **S4 `still_anna_morning.png`:** S1's prompt with the morning look, a calm expression and a fresh coffee mug on the desk. It's only for A6; otherwise reuse S1 and I grade it cooler in the edit.
- **S5 `still_anna_hands.png`:** side close-up of Anna's hands on a laptop keyboard, camel knit sleeves, the screen angled away and out of frame, a printed document beside the keyboard. [AFTERNOON LOOK]

## 3. Clip templates (Seedance, image-to-video, start frame only)

Fill in `[MOOD]` and `[LINE]` from §4. Everything else stays word for word.

**T-ANNA-DESK** (start image S1, or S4 for A6)
> Eye-level medium close-up, locked-off camera with a barely perceptible handheld float. Anna, [ANNA ANCHOR], sits at her office desk turned three-quarters toward a colleague just out of frame right; her laptop's silver back faces the camera and its screen is never visible. [MOOD] She looks off-camera right and says: [LINE] Her lips sync exactly to each word, with natural jaw movement and natural blinking. [ANNA VOICE] [AFTERNOON LOOK] Steady background, natural hands, the laptop stays where it is, no captions, no on-screen text, no music, only her voice and quiet office ambience.

**T-MARK-DESK** (start image S2)
> Eye-level medium close-up, locked-off camera with a barely perceptible handheld float. Mark, [MARK ANCHOR], sits relaxed at the next desk turned three-quarters toward a colleague just out of frame left, holding one white ceramic coffee mug in his right hand; his laptop's silver back faces the camera and its screen is never visible. [MOOD] He looks off-camera left and says: [LINE] His lips sync exactly to each word, with natural jaw movement and natural blinking. [MARK VOICE] [AFTERNOON LOOK] Steady background, natural hands, the same single mug stays in his hand, no captions, no on-screen text, no music, only his voice and quiet office ambience.

**T-ANNA-CAMERA** (start image S3)
> Eye-level medium shot, direct to camera, casual and unposed. Anna, [ANNA ANCHOR], stands in the office holding one white ceramic coffee mug at chest height. [MOOD] She looks straight into the lens and says: [LINE] Her lips sync exactly to each word, with natural jaw movement and natural blinking. [ANNA VOICE] [MORNING LOOK] Steady background, natural hands, the same single mug stays in her hand, no captions, no on-screen text, no music, only her voice and quiet office ambience.

## 4. Line and mood table

The words are sized at about 2.5 words per second. Lines with a pause between them are cut apart in the edit.

| Clip | Beat | Template | [MOOD] | [LINE] | s |
|---|---|---|---|---|---|
| **A1** | 1 hook | ANNA-DESK | She types fast and frantically, stops dead when something off-camera right catches her eye, freezes, then slowly turns her head right in disbelief. | "Wait. Why is your reply already written?" | 8 |
| M1 | 1–2 | MARK-DESK | Unbothered. He takes a slow sip of coffee, lowers the mug back to chest height, then answers with a wry half-smile. | "Because I've answered it too many times." | 7 |
| A2 | 2–3 | ANNA-DESK | Curious, half-hopeful. | "And you don't start from scratch?" Then she pauses, listening, glances toward his screen off-camera right and asks: "ChatGPT?" | 6 |
| M2 | 2–3 | MARK-DESK | Calm and amused, short answers with small listening pauses between them. | "Not anymore." He pauses, listening. "No." He pauses again, then: "It already knows it." | 7 |
| A3 | 3 | ANNA-DESK | Intrigued. She leans slightly toward the right. | "So no pasting all the context in?" | 5 |
| **M3** | 4 product | MARK-DESK | Quietly proud. While he speaks, his free left hand swivels the laptop toward the colleague off-camera left; the lid turns so only its back is ever toward the camera. He pronounces DoviLoop "doh-vee-loop". | "It's DoviLoop. It lives right inside Outlook." Then, nodding at the laptop: "Read it." | 8 |
| **A4** | 5 objection | ANNA-DESK | Sceptical at first; after the first line she reads something off-camera right and her face softens into surprise. | "Okay, but AI replies always sound like a robot." Then she reads, softens, and says quietly: "That actually sounds like you." | 8 |
| A5 | 6–7 | ANNA-DESK | Wary, then hopeful. She nods toward his screen with her chin; her hands stay on the desk. | "And it just sends it?" Then she pauses, listening, and asks: "Could it write like me?" | 7 |
| M4 | 6 twist | MARK-DESK | Matter-of-fact, reassuring. After "Nope." his free left hand rests near the laptop's trackpad. | "Nope." He pauses, then: "Nothing goes out until I read it." | 6 |
| M5 | 7 | MARK-DESK | Warm and knowing. He answers, then takes a small sip. | "It learns from your sent emails." | 5 |
| A6 | 7 realization | ANNA-DESK (S4) | No dialogue. Early morning, calm. She reads her screen, its back to the camera; her eyebrows lift, then a slow small smile of realization, and she taps the trackpad once. | none (ambience only) | 5 |
| **A7** | 8 CTA | ANNA-CAMERA | Calm, confident, warm, as if letting the viewer in on something. | "Maybe it's time to stop answering the same questions from scratch." | 6 |
| I1 | 1 insert (optional) | S5, no template | Close-up: her hands type fast, then stop abruptly mid-word. No dialogue, no screen visible. | none | 4 |

Two changes from the script, both to reduce risk:
- **A5:** Anna nods at the Send button instead of pointing at it, because pointing hands are where generations break.
- **M3:** the laptop turn. If it shows the screen, I'll cut on the start of the turn and whip-pan into the coded product.

## 5. Upload map and credit plan

| Clip | Da Vinci tab | Start image | End image | Prompt box | Settings |
|---|---|---|---|---|---|
| A1 Hook | Video → Create Video | `still_anna_desk.png` | empty | T-ANNA-DESK + A1 | Seedance Fast · 8s · 480p |
| M3 Product | Video → Create Video | `still_mark_desk.png` | empty | T-MARK-DESK + M3 | Seedance Fast · 8s · 480p |
| A4 Objection | Video → Create Video | `still_anna_desk.png` | empty | T-ANNA-DESK + A4 | Seedance Fast · 8s · 480p |
| A7 CTA | Video → Create Video | `still_anna_front.png` | empty | T-ANNA-CAMERA + A7 | Seedance Fast · 6s · 480p |
| M1 | Video → Create Video | `still_mark_desk.png` | empty | T-MARK-DESK + M1 | Seedance Fast · 7s · 480p |
| M2 | Video → Create Video | `still_mark_desk.png` | empty | T-MARK-DESK + M2 | Seedance Fast · 7s · 480p |
| M4 | Video → Create Video | `still_mark_desk.png` | empty | T-MARK-DESK + M4 | Seedance Fast · 6s · 480p |
| M5 | Video → Create Video | `still_mark_desk.png` | empty | T-MARK-DESK + M5 | Seedance Fast · 5s · 480p |
| A2 | Video → Create Video | `still_anna_desk.png` | empty | T-ANNA-DESK + A2 | Seedance Fast · 6s · 480p |
| A3 | Video → Create Video | `still_anna_desk.png` | empty | T-ANNA-DESK + A3 | Seedance Fast · 5s · 480p |
| A5 | Video → Create Video | `still_anna_desk.png` | empty | T-ANNA-DESK + A5 | Seedance Fast · 7s · 480p |
| A6 | Video → Create Video | `still_anna_morning.png` (or S1) | empty | T-ANNA-DESK + A6 | Seedance Fast · 5s · 480p |
| I1 (optional) | Video → Create Video | `still_anna_hands.png` | empty | I1 line as written | Seedance Fast · 4s · 480p |
| Product, pings, clock, cursor, captions, end card | **send to Claude, not Da Vinci** | — | — | — | code |

If a duration isn't offered, use the nearest one at or above it and I trim in the edit.

**Credits** (estimate):
- 12 clips, plus 1 optional, at the skill's ~100–130 Da Vinci credits per Seedance Fast clip (its October 2026 observation): about **1,200–1,700 credits**.
- I don't know your Da Vinci balance or its photo pricing. Check the balance before starting.
- Test **A1 on the cheapest model first**. Make the finals on Fast at 480p. Upscale only the final cut.

**Priority (skill order):** A1 → M3 → A4 → A7, then M1, M2, M4, M5, then A2, A3, A5, A6, I1.

## 6. Reroll triggers (check each clip before moving on)

| Watch for | Most at risk |
|---|---|
| Any screen content visible | M3, A6 |
| The mug duplicating, melting or swapping hands | M1, M5, A7 |
| The voice changing between clips. Keep the voice line identical, and generate one character's clips in one sitting | all |
| "DoviLoop" mispronounced. Reroll, or I can patch that one word in the edit | M3 |
| Hands or fingers deforming | A5, M3, M4, I1 |
| Props drifting from the photo: a second laptop, a different mug | all |

## 7. What happens in the edit (my side)

- **Cutting:** cut each clip at its pauses, then alternate Anna and Mark shot for shot.
- **Code, from the script:**
  - Beat 1: the pings piling up and the client question, "Which documents do you need from me?"
  - Beat 4: the product sequence, drafts landing on the beat.
  - Beat 5: the zoom into the draft.
  - Beat 6: the close-up of the cursor on Send.
  - Beat 7: Anna's draft in her style.
  - The end card.
- **Sound:** the pings and clock, the hard silence, the music drop, silence on the Send hover, then the swell.
- **Captions** that land on their words, the "AI-generated dramatization" label on every AI shot, and loudness normalised.
- **Delivery:** 9:16 first, then the 30 s and 15 s cuts from `launch-film-plan.md` §5.
