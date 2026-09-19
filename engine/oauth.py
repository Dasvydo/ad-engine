"""python -m engine.oauth --status

The Meta access token behind this repository's two Graph API reads - the Ad
Library archive that `engine/discover.py` searches for strangers' ads, and the
insights edge that `engine/measure.py` reads for our own - and the one hazard
that comes with keeping it in a repository secret.

THE DESIGN DECISION, and the reason this module exists as its own file: **a
Meta long-lived token expires 60 days after issue, and nothing a workflow can
do stops the stored one ageing.** Refreshing returns a NEW token valid 60 days
from the refresh - but a workflow can only refresh IN MEMORY. To write the new
token back into the GitHub secret it would need a PAT carrying
`secrets:write`, which is a credential that can rewrite every secret in the
repository, and this design deliberately refuses to hold one. So a refreshed
token would die with the process and THE STORED TOKEN KEEPS AGEING. Meta's own
documentation warns that integrations break silently here, and a module that
refreshed in memory and said nothing would be one of them.

So the token's age is tracked from a stored issue date, not from any provider
response: `meta_token()` WARNS LOUDLY from day 40 of 60 and REFUSES past day
60, before any socket opens. Here that is trivially true, because nothing in
this module can open one. That is the one place this differs from the module
it is ported from, `reel-engine/engine/oauth.py`, which refreshes an Instagram
token in memory to buy one run's worth of Meta vouching for it. There is
nothing equivalent to buy here: the exchange Meta documents for a Facebook
user token takes the app secret as a parameter, so it would put a SECOND
credential in the repository for a vouching that dies with the process, and
the consumers learn the same thing from the first call they make anyway. The
consumers own the transports. This module owns the clock and the scrub.

## What is assumed, said out loud

Sixty days is `reel-engine`'s experience with an Instagram token, carried over
because Meta publishes no fixed lifetime for a token used against the Ad
Library API (docs/AD-RESEARCH-SCOPE.md, section 2.2). The countdown makes a
wrong assumption loud rather than silent. If the real life is shorter, the
consumer's first refused call says so and the warning here fired late, which
is a bug to fix in one constant. If a System User token that does not expire
turns out to be accepted for both reads (section 3.12, unverified), this clock
is wrong in the SAFE direction: it refuses a working token on day 61 and names
the fix, and re-dating the variable is the workaround until
TOKEN_LIFETIME_DAYS is revisited.

## Nothing here is ever written down

No token is cached, to disk or anywhere else. A token is a credential; a
credential in a file is a credential in a backup, an artifact upload and a
`git status` away from the repository. Credentials are read from the
environment only - `os.environ`, never a file - one named helper each, each
raising a message that names the exact secret and where to set it. The
helpers raise rather than returning None, because every caller of these
needs the value: there is no path through discover or measure that runs
without a token.

## No secret is ever emitted

Not in a log line, not in a summary, not in an error message, not in
`--status` output. A name is fine and a day count is fine; a value never is.
Two mechanisms enforce it. First, no value is ever interpolated into a
message - the code has nowhere to leak from. Second, `_never_leak` wraps the
public entry point and scrubs the token, whole or in part, out of ANYTHING it
raises. That second line matters for one mistake in particular: a CREDENTIAL
pasted into the DATE variable's box, which is the kind of thing that happens
in the very screen where both are set. A date parser's own error echoes what
it was given, so `token_age_days` raises its refusal outside the handler
(nothing chained), and echoes an unreadable value back only when it is short
enough AND shaped like a typo rather than a credential (`_looks_opaque`).

That shape rule is load-bearing on its own, not belt to `_never_leak`'s
braces, and the distinction was learned the hard way: `_never_leak` scrubs
the values it is GIVEN, which is the access token and nothing else. When the
value in the wrong box is a different credential - the 32-character Meta app
secret from the same dashboard, say - the scrub list has nothing to cut it
against, and before `_looks_opaque` existed `--status` printed it in full
into the Actions job log. The failure here is silent and permanent: a
credential in a public Actions log is a credential an attacker has.

## The scrub is for the consumers too

`engine/discover.py` and `engine/measure.py` put the token in an
`Authorization: Bearer` header, and a transport that fails can raise with a
URL, a header or a body in its message - `http.client` itself does, on a
malformed header value. Each consumer wraps its transport in a local
`_scrubbed(token, work)` of its own rather than calling `_never_leak`, which
is this module's own wrapper and has no call site anywhere else. What has to
hold is that they all cut with the SAME definition of a leak, which is why
`engine/measure.py` calls `_redact` here instead of keeping a copy of it.

A consumer that keeps its own copy drifts, and the drift is invisible until
it is measured: a whole-value-only copy passes a 32-character slice of the
token through untouched where `_redact` cuts it, and Meta echoes slices. So
whether a consumer delegates is that consumer's own file to answer for, and
this docstring no longer claims that they do - it used to, and one of them
did not.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Declared because every module in this repository declares it and a reader
# looks for it. Nothing here reads or writes a file.
ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Names
#
# Every name this module reads, and nothing reads a name not listed here. No
# Google name: GEMINI_API_KEY belongs to engine/model.py and is not an OAuth
# credential.
# ---------------------------------------------------------------------------

META_ACCESS_TOKEN = "META_ACCESS_TOKEN"

# NOT a secret - a date. It is set as a repository VARIABLE (Settings >
# Secrets and variables > Actions > Variables), not a secret, for one reason
# that matters: a secret is write-only once saved, so an operator who rotates
# the token cannot see whether the date beside it was ever updated. As a
# variable the date is visible in the same screen, at the same moment, as the
# token is pasted - which is the only moment the pair can be kept honest. A
# committed config file would need a commit and a push at exactly that moment
# instead, and the two would drift. It is read from the environment like
# everything else here, so the read path is identical either way.
META_TOKEN_ISSUED = "META_TOKEN_ISSUED"

SECRET_NAMES = (META_ACCESS_TOKEN,)
VARIABLE_NAMES = (META_TOKEN_ISSUED,)

WHERE_TO_SET = (
    "Set it in GitHub > Settings > Secrets and variables > Actions > "
    "New repository secret."
)

WHERE_TO_SET_VARIABLE = (
    "Set it in GitHub > Settings > Secrets and variables > Actions > "
    "Variables > New repository variable. It is a date, not a secret."
)

# ---------------------------------------------------------------------------
# Lifetimes
# ---------------------------------------------------------------------------

# Assumed, not measured: see the module docstring. Sixty days from issue.
TOKEN_LIFETIME_DAYS = 60

# Day 40 of 60 leaves twenty days and - at this repository's weekly cadence -
# at least two more runs that shout before anything breaks. Warning at day 55
# could leave a single run to catch it, and a run nobody watched.
WARN_FROM_DAY = 40

# An issue date up to a day in the future is an operator east of UTC writing
# today's date; further ahead is a typo, and a typo here would hold the age
# below the warning threshold forever. See meta_token.
FUTURE_SLACK_DAYS = 1.0

# The longest thing that can be a date this module reads:
# "2026-08-01T00:00:00.000000+00:00" is 32 characters. A value in the date
# variable longer than that is not a mistyped date; the likeliest thing it is
# is the token, pasted into the wrong box, and echoing "the first 40
# characters of it" back would be a leak. So an unreadable value is echoed
# only when it is short enough to be a date, and described by length otherwise.
#
# Length ALONE is not enough, and that was measured rather than reasoned:
# a Meta app secret is exactly 32 hexadecimal characters, so it sat on the
# permissive side of this ceiling and `--status` printed it in full. It is the
# other credential on the same Meta dashboard the rotation steps send the
# operator to, one box over from this one. See _looks_opaque for the second
# half of the rule, which is what actually separates a credential from a typo.
MAX_DATE_CHARS = 32

REDACTED = "<redacted>"

# Below this length a "secret" is not a credential, and blanket-replacing it
# would turn a message into confetti and hide the real problem.
MIN_REDACTABLE = 4

# A provider that echoes only PART of a token has leaked it just as
# completely, so any run of this many characters lifted from a credential is
# cut too. Twelve is long enough that no English phrase, field name or URL
# fragment collides with an opaque random token by accident.
MIN_REDACTED_RUN = 12

ROTATE_STEPS = (
    "Rotate it by hand: mint a fresh long-lived token for the same Meta app "
    "(docs/SECRETS.md has the steps), then update BOTH %s (Actions > Secrets) "
    "and %s (Actions > Variables, set to today in YYYY-MM-DD) in the same "
    "visit. Updating one without the other is how this breaks silently."
) % (META_ACCESS_TOKEN, META_TOKEN_ISSUED)

# Why the token cannot simply refresh itself. Said in full wherever the
# operator meets the ageing problem, because "just automate it" is the first
# thing anybody reading the warning will think.
NO_WRITEBACK = (
    "A refresh inside a run would only live in memory: writing a new token "
    "back into the repository secret would need a PAT carrying secrets:write "
    "- a credential that can rewrite every secret here - which this design "
    "deliberately does not hold. So the STORED token keeps ageing, and only "
    "a human can replace it."
)


class OAuthError(RuntimeError):
    """Anything that stops a token being obtained. Never carries a value."""


class MissingCredential(OAuthError):
    """A secret or variable is absent, empty, or unreadable as written."""


class TokenExpired(OAuthError):
    """The stored credential is past its life. Only a human can fix it."""


# ---------------------------------------------------------------------------
# Never emit a value
# ---------------------------------------------------------------------------


def _redact(text: str, values) -> str:
    """Cut every known credential, whole or in part, out of `text`.

    The second line of defence. Nothing in this module interpolates a value
    into a message in the first place - but a transport can, and Meta does:
    the Graph API answers a bad token with "Invalid OAuth access token" and
    sometimes the token beside it. That body is exactly what an operator
    needs to read, so it is kept and scrubbed rather than dropped.

    Fragments are cut as well as whole values, because half a token in a
    public log is still half a token more than anyone should have. See
    MIN_REDACTED_RUN and MIN_REDACTABLE for the two floors.
    """
    for value in values:
        if not isinstance(value, str) or len(value) < MIN_REDACTABLE:
            continue
        text = text.replace(value, REDACTED)
        if len(value) > MIN_REDACTED_RUN:
            text = _cut_runs(text, value)
    return text


def _cut_runs(text: str, value: str) -> str:
    """Replace every run of >= MIN_REDACTED_RUN characters taken from `value`.

    One greedy left-to-right pass: where a window of the text appears inside
    the credential, it is extended as far as it still does and the whole run
    goes. Longest-match-first matters - cutting a short window first would
    chop a longer echo into pieces and leave them behind.
    """
    out: list[str] = []
    index, end = 0, len(text)
    while index < end:
        stop = index + MIN_REDACTED_RUN
        if stop <= end and text[index:stop] in value:
            while stop < end and text[index:stop + 1] in value:
                stop += 1
            out.append(REDACTED)
            index = stop
        else:
            out.append(text[index])
            index += 1
    return "".join(out)


def _looks_opaque(text: str) -> bool:
    """True when `text` carries an unbroken alphanumeric run long enough to be
    a credential rather than a mistyped date.

    MEASURED against the values an operator actually holds on the two screens
    this module names: a Meta app secret is 32 hexadecimal characters, a
    long-lived access token about 200, GEMINI_API_KEY 39 - every one of them a
    single unbroken run of letters and digits. Every date a human writes has a
    separator inside it before it gets that long: "2026-13-45", "01/08/2026",
    "1 August 2026", "last tuesday", "60", "whenever". So the floor already
    used for cutting partial echoes, MIN_REDACTED_RUN, tells the two apart -
    and it does it without depending on a length ceiling, which a short
    credential walks straight through.

    The cost is honest and small: a typo written as one long word
    ("August012026") is described by length instead of quoted back. The
    message still names the variable and says what to type.
    """
    run = 0
    for char in text:
        if char.isalnum():
            run += 1
            if run >= MIN_REDACTED_RUN:
                return True
        else:
            run = 0
    return False


def _never_leak(values, work):
    """Run `work()`; scrub `values` out of anything it raises. Returns its value.

    `values` is a LIVE list, not a snapshot: a value that only exists partway
    through - the token, once the environment has been read - is appended to
    it by `work` and is still scrubbed from an error raised after that point.

    EVERY exception is converted, not only OAuthError. `work` may be a
    consumer's transport call, which is arbitrary code and may raise anything,
    with anything in it; and "this raises only OAuthError subclasses" is a far
    easier promise to rely on than a list of what else might escape. An
    OAuthError keeps its own type, scrubbed; any other Exception becomes a
    plain OAuthError that names the original type so the diagnosis survives.

    BELOW Exception the promise is narrower, and saying so precisely is the
    point. KeyboardInterrupt, SystemExit and asyncio.CancelledError derive
    from BaseException, and `except Exception` sails past all three - measured:
    an asyncio-timeout transport, an ordinary thing to write against the seam
    this wrapper exists for, raises CancelledError, and its message and its
    `__context__` came out with the token in them. So they are caught too, but
    they KEEP THEIR OWN TYPE: turning Ctrl-C into an OAuthError would make a
    hung run need a second Ctrl-C to die, and rebuilding SystemExit from a
    string would turn `SystemExit(2)` into exit status 1. The args are
    scrubbed element by element instead, which leaves an integer exit code
    alone, and the replacement is raised out here like every other, so the
    unscrubbed original goes with the chain. A caller's `except OAuthError`
    does not catch these, and should not: an abort is not a credential problem.

    The replacement is ALWAYS a fresh object, raised AFTER the except block,
    and both halves of that are load-bearing rather than stylistic. Raising
    inside a handler makes Python chain the original onto the new exception
    as `__context__`, where the unscrubbed message stays readable to anything
    that walks the chain - `raise ... from None` only hides it from the
    printed traceback, it does not remove it. And re-raising the SAME object
    would carry whatever `__context__` it already had from inside `work`,
    which is how a date parser's "Invalid isoformat string: '<the token>'"
    would ride out on the back of a perfectly clean refusal. A fresh object
    raised out here has nothing attached and the original is unreachable.
    """
    try:
        return work()
    except OAuthError as exc:
        clean = _redact(str(exc), values)
        try:
            error = type(exc)(clean)
        except TypeError:  # a subclass with its own __init__; still an OAuthError
            error = OAuthError(clean)
    except Exception as exc:
        error = OAuthError(_redact("%s: %s" % (type(exc).__name__, exc), values))
    except BaseException as exc:  # noqa: BLE001 - deliberate; see above
        try:
            error = type(exc)(*(
                _redact(arg, values) if isinstance(arg, str) else arg
                for arg in exc.args
            ))
        except Exception:
            # A subclass that will not take its own args back. Converting is
            # the safe direction: a scrubbed OAuthError beats whatever that
            # object was still carrying.
            error = OAuthError(_redact("%s: %s" % (type(exc).__name__, exc), values))
    raise error


def on_warning(message: str) -> None:
    """Where every warning this module raises ends up. The warning seam.

    stderr, so a workflow shows it in the step log without it being mistaken
    for the module's output. Replace this module attribute (or pass
    `on_warning=` to `meta_token`) to collect warnings instead.
    """
    print(message, file=sys.stderr)


def _warn(message: str, override=None) -> None:
    # Reads the module attribute by name so a test that monkeypatches
    # `oauth.on_warning` is seen, and so the keyword argument of the same
    # name in meta_token does not shadow the default.
    (override or on_warning)(message)


# ---------------------------------------------------------------------------
# Credentials, one named helper each
#
# A module-level function per credential, os.environ only, no file, no
# default. Each raises where a missing value would otherwise become a failed
# call three modules downstream with Meta's words and nobody's fix.
# ---------------------------------------------------------------------------


def _from_env(name: str, advice: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        # An entirely-whitespace value is absent: nobody meant to set it.
        raise MissingCredential("%s is not set. %s" % (name, advice))
    return value


def meta_access_token() -> str:
    """The stored long-lived token, exactly as stored - or a refusal.

    A token is opaque and this module does not get to decide what is in it,
    with one exception it can be sure of: whitespace. A line break or a space
    inside the value is the paste, not the token, and a header carrying one
    is rejected by http.client with the WHOLE VALUE in the error message
    (measured on 3.11: "ValueError: Invalid header value b'Bearer ...\\n'").
    So it is refused here, by name, before it can reach a header.
    """
    value = _from_env(
        META_ACCESS_TOKEN,
        "It is a long-lived Meta access token for the app that has the Ad "
        "Library API product added (and, for engine/measure.py, ads_read on "
        "our own ad account); docs/SECRETS.md has the steps. %s Set %s to "
        "the same day, as a variable." % (WHERE_TO_SET, META_TOKEN_ISSUED),
    )
    if value != "".join(value.split()):
        raise MissingCredential(
            "%s contains whitespace - a line break or a space, usually from "
            "the paste - and a token with one in it cannot travel in an "
            "Authorization header. Paste it again with nothing around it. %s"
            % (META_ACCESS_TOKEN, WHERE_TO_SET)
        )
    return value


def meta_token_issued() -> str:
    """The day the stored long-lived token was issued, as YYYY-MM-DD."""
    return _from_env(
        META_TOKEN_ISSUED,
        "It is the day %s was issued, as YYYY-MM-DD - the only way to know "
        "how much of Meta's %d days is left, because a token does not carry "
        "its own age. %s"
        % (META_ACCESS_TOKEN, TOKEN_LIFETIME_DAYS, WHERE_TO_SET_VARIABLE),
    )


# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------


def _utc(today) -> datetime:
    """`today` as an aware UTC datetime; None is the clock, naive is UTC."""
    if today is None:
        return datetime.now(timezone.utc)
    if isinstance(today, datetime):
        return today if today.tzinfo is not None else today.replace(tzinfo=timezone.utc)
    if isinstance(today, date):
        return datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    raise TypeError("today must be a datetime or a date, not %s" % type(today).__name__)


def token_age_days(issued: str, today: datetime | None = None) -> float:
    """Days between the stored issue date and `today`. A float, may be negative.

    Accepts a bare date ("2026-08-01", read as UTC midnight) or any ISO-8601
    timestamp, with or without an offset; a naive one is read as UTC. A date
    is what an operator can actually type into a repository variable without
    getting it wrong, and one day of resolution is ample against a 60-day
    life. `today` pins the clock; None reads it.

    A value that cannot be read raises MissingCredential rather than
    ValueError: an unset date and a mistyped one need the same fix, in the
    same screen, and one error message serves both. The refusal is raised
    outside the parser's except block, so the parser's own error - which
    echoes the whole value it was given - is not chained onto it, and the
    value is quoted back only when it is short enough AND shaped like a typo
    rather than a credential (MAX_DATE_CHARS and _looks_opaque). Anything else
    is described by its length, which is all an operator needs to recognise
    what they pasted.
    """
    text = (issued or "").strip()
    if not text:
        raise MissingCredential(
            "%s is empty. %s" % (META_TOKEN_ISSUED, WHERE_TO_SET_VARIABLE)
        )
    moment = None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    if moment is None:
        if len(text) <= MAX_DATE_CHARS and not _looks_opaque(text):
            what = "%r" % text
        else:
            what = ("a %d-character value (a credential pasted into the wrong "
                    "box?)" % len(text))
        raise MissingCredential(
            "%s is %s, which is not a date this can read. Write the day the "
            "token was issued as YYYY-MM-DD, for example 2026-08-01. %s"
            % (META_TOKEN_ISSUED, what, WHERE_TO_SET_VARIABLE)
        )
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (_utc(today) - moment).total_seconds() / 86400.0


def meta_token(*, on_warning=None, today=None) -> str:
    """A usable Meta access token, or a refusal that says what to do.

    The order here is the point.

    1. AGE FIRST. A token past 60 days cannot read anything, so the refusal
       is raised here rather than waiting for Meta to answer with an error
       that names no secret and no fix - the same posture engine/discover.py
       takes with its quota ledger: a call that cannot succeed is never made.
       No socket is involved at any step; see the module docstring.
    2. A DATE IN THE FUTURE IS REFUSED, not read as a young token. Left
       unchecked this is the worst failure mode in the module: an age that
       never reaches 40 means a warning that never fires, and the first sign
       of trouble is a dead integration on day 61.
    3. WARN from day 40 of 60, every call, through the warning seam. What the
       warning asks for is the one thing only a human can do - see
       NO_WRITEBACK - which is why it does not go away.
    4. Return the stored token, untouched.

    Everything runs inside `_never_leak` with the token in its scrub list from
    the moment it is read, so no refusal - including one about a date variable
    that turns out to hold the token - can carry the value.
    """
    values: list[str] = []

    def work() -> str:
        token = meta_access_token()
        # Appended before anything else can fail, so a complaint about the
        # date cannot be the thing that prints the token.
        values.append(token)
        issued = meta_token_issued()
        age = token_age_days(issued, today)

        if age < -FUTURE_SLACK_DAYS:
            raise MissingCredential(_future_refusal(issued, age))
        if age > TOKEN_LIFETIME_DAYS:
            raise TokenExpired(_expired_refusal(issued, age))
        if age >= WARN_FROM_DAY:
            _warn(_ageing_warning(issued, age), on_warning)
        return token

    return _never_leak(values, work)


def _future_refusal(issued: str, age: float) -> str:
    return (
        "%s is %s, which is %.0f days in the FUTURE. The ageing clock for %s "
        "cannot run from a date that has not happened, so the expiry warning "
        "would never fire. Set it to the day the token was actually issued, "
        "as YYYY-MM-DD. %s"
        % (META_TOKEN_ISSUED, issued.strip(), -age, META_ACCESS_TOKEN,
           WHERE_TO_SET_VARIABLE)
    )


def _expired_refusal(issued: str, age: float) -> str:
    return (
        "%s was issued %s, %.0f days ago, and Meta expires a long-lived token "
        "%d days after issue. It is dead: no call will be answered with it and "
        "no refresh can revive it. %s %s"
        % (META_ACCESS_TOKEN, issued.strip(), age, TOKEN_LIFETIME_DAYS,
           ROTATE_STEPS, NO_WRITEBACK)
    )


def _ageing_warning(issued: str, age: float) -> str:
    """Loud, dated, and specific about what only a human can do."""
    left = TOKEN_LIFETIME_DAYS - age
    return (
        "WARNING: %s is %.0f days old and Meta expires it at %d - %.0f DAYS "
        "LEFT (issued %s). %s %s"
        % (META_ACCESS_TOKEN, age, TOKEN_LIFETIME_DAYS, left, issued.strip(),
           NO_WRITEBACK, ROTATE_STEPS)
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def status(out=None, today=None) -> int:
    """What is set and how much of Meta's 60 days is left. Names, never values.

    Exit 0 only when there is a token, a readable date, and more than
    TOKEN_LIFETIME_DAYS - WARN_FROM_DAY days to go. Everything else is 1, so a
    workflow step can gate on it.

    The one place os.environ is read outside the named helpers, because the
    helpers raise on the first missing name and the whole point here is to
    list them ALL. Presence only for the secret. The variable is a date and a
    date is not a value worth hiding - but it is printed only AFTER it has
    parsed as one, because the thing most likely to be in that box when it is
    not a date is the token.
    """
    out = out or sys.stdout
    say = lambda line="": print(line, file=out)

    token = os.environ.get(META_ACCESS_TOKEN)
    have_token = bool(token and token.strip())
    clean_token = have_token and token == "".join(token.split())
    values = [token] if have_token else []

    if not have_token:
        token_state = "NOT SET"
    elif not clean_token:
        # What meta_access_token() refuses, said here so --status does not
        # report healthy on a token the next run will not accept.
        token_state = "set, but contains whitespace (a line break or space from the paste)"
    else:
        token_state = "set"

    say("secrets (Actions > Secrets):")
    say("  %-20s %s" % (META_ACCESS_TOKEN, token_state))
    say("variables (Actions > Variables):")

    issued = os.environ.get(META_TOKEN_ISSUED)
    if not issued or not issued.strip():
        say("  %-20s NOT SET" % META_TOKEN_ISSUED)
        say()
        say("Meta token age: unknown - %s is not set, so nothing here can "
            "warn you before the token dies on day %d. %s"
            % (META_TOKEN_ISSUED, TOKEN_LIFETIME_DAYS, WHERE_TO_SET_VARIABLE))
        return 1

    try:
        age = token_age_days(issued, today)
    except MissingCredential as exc:
        say("  %-20s set, but not a readable date" % META_TOKEN_ISSUED)
        say()
        say(_redact(str(exc), values))
        return 1

    say("  %-20s %s" % (META_TOKEN_ISSUED, issued.strip()))
    say()

    if age < -FUTURE_SLACK_DAYS:
        say(_future_refusal(issued, age))
        return 1
    if age > TOKEN_LIFETIME_DAYS:
        say("Meta token: %.0f days old, EXPIRED %.0f days ago (issued %s)."
            % (age, age - TOKEN_LIFETIME_DAYS, issued.strip()))
        say("EXPIRED. %s %s" % (ROTATE_STEPS, NO_WRITEBACK))
        return 1

    # A date a few hours ahead (an operator east of UTC) is a token 0 days
    # old, not -0 days old.
    shown = max(age, 0.0)
    say("Meta token: %.0f days old, %.0f of %d left (issued %s)."
        % (shown, TOKEN_LIFETIME_DAYS - shown, TOKEN_LIFETIME_DAYS, issued.strip()))
    if age >= WARN_FROM_DAY:
        say(_ageing_warning(issued, age))
        return 1
    if not have_token:
        say("%s is not set: the date is fine but there is no token to age. %s"
            % (META_ACCESS_TOKEN, WHERE_TO_SET))
        return 1
    if not clean_token:
        say("%s contains whitespace, and meta_token() will refuse it: a token "
            "with a line break or a space in it cannot travel in an "
            "Authorization header. Paste it again with nothing around it. %s"
            % (META_ACCESS_TOKEN, WHERE_TO_SET))
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m engine.oauth",
        description="The Meta access token: what is set and how much of its "
                    "%d days is left. Never prints a value." % TOKEN_LIFETIME_DAYS,
    )
    parser.add_argument(
        "--status", action="store_true",
        help="which names are set and how many of Meta's %d days are left"
             % TOKEN_LIFETIME_DAYS,
    )
    args = parser.parse_args(argv)
    if not args.status:
        parser.error("nothing to do; pass --status")

    try:
        return status()
    except OAuthError as exc:
        # status() answers every case it knows with a line and an exit code;
        # this is the one except clause a caller of this module ever needs.
        # Scrubbed on the way out even though an OAuthError from this module
        # never carries a value: this is the last line before a job log, and
        # nothing downstream masks a repository variable.
        token = os.environ.get(META_ACCESS_TOKEN)
        print(_redact(str(exc), [token] if token else []), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
