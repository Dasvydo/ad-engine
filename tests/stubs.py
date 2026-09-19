"""The engine's model client, stubbed. Every test file that makes a model call
uses this one rather than writing its own.

The sibling repository has seven copies of a StubClient across seven test
files, each a little different, and a change to the reply shape means seven
edits. One copy here, shared, is the whole reason this module exists.

Every stubbed reply LEADS WITH A THINKING BLOCK, exactly as a real one from a
thinking-capable model does. A thinking block has no `.text` at all, so any
code reaching for `reply.content[0].text` raises AttributeError here, in a
test, rather than in a live run. The right read is `engine.model.text_of`.

Every call is put through the same argument path GeminiClient puts it
through - the prompt fold and `_media_part` - so a shape the live client
refuses is refused here too, in the test that wrote it, rather than passing
green over a call that cannot work. See `_as_the_client_would`.

No socket, no key, no google.genai: this module imports engine.model for the
dataclasses it re-exports and for that one validation helper, which takes the
SDK's `types` as an argument rather than importing it.
"""
from __future__ import annotations

import json
import types
from dataclasses import dataclass

from engine.model import Reply, TextBlock, _media_part

__all__ = [
    "Reply", "TextBlock", "ThinkingBlock",
    "StubClient", "json_reply", "text_reply",
]


@dataclass(frozen=True)
class ThinkingBlock:
    """What a thinking block looks like to a call site: a type, and no text."""

    thinking: str = "weighing it up..."
    type: str = "thinking"


def text_reply(text: str, *, stop_reason: str = "end_turn") -> Reply:
    """A Reply whose text block carries `text`, led by a thinking block."""
    return Reply(
        content=[ThinkingBlock(), TextBlock(text=text)],
        stop_reason=stop_reason,
    )


def json_reply(obj, *, stop_reason: str = "end_turn") -> Reply:
    """A Reply whose text block is `obj` as JSON - what a well-behaved model
    answers with when asked for an object."""
    return text_reply(json.dumps(obj, ensure_ascii=False), stop_reason=stop_reason)


class _NoPart:
    """Where `_media_part` builds a google.genai part, it builds one of these.

    _media_part takes the SDK's `types` module as an argument rather than
    importing it, so the stub can run the REAL validation - ref present, file
    on disk, known suffix, under the inline limit, known kind - and throw the
    part away at the end. That keeps the rules in one place (engine/model.py)
    and keeps this module free of google, which tests/test_model.py pins.
    """

    def __init__(self, **_):
        pass

    @staticmethod
    def from_bytes(**_):
        return None


_PART_FREE_TYPES = types.SimpleNamespace(Part=_NoPart, FileData=_NoPart)


def _as_the_client_would(messages) -> None:
    """Everything GeminiClient does to `messages` BEFORE the socket.

    MEASURED against engine.model._Messages.create: thirteen call shapes it
    refuses - a missing model/max_tokens/messages, a non-str content, messages
    that is not a list of dicts, and every invalid media entry - this stub used
    to wave through. Only one call in the suite's ~1,600 was actually wrong
    (a media ref to a file that has never existed, in this module's own test),
    so the stub was not testing a fiction; nothing stopped it starting to. A
    test that attaches a 25MB creative or a .gif goes green while the live run
    raises ValueError before a socket and drops the candidate.

    The fold and the parts are built and discarded: the point is the raising.
    """
    "\n\n".join(m["content"] for m in messages if m.get("content"))
    for message in messages:
        if message.get("media"):
            _media_part(_PART_FREE_TYPES, message["media"])


class StubClient:
    """A client that answers from a queue and remembers what it was asked.

    `replies` are handed back in order, one per `messages.create` call, and
    every call's keyword arguments land in `.calls`. Running out is an
    AssertionError that names the call: a test that expected two model calls
    and got three should say so, not return None into the code under test.

    An item that is an Exception instance is RAISED instead of returned, so a
    test can put a CapacityError second in the queue and watch a selection
    loop skip one concept and carry on to the next.

    Arguments are checked the way the live client checks them before it opens
    a socket: keyword-only model/max_tokens/messages, a foldable `content` on
    every message, and a real `media` entry where one is attached.
    """

    def __init__(self, replies=()):
        if isinstance(replies, Reply) or isinstance(replies, BaseException):
            replies = [replies]
        if isinstance(replies, str):
            # list('hello') is five one-character replies, and the first thing
            # the code under test reads is 'h' - through text_of, ''. A silent
            # queue of nonsense, so it is a TypeError naming the fix instead.
            raise TypeError(
                "StubClient takes Replies, not a string. Wrap the text: "
                "StubClient([text_reply(%r)])" % replies[:40]
            )
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, *, model, max_tokens, messages, **rest):
        # The same keyword-only signature GeminiClient.messages.create has, so
        # a call that forgets one fails here the way it would live.
        kw = {"model": model, "max_tokens": max_tokens, "messages": messages}
        kw.update(rest)
        self.calls.append(kw)
        _as_the_client_would(messages)
        if not self._replies:
            prompt = self.sent(len(self.calls) - 1)
            raise AssertionError(
                "StubClient has no reply left for call %d (model=%r, prompt "
                "opens %r); %d were supplied"
                % (len(self.calls), kw.get("model"), prompt[:80],
                   len(self.calls) - 1)
            )
        reply = self._replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    @property
    def remaining(self) -> int:
        """Replies not yet handed out - a test asserts 0 to prove every
        expected call happened."""
        return len(self._replies)

    def sent(self, index: int = 0) -> str:
        """The prompt of call `index`: every message's content, folded the way
        GeminiClient folds it."""
        messages = self.calls[index].get("messages") or []
        return "\n\n".join(
            m["content"] for m in messages
            if isinstance(m, dict) and m.get("content")
        )

    def media(self, index: int = 0) -> list[dict]:
        """Every `media` entry the messages of call `index` carried, in order."""
        messages = self.calls[index].get("messages") or []
        return [m["media"] for m in messages if isinstance(m, dict) and m.get("media")]
