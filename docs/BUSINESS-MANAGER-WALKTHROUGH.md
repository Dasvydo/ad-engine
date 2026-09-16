# Business Manager — do this with a browser open

> The click-by-click. Companion to `META-ADS-RUNBOOK.md`, which explains *why*.
> Written 2026-09-16. **Meta moves its menu labels constantly** — the route below
> is the shape, not a promise about today's wording. If a label has moved, the
> step still exists somewhere near where it says.

---

## First: no, Claude cannot do this part

The honest split. This is the thing worth understanding before anything else.

| | Who |
|---|---|
| Create a Business Manager | **You, in a browser** |
| Create a Facebook Page | **You** |
| Create an ad account | **You** |
| Add a payment method | **You** — card entry is regulated, never an API |
| Accept Custom Audience terms | **You** — nobody can accept a contract on your behalf |
| Upload the customer list | **You** — no audience tool exists on the connector |
| Install the pixel | **You** (code change + Vercel env var) |
| — everything below this line — | |
| Read performance, build reports | Claude |
| Investigate a spend or frequency change | Claude |
| Draft and vary ad copy | Claude (gated) |
| Create campaigns / ad sets / ads | Claude, **paused** |
| Activate, pause, change budgets | Claude — **but make it ask, every time** |

**The bootstrap problem:** the connector authenticates *into* a Business Manager
that already exists. It cannot create the thing it needs in order to exist. So
Phase 0 is 100% manual, and no amount of agent parallelism changes that.

**Claude becomes useful the moment there is an account with data in it.** Not
before. Everything below is the price of admission.

⚠️ **One security decision, and take it seriously.** When you connect the
connector, Meta's OAuth screen offers scope tiers — reportedly including a
separate **financial/billing scope**. *(Reported by a secondary source, not
verified by me — you'll see the real screen before I will.)*

**Do not grant the financial scope.** Nothing Claude does for you needs it, and
it is the one scope where a mistake costs money directly rather than costing
delivery.

---

## The tick list

Work top to bottom. Each step's "you'll know it worked when" is there so you
don't have to guess.

### ☐ 1. Business Manager
**business.facebook.com** → create a business.

Use the real legal entity name and address — this is what gets verified later if
Meta asks, and a mismatch is a slow problem to unwind.

*Worked when:* you land on a Business Settings page with an empty Accounts list.

---

### ☐ 2. A Facebook Page for DoviLoop
**You cannot run ads without one.** There is no such thing as an ad with no Page
behind it — the Page is the "from" on the ad.

It does not need followers, posts, or activity. It needs to exist, carry the
logo, and be **owned by the Business Manager, not by your personal profile.**

Business Settings → Accounts → Pages → Add. Create a new one if you don't have one.

*Worked when:* the Page appears under Business Settings → Pages, not just on your
personal profile.

> If you already made a DoviLoop Page from your personal account, transfer it in
> rather than making a second one. Two Pages for one brand is a mess to undo.

---

### ☐ 3. Ad account
Business Settings → Accounts → Ad accounts → Add → **Create a new ad account**.

🚨 **Currency and timezone cannot be changed after creation. Ever.** Not by
support, not by you. Set **EUR** and **Europe/Vilnius** and read them back before
confirming.

*Worked when:* you have an ID shaped like `act_123456789`.

**Write that number down.** You will paste it into Claude constantly, and the
numeric ID resolves far more reliably than the account name.

---

### ☐ 4. Payment method
Billing → Payment settings → add a card.

Expect a small temporary authorisation charge. Expect a low initial spending
limit — new accounts get one automatically. It rises on its own with billing
history.

*Worked when:* the account shows an active payment method and no red banner.

---

### ☐ 5. Accept Custom Audience terms
**The step everyone misses, and it silently blocks the audience upload entirely.**

Business Settings → under Data sources / Audiences, there is a one-time **Custom
Audience Terms of Service** to read and accept.

*Worked when:* the accept prompt is gone. If you can't find it, it often only
surfaces at the moment you first try to create a customer-list audience — so if
you hit it in Part 4 of the runbook, that's this step arriving late.

---

### ☐ 6. Create the pixel
Events Manager → Data sources → Connect → **Web**.

Name it something you'll recognise. Copy the ID — 15 or 16 digits.

*Worked when:* the dataset exists and shows "No activity yet". That's correct —
it has nothing to report until step 7 ships.

---

### ☐ 7. Pixel into Vercel
`campaign-site`, variable **`VITE_META_PIXEL_ID`**, documented in
`campaign-site/.env.example` §5.

Vercel → the campaign-site project → Settings → Environment Variables → add it
for **both Production and Preview** → then **redeploy**. Env vars are baked in at
build time; without a redeploy nothing changes.

*Worked when:* load the deployed page, accept the consent banner, and check the
network tab for a request to Facebook. Before consent there should be **nothing**
— no script, no cookie. That's the gate working, not the pixel failing.

---

### ☐ 8. The same pixel on doviloop.dev
Not done yet, and it may be bigger than a copy-paste — I have an agent checking
exactly what the product site would need. I'll report when it lands.

**Why it matters:** with the pixel only on the campaign page, your retargeting
audience contains people who saw the campaign page and nobody else. The product
site is where your traffic already is.

---

### ☐ 9. Then stop, and let it collect
The pixel is a clock. Nothing above this line is urgent to *use* — it is urgent
to *start*, because the value only accrues with time behind it.

Go do the creative and the proofreading while it runs.

---

## When you're done, hand Claude this

Paste this into a fresh Claude Desktop chat once the connector is added:

```
Ad account act_XXXXXXXXX. Confirm you can reach it, then give me
the account's currency, timezone, spending limit and whether the
pixel is receiving events yet. Don't create or change anything.
```

That single prompt proves steps 3, 4, 6 and 7 all landed, and it's read-only.

---

## Things that will happen and are normal

- **A low spending limit on a new account.** Rises with billing history.
- **An ad rejected on automated review.** Request review; the first pass is blunt.
- **Custom audience match rate well under 100%.** Half is normal. Not your fault.
- **Business verification requested.** Have the company registration handy.
- **The connector returning nothing despite connecting.** It's in open beta and
  not every advertiser is enabled. That's a queue position, not a broken setup.
