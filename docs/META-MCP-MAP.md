# Meta MCP — the map

> Companion to `META-MCP-SETUP.md`, which carries the reasoning and the sources.
> This file is the picture. Renders on GitHub and in Obsidian.
> All three diagrams were rendered and checked, not just written.
>
> 🟩 works today · 🟦 works, but manual forever · 🟨 blocked on something of ours
> · 🟥 does not exist · 🟪 contradictory, untested

---

## 1. Everything crosses one gate

```mermaid
flowchart LR
    subgraph IN[" Inputs "]
        direction TB
        H["HiggsField MCP<br/>🟩 already connected"]:::live
        RE["reel-engine<br/>🟩 video + stills"]:::live
        OL["outreach-engine list<br/>🟩 ~750 firms"]:::live
        PX["Meta pixel<br/>🟥 not installed"]:::absent
    end

    subgraph GATE[" ad-engine · the local truth "]
        direction TB
        CK["engine.cli check<br/>claims/evidence.json<br/>3 claim families BLOCKED"]:::gate
        AU["engine.cli audience<br/>SHA-256, never leaves the machine"]:::gate
    end

    subgraph OUT[" Meta · mcp.facebook.com/ads "]
        direction TB
        OK["Reporting<br/>Campaign mgmt, creates PAUSED<br/>Signal diagnostics<br/>🟩 Claude drives these"]:::live
        NO["Audiences · B2B targeting<br/>🟥 no tool exists"]:::absent
        MB["Creative assets<br/>🟪 sources contradict"]:::unknown
    end

    H --> CK
    RE --> CK
    OL --> AU
    CK ==>|"only gated copy ships"| OK
    AU ==>|"BY HAND, every time"| NO
    PX -.->|"needs weeks of collection first"| NO

    classDef live fill:#14532d,stroke:#22c55e,color:#dcfce7
    classDef absent fill:#7f1d1d,stroke:#ef4444,color:#fee2e2
    classDef unknown fill:#4c1d95,stroke:#a855f7,color:#ede9fe
    classDef gate fill:#3730a3,stroke:#818cf8,color:#e0e7ff
    style IN fill:none,stroke:#94a3b8
    style GATE fill:none,stroke:#818cf8,stroke-width:2px
    style OUT fill:none,stroke:#94a3b8
```

**The two thick edges are the whole story.**

- Every asset Claude generates crosses `engine.cli check` before it reaches Meta.
  No off-the-shelf media-buyer skill has this, and every one of them is tuned to
  write exactly the percentage `claims/evidence.json` exists to block.
- `outreach-list` — priority 1, the only audience that matches the ICP — crosses
  into Meta **by hand**, forever. The connector has no audience tool. The single
  most important object in this repo is outside the agent's reach.

---

## 2. The flywheel — theirs vs. ours

```mermaid
flowchart TB
    subgraph V[" Video's loop · runs on conversion volume "]
        direction LR
        V1["Winner<br/>>5% spend AND<br/>above target ROAS"]:::live
        V2["Brief"]:::live
        V3["AI variants"]:::live
        V4["Launch"]:::live
        V5["Measure<br/>5,539 purchases"]:::live
        V1 --> V2 --> V3 --> V4 --> V5 --> V1
    end

    subgraph O[" Ours · zero purchase events exist "]
        direction LR
        O1["Winner<br/>NOTHING TO RANK ON"]:::absent
        O2["Brief"]:::live
        O3["AI variants"]:::live
        O4["engine.cli check"]:::gate
        O5["Launch, paused"]:::live
        O6["Measure<br/>single-digit leads/wk"]:::blocked
        O1 --> O2 --> O3 --> O4 --> O5 --> O6 --> O1
    end

    V ~~~ O

    classDef live fill:#14532d,stroke:#22c55e,color:#dcfce7
    classDef blocked fill:#713f12,stroke:#f59e0b,color:#fef3c7
    classDef absent fill:#7f1d1d,stroke:#ef4444,color:#fee2e2
    classDef gate fill:#3730a3,stroke:#818cf8,color:#e0e7ff
    style V fill:none,stroke:#94a3b8
    style O fill:none,stroke:#818cf8,stroke-width:2px
```

Two differences, and they are the entire adaptation:

- **The loop does not close.** Their `Measure → Winner` edge carries thousands of
  purchases. Ours carries a handful of leads a week — below any statistical test.
  Read it as a log, not a signal. Winners get picked by judgement here.
- **A gate sits in the middle of ours** that has no counterpart in theirs.

**What replaces their detectors:**

| Video builds | Needs | Our substitute |
|---|---|---|
| Winner detection (ROAS + 5% spend) | purchases | qualified leads from PostHog — judgement, not a threshold |
| Anomaly detection at 2 SD | daily conversions | 2 SD on **delivery**: spend · CPM · reach · frequency |
| Creative flywheel, ~100/wk | budget + volume | reel-engine reuse first, 2 arms only, gate every variant |
| Scheduled daily report | nothing | ✅ ports unchanged — cheapest win on the board |

> **⚠️ Frequency is the metric that will bite.** ~750 firms × 2–3 contacts ≈ 2,000
> people. Meta wants ~50 conversions per ad set per week to leave the learning
> phase; we will never supply that, so it never optimises — it just spends. Reach
> saturates in days and frequency climbs hard. **Build that alert first.** The
> videos treat frequency as a secondary metric. On this audience it is the
> primary one.

---

## 3. Critical path — the pixel is a clock

```mermaid
flowchart TB
    subgraph SLOW[" ⏳ The clock lane · start today, cannot be compressed "]
        direction LR
        S1["Business Manager<br/>+ ad account"]:::absent
        S2["Create pixel"]:::absent
        S3["VITE_META_PIXEL_ID<br/>→ Vercel"]:::absent
        S4["Same pixel on<br/>doviloop.dev"]:::absent
        S5["COLLECT<br/>WEEKS"]:::clock
        S6["site-retargeting<br/>has people in it"]:::blocked
        S1 --> S2 --> S3 --> S4 --> S5 --> S6
    end

    subgraph FAST[" ⚡ The afternoon lane · any time before launch "]
        direction LR
        F1["Connect MCP<br/>~10 min"]:::live
        F2["Write our skill"]:::live
        F3["Frequency alert"]:::live
        F4["Daily report"]:::live
        F5["Reconnect<br/>PostHog"]:::blocked
        F6["Proofread<br/>da + lt"]:::blocked
        F7["Upload outreach-list<br/>BY HAND"]:::manual
    end

    GO(["LAUNCH<br/>both lanes complete"]):::gate
    SLOW --> GO
    FAST --> GO

    classDef live fill:#14532d,stroke:#22c55e,color:#dcfce7
    classDef blocked fill:#713f12,stroke:#f59e0b,color:#fef3c7
    classDef absent fill:#7f1d1d,stroke:#ef4444,color:#fee2e2
    classDef manual fill:#1e3a5f,stroke:#3b82f6,color:#dbeafe
    classDef clock fill:#4c1d95,stroke:#a855f7,color:#ede9fe
    classDef gate fill:#3730a3,stroke:#818cf8,color:#e0e7ff
    style SLOW fill:none,stroke:#a855f7,stroke-width:2px
    style FAST fill:none,stroke:#94a3b8
```

**The bottom lane is an afternoon. The top lane is a calendar.**

The pixel does nothing on the day you install it — it has to *have been* running.
`audiences/site-retargeting.json` says exactly that in its own `blocked_on`
field. It is the only item here where delay costs weeks instead of hours, and
it is currently at step zero.

---

## 4. Status ledger

| Thing | State | Where it lives |
|---|---|---|
| Meta ad account | 🟥 no `act_` ID in any of the three repos | — |
| Meta connector | 🟩 available, open beta | `mcp.facebook.com/ads` |
| Audience upload | 🟦 manual forever — no MCP tool | `engine/audience.py` |
| B2B targeting | 🟥 does not exist on any Meta surface | — |
| Creative asset reads | 🟪 sources contradict, untested | §2, setup doc |
| Claims gate | 🟩 working | `engine.cli check` |
| HiggsField | 🟩 connected on this account | verified 2026-09-16 |
| reel-engine assets | 🟩 referenced by creative specs | `creative/capacity.json` |
| Meta pixel | 🟥 `VITE_META_PIXEL_ID` empty | `campaign-site/.env.example` §5 |
| Pixel on doviloop.dev | 🟥 not installed | `audiences/site-retargeting.json` |
| PostHog | 🟨 `needs_reconnect` | connector settings |
| da / lt ad copy | 🟨 `NEEDS_NATIVE_PROOFREAD` | `creative/*.json` |
| Varnan-Tech skill | 🟥 wrong MCP, stale, stubbed | §5, setup doc |
| Our own skill | 🟨 not written | offered, not started |
