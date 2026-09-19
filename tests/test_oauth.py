"""The Meta token: one clock that must be loud, and one value that must not leak.

Three properties carry this file and the rest is bookkeeping.

**No secret is ever emitted.** That is the criterion worth attacking, so this
file attacks it: `test_no_failure_path_emits_a_secret` walks every failure
this module can be driven into - a missing secret, a missing or unreadable
date, an expired token, a future-dated one, the token PASTED INTO THE DATE
VARIABLE by mistake, and a consumer's transport that raises with the token in
a URL, a header, a body or on its own - and for each one checks stdout,
stderr, `str(exc)`, `repr(exc)`, `exc.args`, the whole formatted traceback AND
the exception's `__context__` chain. The chain matters twice over: `raise ...
from None` hides the original from a printed traceback but leaves the object
hanging off the new one, and `datetime.fromisoformat`'s own ValueError echoes
the whole string it was given. engine/oauth.py raises a fresh replacement
outside every except block for exactly this reason, and `surfaces` is what
proves it.

**The stored token ages and nothing here can stop it.** A Meta token dies 60
days after issue and CANNOT be renewed in place - a run could refresh it in
memory but cannot write the new value into a repository secret - so the tests
pin the two things that makes non-negotiable: a loud warning from day 40, and
a refusal past day 60. Every age is arithmetic against a pinned `today=`, so
no test here drifts with the calendar.

**Every test is offline.** An autouse fixture deletes both names from the
environment and makes `socket.socket` explode, and one test parses the module
and asserts it imports nothing that could open one. A test that reached the
network or picked up a real secret would fail rather than pass quietly.
"""
import ast
import asyncio
import io
import socket
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine import oauth


# ---------------------------------------------------------------------------
# A fake credential. Long, distinctive, and obviously not real - it is the
# needle the leak test goes looking for in every haystack.
# ---------------------------------------------------------------------------

TOKEN = "EAAB0FAKEmetaTOKENneverLogMe00112233445566778899aabbcc"

# The OTHER credential an operator holds while setting these two boxes, and
# the one this suite used to be structurally unable to see. A Meta app secret
# is exactly 32 hexadecimal characters - the same length as the longest
# timestamp token_age_days can read - so it passed the length rule and was
# printed in full. It is fabricated, and this repository deliberately does not
# store a real one (see engine/oauth.py's module docstring), but the operator
# handles it on the same dashboard the rotation steps send them to.
APP_SECRET = "b2f4c8a19e7d30516cba8f2e4d9c7a01"

# Everything the leak tests hunt for. A second entry here is the point: with
# only the token in it, nothing in this file could notice a DIFFERENT
# credential being emitted, and `_never_leak`'s scrub list cannot cut one.
SECRET_VALUES = {"meta token": TOKEN, "meta app secret": APP_SECRET}

# Every age in this file is relative to this instant, not the clock.
TODAY = datetime(2026, 9, 18, 6, 0, 0, tzinfo=timezone.utc)


def issued(days_ago: float, today: datetime = TODAY) -> str:
    """An issue date exactly `days_ago` before `today`, as an operator might write it."""
    when = today - timedelta(days=days_ago)
    return when.strftime("%Y-%m-%dT%H:%M:%S+00:00")


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    """Nothing in this file may see a real secret."""
    for name in oauth.SECRET_NAMES + oauth.VARIABLE_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every socket in the process explodes. A test that dials out fails."""
    def boom(*args, **kwargs):
        raise AssertionError("this test tried to open a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


@pytest.fixture
def credentials(monkeypatch):
    """The secret set to a fake value, and a ten-day-old issue date."""
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(10))


@pytest.fixture
def warnings(monkeypatch):
    """Collect what goes to the warning seam instead of printing it."""
    collected: list[str] = []
    monkeypatch.setattr(oauth, "on_warning", collected.append)
    return collected


# ---------------------------------------------------------------------------
# The contract another agent codes against
# ---------------------------------------------------------------------------


def test_the_module_exposes_the_pinned_contract():
    assert oauth.META_ACCESS_TOKEN == "META_ACCESS_TOKEN"
    assert oauth.META_TOKEN_ISSUED == "META_TOKEN_ISSUED"
    assert oauth.TOKEN_LIFETIME_DAYS == 60
    assert oauth.WARN_FROM_DAY == 40
    assert callable(oauth.token_age_days)
    assert callable(oauth.meta_token)
    assert callable(oauth.status)
    assert callable(oauth.main)
    assert callable(oauth.on_warning)


@pytest.mark.parametrize("error", [oauth.MissingCredential, oauth.TokenExpired])
def test_every_failure_is_an_oautherror_and_a_runtimeerror(error):
    # A caller that wants one except clause gets one; a caller that wants to
    # tell "go set a secret" from "only a human can fix this" gets two.
    assert issubclass(error, oauth.OAuthError)
    assert issubclass(oauth.OAuthError, RuntimeError)


def test_every_name_it_reads_is_listed_and_is_meta():
    assert oauth.SECRET_NAMES == ("META_ACCESS_TOKEN",)
    assert oauth.VARIABLE_NAMES == ("META_TOKEN_ISSUED",)


def test_the_names_collide_with_nothing_else_in_the_contract():
    # docs/CONTRACTS.md's secrets table. engine/model.py owns the Gemini
    # names; build.yml owns the PAT; the workflows own GITHUB_TOKEN.
    taken = {"GEMINI_API_KEY", "GOOGLE_API_KEY", "REEL_ENGINE_TOKEN", "GITHUB_TOKEN"}
    assert taken.isdisjoint(oauth.SECRET_NAMES + oauth.VARIABLE_NAMES)


def test_there_is_no_google_and_no_instagram_here():
    # The Meta half of the sibling module, and only that half.
    foreign = [name for name in dir(oauth)
               if "google" in name.lower() or "instagram" in name.lower()
               or "youtube" in name.lower()]
    assert foreign == []


def test_the_warning_window_leaves_more_than_one_run_to_act():
    # At a weekly cadence, warning at day 40 of 60 gives at least two more
    # shouting runs before anything breaks. Day 55 could give one, unwatched.
    assert oauth.TOKEN_LIFETIME_DAYS - oauth.WARN_FROM_DAY >= 14


# ---------------------------------------------------------------------------
# token_age_days: arithmetic against a pinned clock
# ---------------------------------------------------------------------------


def test_a_bare_date_is_read_as_utc_midnight():
    # TODAY is 06:00Z, so yesterday's midnight is 30 hours ago.
    assert oauth.token_age_days("2026-09-17", today=TODAY) == pytest.approx(1.25)


def test_a_full_timestamp_is_read_to_the_second():
    assert oauth.token_age_days(issued(45), today=TODAY) == pytest.approx(45.0)


def test_a_zulu_timestamp_is_accepted():
    assert oauth.token_age_days("2026-09-11T06:00:00Z", today=TODAY) == pytest.approx(7.0)


def test_an_offset_timestamp_is_not_read_as_utc():
    # An operator in UTC+02:00 writing 06:00 their time wrote 04:00Z, which is
    # two hours older than the same digits read as UTC.
    assert oauth.token_age_days(
        "2026-09-13T06:00:00+02:00", today=TODAY
    ) == pytest.approx(5.0 + 2 / 24)


def test_a_naive_today_is_read_as_utc():
    naive = TODAY.replace(tzinfo=None)
    assert oauth.token_age_days("2026-09-17", today=naive) == pytest.approx(1.25)


def test_a_bare_date_for_today_is_read_as_midnight():
    assert oauth.token_age_days("2026-09-17", today=date(2026, 9, 18)) == pytest.approx(1.0)


def test_the_age_is_a_float_so_a_caller_can_compare_it():
    assert isinstance(oauth.token_age_days(issued(3), today=TODAY), float)


def test_a_future_date_reads_as_a_negative_age():
    # The pure function stays honest; meta_token is what refuses.
    assert oauth.token_age_days(issued(-5), today=TODAY) == pytest.approx(-5.0)


def test_today_defaults_to_the_clock():
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    assert 1.0 <= oauth.token_age_days(yesterday) < 2.0


@pytest.mark.parametrize("written", ["", "   ", "1 August 2026", "2026-13-45",
                                     "last tuesday", "60"])
def test_a_date_nobody_can_read_says_what_to_type(written):
    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.token_age_days(written, today=TODAY)

    message = str(caught.value)
    assert oauth.META_TOKEN_ISSUED in message
    assert "YYYY-MM-DD" in message or "empty" in message
    assert "Variables" in message


def test_a_short_unreadable_value_is_echoed_so_the_typo_can_be_seen():
    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.token_age_days("1 August 2026", today=TODAY)

    assert "1 August 2026" in str(caught.value)


def test_a_value_too_long_to_be_a_date_is_described_not_echoed():
    # The likeliest thing in the date box that is not a date is the token.
    # Even the pure function, which cannot know the token's value, does not
    # echo forty characters of it.
    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.token_age_days(TOKEN, today=TODAY)

    message = str(caught.value)
    assert TOKEN not in message
    assert TOKEN[:oauth.MIN_REDACTED_RUN] not in message
    assert "%d-character" % len(TOKEN) in message
    assert "wrong box" in message


def test_the_unreadable_date_refusal_carries_no_chained_parser_error():
    # datetime.fromisoformat's ValueError echoes the whole input. Raised inside
    # its except block, that ValueError would hang off __context__ with the
    # value in it; raised outside, nothing is attached.
    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.token_age_days("whenever", today=TODAY)

    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


# ---------------------------------------------------------------------------
# meta_token: the ageing hazard, with no socket anywhere
# ---------------------------------------------------------------------------


def test_the_stored_token_is_returned_untouched(credentials):
    assert oauth.meta_token(today=TODAY) == TOKEN


def test_a_token_past_sixty_days_is_refused_and_names_the_fix(credentials, monkeypatch):
    # The same posture engine/discover.py takes with its quota ledger: a call
    # that cannot succeed is never made, and the refusal names the fix rather
    # than relaying an error from Meta that names nothing.
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(61))

    with pytest.raises(oauth.TokenExpired) as caught:
        oauth.meta_token(today=TODAY)

    message = str(caught.value)
    assert oauth.META_ACCESS_TOKEN in message
    assert oauth.META_TOKEN_ISSUED in message
    assert "61 days ago" in message
    assert "60 days after issue" in message
    assert "Rotate it by hand" in message
    assert "Actions > Variables" in message and "YYYY-MM-DD" in message


@pytest.mark.parametrize("age", [60.01, 75, 90, 400])
def test_every_age_past_sixty_is_refused(credentials, monkeypatch, age):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(age))

    with pytest.raises(oauth.TokenExpired):
        oauth.meta_token(today=TODAY)


def test_the_expiry_message_explains_why_it_cannot_fix_itself(credentials, monkeypatch):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(90))

    with pytest.raises(oauth.TokenExpired) as caught:
        oauth.meta_token(today=TODAY)

    # "Why doesn't it just refresh itself?" is the first thing anyone asks,
    # and the answer - a PAT with secrets:write - is the design decision.
    assert "secrets:write" in str(caught.value)


def test_a_token_dated_in_the_future_is_refused_rather_than_read_as_new(
    credentials, monkeypatch
):
    # The nastiest silent failure available here: an age that never reaches 40
    # is a warning that never fires, and the first sign is a dead integration.
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(-30))

    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.meta_token(today=TODAY)

    message = str(caught.value)
    assert "FUTURE" in message
    assert "30 days" in message
    assert oauth.META_TOKEN_ISSUED in message
    assert "YYYY-MM-DD" in message


@pytest.mark.parametrize("ahead", [0.1, 0.5, 0.9])
def test_a_date_under_a_day_ahead_is_tolerated(credentials, monkeypatch, ahead):
    # An operator east of UTC writing today's date is legitimately ahead of
    # UTC midnight. That is timezone arithmetic, not a typo.
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(-ahead))

    assert oauth.meta_token(today=TODAY) == TOKEN


def test_a_date_more_than_a_day_ahead_is_not(credentials, monkeypatch):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(-1.5))

    with pytest.raises(oauth.MissingCredential):
        oauth.meta_token(today=TODAY)


def test_a_missing_issue_date_refuses_rather_than_assuming_the_token_is_young(
    credentials, monkeypatch
):
    monkeypatch.delenv(oauth.META_TOKEN_ISSUED)

    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.meta_token(today=TODAY)

    message = str(caught.value)
    assert oauth.META_TOKEN_ISSUED in message
    # It is a Variable, and the message says so - and says it is not a secret,
    # because the screen that sets both puts them a tab apart.
    assert "Variables > New repository variable" in message
    assert "not a secret" in message
    assert "New repository secret" not in message


def test_a_missing_token_names_itself_and_where_to_set_it(credentials, monkeypatch):
    monkeypatch.delenv(oauth.META_ACCESS_TOKEN)

    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.meta_token(today=TODAY)

    message = str(caught.value)
    assert message.startswith("%s is not set" % oauth.META_ACCESS_TOKEN)
    assert "New repository secret" in message
    # And it says to set the date beside it, because the pair is the point.
    assert oauth.META_TOKEN_ISSUED in message


def test_a_whitespace_only_secret_is_treated_as_absent(credentials, monkeypatch):
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, "   \n ")

    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.meta_token(today=TODAY)

    assert "is not set" in str(caught.value)


@pytest.mark.parametrize("pasted", [TOKEN + "\n", " " + TOKEN, TOKEN[:20] + " " + TOKEN[20:]])
def test_a_token_with_whitespace_in_it_is_refused_by_name_before_it_reaches_a_header(
    credentials, monkeypatch, pasted
):
    # http.client rejects a header value with a line break in it - and puts
    # the whole value in its error message. Refuse it here instead.
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, pasted)

    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.meta_token(today=TODAY)

    message = str(caught.value)
    assert oauth.META_ACCESS_TOKEN in message
    assert "whitespace" in message
    assert TOKEN not in message
    assert TOKEN[:oauth.MIN_REDACTED_RUN] not in message


def test_with_both_missing_the_token_is_named_first(credentials, monkeypatch):
    # The token is read before the date so it is in the scrub list before
    # anything about the date can be said; with both missing, that order is
    # what the operator sees.
    monkeypatch.delenv(oauth.META_ACCESS_TOKEN)
    monkeypatch.delenv(oauth.META_TOKEN_ISSUED)

    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.meta_token(today=TODAY)

    assert oauth.META_ACCESS_TOKEN in str(caught.value)


# ---------------------------------------------------------------------------
# meta_token: the warning that has to be impossible to miss
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("age", [39, 39.99, 30, 10, 2, 0])
def test_a_young_token_warns_about_nothing(credentials, monkeypatch, warnings, age):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(age))
    oauth.meta_token(today=TODAY)

    assert warnings == []


@pytest.mark.parametrize("age", [40, 40.01, 45, 55, 59.9, 60])
def test_from_day_forty_every_call_warns(credentials, monkeypatch, warnings, age):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(age))

    assert oauth.meta_token(today=TODAY) == TOKEN
    assert len(warnings) == 1
    assert "WARNING" in warnings[0]


def test_day_forty_fires_and_day_thirty_nine_does_not(credentials, monkeypatch, warnings):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(39))
    oauth.meta_token(today=TODAY)
    assert warnings == []

    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(40))
    oauth.meta_token(today=TODAY)
    assert len(warnings) == 1
    assert "20 DAYS LEFT" in warnings[0]


def test_the_warning_says_how_many_days_are_left_and_what_to_do(
    credentials, monkeypatch, warnings
):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(45))
    oauth.meta_token(today=TODAY)

    text = warnings[0]
    assert "45 days old" in text
    assert "15 DAYS LEFT" in text
    assert oauth.META_ACCESS_TOKEN in text
    assert oauth.META_TOKEN_ISSUED in text
    assert "Rotate it by hand" in text
    # The reason a human has to do this by hand, stated where they meet it.
    assert "secrets:write" in text


def test_the_warning_goes_to_stderr_by_default(credentials, monkeypatch, capsys):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(50))
    oauth.meta_token(today=TODAY)

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    # stdout is a module's output. A warning is not output.
    assert captured.out == ""


def test_a_caller_can_take_the_warnings_itself(credentials, monkeypatch, capsys):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(50))
    collected: list[str] = []

    oauth.meta_token(on_warning=collected.append, today=TODAY)

    assert len(collected) == 1
    assert capsys.readouterr() == ("", "")


def test_a_healthy_call_says_nothing_at_all(credentials, capsys):
    oauth.meta_token(today=TODAY)

    assert capsys.readouterr() == ("", "")


def test_the_warning_never_carries_the_value(credentials, monkeypatch, warnings):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(50))
    oauth.meta_token(today=TODAY)

    assert TOKEN not in warnings[0]
    assert TOKEN[:oauth.MIN_REDACTED_RUN] not in warnings[0]


# ---------------------------------------------------------------------------
# NO SECRET IS EVER EMITTED
#
# The criterion worth attacking. Every failure this module can be driven into,
# and every failure a consumer's transport can hand it, checked against every
# surface a value could reach.
# ---------------------------------------------------------------------------


def surfaces(exc, captured) -> str:
    """Everywhere a value could show up from one failed call, as one string.

    The __context__ walk is the point of the whole helper. `raise X from None`
    stops the original printing in a traceback but leaves it attached to the
    new exception, where anything that walks the chain - a logger, a crash
    reporter, pytest's own -vv output - can still read it. engine/oauth.py
    raises a fresh, scrubbed replacement outside the except block so that
    nothing is attached at all, and this is what proves it.
    """
    found = [
        captured.out,
        captured.err,
        str(exc),
        repr(exc),
        repr(exc.args),
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    ]
    chained, depth = exc.__context__ or exc.__cause__, 0
    while chained is not None and depth < 20:
        found += [str(chained), repr(chained), repr(getattr(chained, "args", ()))]
        chained, depth = chained.__context__ or chained.__cause__, depth + 1
    return "\n".join(found)


def _meta():
    return lambda monkeypatch: oauth.meta_token(today=TODAY)


def _unset(name, then):
    def run(monkeypatch):
        monkeypatch.delenv(name)
        return then(monkeypatch)
    return run


def _dated(days, then):
    def run(monkeypatch):
        monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(days))
        return then(monkeypatch)
    return run


def _misdated(written, then):
    def run(monkeypatch):
        monkeypatch.setenv(oauth.META_TOKEN_ISSUED, written)
        return then(monkeypatch)
    return run


def _with_token(value, then):
    def run(monkeypatch):
        monkeypatch.setenv(oauth.META_ACCESS_TOKEN, value)
        return then(monkeypatch)
    return run


def _transport_raises(error):
    """What engine/discover.py or engine/measure.py could meet: a transport
    holding the token in a URL, a header or a body, and raising with it.

    The consumer takes the token from meta_token and wraps its call in
    _never_leak with that value in the scrub list. This is that wrapping.
    """
    def run(monkeypatch):
        token = oauth.meta_token(today=TODAY)

        def work():
            raise error

        return oauth._never_leak([token], work)
    return run


def _transport_raises_from_a_handler():
    """A transport that wraps its own failure: the token sits on __context__."""
    def run(monkeypatch):
        token = oauth.meta_token(today=TODAY)

        def work():
            try:
                raise ValueError("Invalid header value b'Bearer %s\\n'" % token)
            except ValueError:
                raise RuntimeError("request failed")

        return oauth._never_leak([token], work)
    return run


FAILURES = [
    # -- the credential is not there -------------------------------------
    ("meta/no token", _unset(oauth.META_ACCESS_TOKEN, _meta())),
    ("meta/no issue date", _unset(oauth.META_TOKEN_ISSUED, _meta())),
    ("meta/token has a line break", _with_token(TOKEN + "\n", _meta())),
    ("meta/token has a space inside", _with_token(TOKEN[:20] + " " + TOKEN[20:], _meta())),

    # -- the stored token has aged out -----------------------------------
    ("meta/expired", _dated(75, _meta())),
    ("meta/dated in the future", _dated(-40, _meta())),
    ("meta/unreadable date", _misdated("whenever", _meta())),

    # -- the token in the wrong box --------------------------------------
    ("meta/the token pasted into the date variable", _misdated(TOKEN, _meta())),
    ("meta/half the token pasted into the date variable",
     _misdated(TOKEN[:30], _meta())),
    # A credential SHORT enough to be a date. The scrub list holds the access
    # token and nothing else, so nothing here can cut this one: the shape
    # rule in token_age_days is the only thing between it and the job log.
    ("meta/the app secret pasted into the date variable",
     _misdated(APP_SECRET, _meta())),
    ("meta/the app secret in the date box with a date beside it",
     _misdated("2026-08-01 %s" % APP_SECRET, _meta())),
    ("meta/the token pasted into the date variable with a date beside it",
     _misdated("2026-08-01 %s" % TOKEN, _meta())),

    # -- a consumer's transport blew up, holding the token ----------------
    ("transport/raises with the url", _transport_raises(OSError(
        "GET https://graph.facebook.com/ads_archive?access_token=%s failed" % TOKEN))),
    ("transport/raises with the header", _transport_raises(ValueError(
        "Invalid header value b'Bearer %s\\n'" % TOKEN))),
    ("transport/raises a bare value", _transport_raises(ValueError(TOKEN))),
    ("transport/body echoes the token", _transport_raises(RuntimeError(
        '{"error":{"message":"Invalid OAuth access token: %s","code":190}}' % TOKEN))),
    ("transport/body echoes half the token", _transport_raises(RuntimeError(
        '{"error":{"message":"Invalid OAuth access token %s...","code":190}}'
        % TOKEN[:24]))),
    ("transport/raises an OAuthError of its own with the token in it",
     _transport_raises(oauth.TokenExpired("Meta says %s is dead" % TOKEN))),
    ("transport/raises from inside a handler", _transport_raises_from_a_handler()),
]


@pytest.mark.parametrize("name,run", FAILURES, ids=[n for n, _ in FAILURES])
def test_no_failure_path_emits_a_secret(name, run, credentials, capsys, monkeypatch):
    with pytest.raises(oauth.OAuthError) as caught:
        run(monkeypatch)

    haystack = surfaces(caught.value, capsys.readouterr())
    for label, value in SECRET_VALUES.items():
        assert value not in haystack, "%s leaked the %s" % (name, label)
    # A fragment is a leak too: half a token is half a token more than anyone
    # outside this process should ever have.
    for label, value in SECRET_VALUES.items():
        assert value[:oauth.MIN_REDACTED_RUN + 4] not in haystack, (
            "%s leaked the start of the %s" % (name, label))
        assert value[-(oauth.MIN_REDACTED_RUN + 4):] not in haystack, (
            "%s leaked the end of the %s" % (name, label))


@pytest.mark.parametrize("name,run", FAILURES, ids=[n for n, _ in FAILURES])
def test_every_failure_path_raises_an_oautherror_and_nothing_else(
    name, run, credentials, monkeypatch
):
    # The other half of the contract: a consumer needs one except clause, not
    # a list of everything an injected transport might have thrown.
    with pytest.raises(oauth.OAuthError):
        run(monkeypatch)


@pytest.mark.parametrize("name,run", FAILURES, ids=[n for n, _ in FAILURES])
def test_no_failure_path_chains_anything(name, run, credentials, monkeypatch):
    # Nothing attached at all, so there is nothing for a chain-walker to find.
    with pytest.raises(oauth.OAuthError) as caught:
        run(monkeypatch)

    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_a_redacted_message_still_says_what_went_wrong(credentials):
    # Scrubbing must not turn a diagnosis into a blank. What is cut is the
    # value; Meta's reason survives, and so does the type of what was raised.
    token = oauth.meta_token(today=TODAY)

    def work():
        raise OSError("GET graph.facebook.com/ads_archive with %s: 400 Invalid OAuth "
                      "access token" % token)

    with pytest.raises(oauth.OAuthError) as caught:
        oauth._never_leak([token], work)

    message = str(caught.value)
    assert message.startswith("OSError: ")
    assert "Invalid OAuth access token" in message
    assert oauth.REDACTED in message
    assert token not in message


def test_a_scrubbed_oautherror_keeps_its_type(credentials):
    token = oauth.meta_token(today=TODAY)

    def work():
        raise oauth.TokenExpired("Meta says %s is dead" % token)

    with pytest.raises(oauth.TokenExpired) as caught:
        oauth._never_leak([token], work)

    assert str(caught.value) == "Meta says %s is dead" % oauth.REDACTED


def test_never_leak_returns_what_work_returns():
    assert oauth._never_leak([TOKEN], lambda: 42) == 42


def test_the_scrub_list_is_live_not_a_snapshot():
    # A value that only exists partway through work is still scrubbed from an
    # error raised after that point.
    values: list[str] = []

    def work():
        values.append(TOKEN)
        raise RuntimeError("late: %s" % TOKEN)

    with pytest.raises(oauth.OAuthError) as caught:
        oauth._never_leak(values, work)

    assert TOKEN not in str(caught.value)


def test_the_leak_test_would_notice_a_leak():
    # A guard on the guard: if `surfaces` looked in the wrong places, every
    # assertion above would pass vacuously.
    leaked = RuntimeError("the token is %s" % TOKEN)
    captured = type("C", (), {"out": "", "err": ""})()

    assert TOKEN in surfaces(leaked, captured)


def test_the_leak_test_would_notice_a_leak_on_the_chain():
    try:
        try:
            raise ValueError("the token is %s" % TOKEN)
        except ValueError:
            raise RuntimeError("wrapped")
    except RuntimeError as wrapped:
        captured = type("C", (), {"out": "", "err": ""})()
        assert TOKEN in surfaces(wrapped, captured)


def test_a_short_value_is_not_blanket_replaced():
    # A two-character "secret" is not a credential, and cutting every
    # occurrence of one would shred the message that explains the failure.
    assert oauth._redact("nothing to do with it", ["it"]) == "nothing to do with it"


def test_a_fragment_of_the_value_is_cut_and_a_short_collision_is_not():
    scrubbed = oauth._redact("saw %s and also EAAB0FAKE" % TOKEN[10:40], [TOKEN])

    assert TOKEN[10:40] not in scrubbed
    assert oauth.REDACTED in scrubbed
    # Nine characters is below the run floor: an English word could do that.
    assert "EAAB0FAKE" in scrubbed


def test_none_in_the_scrub_list_is_skipped():
    assert oauth._redact("fine", [None, "", TOKEN]) == "fine"


# ---------------------------------------------------------------------------
# --status: names and days, never values
# ---------------------------------------------------------------------------


def run_status(today=TODAY) -> tuple[int, str]:
    out = io.StringIO()
    code = oauth.status(out=out, today=today)
    return code, out.getvalue()


def test_status_is_content_with_a_young_token(credentials):
    code, printed = run_status()

    assert code == 0
    assert "META_ACCESS_TOKEN    set" in printed
    assert issued(10) in printed
    assert "10 days old, 50 of 60 left" in printed


def test_status_reports_the_warning_band_with_a_nonzero_exit(credentials, monkeypatch):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(45))

    code, printed = run_status()

    assert code == 1
    assert "45 days old, 15 of 60 left" in printed
    assert "WARNING" in printed and "15 DAYS LEFT" in printed


def test_status_reports_an_expired_token(credentials, monkeypatch):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(75))

    code, printed = run_status()

    assert code == 1
    assert "75 days old, EXPIRED 15 days ago" in printed
    assert "Rotate it by hand" in printed


def test_status_refuses_a_future_date(credentials, monkeypatch):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(-30))

    code, printed = run_status()

    assert code == 1
    assert "FUTURE" in printed


def test_status_shows_a_date_a_few_hours_ahead_as_zero_days_old(credentials, monkeypatch):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(-0.5))

    code, printed = run_status()

    assert code == 0
    assert "0 days old, 60 of 60 left" in printed
    assert "-0 days" not in printed


def test_status_says_what_is_missing_without_guessing():
    code, printed = run_status()

    assert code == 1
    assert printed.count("NOT SET") == len(oauth.SECRET_NAMES) + len(oauth.VARIABLE_NAMES)
    assert "%s is not set" % oauth.META_TOKEN_ISSUED in printed
    assert "New repository variable" in printed


def test_status_with_a_date_but_no_token_is_not_healthy(credentials, monkeypatch):
    monkeypatch.delenv(oauth.META_ACCESS_TOKEN)

    code, printed = run_status()

    assert code == 1
    assert "META_ACCESS_TOKEN    NOT SET" in printed
    assert "New repository secret" in printed


def test_status_does_not_call_a_token_with_a_line_break_healthy(credentials, monkeypatch):
    # meta_token() refuses it, so --status must not say "set" and exit 0.
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN + "\n")

    code, printed = run_status()

    assert code == 1
    assert "contains whitespace" in printed
    assert TOKEN not in printed
    assert TOKEN[:oauth.MIN_REDACTED_RUN] not in printed


def test_status_with_an_unreadable_date_says_what_to_type(credentials, monkeypatch):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, "1 August 2026")

    code, printed = run_status()

    assert code == 1
    assert "not a readable date" in printed
    assert "YYYY-MM-DD" in printed


@pytest.mark.parametrize("secret_set", [True, False])
def test_status_never_prints_the_token_pasted_into_the_date_variable(
    monkeypatch, secret_set
):
    # The variable's value is printed only once it has parsed as a date. With
    # the secret set, the scrub knows the value; without it, the length rule
    # in token_age_days is what keeps it off the screen.
    if secret_set:
        monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, TOKEN)

    code, printed = run_status()

    assert code == 1
    assert TOKEN not in printed
    assert TOKEN[:oauth.MIN_REDACTED_RUN] not in printed


@pytest.mark.parametrize("age", [10, 45, 75, -30, -0.5])
def test_status_prints_no_value_in_any_state(credentials, monkeypatch, age):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(age))

    _, printed = run_status()

    assert TOKEN not in printed
    assert TOKEN[:oauth.MIN_REDACTED_RUN] not in printed


def test_status_writes_to_out_and_nowhere_else(credentials, capsys):
    run_status()

    assert capsys.readouterr() == ("", "")


def test_status_defaults_to_the_clock(monkeypatch):
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED,
                       issued(45, today=datetime.now(timezone.utc)))
    out = io.StringIO()

    assert oauth.status(out=out) == 1
    assert "45 days old" in out.getvalue()


# ---------------------------------------------------------------------------
# The CLI
# ---------------------------------------------------------------------------


def now_issued(days_ago: float) -> str:
    """main() has no today=, so its tests date the token against the clock."""
    return issued(days_ago, today=datetime.now(timezone.utc))


def test_the_cli_reports_the_age_without_printing_a_value(monkeypatch, capsys):
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, now_issued(45))

    assert oauth.main(["--status"]) == 1

    printed = capsys.readouterr().out
    assert "45 days old" in printed and "15 of 60 left" in printed
    assert TOKEN not in printed
    assert "set" in printed


def test_the_cli_is_content_with_a_young_token(monkeypatch, capsys):
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, now_issued(10))

    assert oauth.main(["--status"]) == 0
    assert "50 of 60 left" in capsys.readouterr().out


def test_the_cli_exits_nonzero_when_nothing_is_set(capsys):
    assert oauth.main(["--status"]) == 1
    assert "NOT SET" in capsys.readouterr().out


def test_the_cli_exits_nonzero_on_an_expired_token(monkeypatch, capsys):
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, now_issued(61))

    assert oauth.main(["--status"]) == 1
    assert "EXPIRED" in capsys.readouterr().out


def test_the_cli_needs_a_verb():
    with pytest.raises(SystemExit):
        oauth.main([])


def test_the_cli_never_prints_a_value_even_from_the_wrong_box(monkeypatch, capsys):
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, TOKEN)

    assert oauth.main(["--status"]) == 1

    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err
    assert TOKEN[:oauth.MIN_REDACTED_RUN] not in captured.out + captured.err


# ---------------------------------------------------------------------------
# Offline, always - and provably so
# ---------------------------------------------------------------------------


def test_importing_the_module_needs_no_credential_and_no_socket():
    # Nothing is read or requested at import time - the module is importable
    # on a machine that has never heard of Meta.
    import importlib

    importlib.reload(oauth)


def test_the_module_cannot_open_a_socket():
    # "Before any socket" is a property of the code, not of a code path: the
    # module imports nothing that could open one. A consumer that needs a
    # transport owns it, and wraps it in _never_leak.
    tree = ast.parse(Path(oauth.__file__).read_text(encoding="utf-8"))
    forbidden = ("socket", "urllib", "http", "requests", "ssl", "google", "subprocess")
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for name in imported:
        assert name.split(".")[0] not in forbidden, "engine/oauth.py imports %s" % name


def test_a_whole_exercise_of_the_module_opens_no_socket(credentials, monkeypatch):
    # Belt and braces with the AST test: the exploding socket fixture stays
    # un-exploded through every public function.
    oauth.meta_token(today=TODAY)
    oauth.status(out=io.StringIO(), today=TODAY)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(50))
    oauth.meta_token(on_warning=lambda m: None, today=TODAY)


# ---------------------------------------------------------------------------
# A CREDENTIAL SHORT ENOUGH TO BE A DATE
#
# The hole this file could not see. Every "never prints a value" test above
# uses TOKEN, which is 54 characters and so always lands on the safe side of
# MAX_DATE_CHARS - the suite structurally could not reach the branch where a
# value IS echoed. A Meta app secret is 32 characters and did reach it: before
# `_looks_opaque`, `--status` printed it verbatim, and the workflows `cat`
# that output into the Actions job log where a repository VARIABLE is never
# masked. So the rule is shape, not length alone, and these are its edges.
# ---------------------------------------------------------------------------


SHORT_CREDENTIALS = [
    ("meta app secret, 32 hex", APP_SECRET),
    ("a 32-character token slice", TOKEN[:32]),
    ("a 30-character token slice", TOKEN[:30]),
    ("the shortest opaque run there is", "a1b2c3d4e5f6"),
]


@pytest.mark.parametrize("label,secret",
                         SHORT_CREDENTIALS, ids=[n for n, _ in SHORT_CREDENTIALS])
def test_a_credential_short_enough_to_be_a_date_is_still_not_echoed(label, secret):
    # The pure function, with no token anywhere to scrub against.
    assert len(secret) <= oauth.MAX_DATE_CHARS

    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.token_age_days(secret, today=TODAY)

    message = str(caught.value)
    assert secret not in message, "%s was echoed" % label
    assert secret[:oauth.MIN_REDACTED_RUN] not in message
    # Described instead, which is what tells the operator what they pasted.
    assert "%d-character" % len(secret) in message
    assert "wrong box" in message
    assert "YYYY-MM-DD" in message


@pytest.mark.parametrize("label,secret",
                         SHORT_CREDENTIALS, ids=[n for n, _ in SHORT_CREDENTIALS])
@pytest.mark.parametrize("token_state", ["unset", "different", "same"])
def test_status_never_prints_a_short_credential_from_the_date_box(
    monkeypatch, label, secret, token_state
):
    # All three token states, because the scrub list is `[token] if have_token`
    # and cannot help in two of them: unset is the state an operator is in
    # when they pasted one box over and have not filled the other yet, and
    # "different" is the state after they fixed the token but not the date.
    if token_state == "different":
        monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)
    elif token_state == "same":
        monkeypatch.setenv(oauth.META_ACCESS_TOKEN, secret)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, secret)

    code, printed = run_status()

    assert code == 1
    assert "not a readable date" in printed
    assert secret not in printed, "%s reached --status with the token %s" % (
        label, token_state)
    assert secret[:oauth.MIN_REDACTED_RUN] not in printed


def test_the_cli_never_prints_a_short_credential_from_the_wrong_box(
    monkeypatch, capsys
):
    # The whole way out: `python -m engine.oauth --status` is what
    # .github/workflows/research.yml and measure.yml pipe into the job log.
    monkeypatch.delenv(oauth.META_ACCESS_TOKEN, raising=False)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, APP_SECRET)

    assert oauth.main(["--status"]) == 1

    captured = capsys.readouterr()
    assert APP_SECRET not in captured.out + captured.err
    assert APP_SECRET[:oauth.MIN_REDACTED_RUN] not in captured.out + captured.err


@pytest.mark.parametrize("typo", ["1 August 2026", "2026-13-45", "01/08/2026",
                                  "last tuesday", "whenever", "60",
                                  "2026-08-01T25:00:00", "Aug 1 2026"])
def test_a_typo_is_still_echoed_so_the_operator_can_see_what_they_wrote(typo):
    # The affordance the shape rule had to keep. Seeing your own typo quoted
    # back is how you spot the day/month swap; describing it by length would
    # be safe and useless.
    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.token_age_days(typo, today=TODAY)

    assert repr(typo) in str(caught.value)


@pytest.mark.parametrize("written,echoed", [
    ("x" * (oauth.MIN_REDACTED_RUN - 1), True),   # 11: a word could do that
    ("x" * oauth.MIN_REDACTED_RUN, False),        # 12: the run floor
    ("x" * oauth.MAX_DATE_CHARS, False),
    ("x" * (oauth.MAX_DATE_CHARS + 1), False),
    ("2026-13-45-99-11", True),                   # separators all the way down
    ("x" * 11 + "-" + "y" * 11, True),            # two short runs, not one long
])
def test_the_echo_rule_is_shape_and_length_together(written, echoed):
    # MIN_REDACTED_RUN is the floor already used for cutting partial echoes -
    # "long enough that no English phrase collides with it by accident" - and
    # it is reused here rather than inventing a second number.
    with pytest.raises(oauth.MissingCredential) as caught:
        oauth.token_age_days(written, today=TODAY)

    assert (repr(written) in str(caught.value)) is echoed


@pytest.mark.parametrize("text,opaque", [
    ("2026-08-01", False),
    ("1 August 2026", False),
    ("last tuesday", False),
    (APP_SECRET, True),
    (TOKEN, True),
    ("", False),
])
def test_looks_opaque_calls_a_credential_a_credential(text, opaque):
    assert oauth._looks_opaque(text) is opaque


# ---------------------------------------------------------------------------
# Below Exception
#
# `_never_leak`'s docstring promises EVERY exception is converted, and
# `except Exception` does not cover KeyboardInterrupt, SystemExit or
# asyncio.CancelledError - which is what an async transport raises on a
# timeout, the ordinary shape of caller code written against this seam. These
# keep their own type (Ctrl-C must still abort, SystemExit must keep its
# status) and are scrubbed and unchained like everything else.
# ---------------------------------------------------------------------------


BELOW_EXCEPTION = [
    ("KeyboardInterrupt", KeyboardInterrupt),
    ("SystemExit", SystemExit),
    ("asyncio.CancelledError", asyncio.CancelledError),
    ("GeneratorExit", GeneratorExit),
]


@pytest.mark.parametrize("label,kind",
                         BELOW_EXCEPTION, ids=[n for n, _ in BELOW_EXCEPTION])
def test_a_baseexception_from_a_transport_is_scrubbed_and_keeps_its_type(
    label, kind, capsys
):
    def work():
        raise kind("timed out while sending Bearer %s" % TOKEN)

    with pytest.raises(kind) as caught:
        oauth._never_leak([TOKEN], work)

    assert type(caught.value) is kind, "%s was converted away" % label
    haystack = surfaces(caught.value, capsys.readouterr())
    assert TOKEN not in haystack
    assert TOKEN[:oauth.MIN_REDACTED_RUN] not in haystack
    assert oauth.REDACTED in str(caught.value)


def test_an_abort_raised_while_a_token_bearing_error_was_handled_drops_the_chain():
    # The scenario `_never_leak`'s docstring spends a paragraph on, arriving
    # below Exception: the unscrubbed original rides out on __context__.
    def work():
        try:
            raise ValueError("Invalid isoformat string: '%s'" % TOKEN)
        except ValueError:
            raise KeyboardInterrupt("aborted")

    with pytest.raises(KeyboardInterrupt) as caught:
        oauth._never_leak([TOKEN], work)

    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_a_systemexit_keeps_its_exit_status():
    # Scrubbing is per-argument, so an integer exit code is left alone.
    # Rebuilding SystemExit(2) from a string would silently turn it into 1.
    def work():
        raise SystemExit(2)

    with pytest.raises(SystemExit) as caught:
        oauth._never_leak([TOKEN], work)

    assert caught.value.code == 2


def test_a_baseexception_that_will_not_take_its_args_back_still_scrubs():
    class Stubborn(BaseException):
        def __init__(self, first, second):
            super().__init__("%s | %s" % (first, second))

    def work():
        raise Stubborn("Bearer %s" % TOKEN, "second")

    # Cannot be rebuilt, so it is converted - the safe direction.
    with pytest.raises(oauth.OAuthError) as caught:
        oauth._never_leak([TOKEN], work)

    assert TOKEN not in str(caught.value)
    assert "Stubborn" in str(caught.value)


# ---------------------------------------------------------------------------
# The guards nothing pinned
# ---------------------------------------------------------------------------


def test_an_oautherror_subclass_that_wants_two_arguments_is_still_scrubbed():
    # The `except TypeError` fallback in _never_leak. A subclass with its own
    # __init__ cannot be rebuilt from one string, so it comes back as a plain
    # OAuthError rather than crashing inside the handler with the unscrubbed
    # original chained onto the crash.
    class TwoArgs(oauth.OAuthError):
        def __init__(self, reason, code):
            super().__init__("%s (%s)" % (reason, code))
            self.code = code

    def work():
        raise TwoArgs("Meta says %s is dead" % TOKEN, 190)

    with pytest.raises(oauth.OAuthError) as caught:
        oauth._never_leak([TOKEN], work)

    assert type(caught.value) is oauth.OAuthError
    assert TOKEN not in str(caught.value)
    assert oauth.REDACTED in str(caught.value)
    assert caught.value.__context__ is None


@pytest.mark.parametrize("today", ["2026-09-18", 1758160800, [2026, 9, 18]])
def test_a_today_that_is_neither_a_date_nor_a_datetime_says_which_it_got(today):
    # A caller's mistake, not an operator's, so it stays a TypeError rather
    # than becoming a MissingCredential that tells a human to go edit a
    # repository variable they got right.
    with pytest.raises(TypeError) as caught:
        oauth.token_age_days("2026-08-01", today=today)

    assert type(today).__name__ in str(caught.value)


def test_meta_token_turns_a_bad_today_into_a_scrubbed_oautherror(credentials):
    # Inside _never_leak, so a caller still needs one except clause.
    with pytest.raises(oauth.OAuthError) as caught:
        oauth.meta_token(today="2026-09-18")

    assert "TypeError" in str(caught.value)
    assert TOKEN not in str(caught.value)


def test_the_cli_turns_an_oauth_error_escaping_status_into_an_exit_code(
    monkeypatch, capsys
):
    # status() answers every case it knows with a line and a code, so this
    # handler is defensive - but it is the last thing between an exception and
    # a job log, so what it does with one is worth pinning, value and all.
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)

    def boom(*args, **kwargs):
        raise oauth.TokenExpired("Meta says %s is dead" % TOKEN)

    monkeypatch.setattr(oauth, "status", boom)

    assert oauth.main(["--status"]) == 1

    captured = capsys.readouterr()
    assert "Meta says" in captured.err
    assert TOKEN not in captured.err
    assert TOKEN[:oauth.MIN_REDACTED_RUN] not in captured.err


def test_a_value_between_the_two_floors_is_cut_whole_but_not_in_part():
    # MIN_REDACTABLE (4) and MIN_REDACTED_RUN (12) are two different floors
    # and the band between them behaves differently from either side of it:
    # the whole value goes, fragments of it do not. Measured at exactly 12,
    # where `len(value) > MIN_REDACTED_RUN` is False.
    twelve = "abcdefghijkl"
    assert len(twelve) == oauth.MIN_REDACTED_RUN

    assert oauth._redact("saw %s here" % twelve, [twelve]) == "saw %s here" % oauth.REDACTED
    # One character short of the whole value: nothing cuts it.
    assert oauth._redact("saw %s here" % twelve[1:], [twelve]) == "saw bcdefghijkl here"


@pytest.mark.parametrize("written,days", [
    ("2026-08-01", 48),           # the form the message asks for
    ("20260801", 48),             # ISO basic, accepted by 3.11's parser
    ("2026-W32-1", 46),           # an ISO week date is a date to fromisoformat
    ("2026-08-01 12:00:00", 47),  # a space where the T should be
])
def test_the_iso_forms_this_accepts_are_pinned_not_assumed(written, days):
    # The docstring promises "a bare date or any ISO-8601 timestamp".
    # datetime.fromisoformat on 3.11 - the version every workflow pins - is
    # broader than that, and this says by how much, so a reader knows which
    # of these an operator can actually get away with typing.
    assert oauth.token_age_days(written, today=TODAY) == pytest.approx(days, abs=1.0)


def test_the_last_day_of_the_life_warns_with_nothing_left_and_still_works(
    credentials, monkeypatch, warnings
):
    # The rendering at the boundary, not just the decision: an operator
    # reading "0 DAYS LEFT" while the run still succeeds is the last warning
    # they get, and the number in it is the one that makes them act.
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(59.9))

    assert oauth.meta_token(today=TODAY) == TOKEN
    assert "60 days old" in warnings[0]
    assert "0 DAYS LEFT" in warnings[0]

    code, printed = run_status()
    assert code == 1
    assert "60 days old, 0 of 60 left" in printed


def test_the_first_hours_past_the_life_read_as_expired_zero_days_ago(
    credentials, monkeypatch
):
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, issued(60.4))

    with pytest.raises(oauth.TokenExpired):
        oauth.meta_token(today=TODAY)

    code, printed = run_status()
    assert code == 1
    assert "60 days old, EXPIRED 0 days ago" in printed


def test_a_body_that_is_nothing_but_the_token_is_cut_without_pathology():
    # _cut_runs extends a match one character at a time. Nothing in the suite
    # would notice if that became quadratic, and a 400,000-character body is
    # what a gateway echoing a request back looks like. MEASURED at 0.02s;
    # the budget here is loose enough not to flake on a slow runner and tight
    # enough that a quadratic pass could never reach it.
    #
    # Every repeat is TRIMMED at both ends and separated, so the whole value
    # never appears: `str.replace` has nothing to match and _cut_runs is the
    # only thing doing the work.
    import time

    body = ("|" + TOKEN[3:-3]) * 8000
    assert TOKEN not in body
    started = time.monotonic()
    scrubbed = oauth._redact(body, [TOKEN])
    elapsed = time.monotonic() - started

    assert TOKEN[3:-3] not in scrubbed
    assert TOKEN[3:oauth.MIN_REDACTED_RUN + 3] not in scrubbed
    assert elapsed < 5.0, "cutting a 400k body took %.1fs" % elapsed
