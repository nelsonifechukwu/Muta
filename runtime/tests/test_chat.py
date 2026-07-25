"""ChatEngine multi-turn behaviour, using a fake client (no llama-server needed)."""

from __future__ import annotations

import pytest

from runtime.chat import ChatEngine
from runtime.client import Generation
from runtime.memory import ConversationStore


class FakeClient:
    """Records the messages it was handed and returns a canned reply.

    Mirrors InferenceClient: `chat_with_timings` is the real method and `chat` delegates,
    so the double cannot drift from the interface ChatEngine actually calls.
    """

    def __init__(self) -> None:
        self.seen: list[list[dict]] = []

    def chat_with_timings(self, messages, **params) -> Generation:
        self.seen.append(messages)
        return Generation(
            text=f"reply-{len(self.seen)}",
            prompt_tokens=1,
            completion_tokens=2,
            elapsed_s=0.01,
            tokens_per_second=200.0,
            from_wall_clock=True,
        )

    def chat(self, messages, **params) -> str:
        return self.chat_with_timings(messages, **params).text


def _engine(store: ConversationStore, **kw) -> tuple[ChatEngine, FakeClient, ConversationStore]:
    client = FakeClient()
    return ChatEngine(client, store, **kw), client, store


def test_first_turn_creates_conversation_and_persists_both_sides(store):
    engine, client, store = _engine(store)
    result = engine.chat("s1", "what is a derivative?")

    assert result.reply == "reply-1"
    msgs = store.get_messages(result.conversation_id)
    assert [(m["role"], m["content"]) for m in msgs] == [
        ("user", "what is a derivative?"),
        ("assistant", "reply-1"),
    ]
    # System prompt is prepended; history before the first user turn is empty.
    assert client.seen[0][0]["role"] == "system"
    assert client.seen[0][-1] == {"role": "user", "content": "what is a derivative?"}


def test_second_turn_replays_prior_history(store):
    engine, client, store = _engine(store)
    first = engine.chat("s1", "turn one")
    engine.chat("s1", "turn two", conversation_id=first.conversation_id)

    # The model call for turn two must include turn one's user+assistant messages.
    second_call = client.seen[1]
    contents = [m["content"] for m in second_call]
    assert "turn one" in contents
    assert "reply-1" in contents
    assert second_call[-1]["content"] == "turn two"


def test_conversation_id_is_stable_across_turns(store):
    engine, _, _ = _engine(store)
    a = engine.chat("s1", "one")
    b = engine.chat("s1", "two", conversation_id=a.conversation_id)
    assert a.conversation_id == b.conversation_id


def test_history_is_trimmed_to_max(store):
    engine, client, _ = _engine(store, max_history_messages=2)
    first = engine.chat("s1", "m0")
    cid = first.conversation_id
    for i in range(1, 4):
        engine.chat("s1", f"m{i}", conversation_id=cid)

    # Last call: system + at most 2 history messages + the new user message.
    last_call = client.seen[-1]
    assert last_call[0]["role"] == "system"
    assert len(last_call) <= 1 + 2 + 1


def test_system_prompt_override_is_used(store):
    engine, client, _ = _engine(store)
    engine.chat("s1", "hi", system_prompt="BE TERSE")
    assert client.seen[0][0] == {"role": "system", "content": "BE TERSE"}


class StreamingFakeClient(FakeClient):
    """Streams canned deltas; optionally dies mid-stream like a crashed engine."""

    def __init__(self, deltas: list[str], explode_after: int | None = None) -> None:
        super().__init__()
        self.deltas = deltas
        self.explode_after = explode_after

    def stream(self, messages, **params):
        self.seen.append(messages)
        for i, delta in enumerate(self.deltas):
            if self.explode_after is not None and i == self.explode_after:
                raise RuntimeError("engine died mid-stream")
            yield delta

    def stream_events(self, messages, **params):
        for delta in self.stream(messages, **params):
            yield "content", delta


def _stream_engine(store, deltas, **kw) -> tuple[ChatEngine, ConversationStore]:
    client = StreamingFakeClient(deltas, **kw)
    return ChatEngine(client, store), store


def test_stream_chat_persists_full_reply_exactly_once_when_drained(store):
    engine, store = _stream_engine(store, ["Hel", "lo"])
    cid, gen = engine.stream_chat("s1", "hi")
    assert "".join(gen) == "Hello"
    msgs = store.get_messages(cid)
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi"), ("assistant", "Hello")]


def test_stream_chat_persists_partial_reply_when_consumer_abandons(store):
    engine, store = _stream_engine(store, ["Hel", "lo", " world"])
    cid, gen = engine.stream_chat("s1", "hi")
    assert next(gen) == "Hel"
    assert next(gen) == "lo"
    gen.close()  # browser Stop button / disconnect
    msgs = store.get_messages(cid)
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi"), ("assistant", "Hello")]


def test_stream_events_chat_persists_partial_reply_on_midstream_error(store):
    engine, store = _stream_engine(store, ["a", "b", "c"], explode_after=2)
    cid, gen = engine.stream_events_chat("s1", "hi")
    got: list[str] = []
    with pytest.raises(RuntimeError):
        for _kind, text in gen:
            got.append(text)
    assert got == ["a", "b"]
    msgs = store.get_messages(cid)
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi"), ("assistant", "ab")]


def test_stream_chat_skips_empty_assistant_message_when_nothing_streamed(store):
    engine, store = _stream_engine(store, ["x"], explode_after=0)
    cid, gen = engine.stream_chat("s1", "hi")
    with pytest.raises(RuntimeError):
        next(gen)
    msgs = store.get_messages(cid)
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi")]
