"""Multi-turn chat orchestration.

Turns are reconstructed from the store and replayed to the model, so the conversation has
memory across requests and across process restarts. The system prompt is *injected by the
caller* (the gateway supplies the mode/persona prompt) — the engine stays a pure mechanism
and carries no pedagogy of its own.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass

from runtime.client import Generation, InferenceClient, Message
from runtime.memory import ConversationStore

DEFAULT_SYSTEM_PROMPT = (
    "You are a patient tutor for mathematics and scientific reasoning. Be concise, guide "
    "the student's own thinking, and show working when you compute."
)


@dataclass
class ChatResult:
    conversation_id: str
    reply: str
    # Present for non-streaming turns; bench/profile.py reads TPS from here. Optional so the
    # streaming path and existing callers are unaffected.
    generation: Generation | None = None
    # Row id of the persisted user turn — attachment linking keys on it.
    user_message_id: int | None = None


class _ReplyWriter:
    """Writes a streaming assistant reply to the store *as it arrives*.

    Why not just persist once at the end: the end is not guaranteed to happen. When a
    browser disconnects mid-stream, Starlette abandons the response generator inside a
    reference cycle — its `finally` runs whenever the cyclic GC next collects, which is
    unbounded. Measured against a real uvicorn (2026-08-08): after a disconnect the reply
    was still absent from Postgres seconds later, and appeared only when `gc.collect()` was
    forced. A student switching conversations and switching back saw their answer gone.

    So durability cannot depend on finalization. The first content chunk INSERTs the row and
    each subsequent flush UPDATEs it in place, which bounds the loss to `interval_s` of text
    and keeps the row's serial id — and therefore its place in history — fixed. The trailing
    `flush()` in the caller's `finally` is now an optimisation, not the mechanism.

    Nothing is written until the first content chunk: an assistant turn that produced only
    reasoning, or nothing at all, still stores nothing.
    """

    def __init__(self, store: ConversationStore, conversation_id: str, interval_s: float) -> None:
        self.store = store
        self.cid = conversation_id
        self.interval_s = interval_s
        self.chunks: list[str] = []
        self.message_id: int | None = None
        self._flushed_len = 0
        self._last_flush = 0.0

    def add(self, text: str) -> None:
        self.chunks.append(text)
        now = time.monotonic()
        if now - self._last_flush >= self.interval_s:
            self.flush()
            self._last_flush = now

    def flush(self) -> None:
        """Idempotent: a flush with nothing new since the last one touches no rows."""
        if not self.chunks:
            return
        text = "".join(self.chunks)
        if len(text) == self._flushed_len:
            return
        if self.message_id is None:
            self.message_id = self.store.add_message(self.cid, "assistant", text)
        else:
            self.store.update_message(self.message_id, text)
        self._flushed_len = len(text)


class ChatEngine:
    def __init__(
        self,
        client: InferenceClient,
        store: ConversationStore,
        *,
        max_history_messages: int = 20,
        default_system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        # 0.25 s bounds a disconnect's cost to ~1 token on the x86 target (5 tok/s) and ~8
        # on a fast native box, for four small UPDATEs per second per active stream — far
        # below anything Postgres notices, and cheaper than the alternative of a student
        # losing a paragraph.
        persist_interval_s: float = 0.25,
    ) -> None:
        self.client = client
        self.store = store
        self.max_history_messages = max_history_messages
        self.default_system_prompt = default_system_prompt
        # How often a streaming reply is written through to the store. See `_ReplyWriter`:
        # this is the bound on how much of a reply a disconnect can cost.
        self.persist_interval_s = persist_interval_s

    def _open(self, student_id: str, conversation_id: str | None, **meta) -> str:
        if conversation_id:
            conversation = self.store.get_conversation(conversation_id)
            if conversation is not None and conversation.get("student_id") != student_id:
                raise PermissionError("conversation belongs to another learner")
            if conversation is not None:
                return conversation_id
        return self.store.create_conversation(student_id, **meta)

    def _assemble(self, conversation_id: str, system_prompt: str | None, message: str) -> list[Message]:
        history = self.store.get_messages(conversation_id, limit=self.max_history_messages)
        messages: list[Message] = [
            {"role": "system", "content": system_prompt or self.default_system_prompt}
        ]
        messages += [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": message})
        return messages

    def _assemble_history(self, conversation_id: str, system_prompt: str | None) -> list[Message]:
        """Prompt for regeneration: system + existing history, with NO new user turn appended.
        The last stored message is already the user's turn, so this re-answers it — used by
        'answer now', which re-runs the in-flight turn without duplicating the question."""
        history = self.store.get_messages(conversation_id, limit=self.max_history_messages)
        messages: list[Message] = [
            {"role": "system", "content": system_prompt or self.default_system_prompt}
        ]
        messages += [{"role": m["role"], "content": m["content"]} for m in history]
        return messages

    def chat(
        self,
        student_id: str,
        message: str,
        *,
        conversation_id: str | None = None,
        system_prompt: str | None = None,
        mode: str | None = None,
        persona: str | None = None,
        subject: str | None = None,
        language: str | None = None,
        title: str | None = None,
        **params,
    ) -> ChatResult:
        cid = self._open(
            student_id, conversation_id,
            mode=mode, persona=persona, subject=subject, language=language, title=title,
        )
        messages = self._assemble(cid, system_prompt, message)
        user_message_id = self.store.add_message(cid, "user", message)
        generation = self.client.chat_with_timings(messages, **params)
        self.store.add_message(cid, "assistant", generation.text)
        return ChatResult(
            conversation_id=cid,
            reply=generation.text,
            generation=generation,
            user_message_id=user_message_id,
        )

    def stream_chat(
        self,
        student_id: str,
        message: str,
        *,
        conversation_id: str | None = None,
        system_prompt: str | None = None,
        mode: str | None = None,
        persona: str | None = None,
        subject: str | None = None,
        language: str | None = None,
        title: str | None = None,
        **params,
    ) -> tuple[str, int, Iterator[str]]:
        """Returns (conversation_id, user_message_id, token iterator). The reply is persisted
        when the iterator finishes — including early close/error (partial persist)."""
        cid = self._open(
            student_id, conversation_id,
            mode=mode, persona=persona, subject=subject, language=language, title=title,
        )
        messages = self._assemble(cid, system_prompt, message)
        user_message_id = self.store.add_message(cid, "user", message)

        def _gen() -> Iterator[str]:
            writer = _ReplyWriter(self.store, cid, self.persist_interval_s)
            try:
                for delta in self.client.stream(messages, **params):
                    # Written through as it arrives: losing the assistant half of a turn
                    # corrupts the replayed history for every later turn, and a disconnect
                    # gives no reliable chance to save it afterwards.
                    writer.add(delta)
                    yield delta
            finally:
                writer.flush()

        return cid, user_message_id, _gen()

    def stream_events_chat(
        self,
        student_id: str,
        message: str,
        *,
        conversation_id: str | None = None,
        system_prompt: str | None = None,
        mode: str | None = None,
        persona: str | None = None,
        subject: str | None = None,
        language: str | None = None,
        title: str | None = None,
        regenerate: bool = False,
        **params,
    ) -> tuple[str, int | None, Iterator[tuple[str, str]]]:
        """Like `stream_chat`, but yields ('reasoning' | 'content', text) chunks so a client
        can render Qwen3 thinking as it happens. Only the answer content is persisted — the
        chain of thought is ephemeral, matching the non-streaming path which stores `content`.

        With ``regenerate`` the last stored user turn is re-answered and NO new user message is
        added (the 'answer now' path re-runs the in-flight turn without the thinking phase)."""
        cid = self._open(
            student_id, conversation_id,
            mode=mode, persona=persona, subject=subject, language=language, title=title,
        )
        if regenerate:
            messages = self._assemble_history(cid, system_prompt)
            user_message_id = None
        else:
            messages = self._assemble(cid, system_prompt, message)
            user_message_id = self.store.add_message(cid, "user", message)

        def _gen() -> Iterator[tuple[str, str]]:
            writer = _ReplyWriter(self.store, cid, self.persist_interval_s)
            try:
                for kind, text in self.client.stream_events(messages, **params):
                    if kind == "content":
                        writer.add(text)
                    yield kind, text
            finally:
                # Same write-through rule as stream_chat; reasoning stays ephemeral, so a
                # turn abandoned during the thinking phase still stores nothing.
                writer.flush()

        return cid, user_message_id, _gen()
