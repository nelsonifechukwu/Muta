"""ChatEngine multi-turn behaviour, using a fake client (no llama-server needed)."""

from __future__ import annotations

import httpx
import pytest

from runtime.chat import ChatEngine, _message_tokens, strip_visualization_protocol
from runtime.client import Generation, InferenceStreamError
from runtime.memory import ConversationStore


class FakeClient:
    """Records the messages it was handed and returns a canned reply.

    Mirrors InferenceClient: `chat_with_timings` is the real method and `chat` delegates,
    so the double cannot drift from the interface ChatEngine actually calls.
    """

    def __init__(self) -> None:
        self.seen: list[list[dict]] = []
        self.seen_params: list[dict] = []

    def chat_with_timings(self, messages, **params) -> Generation:
        self.seen.append(messages)
        self.seen_params.append(params)
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

    def stream_events(self, messages, **params):
        self.seen.append(messages)
        self.seen_params.append(params)
        yield "content", f"reply-{len(self.seen)}"


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


def test_visualization_payload_is_persisted_but_not_replayed_to_model(store):
    engine, client, store = _engine(store)
    first = engine.chat("s1", "Draw a curve")
    visual_reply = (
        "The curve is U-shaped.\n\n```muta-viz\n"
        '{"version":1,"library":"d3","kind":"line","title":"Curve",'
        '"aria_label":"A curve.","height":300,"series":[{"label":"y",'
        '"points":[[0,0],[1,1]]}]}\n```'
    )
    store.update_message(first.assistant_message_id, visual_reply)
    engine.chat("s1", "Why?", conversation_id=first.conversation_id)

    assert client.seen[1][2]["content"] == "The curve is U-shaped."
    assert store.get_messages(first.conversation_id)[1]["content"] == visual_reply
    assert strip_visualization_protocol("```muta-viz\n{bad}\n```").startswith("```muta-viz")


def test_language_change_replaces_only_the_next_system_prompt_and_keeps_history(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'language-change.sqlite3'}")
    try:
        engine, client, store = _engine(store)
        first = engine.chat(
            "s1",
            "Explain projectile motion.",
            system_prompt="SYSTEM: respond in English",
            turn_instruction="TURN: respond in English",
            language="en",
        )
        engine.chat(
            "s1",
            "Kannst du das einfacher erklären?",
            conversation_id=first.conversation_id,
            system_prompt="SYSTEM: AUTO follows the latest user message",
            turn_instruction="",
            language="auto",
        )

        assert client.seen[1] == [
            {"role": "system", "content": "SYSTEM: AUTO follows the latest user message"},
            {"role": "user", "content": "Explain projectile motion."},
            {"role": "assistant", "content": "reply-1"},
            {"role": "user", "content": "Kannst du das einfacher erklären?"},
        ]
        assert [
            (message["role"], message["content"])
            for message in store.get_messages(first.conversation_id)
        ] == [
            ("user", "Explain projectile motion."),
            ("assistant", "reply-1"),
            ("user", "Kannst du das einfacher erklären?"),
            ("assistant", "reply-2"),
        ]
    finally:
        store.close()


def test_stream_language_change_keeps_earlier_turns_byte_identical(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'stream-language-change.sqlite3'}")
    try:
        engine, client, store = _engine(store)
        conversation_id, _message_id, first_events = engine.stream_events_chat(
            "s1",
            "Explain projectile motion.",
            system_prompt="SYSTEM: respond in English",
            turn_instruction="TURN: respond in English",
            language="en",
        )
        assert list(first_events) == [("content", "reply-1")]

        repeated_id, _message_id, second_events = engine.stream_events_chat(
            "s1",
            "Kannst du das einfacher erklären?",
            conversation_id=conversation_id,
            system_prompt="SYSTEM: AUTO follows the latest user message",
            turn_instruction="",
            language="auto",
        )
        assert repeated_id == conversation_id
        assert list(second_events) == [("content", "reply-2")]

        assert client.seen[1] == [
            {"role": "system", "content": "SYSTEM: AUTO follows the latest user message"},
            {"role": "user", "content": "Explain projectile motion."},
            {"role": "assistant", "content": "reply-1"},
            {"role": "user", "content": "Kannst du das einfacher erklären?"},
        ]
        assert [
            (message["role"], message["content"]) for message in store.get_messages(conversation_id)
        ] == [
            ("user", "Explain projectile motion."),
            ("assistant", "reply-1"),
            ("user", "Kannst du das einfacher erklären?"),
            ("assistant", "reply-2"),
        ]
    finally:
        store.close()


def test_conversation_id_is_stable_across_turns(store):
    engine, _, _ = _engine(store)
    a = engine.chat("s1", "one")
    b = engine.chat("s1", "two", conversation_id=a.conversation_id)
    assert a.conversation_id == b.conversation_id


def test_conversation_cannot_be_continued_by_another_student(store):
    engine, _, store = _engine(store)
    first = engine.chat("s1", "private question")

    with pytest.raises(PermissionError, match="another learner"):
        engine.chat("s2", "inject this", conversation_id=first.conversation_id)

    assert [message["content"] for message in store.get_messages(first.conversation_id)] == [
        "private question",
        "reply-1",
    ]


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


def test_history_token_budget_drops_oldest_turns_without_mutating_storage(store):
    engine, client, store = _engine(store, history_token_budget=70)
    first = engine.chat("s1", "x" * 180)
    engine.chat("s1", "y" * 60, conversation_id=first.conversation_id)
    before = [message["content"] for message in store.get_messages(first.conversation_id)]

    engine.chat("s1", "what next?", conversation_id=first.conversation_id)
    sent = client.seen[-1]
    contents = [message["content"] for message in sent]

    assert "x" * 180 not in contents
    assert "y" * 60 in contents
    assert sent[0]["role"] == "system"
    assert sent[1]["role"] == "user"
    assert [message["content"] for message in store.get_messages(first.conversation_id)][
        : len(before)
    ] == before


def test_history_budget_counts_visual_reply_without_its_protocol_payload(store):
    engine, client, store = _engine(store, history_token_budget=120)
    first = engine.chat("s1", "older useful question")
    second = engine.chat("s1", "draw it", conversation_id=first.conversation_id)
    points = ",".join(f"[{value},{value * value}]" for value in range(200))
    visual_reply = (
        "Useful visual explanation.\n\n```muta-viz\n"
        '{"version":1,"library":"d3","kind":"line","title":"Large",'
        '"aria_label":"A large graph.","height":300,"series":[{"label":"y",'
        f'"points":[{points}]}}]}}\n```'
    )
    store.update_message(second.assistant_message_id, visual_reply)

    engine.chat("s1", "continue", conversation_id=first.conversation_id)
    contents = [message["content"] for message in client.seen[-1]]
    assert "older useful question" in contents
    assert "Useful visual explanation." in contents
    assert not any("muta-viz" in content for content in contents)


def test_request_fitting_reserves_output_inside_the_active_context(store):
    engine, client, _ = _engine(
        store,
        context_window_tokens=320,
        context_safety_tokens=32,
    )
    engine.chat(
        "s1",
        "question " * 30,
        system_prompt="system rules " * 35,
        max_tokens=240,
    )

    sent = client.seen[-1]
    params = client.seen_params[-1]
    assert sum(_message_tokens(message) for message in sent) + params["max_tokens"] + 32 <= 320
    assert 1 <= params["max_tokens"] < 240


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
        self.seen_params.append(params)
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
    cid, _mid, gen = engine.stream_chat("s1", "hi")
    assert "".join(gen) == "Hello"
    msgs = store.get_messages(cid)
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi"), ("assistant", "Hello")]


def test_stream_chat_persists_partial_reply_when_consumer_abandons(store):
    engine, store = _stream_engine(store, ["Hel", "lo", " world"])
    cid, _mid, gen = engine.stream_chat("s1", "hi")
    assert next(gen) == "Hel"
    assert next(gen) == "lo"
    gen.close()  # browser Stop button / disconnect
    msgs = store.get_messages(cid)
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi"), ("assistant", "Hello")]


def test_stream_events_chat_persists_partial_reply_on_midstream_error(store):
    engine, store = _stream_engine(store, ["a", "b", "c"], explode_after=2)
    cid, _mid, gen = engine.stream_events_chat("s1", "hi")
    got: list[str] = []
    with pytest.raises(RuntimeError):
        for _kind, text in gen:
            got.append(text)
    assert got == ["a", "b"]
    msgs = store.get_messages(cid)
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi"), ("assistant", "ab")]


def test_transient_stream_drop_resumes_in_the_same_assistant_row(store):
    class RecoverOnce:
        def __init__(self) -> None:
            self.calls: list[list[dict]] = []

        def stream_events(self, messages, **params):
            self.calls.append(messages)
            if len(self.calls) == 1:
                yield "content", "**Projectile Motion in"
                raise httpx.ReadError("socket reset")
            assert messages[-2] == {
                "role": "assistant",
                "content": "**Projectile Motion in",
            }
            assert "Continue the interrupted assistant response" in messages[-1]["content"]
            yield "content", " Two Dimensions**"

    client = RecoverOnce()
    engine = ChatEngine(
        client,
        store,
        persist_interval_s=0.0,
        stream_retry_attempts=1,
        stream_retry_backoff_s=0.0,
    )
    cid, _mid, events = engine.stream_events_chat("s1", "teach projectile motion")

    received = list(events)
    assert any(kind == "recovering" for kind, _text in received)
    assert "".join(text for kind, text in received if kind == "content") == (
        "**Projectile Motion in Two Dimensions**"
    )
    assert [(m["role"], m["content"]) for m in store.get_messages(cid)] == [
        ("user", "teach projectile motion"),
        ("assistant", "**Projectile Motion in Two Dimensions**"),
    ]


def test_permanent_context_error_is_not_retried(store):
    class ContextFailure:
        calls = 0

        def stream_events(self, messages, **params):
            self.calls += 1
            raise InferenceStreamError("Context size has been exceeded", retryable=False)
            yield  # pragma: no cover - keep this a generator

    client = ContextFailure()
    engine = ChatEngine(client, store, stream_retry_attempts=5, stream_retry_backoff_s=0.0)
    _cid, _mid, events = engine.stream_events_chat("s1", "hi")

    with pytest.raises(InferenceStreamError, match="Context size"):
        list(events)
    assert client.calls == 1


def test_stream_chat_skips_empty_assistant_message_when_nothing_streamed(store):
    engine, store = _stream_engine(store, ["x"], explode_after=0)
    cid, _mid, gen = engine.stream_chat("s1", "hi")
    with pytest.raises(RuntimeError):
        next(gen)
    msgs = store.get_messages(cid)
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi")]


def test_regenerate_reanswers_the_last_user_turn_without_adding_one(store):
    # 'answer now' scenario: the user turn is already persisted (the in-flight reply was
    # thinking-only, so nothing assistant-side was saved), and we re-answer it thinking-off.
    engine, store = _stream_engine(store, ["4"])
    cid = store.create_conversation("s1")
    store.add_message(cid, "user", "what is 2+2?")

    cid2, mid, gen = engine.stream_events_chat(
        "s1",
        "what is 2+2?",
        conversation_id=cid,
        turn_instruction="TURN: respond in German",
        regenerate=True,
    )
    assert cid2 == cid
    assert mid is None  # no new user message row
    assert "".join(t for _k, t in gen) == "4"

    msgs = store.get_messages(cid)
    assert [m["role"] for m in msgs] == ["user", "assistant"]  # NOT a duplicated user turn
    # The request copy is wrapped, while the existing persisted user turn stays unchanged.
    assert engine.client.seen[-1][-1] == {
        "role": "user",
        "content": (
            "what is 2+2?\n\n"
            "[MUTA RUNTIME INSTRUCTION — not part of the learner's message]\n"
            "TURN: respond in German"
        ),
    }


def test_nonstream_regenerate_reanswers_without_duplicating_the_user_turn(store):
    engine, client, store = _engine(store)
    cid = store.create_conversation("s1")
    store.add_message(cid, "user", "what is electron spin?")

    result = engine.chat(
        "s1",
        "what is electron spin?",
        conversation_id=cid,
        turn_instruction="TURN: respond in German",
        regenerate=True,
    )

    assert result.user_message_id is None
    assert [message["role"] for message in client.seen[-1]] == ["system", "user"]
    assert client.seen[-1][-1]["content"].startswith("what is electron spin?")
    assert client.seen[-1][-1]["content"].endswith("TURN: respond in German")
    assert [(message["role"], message["content"]) for message in store.get_messages(cid)] == [
        ("user", "what is electron spin?"),
        ("assistant", "reply-1"),
    ]


def test_regenerate_rejects_a_conversation_that_already_has_an_answer(store):
    engine, _client, store = _engine(store)
    first = engine.chat("s1", "what is electron spin?")
    stored = store.get_messages(first.conversation_id)

    with pytest.raises(ValueError, match="last message is the user"):
        engine.chat(
            "s1",
            "what is electron spin?",
            conversation_id=first.conversation_id,
            regenerate=True,
        )

    assert store.get_messages(first.conversation_id) == stored


@pytest.mark.parametrize("conversation_id", [None, "missing-conversation"])
def test_regenerate_rejects_missing_conversation_without_creating_a_ghost(store, conversation_id):
    engine, _client, store = _engine(store)

    with pytest.raises(ValueError, match="existing conversation"):
        engine.chat(
            "s1",
            "what is electron spin?",
            conversation_id=conversation_id,
            regenerate=True,
        )

    assert store.list_conversations("s1") == []


# --- write-through streaming ------------------------------------------------------------
# A reply is written to its row AS IT ARRIVES rather than once at the end, because the end
# is not guaranteed to happen: when a browser disconnects, Starlette abandons the response
# generator inside a reference cycle and the `finally` only runs at the next cyclic GC.
# Measured against a real uvicorn (2026-08-08): the reply was still missing from Postgres
# seconds after the disconnect, and appeared only when gc.collect() was forced — which is
# what made a student's answer vanish when they switched conversations and switched back.


def test_reply_is_readable_from_the_store_mid_stream(store):
    """The point of the whole mechanism: a reader that has never touched the generator can
    already see what has streamed so far."""
    engine, store = _stream_engine(store, ["alpha ", "beta ", "gamma"])
    engine.persist_interval_s = 0.0  # flush every chunk, so the assertion is deterministic
    cid, _mid, gen = engine.stream_chat("s1", "hi")

    assert next(gen) == "alpha "
    assert [m["content"] for m in store.get_messages(cid) if m["role"] == "assistant"] == ["alpha "]
    assert next(gen) == "beta "
    assert [m["content"] for m in store.get_messages(cid) if m["role"] == "assistant"] == [
        "alpha beta "
    ]


def test_write_through_keeps_one_row_that_grows_in_place(store):
    """Flushes must UPDATE, never append: one assistant turn is one message, and its serial
    id fixes its position in history."""
    engine, store = _stream_engine(store, ["a", "b", "c", "d"])
    engine.persist_interval_s = 0.0
    cid, _mid, gen = engine.stream_chat("s1", "hi")
    ids = []
    for _ in gen:
        rows = [m for m in store.list_messages(cid) if m["role"] == "assistant"]
        ids.append(rows[0]["id"] if rows else None)

    assert len(set(i for i in ids if i is not None)) == 1, "the reply forked into extra rows"
    msgs = store.get_messages(cid)
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi"), ("assistant", "abcd")]


def test_abandoned_stream_leaves_what_had_streamed_without_being_closed(store):
    """The disconnect case, reproduced honestly: the generator is neither closed nor
    collected — exactly the state Starlette leaves it in — and the text is still there."""
    engine, store = _stream_engine(store, ["one ", "two ", "three ", "four"])
    engine.persist_interval_s = 0.0
    cid, _mid, gen = engine.stream_chat("s1", "hi")
    next(gen)
    next(gen)
    del gen  # dropped on the floor; no close(), no gc.collect()

    msgs = [m for m in store.get_messages(cid) if m["role"] == "assistant"]
    assert msgs and msgs[0]["content"] == "one two "


def test_thinking_only_turn_still_stores_nothing(store):
    """Reasoning stays ephemeral: a turn abandoned before the answer began must not leave a
    half-written assistant row behind."""

    class ThinkingOnly(StreamingFakeClient):
        def stream_events(self, messages, **params):
            for i in range(3):
                yield "reasoning", f"think{i}"

    engine = ChatEngine(ThinkingOnly([]), store, persist_interval_s=0.0)
    cid, _mid, gen = engine.stream_events_chat("s1", "hi")
    list(gen)
    assert [m["role"] for m in store.get_messages(cid)] == ["user"]


def test_repeated_flush_without_new_text_is_a_no_op(store):
    """Guards the idempotence the trailing flush relies on — a final flush after the last
    periodic one must not rewrite or duplicate anything."""
    engine, store = _stream_engine(store, ["x", "y"])
    engine.persist_interval_s = 0.0
    cid, _mid, gen = engine.stream_chat("s1", "hi")
    assert "".join(gen) == "xy"  # drains, then the finally flushes again
    msgs = store.get_messages(cid)
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "hi"), ("assistant", "xy")]
