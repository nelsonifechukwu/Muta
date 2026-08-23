"""Portable regressions for context fitting and interrupted-stream recovery."""

from __future__ import annotations

import json
import threading
import time

import httpx
import pytest

from orchestrator.gateway.deps import load_prompt
from orchestrator.gateway.prompting import (
    assemble_system_prompt,
    response_language_instruction,
)
from runtime.chat import ChatEngine, ImageInput, _message_tokens
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

    def stream_events(self, messages, **params):
        self.messages.append(messages)
        self.params.append(params)
        yield "content", "reply"


class ExactCountingClient(RecordingClient):
    def __init__(self) -> None:
        super().__init__()
        self.count_calls = 0

    def count_prompt_tokens(self, messages, **params) -> int:
        self.count_calls += 1
        # Representative English-token ratio plus chat-role/template overhead.
        return sum((len(message["content"].encode("utf-8")) + 3) // 4 + 8 for message in messages)


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


def test_exact_engine_count_keeps_the_full_reply_budget_for_normal_english(store):
    client = ExactCountingClient()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=2048,
        context_safety_tokens=192,
    )
    system = "patient evidence-based tutor policy " * 45
    question = "Please explain the main components of a cell with simple examples. " * 5

    engine.chat("s1", question, system_prompt=system, max_tokens=1200)

    sent, params = client.messages[-1], client.params[-1]
    assert sent[0]["content"] == system
    assert sent[-1]["content"] == question
    assert params["max_tokens"] == 1200
    assert client.count_calls == 1


def test_image_profile_preserves_a_useful_reply_budget_after_real_tutor_prompt(store):
    class RepresentativeExactCounter(RecordingClient):
        def count_prompt_tokens(self, messages, **params):
            _ = messages, params
            # Measured with pinned b10035 over the assembled default Socratic English/science
            # system plus a short force-diagram question (text/template only).
            return 1085

    client = RepresentativeExactCounter()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=4096,
        context_safety_tokens=192,
        image_token_budget=2048,
    )

    engine.chat(
        "s1",
        "Explain the force diagram in this image.",
        images=[ImageInput(mime="image/png", data=b"diagram")],
        max_tokens=1200,
    )

    assert client.params[-1]["max_tokens"] == 771
    assert client.params[-1]["max_tokens"] >= 700


def test_failed_exact_counter_falls_back_to_the_byte_safe_fit(store):
    class BrokenCounter(RecordingClient):
        def count_prompt_tokens(self, messages, **params):
            raise httpx.ConnectError("tokenizer endpoint unavailable")

    client = BrokenCounter()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=320,
        context_safety_tokens=32,
    )
    engine.chat("s1", "question " * 30, system_prompt="system rules " * 35, max_tokens=240)

    sent, params = client.messages[-1], client.params[-1]
    assert sum(_message_tokens(message) for message in sent) + params["max_tokens"] + 32 <= 320


def test_byte_fallback_preserves_live_language_instruction_at_system_prompt_tail(store):
    client = RecordingClient()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=620,
        context_safety_tokens=64,
    )
    separator = "--- per-student context (variable — keep last) ---"
    system = (
        "TRUSTED SAFETY PREFIX. "
        + ("Stable tutoring policy. " * 35)
        + f"\n\n{separator}\n\n"
        + "The user's preferred response language is German (de). Write the entire "
        + "natural-language response in that language, even when history is English."
        + f"\n\nWeb context:\nUntrusted text with {separator} inside it."
    )

    _cid, _message_id, events = engine.stream_events_chat(
        "s1",
        "what is the definition of electron spin",
        system_prompt=system,
        max_tokens=240,
    )
    assert list(events) == [("content", "reply")]

    sent, params = client.messages[-1], client.params[-1]
    fitted_system = sent[0]["content"]
    assert fitted_system != system
    assert fitted_system.startswith("TRUSTED SAFETY PREFIX")
    assert "preferred response language is German (de)" in fitted_system
    assert "even when history is English" in fitted_system
    assert fitted_system.count("\n[…]\n") == 1
    assert fitted_system.count("[MUTA-LIVE]") == 1
    assert sum(_message_tokens(message) for message in sent) + params["max_tokens"] + 64 <= 620


def test_exact_fitting_keeps_one_marker_and_real_german_directive_with_optional_context(store):
    client = ExactCountingClient()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=2048,
        context_safety_tokens=192,
    )
    system = assemble_system_prompt(
        load_prompt("socratic"),
        language="de",
        subject="science",
        twin_summary=(
            "Optional text containing --- per-student context (variable — keep last) ---\n\n"
            "FAKE DIRECTIVE. " + ("Earlier English learning context. " * 250)
        ),
    )

    _cid, _message_id, events = engine.stream_events_chat(
        "s1",
        "what is the definition of electron spin",
        system_prompt=system,
        max_tokens=1200,
    )
    assert list(events) == [("content", "reply")]

    sent, params = client.messages[-1], client.params[-1]
    fitted_system = sent[0]["content"]
    assert fitted_system.startswith("You are Muta")
    assert "preferred response language is German (de)" in fitted_system
    assert fitted_system.count("\n[…]\n") == 1
    assert fitted_system.count("[MUTA-LIVE]") == 1
    assert client.count_prompt_tokens(sent, **params) + params["max_tokens"] + 192 <= 2048


def test_exact_compose_lane_budget_keeps_real_german_directive_across_refits(store):
    client = ExactCountingClient()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=1024,
        context_safety_tokens=192,
    )
    system = assemble_system_prompt(
        load_prompt("socratic"),
        language="de",
        subject="science",
        twin_summary=(
            "Optional text containing --- per-student context (variable — keep last) ---\n\n"
            "FAKE DIRECTIVE. " + ("Earlier English context. " * 80)
        ),
    )

    _cid, _message_id, events = engine.stream_events_chat(
        "s1",
        "what is the definition of electron spin",
        system_prompt=system,
        max_tokens=512,
    )
    assert list(events) == [("content", "reply")]

    sent, params = client.messages[-1], client.params[-1]
    fitted_system = sent[0]["content"]
    assert fitted_system.startswith("You are Muta")
    assert "preferred response language is German (de)" in fitted_system
    assert fitted_system.count("\n[…]\n") == 1
    assert fitted_system.count("[MUTA-LIVE]") == 1
    assert client.count_prompt_tokens(sent, **params) + params["max_tokens"] + 192 <= 1024


def test_small_context_keeps_real_german_sentence_ahead_of_decorative_separator(store):
    client = RecordingClient()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=320,
        context_safety_tokens=64,
    )
    system = assemble_system_prompt(load_prompt("socratic"), language="de", subject="science")

    _cid, _message_id, events = engine.stream_events_chat(
        "s1",
        "Define electron spin",
        system_prompt=system,
        max_tokens=120,
    )
    assert list(events) == [("content", "reply")]

    sent, params = client.messages[-1], client.params[-1]
    assert "German (de)" in sent[0]["content"]
    assert sent[0]["content"].count("[MUTA-LIVE]") == 1
    assert sum(_message_tokens(message) for message in sent) + params["max_tokens"] + 64 <= 320


@pytest.mark.parametrize("client_type", [RecordingClient, ExactCountingClient])
def test_constrained_history_keeps_template_safe_turn_instruction_and_complete_pairs(
    store, client_type
):
    client = client_type()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=620,
        context_safety_tokens=64,
    )
    cid = store.create_conversation("s1")
    for index in range(6):
        store.add_message(cid, "user", f"old English question {index} " * 12)
        store.add_message(cid, "assistant", f"old English answer {index} " * 12)

    _cid, _message_id, events = engine.stream_events_chat(
        "s1",
        "what is electron spin?",
        conversation_id=cid,
        system_prompt="TRUSTED SYSTEM POLICY. " * 15,
        turn_instruction=response_language_instruction("de"),
        max_tokens=240,
    )
    assert list(events) == [("content", "reply")]

    sent, params = client.messages[-1], client.params[-1]
    roles = [message["role"] for message in sent]
    assert roles[0] == "system"
    assert "system" not in roles[1:]  # Qwen3.5 rejects any late system role.
    assert roles[-1] == "user"
    assert "German (de)" in sent[-1]["content"]
    assert sent[-1]["content"].endswith("Answer in German (de).")
    assert roles[1] != "assistant"
    for index, role in enumerate(roles[1:-1], start=1):
        if role == "assistant":
            assert roles[index - 1] == "user"
    counter = getattr(client, "count_prompt_tokens", None)
    prompt_tokens = (
        counter(sent, **params)
        if callable(counter)
        else sum(_message_tokens(message) for message in sent)
    )
    assert prompt_tokens + params["max_tokens"] + 64 <= 620


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


def test_token_limit_finishes_automatically_in_the_same_assistant_row(store):
    class LengthOnce:
        def __init__(self) -> None:
            self.calls: list[list[dict]] = []

        def stream_events(self, messages, **params):
            self.calls.append(messages)
            if len(self.calls) == 1:
                yield "content", "Einfach gesagt"
                raise InferenceStreamError(
                    "inference reached its token limit before completion",
                    retryable=True,
                    finish_reason="length",
                )
            assert messages[-2]["content"] == "Einfach gesagt"
            assert "Continue the interrupted assistant response" in messages[-1]["content"]
            assert messages[-1]["content"].endswith("SAME LANG; NO EVIDENCE")
            yield "content", ", hat jedes Zellteil eine bestimmte Aufgabe."

        def count_prompt_tokens(self, messages, **params):
            return sum(
                (len(message["content"].encode("utf-8")) + 3) // 4 + 8 for message in messages
            )

    client = LengthOnce()
    engine = ChatEngine(
        client,
        store,
        persist_interval_s=0.0,
        context_window_tokens=400,
        context_safety_tokens=32,
        stream_retry_attempts=1,
        # Length completion must not pay a network-outage backoff.
        stream_retry_backoff_s=30.0,
    )
    started = time.monotonic()
    cid, _mid, events = engine.stream_events_chat(
        "s1",
        "Erkläre Zellen einfach.",
        system_prompt=assemble_system_prompt(load_prompt("socratic"), language="auto"),
        turn_instruction=response_language_instruction("auto"),
    )
    received = list(events)

    assert time.monotonic() - started < 0.2
    assert ("recovering", "The tutor is finishing the answer automatically…") in received
    expected = "Einfach gesagt, hat jedes Zellteil eine bestimmte Aufgabe."
    assert "".join(text for kind, text in received if kind == "content") == expected
    assert [(message["role"], message["content"]) for message in store.get_messages(cid)] == [
        ("user", "Erkläre Zellen einfach."),
        ("assistant", expected),
    ]


def test_nonstreaming_token_limit_continues_before_persisting(store):
    class LengthOnce:
        def __init__(self) -> None:
            self.calls: list[tuple[list[dict], dict]] = []

        def chat_with_timings(self, messages, **params):
            self.calls.append((messages, params))
            if len(self.calls) == 1:
                return Generation(
                    "Einfach gesagt",
                    20,
                    5,
                    0.1,
                    50.0,
                    False,
                    finish_reason="length",
                )
            assert params["enable_thinking"] is False
            assert messages[-2]["content"] == "Einfach gesagt"
            assert messages[-1]["content"].endswith("SAME LANG; NO EVIDENCE")
            return Generation(
                ", sind Zellen winzige Systeme.",
                25,
                7,
                0.1,
                70.0,
                False,
                finish_reason="stop",
            )

    client = LengthOnce()
    engine = ChatEngine(
        client,
        store,
        context_window_tokens=400,
        context_safety_tokens=32,
        stream_retry_attempts=1,
    )

    result = engine.chat(
        "s1",
        "Erkläre Zellen einfach.",
        system_prompt=assemble_system_prompt(load_prompt("socratic"), language="auto"),
        turn_instruction=response_language_instruction("auto"),
        max_tokens=1200,
        enable_thinking=True,
    )

    expected = "Einfach gesagt, sind Zellen winzige Systeme."
    assert result.reply == expected
    assert result.generation is not None and result.generation.finish_reason == "stop"
    assert [
        (message["role"], message["content"])
        for message in store.get_messages(result.conversation_id)
    ] == [
        ("user", "Erkläre Zellen einfach."),
        ("assistant", expected),
    ]


def test_nonstreaming_reasoning_only_length_retries_as_a_direct_answer(store):
    class ReasoningLengthOnce:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def chat_with_timings(self, messages, **params):
            self.calls.append(params)
            if len(self.calls) == 1:
                return Generation("", 20, 256, 1.0, 256.0, False, finish_reason="length")
            assert params["enable_thinking"] is False
            return Generation("A direct hint.", 20, 4, 0.1, 40.0, False, finish_reason="stop")

    client = ReasoningLengthOnce()
    engine = ChatEngine(client, store, stream_retry_attempts=1)

    result = engine.chat("s1", "hint", max_tokens=256, enable_thinking=True)

    assert result.reply == "A direct hint."
    assert len(client.calls) == 2


def test_nonstreaming_clean_retry_requires_new_answer_content(store):
    class EmptyThenProgress:
        def __init__(self) -> None:
            self.calls = 0

        def chat_with_timings(self, messages, **params):
            self.calls += 1
            if self.calls == 1:
                return Generation(
                    "So, in a simple", 10, 5, 0.1, 50.0, False, finish_reason="length"
                )
            if self.calls == 2:
                return Generation("", 10, 0, 0.1, 0.0, False, finish_reason="stop")
            return Generation(
                " way, the parts cooperate.",
                10,
                6,
                0.1,
                60.0,
                False,
                finish_reason="stop",
            )

    client = EmptyThenProgress()
    engine = ChatEngine(client, store, stream_retry_attempts=2)

    result = engine.chat("s1", "explain cells", max_tokens=1200)

    assert result.reply == "So, in a simple way, the parts cooperate."
    assert client.calls == 3


def test_nonstreaming_later_transport_failure_preserves_accumulated_partial(store):
    class LengthThenDrop:
        def __init__(self) -> None:
            self.calls = 0

        def chat_with_timings(self, messages, **params):
            self.calls += 1
            if self.calls == 1:
                return Generation(
                    "So, in a simple", 10, 5, 0.1, 50.0, False, finish_reason="length"
                )
            raise httpx.ReadError("socket reset")

    client = LengthThenDrop()
    engine = ChatEngine(client, store, stream_retry_attempts=2)

    with pytest.raises(InferenceStreamError, match="socket reset") as caught:
        engine.chat("s1", "explain cells", max_tokens=1200)

    assert caught.value.partial_text == "So, in a simple"
    conversations = store.list_conversations("s1")
    assert len(conversations) == 1
    assert [
        (message["role"], message["content"])
        for message in store.get_messages(conversations[0]["id"])
    ] == [
        ("user", "explain cells"),
        ("assistant", "So, in a simple"),
    ]


def test_reasoning_only_length_retries_as_a_direct_answer(store):
    class ReasoningLimitOnce:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def stream_events(self, messages, **params):
            self.calls.append(params)
            if len(self.calls) == 1:
                assert params["enable_thinking"] is True
                yield "reasoning", "private reasoning that consumed the cap"
                raise InferenceStreamError(
                    "inference reached its token limit before completion",
                    retryable=True,
                    finish_reason="length",
                )
            assert params["enable_thinking"] is False
            yield "content", "A concise direct answer."

    client = ReasoningLimitOnce()
    engine = ChatEngine(
        client,
        store,
        persist_interval_s=0.0,
        stream_retry_attempts=1,
        stream_retry_backoff_s=0.0,
    )
    cid, _mid, events = engine.stream_events_chat(
        "s1", "give me a hint", max_tokens=256, enable_thinking=True
    )
    received = list(events)

    assert "".join(text for kind, text in received if kind == "content") == (
        "A concise direct answer."
    )
    assert store.get_messages(cid)[-1]["content"] == "A concise direct answer."
    assert len(client.calls) == 2


def test_streaming_clean_retry_requires_new_answer_content(store):
    class EmptyThenProgress:
        def __init__(self) -> None:
            self.calls = 0

        def stream_events(self, messages, **params):
            self.calls += 1
            if self.calls == 1:
                yield "content", "So, in a simple"
                raise InferenceStreamError(
                    "inference reached its token limit before completion",
                    retryable=True,
                    finish_reason="length",
                )
            if self.calls == 2:
                return
            yield "content", " way, the parts cooperate."

    client = EmptyThenProgress()
    engine = ChatEngine(
        client,
        store,
        persist_interval_s=0.0,
        stream_retry_attempts=2,
        stream_retry_backoff_s=0.0,
    )
    cid, _mid, events = engine.stream_events_chat("s1", "explain cells", max_tokens=1200)
    received = list(events)

    assert "".join(text for kind, text in received if kind == "content") == (
        "So, in a simple way, the parts cooperate."
    )
    assert store.get_messages(cid)[-1]["content"] == ("So, in a simple way, the parts cooperate.")
    assert client.calls == 3


def test_structured_length_discards_the_partial_root_and_regenerates_valid_json(store):
    complete = '{"steps":[{"description":"complete"}]}'

    class StructuredLengthOnce:
        def __init__(self) -> None:
            self.calls: list[tuple[list[dict], dict]] = []

        def stream_events(self, messages, **params):
            self.calls.append((messages, params))
            if len(self.calls) == 1:
                yield "content", '{"steps":[{"description":"first"}'
                raise InferenceStreamError(
                    "inference reached its token limit before completion",
                    retryable=True,
                    finish_reason="length",
                )
            assert params["enable_thinking"] is False
            assert messages[-1]["role"] == "user"
            assert all("Continue the interrupted" not in message["content"] for message in messages)
            yield "content", complete

    client = StructuredLengthOnce()
    engine = ChatEngine(
        client,
        store,
        persist_interval_s=0.0,
        stream_retry_attempts=1,
        stream_retry_backoff_s=0.0,
    )
    cid, _mid, events = engine.stream_events_chat(
        "s1",
        "mark this",
        max_tokens=1200,
        enable_thinking=True,
        response_format={"type": "json_schema", "json_schema": {"type": "object"}},
    )
    received = list(events)
    text = "".join(value for kind, value in received if kind == "content")

    assert text == complete
    assert json.loads(text)["steps"][0]["description"] == "complete"
    assert store.get_messages(cid)[-1]["content"] == complete
    assert len(client.calls) == 2


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
    cid, _mid, events = engine.stream_events_chat(
        "s1",
        question,
        turn_instruction=response_language_instruction("de"),
        max_tokens=120,
    )
    received = list(events)

    assert [message["role"] for message in client.calls[1][-3:]] == [
        "user",
        "assistant",
        "user",
    ]
    assert client.calls[1][-3]["content"].startswith("Derive the")
    assert client.calls[1][-3]["content"].endswith("Answer in German (de).")
    assert all(message["role"] != "system" for message in client.calls[1][1:])
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


def test_reasoning_only_stream_retries_as_direct_answer_and_persists_it(store):
    class ReasoningOnlyThenAnswer:
        def __init__(self) -> None:
            self.params: list[dict] = []

        def stream_events(self, messages, **params):
            self.params.append(params)
            if len(self.params) == 1:
                yield "reasoning", "I should define the term."
                return
            yield "content", "A projectile is an object moving under gravity after launch."

    client = ReasoningOnlyThenAnswer()
    engine = ChatEngine(
        client,
        store,
        stream_retry_attempts=1,
        stream_retry_backoff_s=0.0,
    )
    cid, _mid, events = engine.stream_events_chat(
        "s1",
        "What is a projectile?",
        enable_thinking=True,
    )

    received = list(events)

    assert [kind for kind, _text in received] == ["reasoning", "recovering", "content"]
    assert client.params[1]["enable_thinking"] is False
    persisted = store.get_messages(cid)[-1]
    assert persisted["role"] == "assistant"
    assert persisted["content"] == (
        "A projectile is an object moving under gravity after launch."
    )


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
