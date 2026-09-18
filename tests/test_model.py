"""engine.model: the provider adapter, the call-site helpers, and the stub.

GeminiClient presents Google's SDK as the engine's internal model contract:
messages.create(...) -> reply.content blocks plus reply.stop_reason. That
shape is not Gemini's, so the adapter is where a provider swap lands - and
where it can quietly go wrong without any call site noticing.

call_model converts the operator's faults, and only those. On the free tier
those are a rejected key, a rate limit and a capacity spike that outlasted
the retry ladder - none is a bug, and none is fixed by a retry in the same
process. A malformed request keeps its traceback.

Every test here is offline. Constructing a real genai.Client does not open a
socket and the key is never used; the retry tests read the policy off one so
the constants cannot be right and still never reach the SDK.
"""
import types

import pytest
from google.genai import errors

from engine import model
from engine.model import (
    CapacityError,
    ConfigError,
    Reply,
    TextBlock,
    call_model,
    first_json_object,
    text_of,
)
from tests.stubs import StubClient, ThinkingBlock, json_reply, text_reply

# ---------------------------------------------------------------------------
# The adapter: Google's shape in, the engine's shape out.
# ---------------------------------------------------------------------------


class FakeModels:
    """Google's models.generate_content, without the network."""

    def __init__(self, text, finish="STOP"):
        self._text = text
        self._finish = finish
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        candidate = types.SimpleNamespace(
            finish_reason=types.SimpleNamespace(name=self._finish))
        return types.SimpleNamespace(text=self._text, candidates=[candidate])


def client_over(models) -> model.GeminiClient:
    client = model.GeminiClient.__new__(model.GeminiClient)
    client._client = types.SimpleNamespace(models=models)
    client.messages = model._Messages(client._client)
    return client


def test_the_reply_carries_text_in_a_block():
    client = client_over(FakeModels("hello"))
    reply = client.messages.create(
        model="m", max_tokens=64, messages=[{"role": "user", "content": "hi"}])
    assert isinstance(reply, Reply)
    assert [b.text for b in reply.content if b.type == "text"] == ["hello"]


def test_a_normal_finish_is_end_turn():
    client = client_over(FakeModels("hello"))
    reply = client.messages.create(model="m", max_tokens=64, messages=[])
    assert reply.stop_reason == "end_turn"


def test_max_tokens_is_reported_as_max_tokens():
    """A call site turns this into a readable failure instead of guessing
    that an empty answer meant rejection."""
    client = client_over(FakeModels("", finish="MAX_TOKENS"))
    reply = client.messages.create(model="m", max_tokens=1, messages=[])
    assert reply.stop_reason == "max_tokens"


def test_a_none_text_becomes_an_empty_string_not_none():
    """A MAX_TOKENS stop that spent its whole budget thinking returns .text of
    None. A call site reading a text block must never meet it."""
    client = client_over(FakeModels(None, finish="MAX_TOKENS"))
    reply = client.messages.create(model="m", max_tokens=1, messages=[])
    assert reply.content[0].text == ""
    assert text_of(reply) == ""


def test_max_tokens_reaches_the_sdk_as_max_output_tokens():
    models = FakeModels("ok")
    client_over(models).messages.create(model="m", max_tokens=4096, messages=[])
    assert models.calls[0]["config"].max_output_tokens == 4096


def test_the_model_id_reaches_the_sdk_untouched():
    models = FakeModels("ok")
    client_over(models).messages.create(
        model=model.MODEL_WRITE, max_tokens=8, messages=[])
    assert models.calls[0]["model"] == model.MODEL_WRITE


def test_messages_are_folded_into_one_prompt():
    models = FakeModels("ok")
    client_over(models).messages.create(
        model="m", max_tokens=64,
        messages=[{"role": "user", "content": "one"},
                  {"role": "user", "content": "two"}])
    assert models.calls[0]["contents"] == "one\n\ntwo"


# ---------------------------------------------------------------------------
# The key.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
def test_either_key_name_is_accepted(monkeypatch, name):
    for other in model.KEY_NAMES:
        monkeypatch.delenv(other, raising=False)
    monkeypatch.setenv(name, "k-123")
    assert model.api_key() == "k-123"


def test_gemini_api_key_wins_because_that_is_the_documented_one(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "google")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini")
    assert model.api_key() == "gemini"


def test_no_key_is_none_not_an_empty_string(monkeypatch):
    for name in model.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    assert model.api_key() is None


def test_client_without_a_key_names_the_variable_to_set(monkeypatch):
    """The fault is the operator's and the message says what to do, before
    any socket."""
    for name in model.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        model.client()
    with pytest.raises(ConfigError, match="aistudio.google.com"):
        model.client()


def test_client_with_a_key_is_a_gemini_client_and_opens_nothing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    built = model.client()
    assert isinstance(built, model.GeminiClient)
    assert hasattr(built.messages, "create")


def test_an_empty_key_counts_as_unset(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        model.client()


def test_the_key_value_never_reaches_an_error_message(monkeypatch):
    """Secrets are read by one helper and never interpolated into a message,
    a log line or a filename. A rejected-key error carries the provider's
    words, and the provider does not echo the key - so the only way the value
    could appear is this module adding it, which is what this pins."""
    monkeypatch.setenv("GEMINI_API_KEY", "sk-live-secret-value")
    client = raising(client_error(403, "API_KEY_INVALID", "PERMISSION_DENIED"))
    with pytest.raises(ConfigError) as info:
        call_model(client, model="m", max_tokens=1, messages=[])
    assert "sk-live-secret-value" not in str(info.value)
    assert "sk-live-secret-value" not in repr(info.value)


# ---------------------------------------------------------------------------
# Attaching a creative. The difference between the model SEEING a creative and
# being TOLD about one - and the seam where nothing is ever fetched.
# ---------------------------------------------------------------------------


class _SpyModels:
    def __init__(self):
        self.contents = None

    def generate_content(self, *, model, contents, config):
        self.contents = contents

        class _Response:
            text = '{"ok": 1}'
            candidates = []

        return _Response()


def _transport():
    client = model.GeminiClient.__new__(model.GeminiClient)
    inner = types.SimpleNamespace(models=_SpyModels())
    client._client = inner
    client.messages = model._Messages(inner)
    return client, inner


def _send(client, media):
    return client.messages.create(
        model="m", max_tokens=10,
        messages=[{"role": "user", "content": "look", "media": media}])


def test_a_message_with_no_media_still_sends_a_bare_string():
    """Every text-only call site must send exactly what it would without the
    media path existing."""
    client, inner = _transport()
    client.messages.create(model="m", max_tokens=10,
                           messages=[{"role": "user", "content": "hello"}])
    assert inner.models.contents == "hello"
    assert isinstance(inner.models.contents, str)


def test_the_inline_limit_is_twenty_mebibytes():
    assert model.INLINE_LIMIT == 20 * 1024 * 1024


def test_the_suffix_table_covers_video_and_stills_and_nothing_else():
    assert set(model.MIME_BY_SUFFIX) == {
        ".mp4", ".mov", ".m4v", ".webm", ".jpg", ".jpeg", ".png", ".webp"}


def test_a_local_clip_is_attached_as_bytes_with_its_mime_type(tmp_path):
    clip = tmp_path / "fb-123.mp4"
    clip.write_bytes(b"\x00\x01video")
    client, inner = _transport()
    _send(client, {"kind": "local-file", "ref": str(clip)})
    parts = inner.models.contents
    assert isinstance(parts, list) and len(parts) == 2
    assert parts[0].text == "look"
    blob = parts[1].inline_data
    assert blob.mime_type == "video/mp4"
    assert blob.data == b"\x00\x01video"


def test_a_local_still_is_attached_as_an_image(tmp_path):
    """An ad creative is as often a still as a clip; the sibling never needed
    an image type and this repository does."""
    still = tmp_path / "fb-123.jpg"
    still.write_bytes(b"\xff\xd8jpeg")
    client, inner = _transport()
    _send(client, {"kind": "local-file", "ref": str(still)})
    blob = inner.models.contents[1].inline_data
    assert blob.mime_type == "image/jpeg"
    assert blob.data == b"\xff\xd8jpeg"


def test_the_suffix_lookup_is_case_insensitive(tmp_path):
    still = tmp_path / "fb-123.PNG"
    still.write_bytes(b"\x89png")
    client, inner = _transport()
    _send(client, {"kind": "local-file", "ref": str(still)})
    assert inner.models.contents[1].inline_data.mime_type == "image/png"


def test_a_file_too_big_to_send_inline_is_refused_by_name(tmp_path):
    clip = tmp_path / "long.mp4"
    clip.write_bytes(b"\x00" * (model.INLINE_LIMIT + 1))
    client, _ = _transport()
    with pytest.raises(ValueError, match="long.mp4") as info:
        _send(client, {"kind": "local-file", "ref": str(clip)})
    assert "File API" in str(info.value)
    assert "20MB" in str(info.value)


def test_a_file_exactly_at_the_limit_is_still_sent(tmp_path):
    clip = tmp_path / "edge.mp4"
    clip.write_bytes(b"\x00" * model.INLINE_LIMIT)
    client, inner = _transport()
    _send(client, {"kind": "local-file", "ref": str(clip)})
    assert len(inner.models.contents[1].inline_data.data) == model.INLINE_LIMIT


def test_an_unknown_suffix_names_the_file_and_what_is_accepted(tmp_path):
    clip = tmp_path / "fb-123.avi"
    clip.write_bytes(b"\x00")
    client, _ = _transport()
    with pytest.raises(ValueError, match="fb-123.avi") as info:
        _send(client, {"kind": "local-file", "ref": str(clip)})
    message = str(info.value)
    assert ".mp4" in message and ".jpg" in message and ".webp" in message


def test_a_missing_file_says_where_a_creative_comes_from(tmp_path):
    """The seam is manual: the message has to say a human saves the file,
    not leave an operator looking for the download that does not exist."""
    client, _ = _transport()
    with pytest.raises(ValueError, match="research/media"):
        _send(client, {"kind": "local-file", "ref": str(tmp_path / "gone.mp4")})


def test_a_media_entry_without_a_ref_is_refused():
    client, _ = _transport()
    with pytest.raises(ValueError, match="ref"):
        _send(client, {"kind": "local-file"})


def test_a_file_uri_with_its_mime_type_is_attached_by_reference():
    client, inner = _transport()
    _send(client, {"kind": "file-uri",
                   "ref": "https://generativelanguage.googleapis.com/v1beta/files/abc",
                   "mime_type": "video/mp4"})
    part = inner.models.contents[1]
    assert part.file_data.file_uri.endswith("/files/abc")
    assert part.file_data.mime_type == "video/mp4"


def test_a_bare_file_api_uri_is_attached_without_a_mime_type():
    """Part.from_uri infers a mime type from the uri's suffix and raises when
    there is none - and a File API uri never has one. Measured against
    google-genai 2.24.0. The service recorded the type at upload, so the part
    carries the uri alone rather than failing before the wire."""
    client, inner = _transport()
    _send(client, {"kind": "file-uri",
                   "ref": "https://generativelanguage.googleapis.com/v1beta/files/abc"})
    part = inner.models.contents[1]
    assert part.file_data.file_uri.endswith("/files/abc")
    assert part.file_data.mime_type is None


def test_a_file_uri_with_a_suffix_gets_its_type_from_the_table():
    client, inner = _transport()
    _send(client, {"kind": "file-uri", "ref": "https://x/y/creative.webp"})
    assert inner.models.contents[1].file_data.mime_type == "image/webp"


def test_an_unknown_media_kind_is_refused_rather_than_silently_dropped():
    client, _ = _transport()
    with pytest.raises(ValueError, match="unknown media kind"):
        _send(client, {"kind": "telepathy", "ref": "x"})


def test_there_is_no_youtube_kind_because_nothing_here_watches_youtube():
    """The sibling attaches a YouTube URL by reference. This repository reads
    ads, not videos, and a kind that names a URL to fetch is the one thing
    the scope forbids."""
    client, _ = _transport()
    with pytest.raises(ValueError, match="unknown media kind"):
        _send(client, {"kind": "youtube-url", "ref": "https://youtube.com/shorts/abc"})
    assert set(model.MEDIA_KINDS) == {"local-file", "file-uri"}


def test_the_module_opens_no_socket_and_fetches_nothing():
    """Nothing in this repository downloads a creative. The module has no
    HTTP client in it to do so with; the SDK is the only thing that talks."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(model.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"urllib", "http", "socket", "requests", "httpx", "subprocess"}, imported


# ---------------------------------------------------------------------------
# The retry policy. Read off a REAL constructed client rather than off the
# constants, because the failure it exists to catch is the constants being
# right and never reaching the SDK. Four propose runs died on an unretried 503
# while `tenacity` sat in the traceback looking like a retry loop; it was
# configured to stop after one attempt. No network is touched - constructing
# a client does not call anything, and the key is never used.
# ---------------------------------------------------------------------------


def _retry_policy():
    return model.GeminiClient("not-a-real-key")._client._api_client._retry


def _api_error(code: int, status: str):
    return errors.APIError(
        code, {"error": {"code": code, "status": status, "message": "x"}})


def test_the_sdk_on_its_own_would_not_retry_anything():
    """The premise the rest of these rest on, pinned so it cannot rot.

    If a future google-genai starts retrying by default this goes red, and the
    policy below becomes a thing to re-decide rather than a thing to keep.
    """
    from google import genai

    bare = genai.Client(api_key="not-a-real-key")
    assert bare._api_client._retry.stop.max_attempt_number == 1


def test_http_options_carries_the_constants_verbatim():
    options = model.http_options()
    retry = options.retry_options
    assert retry.attempts == model.RETRY_ATTEMPTS
    assert retry.initial_delay == model.RETRY_INITIAL_DELAY
    assert retry.exp_base == model.RETRY_EXP_BASE
    assert retry.max_delay == model.RETRY_MAX_DELAY
    assert tuple(retry.http_status_codes) == model.RETRY_STATUS_CODES


def test_a_503_is_retried_rather_than_ending_the_run():
    """The actual bug: a spike on a free-tier endpoint that describes itself as
    temporary threw away a whole run on its first call."""
    policy = _retry_policy()
    assert policy.stop.max_attempt_number > 1
    assert policy.retry.predicate(_api_error(503, "UNAVAILABLE"))


def test_every_transient_server_fault_is_retried():
    policy = _retry_policy()
    for code in model.RETRY_STATUS_CODES:
        assert policy.retry.predicate(_api_error(code, "x")), code


def test_a_quota_429_is_left_alone():
    """Deliberate, and the opposite of the SDK's own default set.

    A free-tier 429 is quota. Some are a per-minute ceiling a wait would clear;
    the rest are the per-day one, which no wait clears, and the error does not
    reliably say which. call_model already turns it into one plain line.
    Retrying it spends runner minutes re-asking a calendar.
    """
    assert 429 not in model.RETRY_STATUS_CODES
    assert not _retry_policy().retry.predicate(
        _api_error(429, "RESOURCE_EXHAUSTED"))


def test_a_malformed_request_is_not_retried():
    """A 400 is a bug in what we sent. Retrying it five times makes the same
    mistake five times and delays the traceback that explains it."""
    assert not _retry_policy().retry.predicate(
        _api_error(400, "INVALID_ARGUMENT"))


def test_the_ladder_is_bounded_in_attempts_and_in_delay():
    policy = _retry_policy()
    assert policy.stop.max_attempt_number == model.RETRY_ATTEMPTS
    assert model.RETRY_ATTEMPTS <= 8
    assert model.RETRY_MAX_DELAY <= 60.0


def test_the_wait_is_bounded_well_inside_the_propose_timeout():
    """Patience costs runner minutes, which is the budget this repo actually
    has. propose writes and gates up to three concepts - six calls - under
    timeout-minutes: 25 with ~5 minutes of real work in it. Six calls each
    needing their last retry must still leave room for that work.
    """
    import tenacity

    policy = _retry_policy()
    attempts = policy.stop.max_attempt_number
    total = 0.0
    for n in range(1, attempts):
        state = tenacity.RetryCallState(None, None, None, None)
        state.attempt_number = n
        total += policy.wait(state)

    assert total < 90, "%.1fs of waiting per call" % total
    assert 6 * total < 12 * 60, "six calls would spend %.1f minutes" % (
        6 * total / 60)


# ---------------------------------------------------------------------------
# The two model ids.
# ---------------------------------------------------------------------------


def test_the_judge_does_not_share_a_model_with_the_writer():
    """Two reasons, either one sufficient, both MEASURED on propose run 26.

    The free tier's cap is `GenerateRequestsPerDayPerProjectPerModel`, 20 a
    day - counted PER MODEL. One id for both halves means one allowance for
    both, and run 26 exhausted it on the second of three concepts.

    And a writer marking its own homework is the weaker arrangement. The gate
    exists to refuse copy; having it be the same model that wrote the copy is
    a check with its thumb on the scale.
    """
    assert model.MODEL_FLASH != model.MODEL_WRITE


def test_the_judge_keeps_the_model_measured_making_its_judgements():
    """gemini-3.5-flash is the model actually observed gating: on run 26 it
    refused a latency promise and a judgement-call tag, then passed the
    rewrite. Moving the gate would trade a known judge for an unknown one."""
    assert model.MODEL_FLASH == "gemini-3.5-flash"
    assert model.MODEL_WRITE == "gemini-3.6-flash"


# ---------------------------------------------------------------------------
# call_model converts the operator's faults, and only those.
# ---------------------------------------------------------------------------


def raising(exc):
    """A client whose messages.create raises."""
    def create(**kwargs):
        raise exc
    return types.SimpleNamespace(messages=types.SimpleNamespace(create=create))


def client_error(code: int, message: str, status: str):
    return errors.ClientError(
        code, {"error": {"message": message, "status": status}}, None)


def server_error(code: int, message: str, status: str = "UNAVAILABLE"):
    return errors.ServerError(
        code, {"error": {"message": message, "status": status}}, None)


def test_a_rejected_key_becomes_a_config_error():
    client = raising(client_error(403, "API_KEY_INVALID", "PERMISSION_DENIED"))
    with pytest.raises(ConfigError, match="rejected the key"):
        call_model(client, model="m", max_tokens=1, messages=[])


def test_a_401_is_the_same_fault_as_a_403():
    client = raising(client_error(401, "unauthenticated", "UNAUTHENTICATED"))
    with pytest.raises(ConfigError, match="rejected the key"):
        call_model(client, model="m", max_tokens=1, messages=[])


def test_the_message_names_the_variable_and_where_to_mint_a_free_key():
    client = raising(client_error(403, "API_KEY_INVALID", "PERMISSION_DENIED"))
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        call_model(client, model="m", max_tokens=1, messages=[])
    with pytest.raises(ConfigError, match="aistudio.google.com"):
        call_model(client, model="m", max_tokens=1, messages=[])


def test_a_permission_denied_status_is_a_rejected_key_whatever_the_code():
    client = raising(client_error(400, "no access", "PERMISSION_DENIED"))
    with pytest.raises(ConfigError, match="rejected the key"):
        call_model(client, model="m", max_tokens=1, messages=[])


def test_a_rate_limited_free_tier_becomes_a_config_error():
    """The free tier is the whole point of this provider, so being throttled
    is an ordinary operating condition, not a crash - and the message has to
    say it resets on its own, or an operator starts changing things."""
    client = raising(client_error(429, "Quota exceeded", "RESOURCE_EXHAUSTED"))
    with pytest.raises(ConfigError, match="rate limited"):
        call_model(client, model="m", max_tokens=1, messages=[])
    with pytest.raises(ConfigError, match="resets on its own"):
        call_model(client, model="m", max_tokens=1, messages=[])


def test_a_rate_limit_is_not_a_capacity_error():
    """A 429 is quota, which a later call in the same run cannot clear; a
    selection loop that skips past CapacityError must not skip past this."""
    client = raising(client_error(429, "Quota exceeded", "RESOURCE_EXHAUSTED"))
    with pytest.raises(ConfigError) as info:
        call_model(client, model="m", max_tokens=1, messages=[])
    assert not isinstance(info.value, CapacityError)


def test_an_ordinary_client_error_still_raises():
    """A malformed request is a bug. It keeps its traceback."""
    client = raising(client_error(400, "max_output_tokens must be > 0", "INVALID_ARGUMENT"))
    with pytest.raises(errors.ClientError):
        call_model(client, model="m", max_tokens=0, messages=[])


# A ServerError reaching call_model is a spike that OUTLASTED about 65 seconds
# of waiting - the ladder above is what makes converting it honest, and
# re-running later really is the only thing left to do. If that ladder is ever
# removed, these tests are wrong and the retry tests above go red first.
def test_a_capacity_spike_that_outlasted_the_retries_becomes_a_capacity_error():
    client = raising(server_error(
        503, "This model is currently experiencing high demand."))
    with pytest.raises(CapacityError, match="out of capacity"):
        call_model(client, model="m", max_tokens=1, messages=[])


def test_a_capacity_error_is_a_config_error_so_every_handler_keeps_working():
    assert issubclass(CapacityError, ConfigError)
    assert issubclass(ConfigError, RuntimeError)


def test_the_capacity_message_does_not_blame_the_operator():
    """The whole reason to convert it. An operator who reads a traceback goes
    looking for a broken key or a bad config; there is neither, and the last
    run that printed one cost an evening of re-running."""
    client = raising(server_error(503, "high demand"))
    with pytest.raises(ConfigError, match="Nothing is wrong with the setup"):
        call_model(client, model="m", max_tokens=1, messages=[])
    with pytest.raises(ConfigError, match="high demand"):
        call_model(client, model="m", max_tokens=1, messages=[])
    with pytest.raises(ConfigError, match="503"):
        call_model(client, model="m", max_tokens=1, messages=[])


def test_every_5xx_is_a_capacity_error_not_just_503():
    for code in (500, 502, 504):
        client = raising(server_error(code, "x", "INTERNAL"))
        with pytest.raises(CapacityError):
            call_model(client, model="m", max_tokens=1, messages=[])


def test_a_successful_call_passes_straight_through():
    sentinel = object()
    client = types.SimpleNamespace(
        messages=types.SimpleNamespace(create=lambda **kw: sentinel))
    assert call_model(client, model="m", max_tokens=1, messages=[]) is sentinel


def test_call_model_forwards_exactly_the_three_named_arguments():
    client = StubClient([text_reply("ok")])
    messages = [{"role": "user", "content": "hi"}]
    call_model(client, model="m", max_tokens=7, messages=messages)
    assert client.calls == [{"model": "m", "max_tokens": 7, "messages": messages}]


def test_call_model_takes_keyword_arguments_only():
    with pytest.raises(TypeError):
        call_model(StubClient([text_reply("ok")]), "m", 1, [])


# ---------------------------------------------------------------------------
# text_of and first_json_object: reading an answer.
# ---------------------------------------------------------------------------


def test_text_of_takes_the_first_text_block_past_the_thinking():
    reply = Reply(content=[ThinkingBlock("hmm"), TextBlock("answer"), TextBlock("later")])
    assert text_of(reply) == "answer"


def test_text_of_is_empty_when_no_block_is_text():
    assert text_of(Reply(content=[ThinkingBlock("only thinking")])) == ""
    assert text_of(Reply(content=[])) == ""


def test_text_of_reads_duck_typed_blocks_too():
    """A block is anything with .type; a SimpleNamespace from an older stub
    must read the same as the dataclass."""
    reply = types.SimpleNamespace(content=[
        types.SimpleNamespace(type="thinking", thinking="..."),
        types.SimpleNamespace(type="text", text="duck"),
    ])
    assert text_of(reply) == "duck"


def test_text_of_coerces_a_none_text_to_empty():
    assert text_of(Reply(content=[TextBlock(text=None)])) == ""


def test_first_json_object_takes_a_bare_object():
    assert first_json_object('{"a": 1}') == {"a": 1}


def test_first_json_object_handles_a_fenced_answer():
    fenced = 'Here you go:\n```json\n{"pass": true, "failures": []}\n```\n'
    assert first_json_object(fenced) == {"pass": True, "failures": []}


def test_first_json_object_handles_prose_on_both_sides():
    text = 'Sure. {"id": "fb-1", "hook": {"device": "question"}} Hope that helps.'
    assert first_json_object(text) == {"id": "fb-1", "hook": {"device": "question"}}


def test_first_json_object_survives_a_stray_brace_in_trailing_prose():
    """The greedy match runs to the LAST brace; when prose after the object
    carries one, decoding from the first brace still finds the object."""
    text = '{"a": 1}\n\nNote: the shape is {id: ...} as requested.'
    assert first_json_object(text) == {"a": 1}


def test_first_json_object_is_none_for_no_object():
    assert first_json_object("no json here") is None
    assert first_json_object("") is None


def test_first_json_object_is_none_for_a_list_or_scalar():
    assert first_json_object("[1, 2, 3]") is None
    assert first_json_object("42") is None


def test_first_json_object_is_none_for_broken_json():
    assert first_json_object('{"a": 1,}') is None


def test_first_json_object_keeps_non_ascii():
    assert first_json_object('{"hook": "Så er der løn"}') == {"hook": "Så er der løn"}


# ---------------------------------------------------------------------------
# tests/stubs.py: the one stub every later test file uses.
# ---------------------------------------------------------------------------


def test_stub_pops_replies_in_order_and_records_every_call():
    client = StubClient([text_reply("first"), text_reply("second")])
    a = client.messages.create(model="m", max_tokens=1, messages=[{"role": "user", "content": "1"}])
    b = client.messages.create(model="m", max_tokens=2, messages=[{"role": "user", "content": "2"}])
    assert text_of(a) == "first" and text_of(b) == "second"
    assert [c["max_tokens"] for c in client.calls] == [1, 2]
    assert client.sent(0) == "1" and client.sent(1) == "2"
    assert client.remaining == 0


def test_stub_raises_naming_the_call_when_out_of_replies():
    client = StubClient([text_reply("only")])
    client.messages.create(model="m", max_tokens=1, messages=[{"role": "user", "content": "x"}])
    with pytest.raises(AssertionError, match="call 2"):
        client.messages.create(model="judge", max_tokens=1,
                               messages=[{"role": "user", "content": "second prompt"}])
    # The unanswered call is still on record, so a test can see what asked.
    assert len(client.calls) == 2 and client.calls[1]["model"] == "judge"


def test_stub_with_no_replies_refuses_the_first_call():
    with pytest.raises(AssertionError, match="0 were supplied"):
        StubClient().messages.create(model="m", max_tokens=1, messages=[])


def test_stub_raises_an_exception_placed_in_the_queue():
    """A CapacityError second in the queue lets a selection loop be tested
    skipping one concept and carrying on to the next."""
    client = StubClient([text_reply("ok"), CapacityError("spike"), text_reply("after")])
    call_model(client, model="m", max_tokens=1, messages=[])
    with pytest.raises(CapacityError):
        call_model(client, model="m", max_tokens=1, messages=[])
    assert text_of(call_model(client, model="m", max_tokens=1, messages=[])) == "after"


def test_stub_accepts_a_single_reply_without_a_list():
    client = StubClient(text_reply("one"))
    assert text_of(client.messages.create(model="m", max_tokens=1, messages=[])) == "one"


def test_json_reply_round_trips_through_text_of_and_first_json_object():
    reply = json_reply({"ads": {"fb-1": {"hook": "Så er der løn"}}})
    assert first_json_object(text_of(reply)) == {"ads": {"fb-1": {"hook": "Så er der løn"}}}


def test_stub_replies_lead_with_a_thinking_block():
    """So code reaching for content[0].text raises here, not in a live run."""
    reply = json_reply({"a": 1})
    assert reply.content[0].type == "thinking"
    with pytest.raises(AttributeError):
        reply.content[0].text


def test_json_reply_carries_a_stop_reason():
    assert json_reply({}, stop_reason="max_tokens").stop_reason == "max_tokens"
    assert json_reply({}).stop_reason == "end_turn"


def test_stub_media_lists_what_a_call_attached():
    client = StubClient([text_reply("ok")])
    client.messages.create(model="m", max_tokens=1, messages=[
        {"role": "user", "content": "look",
         "media": {"kind": "local-file", "ref": "research/media/fb-1.mp4"}}])
    assert client.media(0) == [{"kind": "local-file", "ref": "research/media/fb-1.mp4"}]


def test_the_stub_imports_no_provider():
    """The stub is what keeps every later test offline; it must not itself
    pull the SDK in."""
    import ast
    from pathlib import Path

    from tests import stubs

    tree = ast.parse(Path(stubs.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(a.name.startswith("google") for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("google")
