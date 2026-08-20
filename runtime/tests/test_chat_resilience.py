"""Portable regressions for context fitting and interrupted-stream recovery."""

from __future__ import annotations

import threading
import time

import httpx
import pytest

from runtime.chat import ChatEngine, _message_tokens
from runtime.client import Generation, InferenceStreamError
from runtime.sqlite_memory import SQLiteConversationStore


@pytest.fixture()
def store(tmp_path):
    value = SQLiteConversationStore(f"sqlite:///{tmp_path / 'chat.sqlite3'}")
    yield value
    value.close()


class RecordingClient:
    def __init__(self) -> None:
        self.messages: list[list[dict]] = []
        self.params: list[dict] = []

    def chat_with_timings(self, messages, **params) -> Generation:
        self.messages.append(messages)
        self.params.append(params)
        return Generation("reply", 1, 1, 0.01, 100.0, True)


def test_history_budget_trims_prompt_only_and_keeps_a_user_boundary(store):
    client = RecordingClient()
    engine = ChatEngine(client, store, history_token_budget=70)
    first = engine.chat("s1", "x" * 180)
    engine.chat("s1", "y" * 60, conversation_id=first.conversation_id)
    stored_before = store.get_messages(first.conversation_id)

    engine.chat("s1", "what next?", conversation_id=first.conversation_id)
    sent = client.messages[-1]

    assert "x" * 180 not in [message["content"] for message in sent]
    assert "y" * 60 in [message["content"] for message in sent]
    assert sent[1]["role"] == "user"
    assert store.get_messages(first.conversation_id)[: len(stored_before)] == stored_before


def test_oversized_latest_reply_is_kept_for_continue_and_fitted_without_store_mutation(store):
    client = RecordingClient()
    engine = ChatEngine(
        client,
        store,
        history_token_budget=70,
        context_window_tokens=320,
        context_safety_tokens=32,
    )
    cid = store.create_conversation("s1")
    store.add_message(cid, "user", "Explain the entire derivation")
    original = "long derivation " * 100
    store.add_message(cid, "assistant", original)

    engine.chat("s1", "continue", conversation_id=cid, max_tokens=200)

    sent = client.messages[-1]
    assert [message["role"] for message in sent[-3:]] == ["user", "assistant", "user"]
    assert sent[-1]["content"] == "continue"
    assert "long derivation" in sent[-2]["content"]
    assert store.get_messages(cid)[1]["content"] == original
    assert (
        sum(_message_tokens(message) for message in sent) + client.params[-1]["max_tokens"] + 32
        <= 320
    )


def test_request_fitting_reserves_reply_tokens_inside_active_context(store):
    client = RecordingClient()
    engine = ChatEngine(
        client,
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

    sent, params = client.messages[-1], client.params[-1]
    assert sum(_message_tokens(message) for message in sent) + params["max_tokens"] + 32 <= 320
    assert 1 <= params["max_tokens"] < 240


def test_transient_drop_resumes_same_turn_and_same_assistant_row(store):
    class RecoverOnce:
        def __init__(self) -> None:
            self.calls: list[list[dict]] = []

        def stream_events(self, messages, **params):
            self.calls.append(messages)
            if len(self.calls) == 1:
                yield "content", "**Projectile Motion in"
                raise httpx.ReadError("socket reset")
            assert messages[-2]["content"] == "**Projectile Motion in"
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
    assert [(message["role"], message["content"]) for message in store.get_messages(cid)] == [
        ("user", "teach projectile motion"),
        ("assistant", "**Projectile Motion in Two Dimensions**"),
    ]


def test_recovery_fit_keeps_original_question_and_removes_repeated_boundary(store):
    class RepeatingRecovery:
        def __init__(self) -> None:
            self.calls: list[list[dict]] = []

        def stream_events(self, messages, **params):
            self.calls.append(messages)
            if len(self.calls) == 1:
                yield "content", "Projectile "
                raise httpx.ReadError("socket reset")
            yield "reasoning", "restarted private thought"
            yield "content", "Projectile motion continues."

    client = RepeatingRecovery()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=180,
        context_safety_tokens=20,
        persist_interval_s=0.0,
        stream_retry_attempts=1,
        stream_retry_backoff_s=0.0,
    )
    question = "Derive the two-dimensional equations from first principles " * 8
    cid, _mid, events = engine.stream_events_chat("s1", question, max_tokens=120)
    received = list(events)

    assert [message["role"] for message in client.calls[1][-3:]] == [
        "user",
        "assistant",
        "user",
    ]
    assert "first principles" in client.calls[1][-3]["content"]
    assert not any(text == "restarted private thought" for _kind, text in received)
    assert "".join(text for kind, text in received if kind == "content") == (
        "Projectile motion continues."
    )
    assert store.get_messages(cid)[-1]["content"] == "Projectile motion continues."


@pytest.mark.parametrize("partial", ["P", "Proj", "1234567"])
def test_recovery_deduplicates_even_a_one_to_seven_character_partial(store, partial):
    completed = f"{partial} completed without a repeated prefix"

    class ShortDrop:
        calls = 0

        def stream_events(self, messages, **params):
            self.calls += 1
            if self.calls == 1:
                yield "content", partial
                raise httpx.ReadError("socket reset")
            yield "content", completed

    engine = ChatEngine(
        ShortDrop(),
        store,
        persist_interval_s=0.0,
        stream_retry_attempts=1,
        stream_retry_backoff_s=0.0,
    )
    cid, _mid, events = engine.stream_events_chat("s1", "question")

    assert "".join(text for kind, text in events if kind == "content") == completed
    assert store.get_messages(cid)[-1]["content"] == completed


def test_hostile_unmergeable_user_input_is_hard_capped_by_utf8_bytes(store):
    client = RecordingClient()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=2048,
        context_safety_tokens=192,
    )
    hostile = "!a#B%7&x*Q?" * 800
    result = engine.chat(
        "s1", hostile, system_prompt="trusted tutor policy " * 120, max_tokens=1200
    )

    sent, params = client.messages[-1], client.params[-1]
    assert sent[-1]["content"] != hostile
    assert sum(_message_tokens(message) for message in sent) + params["max_tokens"] + 192 <= 2048
    assert store.get_messages(result.conversation_id)[0]["content"] == hostile


def test_dynamic_system_context_uses_the_same_byte_fallback_hard_cap(store):
    client = RecordingClient()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=2048,
        context_safety_tokens=192,
    )
    dynamic_system = "trusted policy\n\nWeb context:\n" + ("!a#B%7&x*Q?" * 500)
    engine.chat("s1", "help", system_prompt=dynamic_system, max_tokens=1200)

    sent, params = client.messages[-1], client.params[-1]
    assert sent[0]["content"] != dynamic_system
    assert sum(_message_tokens(message) for message in sent) + params["max_tokens"] + 192 <= 2048


def test_cancel_during_recovery_backoff_prevents_another_inference_call(store):
    class AlwaysDrops:
        def __init__(self) -> None:
            self.calls = 0

        def stream_events(self, messages, **params):
            self.calls += 1
            yield "content", "partial"
            raise httpx.ReadError("socket reset")

    cancel = threading.Event()
    client = AlwaysDrops()
    engine = ChatEngine(
        client,
        store,
        stream_retry_attempts=5,
        stream_retry_backoff_s=1.0,
    )
    _cid, _mid, events = engine.stream_events_chat("s1", "question", cancel_event=cancel)
    assert next(events) == ("content", "partial")
    assert next(events)[0] == "recovering"

    started = time.monotonic()
    cancel.set()
    with pytest.raises(StopIteration):
        next(events)
    assert time.monotonic() - started < 0.2
    assert client.calls == 1


def test_context_error_is_permanent_and_not_retried(store):
    class ContextFailure:
        def __init__(self) -> None:
            self.calls = 0

        def stream_events(self, messages, **params):
            self.calls += 1
            raise InferenceStreamError("Context size has been exceeded", retryable=False)
            yield  # pragma: no cover

    client = ContextFailure()
    engine = ChatEngine(client, store, stream_retry_attempts=5, stream_retry_backoff_s=0.0)
    _cid, _mid, events = engine.stream_events_chat("s1", "hi")

    with pytest.raises(InferenceStreamError, match="Context size"):
        list(events)
    assert client.calls == 1
