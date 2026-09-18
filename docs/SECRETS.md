# Repository secrets

Every secret and variable the workflows read, what needs it, and what breaks
without it. Secrets live in GitHub Actions secrets. Never in the repository,
never in a Drive mirror, never in a URL.

Set them at **Settings > Secrets and variables > Actions**. Secrets and
Variables are two different tabs on that screen, and one of the five below is
deliberately a variable.

| Name | Kind | Read by | Required today |
|---|---|---|---|
| `GEMINI_API_KEY` | secret | `research.yml` and `propose.yml`, through `engine/model.py` | **Yes, to research or to propose** |
| `META_ACCESS_TOKEN` | secret | `research.yml` and `measure.yml`, through `engine/oauth.py` | **Yes, to discover or to measure.** Does not exist yet |
| `META_TOKEN_ISSUED` | **variable**, `YYYY-MM-DD` | `engine/oauth.py` | **Yes, beside the token.** Set it in the same visit |
| `REEL_ENGINE_TOKEN` | secret, fine-grained PAT | `build.yml` only, and only for a `reel` creative | **Yes, to shoot a video.** Does not exist yet |
| `GITHUB_TOKEN` | automatic | every workflow that commits, and the four that open, label or close an issue | Supplied by Actions - not something you create |
| `META_GRAPH_VERSION` | optional variable, `v21.0` | `engine/discover.py`, `engine/measure.py` | No. Unset means the unversioned host, which is what both modules want |

`GOOGLE_API_KEY` is accepted as a fallback for `GEMINI_API_KEY` because the
Google SDK looks for it unprompted, but set `GEMINI_API_KEY`: it is the name
every error message here names.

**No secret value is ever interpolated into a message, a log line, a filename
or a URL.** `engine/oauth.py` scrubs the token out of anything it raises - the
whole value and any run of twelve characters or more - and re-raises outside
the `except` block so nothing unscrubbed rides along on `__context__`.
`engine/discover.py` and `engine/measure.py` wrap every transport call in the
same scrub, because the exception that echoes a token is usually somebody
else's: `http.client` puts the whole header in a `ValueError` when the value
has a line break in it, and Meta will happily repeat a bad token back to you in
an error body.

---

## `GEMINI_API_KEY`

Three steps write with it and one judges with it, on two pinned model ids:

```
engine/analyse.py     gemini-3.6-flash   one call per batch of 12 ads
engine/concepts.py    gemini-3.6-flash   one call, twelve concepts
engine/score.py       gemini-3.6-flash   one call, the editorial dimension
engine/write.py       gemini-3.6-flash   one call per attempt, the ad copy
engine/gate.py        gemini-3.5-flash   one call per attempt, the rubric
```

**It is free.** Mint one at [aistudio.google.com](https://aistudio.google.com)
- no card, no billing account. The free tier is 20 requests a day **per model**,
which is why the two ids are split: the judge and the writer each get their own
20 rather than sharing one. `docs/COST.md` has the arithmetic, including what a
Monday that runs both the sweep and a propose costs.

`research.yml` and `propose.yml` both **fail on their first step** when it is
unset, with a message naming the secret. They do not skip a step and report
success - a silent skip on an unattended cron is how an engine looks healthy
while doing nothing.

`engine/model.py` is the only module that imports `google.genai`, and
`engine/model.client()` raises before any socket when the key is missing, with
a message naming `GEMINI_API_KEY` and where to mint one. An empty string counts
as unset.

**A second key is a legitimate answer.** `reel-engine` runs its own sweep on
Monday morning against the same free allowance. If the two collide, give this
repository its own AI Studio key rather than staggering the crons: it is free,
and it doubles the headroom instead of moving the collision.

---

## `META_ACCESS_TOKEN` and the `META_TOKEN_ISSUED` variable

**One token pair, two APIs.** The same `META_ACCESS_TOKEN` reads the Ad
Library archive for strangers' ads and the Marketing API insights edge for our
own. They are different endpoints and different permissions, but one token
carries both, and `engine/oauth.py` is the only module that reads either name
out of the environment.

### Getting the token

1. **Verify your identity at `facebook.com/ID`.** A government id, and Meta
   takes one to three business days. Nothing below works before this, and it is
   the long pole - start it first. *Unblocks everything on this page.*
2. **Create a Meta developer app** at `developers.facebook.com` and add the
   **Ad Library API** product to it. This is the product that makes
   `ads_archive` answer at all. *Unblocks discovery.*
3. **Add the Marketing API product too, and grant the token's user `ads_read`
   on our own ad account** in Business Manager. This is a different permission
   on the same token, and it is what `engine/measure.py` needs to read our own
   launched ads. Measure never needs `own.ad_account_id` from
   `research/seeds.yaml` - it looks an ad up by the id a human pinned, and the
   token's `ads_read` on our account is what scopes the answer - so this
   permission is the whole of what stands between a pinned ad and a CTR.
   *Unblocks measure.*
4. **Mint a long-lived token** for that app.
5. **Set two things, in the same visit:**
   - `META_ACCESS_TOKEN` - the token. Actions > **Secrets**.
   - `META_TOKEN_ISSUED` - **today's date**, `YYYY-MM-DD`. Actions >
     **Variables**, which is a different tab.

### Why the date is a variable and not a secret

A date is not a credential, and the ageing clock needs it to be *visible*: a
secret is write-only once saved, so an operator who rotates the token could
never check whether the date beside it was updated too. As a variable it sits
on the same screen at the same moment the token is pasted - the only moment the
pair can be kept honest - and an error message can echo it back to say how many
of the 60 days are left.

Set it wrong and the clock runs from the wrong day. Leave it unset and nothing
can warn you before the token dies. **A date more than a day in the future is
refused outright**, because an age that never reaches 40 is a warning that
never fires. (A day of slack is allowed on purpose, for an operator east of
UTC setting it from their own calendar.)

`engine/oauth.py` reads the token **before** it reads the date, and adds it to
the live scrub list immediately - so a refusal about `META_TOKEN_ISSUED` can
never carry the token, including the case where the token was pasted into the
date variable's box by mistake. If the value in `META_TOKEN_ISSUED` is longer
than 32 characters it is described by its length rather than echoed, for the
same reason.

### The 60-day countdown

**Meta expires a long-lived token 60 days after issue, and refreshing it inside
a run does not help.** A refresh returns a *new* token, valid 60 days from the
refresh - but only in memory. Writing it back into the repository secret would
need a Personal Access Token carrying `secrets: write`, a credential that can
rewrite every secret here, and this repository deliberately does not hold one.
So the refreshed token would die with the process and **the stored token keeps
ageing**. There is no writeback and no automatic renewal, and any document that
implies otherwise is wrong.

That makes rotation a calendar entry for a human, roughly every two months.
What the code does about it, and all it does:

- It **warns from day 40 of 60** whenever something asks for the token, with
  the days left and the date it counted from. The warning goes to stderr; in
  Actions it lands in the run log of `research.yml` and `measure.yml`.
- It **refuses past day 60 before opening a socket**, rather than letting Meta
  answer with an error that names no secret and no fix.
- `python -m engine.oauth --status` prints the countdown on demand - **names,
  never values** - and exits nonzero when the token is missing, has whitespace
  in it, the date is missing or unreadable or in the future, the token is
  expired, or it is inside the 20-day warning band. Zero means: token set and
  clean, date readable, more than 20 days left.

Both scheduled workflows run `--status` as a cheap pre-step. It costs nothing,
opens no socket, and its stdout never carries a value.

### The 60 days is an assumption, and it is wrong in the safe direction

Meta does not publish a token lifetime for this use. The 60 days is carried
over from `reel-engine`'s Instagram experience and is stated as an assumption
in `engine/oauth.py`'s own docstring. If a **System User token** from Business
Manager turns out to be accepted here - it does not expire - the clock is wrong
in the direction that refuses a live token on day 61 rather than the one that
lets a dead token through. Changing it is one constant. Checking whether a
System User token works is the first thing to do when the ad account is wired.

### To rotate

Mint a fresh long-lived token for the **same Meta app**, then update **both**
`META_ACCESS_TOKEN` (Secrets) and `META_TOKEN_ISSUED` (Variables, set to today)
in the same visit. Updating one without the other is exactly how this breaks
silently - a fresh token with a stale date warns for no reason, and a stale
token with a fresh date never warns at all.

### A token with whitespace in it is refused

Pasting a token into the secrets box sometimes brings a trailing newline with
it. `engine/oauth.py` refuses that rather than returning it verbatim, because
`http.client` rejects a header value containing a line break with a
`ValueError` that prints **the whole header** - which is to say, the token - and
that traceback would then sit in a run log. `--status` reports it as `set, but
contains whitespace` and exits nonzero. Re-paste it without the newline.

---

## `REEL_ENGINE_TOKEN`

**`build.yml` only, and only when the job's `creative_source.kind` is `reel`.**
Nothing else in this repository reads the sibling repository at run time, and
that is deliberate: the weekly research cron must not be able to fail on a
credential it has no other use for. The segment backlog is a **copy** in
`queue/backlog.md` for exactly this reason - see
`docs/AD-RESEARCH-SCOPE.md` §8 - and `tools/sync_backlog.py` is what keeps it
honest, run by hand from a checkout that has both.

The ad's video is a reel, and reels are shot by `reel-engine`: its templates,
its pinned Chromium, its claims gate, its deterministic frame seeking.
`build.yml` checks that repository out as a sibling at `../reel-engine`,
installs it there, and runs **its** `engine.propose` against the selection
sidecar this repository wrote beside the job. That checkout needs a token
because `Dasvydo/reel-engine` is private and `GITHUB_TOKEN` cannot read across
repositories.

**To mint it:** Settings > Developer settings > Personal access tokens >
**Fine-grained**. Resource owner `Dasvydo`, repository access **only**
`Dasvydo/reel-engine`, Repository permissions > **Contents: Read-only**.
Nothing else, and nothing write. Set it here as `REEL_ENGINE_TOKEN`.

Without it, `build.yml` fails on a reel job naming the secret. A `still` or
`none` creative takes the short path - no sibling checkout, no browser, no
model call - and needs nothing from this section.

---

## `GITHUB_TOKEN`

Supplied by Actions. Not something you create. Each workflow declares the
narrowest set it needs:

```
tests.yml      contents: read                    pushes nothing
research.yml   contents: write                   commits research/, opens no issue
measure.yml    contents: write                   commits research/, opens no issue
propose.yml    contents: write, issues: write    commits queue/, opens one issue per segment
build.yml      contents: write, issues: write
launch.yml     contents: write, issues: write
reject.yml     contents: write, issues: write
```

`research.yml` and `measure.yml` do not get `issues: write`, and that is not an
oversight: they commit files and open nothing, so granting it would widen a
token for the two jobs that make outbound calls against ads nobody in this
repository chose. `tests/test_workflows.py` pins both exclusions by name, so
the next person cannot quietly widen one to make a test pass - which is the
shape that mistake usually takes.

The token's no-recursion rule is scoped to *who acted*, so a workflow removing
`go` is correctly silent while a human re-adding it fires normally. No PAT is
needed for approval.

---

## Labels the workflows expect

Create these four once, at **Issues > Labels**. A workflow that adds a label
which does not exist fails the step.

| Label | Meaning |
|---|---|
| `go` | You approve. Added by a human, **twice** - once per tap |
| `no` | You reject. `reject.yml` drops the job and returns the segment to the backlog |
| `stage:copy` | Awaiting copy approval. Mirrors `queue/proposed/`. Applied by `engine.approval open` |
| `stage:creative` | Awaiting launch. Mirrors `queue/built/`. Swapped in by `build.yml` |

The stage labels are a human-readable mirror of the job's directory and are
**never the authority on stage**. The two `go` taps are byte-identical in the
webhook payload, so only `queue/<stage>/` can tell them apart - and a workflow
that finds the label and the directory disagreeing stops rather than guessing.
That is why `build.yml` resolves the issue with `--expect proposed` even though
it has already filtered on `stage:copy`.

---

## Before you trust the cron

Nothing in this repository has ever run against a live key or a live token.
Every test injects a transport or a stub client and none needs a credential, so
the first real run is also the first proof. Do these in order, by hand, before
letting a schedule fire unattended.

1. **`python -m engine.oauth --status`**, with the two names in your
   environment. It makes no network call. It should say the secret is set, the
   date is readable, and most of the 60 days are left. If it exits nonzero, fix
   that before anything else - it is the only thing that can warn you later.

2. **`python -m engine.fanout --dry-run`.** No key, no token, no socket, writes
   nothing. It prints the seed file it read, how many searches that is, and the
   call spread against the budget. Read the numbers against `docs/COST.md`. The
   shipped seed file has both competitor pages commented out with blank ids on
   purpose, and the dry run says so as a skip note, not a failure.

3. **`python -m engine.discover --dry-run`** for the same plan at the discovery
   level - also tokenless and socketless - and then, with the token set, one
   real `python -m engine.discover --days 30 --json`. That is the first live Ad
   Library call in this repository's history. **A research run with `dry_run`
   ticked is not it**: `--dry-run` there opens nothing at all. What to look at
   in the response: the field set. `docs/AD-RESEARCH-SCOPE.md` §2.2 lists four
   targeting fields the reference is ambiguous about, and the first live
   response settles them.

4. **Read Meta's Ad Library API terms** before the first corpus record is
   committed, and take the decision in §8 on whether the record holds the
   creative text verbatim or only what was derived from it. The corpus is in a
   private repository either way; the decision is about what may be stored, not
   who can see it.

5. **`python -m engine.measure --dry-run --raw`**, once one ad is launched.
   It calls the API, prints each row's raw insights object, and writes nothing.
   Check it against the `TODO(integration): UNVERIFIED AGAINST A LIVE RESPONSE`
   block above `INSIGHT_FIELDS` in `engine/measure.py`: the field names, the
   string-typed numbers, `actions` where `action_type == "video_view"` as the
   3-second plays, and the `[0].value` shape of the video lists. All of it is
   from the reference as remembered, and none of it has met a live response.

6. **Run `propose.yml` once by hand** - Actions > propose > Run workflow. Two
   things cannot be tested any other way: `issues` events only trigger workflow
   files from the **default branch**, so `build.yml`, `reject.yml` and the
   label path are inert until merged, and the approval issue's rendering (and
   later the still's `?raw=1` link into a private repository) has to be
   confirmed in a browser and in GitHub Mobile by an authenticated viewer.

7. **Fill in the `own:` block** of `research/seeds.yaml` before trusting
   `measure.yml`. It is not a secret and does not belong on this page: a page
   id is public, that file is the hand-maintained record of what the engine
   watches, and git history is what says when it changed. Left blank, an own
   corpus record carries `page_id: ""` and the channel name `own` - true
   statements, just less useful ones.

**The Danish and Lithuanian copy is not a credential problem and it is not
optional.** Every `da` and `lt` field ships as `NEEDS_NATIVE_PROOFREAD` and the
writer never stamps anything else. A human replaces them before the ad runs in
either market. That is a gate in the approval flow, not a model's opinion.
