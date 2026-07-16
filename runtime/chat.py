"""Multi-turn chat orchestration.

Turns are reconstructed from the store and replayed to the model, so the conversation has
memory across requests and across process restarts. The system prompt is *injected by the
caller* (the gateway supplies the mode/persona prompt) — the engine stays a pure mechanism
and carries no pedagogy of its own.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from runtime.client import InferenceClient, Message
from runtime.memory import ConversationStore

DEFAULT_SYSTEM_PROMPT = (
    "You are a patient tutor for mathematics and scientific reasoning. Be concise, guide "
    "the student's own thinking, and show working when you compute."
)


@dataclass
class ChatResult:
    conversation_id: str
    reply: str


class ChatEngine:
    def __init__(
        self,
        client: InferenceClient,
        store: ConversationStore,
        *,
        max_history_messages: int = 20,
        default_system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self.client = client
        self.store = store
        self.max_history_messages = max_history_messages
        self.default_system_prompt = default_system_prompt

    def _open(self, student_id: str, conversation_id: str | None, **meta) -> str:
        if conversation_id and self.store.get_conversation(conversation_id):
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
        **params,
    ) -> ChatResult:
        cid = self._open(
            student_id, conversation_id,
            mode=mode, persona=persona, subject=subject, language=language,
        )
        messages = self._assemble(cid, system_prompt, message)
        self.store.add_message(cid, "user", message)
        reply = self.client.chat(messages, **params)
        self.store.add_message(cid, "assistant", reply)
        return ChatResult(conversation_id=cid, reply=reply)

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
        **params,
    ) -> tuple[str, Iterator[str]]:
        """Returns (conversation_id, token iterator). The full reply is persisted once the
        iterator is exhausted, so callers must drain it."""
        cid = self._open(
            student_id, conversation_id,
            mode=mode, persona=persona, subject=subject, language=language,
        )
        messages = self._assemble(cid, system_prompt, message)
        self.store.add_message(cid, "user", message)

        def _gen() -> Iterator[str]:
            chunks: list[str] = []
            for delta in self.client.stream(messages, **params):
                chunks.append(delta)
                yield delta
            self.store.add_message(cid, "assistant", "".join(chunks))

        return cid, _gen()
