"""The engine's model client, stubbed. Every test file that makes a model call
uses this one rather than writing its own.

The sibling repository has seven copies of a StubClient across seven test
files, each a little different, and a change to the reply shape means seven
edits. One copy here, shared, is the whole reason this module exists.

Every stubbed reply LEADS WITH A THINKING BLOCK, exactly as a real one from a
thinking-capable model does. A thinking block has no `.text` at all, so any
code reaching for `reply.content[0].text` raises AttributeError here, in a
test, rather than in a live run. The right read is `engine.model.text_of`.

No socket, no key, no google.genai: this module imports engine.model only for
the dataclasses it re-exports.
"""
from __future__ import annotations

import json
import types
from dataclasses import dataclass

from engine.model import Reply, TextBlock

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


class StubClient:
    """A client that answers from a queue and remembers what it was asked.

    `replies` are handed back in order, one per `messages.create` call, and
    every call's keyword arguments land in `.calls`. Running out is an
    AssertionError that names the call: a test that expected two model calls
    and got three should say so, not return None into the code under test.

    An item that is an Exception instance is RAISED instead of returned, so a
    test can put a CapacityError second in the queue and watch a selection
    loop skip one concept and carry on to the next.
    """

    def __init__(self, replies=()):
        if isinstance(replies, Reply) or isinstance(replies, BaseException):
            replies = [replies]
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
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
