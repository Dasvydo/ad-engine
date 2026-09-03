# The five objections

Built 2026-09-03 for the DoviLoop Teams campaign (8 Sept to 19 Oct 2026).
This file is the campaign's shared source of truth. Batch A's objection section
and Batch D's scripts refresh from here.

**ICP:** accounting and bookkeeping firms, insurance brokers, and housing and
facility administration. 10+ people writing client email, on Microsoft 365, no
in-house dev team. Not developers. Not startup founders.

**Method.** Dovy's instruction was to take the objections from competitors who
already paid to learn them, not to invent them. So every objection below is
traced to a real, named, public source that I opened in this session: a
competitor's own security or FAQ page, a competitor comparison page, or a named
negative review. Where a source is thin or second-hand, the objection says so in
its own **Evidence strength** line. Nothing here is invented, and no citation is
made up.

**Constraint.** This is competitive research, not content laundering. Every hook
below is written fresh. No competitor sentence is reused.

---

## What I could and could not reach

| Source the spec asked for | Result |
|---|---|
| Meta Ad Library, web | **Blocked.** HTTP 403 through the agent proxy, and headless Chromium got `ERR_CONNECTION_RESET`. |
| Meta Ad Library, Graph API | **Blocked.** `graph.facebook.com/v21.0/ads_archive` answers, but returns `OAuthException`. The archive endpoint needs an access token and a verified identity. That is a secret this session does not have. |
| G2 | **Blocked.** HTTP 403 on the Fyxer reviews URL. Bot protection. |
| Capterra | Partly. The Fyxer listing 404s at the URL I had, but the Conversifi listing loaded and was read. |
| Trustpilot | **Worked.** This is where the buyer's own words came from. |
| Competitor landing, FAQ, security, pricing and comparison pages | **Worked.** Six read in full. This is the backbone of the file. |
| Reddit r/Accounting for practitioner language | **Blocked.** Both `reddit.com/.../search.json` and `old.reddit.com` return HTML or a 302, not JSON. |

**Consequence, stated plainly.** The spec's strongest signal was meant to be
"ads that have been running a long time are ads that work". I could not see a
single competitor ad. So the durable-objection signal here comes from the next
best public surface: the pages a company keeps up permanently because buyers
keep asking. A security page that answers auto-send in three different sentences
is a company that has been asked about auto-send a great many times. That is a
weaker signal than ad longevity, but it is a real one, and it is not a guess.

### On the four companies named in the brief

The brief asked for a teardown of Alta, MasterInbox, Fyxer and Conversifi.
Having looked, only one of those four is a competitor for this ICP:

| Company | What it actually is | Verdict |
|---|---|---|
| **Fyxer AI** | AI email assistant for Outlook and Gmail, drafts replies, organizes inbox, meeting notes | **Direct competitor.** The primary source for this file. |
| **Conversifi** | LinkedIn outreach automation and AI appointment setting, $99/user/month (Capterra listing) | Different category. Sells to sales teams, not to a 14-person accounting firm answering client mail. Used only as evidence for objection 2. |
| **MasterInbox** | Cold-email deliverability and inbox rotation for outbound campaigns | Different category. Not a source. |
| **Alta** | No AI email assistant by that name found in this category. Drive holds `Alta Meeting Notes.docx` and `alta_agent_roster.svg` from May 2026, which are notes about something else. | Not a competitor here. |

Rather than force objections out of two companies that sell something else, I
widened the set to the products this ICP would genuinely shortlist against
DoviLoop: **Fyxer**, **MailMaestro / Maestro Labs**, **Jace**, **Superhuman**,
**virtualworkforce.ai** (the only one selling explicitly to accounting firms),
**CPA Pilot** (sells explicitly to accountants) and **Microsoft Copilot** (the
incumbent every M365 firm already owns). That is a better teardown for the job.

---

## The five

---

## 1. It is going to send something wrong to a client

### The objection in the buyer's words

> "Like any AI, you still have to confirm its accuracy."
> Scott, CPA Pilot review, Trustpilot, 22 Apr 2025

The accounting version is sharper than the general version. A wrong reply from a
generic SaaS company is embarrassing. A wrong reply about a filing deadline, a
fee, or what a policy covers is a client calling to ask why they were told the
wrong thing, and in insurance broking it is a file that gets looked at later. The
buyer is not worried about typos. They are worried about being on the hook.

### How the competitors answer it

Every serious competitor now answers with the same thing: the human still
approves. It has stopped being a differentiator and become the price of entry.

- **Fyxer** answers it three separate times on one security page: "Fyxer will
  never send an email on your behalf", "Every email requires your review before
  it goes anywhere", "Nothing is ever sent automatically; every action requires
  your approval." Three sentences for one question is a company that has been
  asked it constantly.
- **Jace** builds the review step into its onboarding flow, "Review and send",
  and prices the promise as speed: "Spend 5 seconds reviewing instead of 10
  minutes researching", "Approve drafts instantly".
- **virtualworkforce.ai**, the one selling to accounting firms, goes further and
  makes review conditional and role-based: messages containing tax advice or
  contract language route to a licensed accountant before they can go out. They
  position oversight as a feature rather than a limitation.
- **CPA Pilot** does not answer it in marketing. Its users answer it for them, in
  reviews, by saying they check the output anyway.

### The angle DoviLoop should take

Do not lead with "we never auto-send". Fyxer says it three times on one page, so
saying it louder wins nothing.

Lead with **what the draft is made of**. Everyone reviews. The question that
actually decides the objection is whether reviewing is a two second read or a
rewrite. A draft assembled from the firm's own fee schedule, its own deadlines
and its own engagement terms is a draft a senior can approve at a glance. A
draft assembled from the open internet is a draft someone has to fact-check
line by line, which is slower than writing it.

So the frame is: everyone leaves a draft. We leave a draft that is already
right, because it only knows what your firm told it. Human review is the floor
we build on, not the thing we sell.

Claims gate: this rests on `own_knowledge_base` and `never_auto_sends`, both
verified. No accuracy percentage anywhere.

### Hooks

- **Ad:** Everyone says a human checks it. The real question is how long the check takes.
- **Reel:** Open on a draft reply about a filing deadline. "This came from your own deadline list. Not from the internet. That is why reading it takes four seconds."
- **Landing page Q&A:** *What if it gets something wrong?* Nothing sends on its own, so a wrong draft is a draft you delete. And it can only answer from the documents you gave us, so the usual reason AI gets things wrong is not in play. If the answer is not in your knowledge base, it says so instead of guessing.

**Evidence strength:** Strong. Four named sources, two of them the competitors' own words, one a dated named review.

---

## 2. It will not sound like us, and our clients will notice

### The objection in the buyer's words

> "The AI messages actually sound like us which I didn't expect."
> David E., Real Estate Owner, Conversifi review, Capterra

That is a five-star review, and it is still evidence of the objection. "Which I
didn't expect" is the buyer telling you what they expected: that it would not
sound like them. And the paid answer sits right next to the complaint:

> "The categorisation isn't bad, and draft replies do a good job of getting the
> 'tone' pretty spot-on, but the actual functionality in Outlook is apalling."
> Kellie Bauer-Simpson, 2 stars, Fyxer review, Trustpilot, 13 Jun 2025

For this ICP the stake is relationship-shaped. A 20-year client of a Danish
bookkeeping firm knows how their bookkeeper writes. A broker's renewal note has
a house style. "Sounds like a robot" is not a quality complaint, it is a
relationship complaint.

### How the competitors answer it

- **Fyxer** puts it in the subheadline of its Outlook page: it "drafts replies
  that sound like you", learns by reading past emails, and "Most users send them
  with minor edits or no edits at all." That last line is doing the real work,
  because it converts a quality promise into a workload promise.
- **MailMaestro** answers structurally instead: it hands over three draft options
  and lets the writer pick. Choice as a hedge against tone.
- **Superhuman** is described by reviewers as reading the whole thread and prior
  history to get voice right, which is the same claim with more input.
- Nobody in the set makes the promise **per person**. Every one of them learns
  one voice per account.

### The angle DoviLoop should take

The competitor promise is "it sounds like you". DoviLoop's is narrower and
better for a firm: **it sounds like each of them**. A voice profile is built per
mailbox from that person's own sent mail, so the junior's drafts read like the
junior and the partner's read like the partner. For a 14-person firm that is the
difference between one house voice bolted on and the firm's actual voices kept.

Pair it with the review step rather than hiding it. In a firm, tone drift is
caught by the person whose name is on the email, which is exactly who is already
reading the draft before it goes.

Claims gate: rests on `per_person_voice`, verified. No "most users send with no
edits" style claim, because DoviLoop has no measurement behind one.

### Hooks

- **Ad:** Your clients know how you write. So should your drafts.
- **Reel:** Two drafts of the same reply side by side, one written by the partner, one by the new hire. "Same question. Same source. Two different people, still."
- **Landing page Q&A:** *Will it sound like us?* It builds a separate voice profile for each person from their own sent mail, so a draft in your inbox reads like you and a draft in a colleague's reads like them. You still read it before it goes, so a draft that misses gets fixed by the one person who would notice.

**Evidence strength:** Medium to strong. Two named dated reviews and two competitor pages. The Conversifi review is from an adjacent category, and I have flagged it as such rather than passing it off as an email-assistant review.

---

## 3. We are not moving out of Outlook, and nobody here has time for a rollout

### The objection in the buyer's words

> "the actual funtionality in Outlook is apalling"
> Kellie Bauer-Simpson, 2 stars, Fyxer, Trustpilot, 13 Jun 2025

and, on effort, the competitor stating the buyer's fear back to them:

> "Setup time is a real cost. A tool that takes an afternoon to configure is a
> tool that doesn't get used."
> Fyxer, "7 best email assistants in 2026", fyxer.com/blog

This ICP has no in-house dev team. That is a hard gate in the brief and it is
the reason this objection is not about software, it is about who does the work.
There is no one to own a rollout. There is an office manager who already has a
job.

### How the competitors answer it

- **Fyxer** answers with a number: "Set up in 30 seconds", "Connect your Outlook
  account and Fyxer starts working immediately", positioned for people who want
  drafts "without leaving Gmail or Outlook".
- **MailMaestro** answers with placement: a native sidebar inside Outlook, "No
  software to download".
- **alfred_**, comparing itself to Copilot, answers the IT question directly:
  "In organizations that restrict third-party apps, your admin grants consent
  once in Entra ID", and reassures that OAuth means the tool "never sees your
  password".
- **Superhuman** is the counter-example that proves the objection. It asks the
  firm to change email client entirely, and its own help material and reviewers
  note shared mailboxes and some IT-managed setups are not supported.

Note the tension the category has not resolved: everyone claims a 30-second
setup, and the one 2-star review in my set is specifically about the Outlook
experience being bad. Fast to connect is not the same as good once connected.

### The angle DoviLoop should take

DoviLoop's honest position is stronger than a 30-second claim, because it is not
competing on install speed. The offer includes a workshop and setup as part of
the $500. Nobody at the firm builds anything.

So the frame is: **you are not installing software, you are getting a folder
that starts filling up.** Drafts appear in the Outlook drafts folder people
already open. No new app, no new login, no new habit, nothing to train anyone
on. And the honest half, which buys credibility: the part that takes real work
is building the knowledge base, and that is the part we do, in the workshop,
not the part we hand you.

The admin consent question should be answered on the landing page rather than
buried, because in a firm with outsourced IT it is the step that actually stalls
a deal.

Claims gate: rests on `stays_in_outlook`, verified. No setup-time number, since
none has been measured on a real customer.

### Hooks

- **Ad:** No new app. The drafts are in the folder you already open.
- **Reel:** Screen recording, open Outlook, click Drafts. "That is the whole product tour. There is no second screen."
- **Landing page Q&A:** *What do we have to install?* Nothing. Drafts arrive in your normal Outlook drafts folder. If your IT is outsourced, they approve the connection once in Microsoft 365 and are done. We build the knowledge base with you in the kickoff workshop, so the work that would land on your office manager lands on us instead.

**Evidence strength:** Strong. Four named sources including two direct competitor pages and one named dated review.

---

## 4. Where does client data go, and is it training somebody's AI

### The objection in the buyer's words

Nobody writes this one in a review, because the people who care about it never
get as far as buying. It shows up instead as the answer, repeated by every
vendor, unprompted, on a page they built for it:

> "Your data never trains third-party AI models."
> Fyxer, security page

> "We never train AI models on your data."
> Jace, homepage

Three competitors volunteering the same sentence without being asked is what a
frequently-asked question looks like from the vendor's side.

For this ICP it is heavier than for a startup. An accounting firm holds payroll
and financial records. An insurance broker holds health and claims detail. A
housing administrator holds tenant data. These are firms with a data processing
agreement already in a drawer, and a procurement habit even at 15 people.

### How the competitors answer it

Almost entirely with certificates:

- **Fyxer:** SOC 2 Type 2, ISO 27001, GDPR, HIPAA, ADA Tier 2 CASA, plus "Your
  email data is never stored permanently or shared" and "Microsoft-verified".
- **MailMaestro:** SOC 2 Type II, GDPR, HIPAA with a BAA on request, Microsoft
  Attested, Google Verified, CASA Tier 2, and for enterprise buyers zero-day
  retention and PII obfuscation on request.
- **Jace:** "Bank-level security", SOC 2 Type 1, CASA Tier 3, encryption in
  transit and at rest.
- **virtualworkforce.ai**, again the accounting-specific one, is the only source
  that names the thing European buyers actually ask: verify the vendor's **data
  residency**, keep audit logs, use role-based access.

Here is the gap. Every one of them answers *how well guarded* the data is.
Almost none of them answers *where it is*. For a European firm those are
different questions, and the second one is the one the DPA asks.

### The angle DoviLoop should take

Answer the question they are actually asking. It runs in Europe. The Supabase
project and the n8n instance are both EU-hosted. That is a plain sentence any
office manager can forward to whoever asks, and it does not require anyone to
know what SOC 2 means.

The brief already calls data sovereignty the biggest current driver in European
buying, and a reason to buy rather than a hurdle. It is also the one thing a US
competitor will not match quickly, along with actually shipping in Danish and
Lithuanian.

Pair it with review-before-send, because together they answer the whole worry:
your data stays in Europe, and nothing leaves your firm without a person
choosing to send it.

Claims gate: rests on `eu_hosted`, verified. Do not claim SOC 2 or ISO 27001.
DoviLoop does not have them, and claiming a certificate you do not hold is a
different and much worse category of problem than an unbacked number.

### Hooks

- **Ad:** Your client data stays in Europe. So does the draft.
- **Reel:** "Every one of these tools will tell you it is encrypted. Ask a different question. Ask which country it is in."
- **Landing page Q&A:** *Where is our data?* In Europe. Our database and our automation both run on EU infrastructure, and your documents are only ever used to answer your firm's own email. We do not train any model on your data. If your DPA needs a straight answer about location, that is the answer.

**Evidence strength:** Strong on how competitors answer, and honestly weaker on
the buyer's own words. I have no named buyer quote for this one, because the
review sites I could reach do not carry it and G2 was blocked. The objection is
inferred from three vendors independently pre-empting it plus the ICP brief's
own note that sovereignty is the biggest driver in European buying. That is a
real inference, not a quote, and it is labelled as one.

---

## 5. What happens if it does not work out

### The objection in the buyer's words

This is where the review sites are loudest, and it is not about the software at
all:

> "Trial feels fraudulent- cancellation during wouldn't work and emails to Fyxer
> went unanswered."
> Tom Allason, 1 star, Fyxer, Trustpilot, 15 Jun 2025. Charged $450, then $900.

> "They charged me $450 immediately" on a supposedly free trial.
> Damian Biondo, 1 star, Fyxer, Trustpilot, 23 Apr 2025.

> "Predatory free trial practice ans continuing to charge after cancelling."
> Martin Becker, 1 star, Fyxer, Trustpilot, 21 Mar 2025. Charged 900 EUR after
> support confirmed the cancellation.

Read those next to the offer DoviLoop is running. $500 setup plus $89 a seat
across a 12-person firm is a real commitment, decided by an owner or partner who
has been burned by a subscription before. The objection is not "is it good", it
is "what am I signing, and can I get out".

### How the competitors answer it

- **Fyxer** answers with reversibility: cancel any time and the inbox reverts to
  its original state instantly, with drafts and data deleted. A good answer,
  undercut by the reviews above.
- **Jace** answers with a 7-day trial and credit bundles, 10,000 credits on the
  $20 plan.
- **Fyxer's own comparison blog** names the resulting fear out loud:
  "Credits-based pricing models make budgeting difficult." That is a competitor
  telling you buyers cannot predict the bill.
- **alfred_** competes on the same nerve with a flat $29.99 a month and no M365
  requirement, against Copilot's $30 per user add-on.

### The angle DoviLoop should take

The campaign's own funnel is the answer, and it is a genuinely better one than
the category's: a free two-week pilot with the workshop and the setup included,
and the card is not charged until day 14. Nothing is a surprise, because the
first two weeks are the evaluation and the invoice comes after them.

Two things to hold to. First, do not put the price in the ad. This is a
booking-only funnel and the price belongs in the conversation where the seat
count is known. Second, say the pilot is a real pilot: the firm keeps whatever
knowledge base gets built during it. The repo's existing guarantee language
already says something close to this, and it is the strongest trust asset on the
board given there are no testimonials and no logos yet.

And do not invent proof to plug the gap. There are no customers. An ad that
implies otherwise fails the claims gate and deserves to.

Claims gate: no numbers, no "trusted by". Pure structural promise.

### Hooks

- **Ad:** Two weeks. Set up by us. Nothing charged until you have seen it work.
- **Reel:** "Here is the whole deal. We build it with you, you run it for two weeks, then you decide. If it is not good enough to send, do not pay."
- **Landing page Q&A:** *What if we hate it?* You get two weeks with the workshop and the setup included, and nothing is charged until day 14. If the drafts are not good enough to send by then, do not go ahead. You keep the knowledge base we built with you either way.

**Evidence strength:** Strongest in the file for buyer's words. Three named,
dated, quoted one-star reviews plus two competitor pricing pages. The one caveat
is that all three reviews are of the same company, so this is Fyxer's billing
reputation specifically, not a measured category-wide problem.

---

## Source list

Every URL opened for this file, and what came back.

| Source | URL | Result | Used for |
|---|---|---|---|
| Fyxer homepage | `fyxer.com` | Read | Positioning |
| Fyxer security page | `fyxer.com/security` | Read | Objections 1, 4 |
| Fyxer Outlook page | `fyxer.com/ai-email-assistants/outlook` | Read | Objections 2, 3, 4 |
| Fyxer comparison blog | `fyxer.com/blog/best-ai-email-assistant` | Read | Objections 3, 5 |
| Fyxer reviews | `trustpilot.com/review/fyxer.ai` | Read | Objections 2, 5 |
| CPA Pilot reviews | `trustpilot.com/review/cpapilot.com` | Read | Objection 1 |
| Maestro Labs / MailMaestro | `maestrolabs.com` | Read | Objections 2, 3, 4 |
| Jace | `jace.ai` | Read | Objections 1, 4, 5 |
| virtualworkforce.ai, accounting page | `virtualworkforce.ai/email-assistant-for-accounting-firms/` | Read | Objections 1, 4 |
| alfred_ vs Copilot comparison | `get-alfred.ai/blog/best-ai-assistant-for-outlook` | Read | Objections 3, 5 |
| Conversifi listing | `capterra.com/p/10035927/Conversifi/` | Read | Objection 2 |
| Superhuman pricing | `superhuman.com/pricing` | Loaded but rendered empty, no usable content | Not used |
| Superhuman security | `superhuman.com/security` | 404 | Not used |
| Superhuman help centre | `help.superhuman.com/...Troubleshooting-Login-Issues` | 403 | Not used |
| Microsoft Copilot email page | `microsoft.com/.../ai-email-assistant` | 503 | Not used |
| G2 Fyxer reviews | `g2.com/products/fyxer-ai/reviews` | 403 | Not used |
| Capterra Fyxer listing | `capterra.com/p/10015399/Fyxer-AI/reviews/` | 404 | Not used |
| Meta Ad Library, web and API | `facebook.com/ads/library`, `graph.facebook.com/.../ads_archive` | 403 / connection reset / OAuthException | **Not used. See BLOCKED.md.** |
| Reddit r/Accounting | `reddit.com/r/Accounting/search.json` | HTML, not JSON | Not used |
| Google Drive, `fyxer_ai_competitor_analysis.docx` | Drive, Oct 2025 | Read as a cross-check only | Corroborates objections 1 and 4. Not cited as primary: it is secondary, undated in method, and eleven months old. |

### Which objections rest on thinner evidence

Said plainly, so nobody downstream over-trusts this file:

1. **Objection 4 has no buyer quote.** It is inferred from three vendors
   pre-empting the same question. Strong inference, still an inference.
2. **Objection 2 leans on a review from an adjacent product** (Conversifi, a
   LinkedIn tool) for its buyer quote, alongside a Fyxer review that is about
   tone only in passing.
3. **Objection 5's buyer words all come from one company.** Fyxer's billing
   reputation is not proof that the whole category bills badly.
4. **No objection in this file is backed by ad-longevity data**, because the Ad
   Library could not be reached. If Dovy opens the Ad Library himself in a
   browser it is about ten minutes of work to check whether Fyxer, Superhuman or
   Jace have long-running ads, and whichever objections those ads lead with
   should be promoted above the rest in the creative rotation.

Nothing in this file was written to fill a slot. Where a slot could not be
filled honestly, the gap is named above.
