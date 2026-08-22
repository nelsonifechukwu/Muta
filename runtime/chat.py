"""Multi-turn chat orchestration.

Turns are reconstructed from the store and replayed to the model, so the conversation has
memory across requests and across process restarts. The system prompt is *injected by the
caller* (the gateway supplies the mode/persona prompt) — the engine stays a pure mechanism
and carries no pedagogy of its own.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx

from runtime.client import Generation, InferenceClient, InferenceStreamError, Message
from runtime.memory import ConversationStore

_MESSAGE_OVERHEAD_TOKENS = 8
_MIN_REPLY_TOKENS = 64
_PER_STUDENT_CONTEXT = "--- per-student context (variable — keep last) ---".encode()
_LIVE_CONTEXT = b"\n[MUTA-LIVE]\n"
_TURN_INSTRUCTION = "\n\n[MUTA RUNTIME INSTRUCTION — not part of the learner's message]\n"
_RESUME_PROMPT = (
    "Internal Muta runtime continuation instruction: this is not a learner message and is never "
    "language evidence. Continue the interrupted assistant response directly from its exact "
    "final character and in exactly the same response language. Do not repeat or restart any "
    "part, apologize, mention the interruption, or add a new heading. Finish the original "
    "answer only. SAME LANG; NO EVIDENCE"
)
_MAX_RESUME_OVERLAP = 512
_MIN_RESUME_OVERLAP = 8
_VIZ_KINDS = {
    "d3": {"line", "scatter", "bar", "force"},
    "three": {"scene3d"},
    "gsap": {"animation"},
    "anime": {"animation"},
    "motion": {"animation"},
}
_VIZ_FENCE = re.compile(
    r"(^|\n)( {0,3})```muta-viz[\t ]*\r?\n([\s\S]*?)\r?\n\2```[\t ]*(?=\r?\n|$)"
)
_VIZ_MARKED_JSON_FENCE = re.compile(
    r"(^|\n)( {0,3})\$\$muta-viz\$\$[\t ]*\r?\n\2```json[\t ]*\r?\n"
    r"([\s\S]*?)\r?\n\2```[\t ]*(?=\r?\n|$)"
)


def strip_visualization_protocol(text: str) -> str:
    """Remove only recognized, minimally valid visual blocks from a prompt/evaluation copy.

    The persisted/public reply stays byte-identical for browser replay. Old declarative payloads
    do not need to consume the next 2,048-token inference lane or contaminate quality grading.
    """

    def replace(match: re.Match[str]) -> str:
        try:
            candidate = json.loads(match.group(3))
        except (json.JSONDecodeError, TypeError):
            return match.group(0)
        if not isinstance(candidate, dict) or candidate.get("version") != 1:
            return match.group(0)
        library = candidate.get("library")
        if library not in _VIZ_KINDS or candidate.get("kind") not in _VIZ_KINDS[library]:
            return match.group(0)
        if not isinstance(candidate.get("title"), str) or not isinstance(
            candidate.get("aria_label"), str
        ):
            return match.group(0)
        height = candidate.get("height")
        if not isinstance(height, int) or isinstance(height, bool) or not 240 <= height <= 600:
            return match.group(0)
        return match.group(1)

    cleaned = _VIZ_FENCE.sub(replace, str(text or ""))
    cleaned = _VIZ_MARKED_JSON_FENCE.sub(replace, cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _prompt_content(message: dict) -> str:
    content = str(message.get("content", ""))
    return strip_visualization_protocol(content) if message.get("role") == "assistant" else content


def _estimate_tokens(text: str) -> int:
    """Tokenizer-free planning estimate: UTF-8 bytes/3, rounded up.

    The separate template/message overhead and context safety margin absorb normal variance;
    llama-server remains the authority for exact model-token counts.
    """
    return max(1, (len(text.encode("utf-8")) + 2) // 3)


def _message_tokens(message: Message) -> int:
    content = message.get("content", "")
    # Byte-fallback BPE can approach one token per UTF-8 byte. This includes role=system:
    # the gateway appends live web/RAG/twin context to that message, so its contents are not
    # wholly static or trusted. bytes/3 remains a history-quality heuristic only.
    return _MESSAGE_OVERHEAD_TOKENS + max(1, len(content.encode("utf-8")))


def _retryable_stream_error(exc: Exception) -> bool:
    if isinstance(exc, InferenceStreamError):
        return exc.retryable
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 425, 429, 500, 502, 503, 504}
    return isinstance(exc, (httpx.TransportError, ConnectionError, TimeoutError))


def _truncate_message(message: Message, token_budget: int) -> Message:
    """Return a prompt-only truncation; the persisted message is never modified."""
    content_budget = max(1, token_budget - _MESSAGE_OVERHEAD_TOKENS)
    raw = message.get("content", "").encode("utf-8")
    max_bytes = content_budget
    if len(raw) <= max_bytes:
        return dict(message)
    marker = "\n[…]\n".encode()
    usable = max(1, max_bytes - len(marker))
    if message.get("role") == "system":
        # The stable safety/pedagogy prefix is deliberately first for prompt caching, while
        # live persona/language instructions begin at the per-student separator. Keeping only
        # the head silently drops "respond in German" on a full conversation and lets older
        # English history win. Preserve the prefix head plus the complete first variable block;
        # optional twin/RAG/web blocks after it are lower-priority when the context is this full.
        # The full authored separator becomes a compact private boundary after the first clip.
        # Keeping that boundary makes every later exact-token fitting pass rediscover the live
        # directive instead of falling back to head-only truncation. Optional retrieved/web text
        # is untrusted, so the earliest recognized boundary wins; appended lookalikes come later.
        original_start = raw.find(_PER_STUDENT_CONTEXT)
        live_start = raw.find(_LIVE_CONTEXT)
        boundaries = [
            (position, token)
            for position, token in (
                (original_start, _PER_STUDENT_CONTEXT),
                (live_start, _LIVE_CONTEXT),
            )
            if position >= 0
        ]
        context_start, context_token = min(boundaries, default=(-1, b""), key=lambda item: item[0])
        if context_start >= 0:
            directive_start = context_start + len(context_token)
            while directive_start < len(raw) and raw[directive_start] in b"\r\n":
                directive_start += 1
            directive_end = raw.find(b"\n\n", directive_start)
            if directive_end < 0:
                directive_end = len(raw)
            directive = raw[directive_start:directive_end]
            prefix = raw[:context_start]
            while prefix.endswith(marker):
                prefix = prefix[: -len(marker)]
            system_usable = max(1, max_bytes - len(marker) - len(_LIVE_CONTEXT))
            if len(directive) <= system_usable:
                head_budget = min(len(prefix), system_usable - len(directive))
                optional_budget = system_usable - head_budget - len(directive)
                optional = raw[directive_end : directive_end + optional_budget]
                clipped = prefix[:head_budget] + marker + _LIVE_CONTEXT + directive + optional
            else:
                head_budget = min(len(prefix), system_usable // 4)
                directive_budget = max(1, system_usable - head_budget)
                clipped = (
                    prefix[:head_budget] + marker + _LIVE_CONTEXT + directive[:directive_budget]
                )
        else:
            clipped = raw[:max_bytes]
    else:
        # A long question needs its setup and its actual ask; an interrupted assistant needs
        # the immediate tail. Keeping both is safer than blindly retaining one side.
        head = usable // 3
        clipped = raw[:head] + marker + raw[-(usable - head) :]
    return {**message, "content": clipped.decode("utf-8", errors="ignore")}


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
    # Exact assistant row for durable citations and other turn-owned metadata.
    assistant_message_id: int | None = None


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

    @property
    def text(self) -> str:
        return "".join(self.chunks)

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


class _ReplyEventStream(Iterator[tuple[str, str]]):
    """Iterator facade that exposes the exact assistant row owned by this generation.

    Parallel jobs may share a conversation, so callers appending metadata must never rediscover
    their row with `last_message_id()`: another job can finish between generation and append.
    """

    def __init__(self, iterator: Iterator[tuple[str, str]], writer: _ReplyWriter) -> None:
        self._iterator = iterator
        self._writer = writer

    @property
    def assistant_message_id(self) -> int | None:
        return self._writer.message_id

    def __iter__(self) -> _ReplyEventStream:
        return self

    def __next__(self) -> tuple[str, str]:
        return next(self._iterator)

    def close(self) -> None:
        close = getattr(self._iterator, "close", None)
        if callable(close):
            close()


class _ResumeDeduplicator:
    """Remove an exact repeated boundary prefix without delaying unrelated continuation."""

    def __init__(self, prior: str) -> None:
        self.prior = prior[-_MAX_RESUME_OVERLAP:]
        self.pending = ""
        self.min_overlap = min(_MIN_RESUME_OVERLAP, max(1, len(self.prior)))
        self.decided = not self.prior

    def feed(self, text: str) -> str:
        if self.decided:
            return text
        self.pending += text
        limit = min(len(self.prior), _MAX_RESUME_OVERLAP)
        possible_longer: list[int] = []
        full: list[int] = []
        for size in range(self.min_overlap, limit + 1):
            suffix = self.prior[-size:]
            if len(self.pending) <= size and suffix.startswith(self.pending):
                possible_longer.append(size)
            elif self.pending.startswith(suffix):
                full.append(size)
        if possible_longer and len(self.pending) < _MAX_RESUME_OVERLAP:
            return ""
        self.decided = True
        overlap = max(full, default=0)
        output, self.pending = self.pending[overlap:], ""
        return output

    def finish(self) -> str:
        if self.decided:
            output, self.pending = self.pending, ""
            return output
        limit = min(len(self.prior), len(self.pending), _MAX_RESUME_OVERLAP)
        overlap = max(
            (
                size
                for size in range(self.min_overlap, limit + 1)
                if self.pending.startswith(self.prior[-size:])
            ),
            default=0,
        )
        self.decided = True
        output, self.pending = self.pending[overlap:], ""
        return output


class ChatEngine:
    def __init__(
        self,
        client: InferenceClient,
        store: ConversationStore,
        *,
        max_history_messages: int = 20,
        history_token_budget: int = 0,
        context_window_tokens: int = 0,
        context_safety_tokens: int = 192,
        stream_retry_attempts: int = 0,
        stream_retry_backoff_s: float = 0.5,
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
        self.history_token_budget = max(0, history_token_budget)
        self.context_window_tokens = max(0, context_window_tokens)
        self.context_safety_tokens = max(0, context_safety_tokens)
        self.stream_retry_attempts = max(0, stream_retry_attempts)
        self.stream_retry_backoff_s = max(0.0, stream_retry_backoff_s)
        self.default_system_prompt = default_system_prompt
        # How often a streaming reply is written through to the store. See `_ReplyWriter`:
        # this is the bound on how much of a reply a disconnect can cost.
        self.persist_interval_s = persist_interval_s

    def _open(
        self,
        student_id: str,
        conversation_id: str | None,
        *,
        create: bool = True,
        **meta,
    ) -> str:
        if conversation_id:
            conversation = self.store.get_conversation(conversation_id)
            if conversation is not None and conversation.get("student_id") != student_id:
                raise PermissionError("conversation belongs to another learner")
            if conversation is not None:
                return conversation_id
        if not create:
            raise ValueError("regenerate requires an existing conversation")
        return self.store.create_conversation(student_id, **meta)

    def _history(self, conversation_id: str) -> list[dict]:
        history = self.store.get_messages(conversation_id, limit=self.max_history_messages)
        if self.history_token_budget <= 0:
            return history
        spent = 0
        start = len(history)
        for index in range(len(history) - 1, -1, -1):
            row = history[index]
            cost = _estimate_tokens(_prompt_content(row)) + _MESSAGE_OVERHEAD_TOKENS
            # Keep the latest row even when it alone exceeds the replay budget. The request
            # fitter can safely truncate that prompt copy; dropping it here makes a student's
            # ordinary "continue" lose the response they are asking the tutor to continue.
            if spent and spent + cost > self.history_token_budget:
                break
            spent += cost
            start = index
        # Do not begin replay at an orphan assistant. If a newer complete exchange exists,
        # discard the orphan; if the oversized newest reply is the only selected row, retain
        # its adjacent question so "continue" still has a coherent boundary.
        while start < len(history) and history[start]["role"] == "assistant":
            if any(row["role"] == "user" for row in history[start + 1 :]):
                start += 1
            elif start > 0 and history[start - 1]["role"] == "user":
                start -= 1
                break
            else:
                break
        return history[start:]

    def _assemble(
        self,
        conversation_id: str,
        system_prompt: str | None,
        message: str,
        turn_instruction: str | None = None,
    ) -> list[Message]:
        history = self._history(conversation_id)
        messages: list[Message] = [
            {"role": "system", "content": system_prompt or self.default_system_prompt}
        ]
        messages += [
            {
                "role": m["role"],
                "content": _prompt_content(m),
            }
            for m in history
        ]
        prompt_copy = message
        if turn_instruction:
            # Qwen3.5 permits a system role only at messages[0]. Keep this trusted gateway
            # instruction in a request-only envelope at the tail of the current user prompt:
            # it gets strong recency without changing the persisted learner message.
            prompt_copy += _TURN_INSTRUCTION + turn_instruction
        messages.append({"role": "user", "content": prompt_copy})
        return messages

    def _assemble_history(
        self,
        conversation_id: str,
        system_prompt: str | None,
        turn_instruction: str | None = None,
    ) -> list[Message]:
        """Prompt for regeneration: system + existing history, with NO new user turn appended.
        The last stored message is already the user's turn, so this re-answers it — used by
        'answer now', which re-runs the in-flight turn without duplicating the question."""
        history = self._history(conversation_id)
        if not history or history[-1].get("role") != "user":
            raise ValueError("regenerate requires a conversation whose last message is the user")
        messages: list[Message] = [
            {"role": "system", "content": system_prompt or self.default_system_prompt}
        ]
        messages += [
            {
                "role": m["role"],
                "content": _prompt_content(m),
            }
            for m in history
        ]
        if turn_instruction:
            # Regeneration reuses the stored final user turn, so only its ephemeral request
            # copy receives the envelope. The database row remains byte-identical.
            messages[-1] = {
                **messages[-1],
                "content": messages[-1]["content"] + _TURN_INSTRUCTION + turn_instruction,
            }
        return messages

    def _fit_request(
        self,
        messages: list[Message],
        params: dict,
        *,
        protected_tail_messages: int = 1,
    ) -> tuple[list[Message], dict]:
        """Fit prompt + requested generation inside the configured llama context."""
        fitted = [dict(message) for message in messages]
        fitted_params = dict(params)
        if self.context_window_tokens <= 0 or not fitted:
            return fitted, fitted_params

        prompt_limit = max(
            1,
            self.context_window_tokens - self.context_safety_tokens - _MIN_REPLY_TOKENS,
        )
        protected = max(1, min(protected_tail_messages, max(1, len(fitted) - 1)))

        exact_counter = getattr(self.client, "count_prompt_tokens", None)
        cached_prompt_tokens: int | None = None

        def prompt_tokens() -> int:
            nonlocal cached_prompt_tokens, exact_counter
            if cached_prompt_tokens is not None:
                return cached_prompt_tokens
            if callable(exact_counter):
                try:
                    counted = exact_counter(fitted, **fitted_params)
                    if not isinstance(counted, int) or counted <= 0:
                        raise ValueError("invalid prompt token count")
                    cached_prompt_tokens = counted
                    return counted
                except Exception:  # noqa: BLE001 — optional engine probe; hard fallback is safe
                    exact_counter = None
            cached_prompt_tokens = sum(_message_tokens(message) for message in fitted)
            return cached_prompt_tokens

        def invalidate_prompt_count() -> None:
            nonlocal cached_prompt_tokens
            cached_prompt_tokens = None

        # Drop whole oldest exchanges, leaving the stable system prefix and current/resume tail.
        while len(fitted) > 1 + protected and prompt_tokens() > prompt_limit:
            fitted.pop(1)
            while len(fitted) > 1 + protected and fitted[1].get("role") == "assistant":
                fitted.pop(1)
            invalidate_prompt_count()

        # An enormous current turn or optional grounding block can exceed the window alone.
        # Shrink only the request copy, largest reducible message first, until a useful reply
        # still fits. Stored history and the user's original text remain byte-identical.
        minimums = [96] + [48] * (len(fitted) - 1)
        while prompt_tokens() > prompt_limit:
            costs = [_message_tokens(message) for message in fitted]
            candidates = [
                (cost - minimums[index], index)
                for index, cost in enumerate(costs)
                if cost > minimums[index]
            ]
            if not candidates:
                break
            reducible, index = max(candidates)
            overflow = prompt_tokens() - prompt_limit
            target = costs[index] - min(reducible, overflow)
            fitted[index] = _truncate_message(fitted[index], target)
            invalidate_prompt_count()

        available = max(
            1,
            self.context_window_tokens - self.context_safety_tokens - prompt_tokens(),
        )
        requested = fitted_params.get("max_tokens")
        if not isinstance(requested, int) or requested <= 0:
            requested = available
        fitted_params["max_tokens"] = min(requested, available)
        return fitted, fitted_params

    def _events_with_recovery(
        self,
        messages: list[Message],
        params: dict,
        writer: _ReplyWriter,
        cancel_event: threading.Event | None = None,
    ) -> Iterator[tuple[str, str]]:
        attempt = 0
        request_messages = messages
        request_params = params
        retry_params = dict(params)
        structured = "response_format" in params
        awaiting_completion_progress = False
        stream = self.client.stream_events
        while True:
            if cancel_event is not None and cancel_event.is_set():
                return
            deduplicator = _ResumeDeduplicator(writer.text) if attempt and writer.text else None
            buffered_content: list[str] = []
            attempt_content_progress = False
            try:
                events = iter(stream(request_messages, **request_params))
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    try:
                        kind, text = next(events)
                    except StopIteration:
                        break
                    # A restarted reasoning trace is neither persisted nor useful to append
                    # to the abandoned one. Keep the original trace visible until content
                    # resumes, then the normal UI transition settles it.
                    if attempt and kind == "reasoning":
                        continue
                    if structured and kind == "content":
                        # A schema-root JSON document cannot be continued by appending another
                        # freshly generated root. Buffer until the attempt terminates cleanly;
                        # a failed attempt is discarded and regenerated from the original prompt.
                        if text:
                            buffered_content.append(text)
                            attempt_content_progress = True
                        continue
                    if kind == "content" and deduplicator is not None:
                        text = deduplicator.feed(text)
                        if not text:
                            continue
                    if kind == "content" and text:
                        attempt_content_progress = True
                    yield kind, text
                if deduplicator is not None:
                    tail = deduplicator.finish()
                    if tail:
                        attempt_content_progress = True
                        yield "content", tail
                if (structured or awaiting_completion_progress) and not attempt_content_progress:
                    # A clean stop frame with no new answer text is not proof that a previously
                    # truncated response was completed. Keep trying within the same bound, then
                    # fail visibly instead of relabeling the old partial as success.
                    raise InferenceStreamError(
                        "continuation ended without producing answer content",
                        retryable=True,
                        finish_reason="length" if awaiting_completion_progress else None,
                    )
                if structured:
                    yield from (("content", text) for text in buffered_content)
                return
            except Exception as exc:
                if deduplicator is not None:
                    tail = deduplicator.finish()
                    if tail:
                        yield "content", tail
                if not _retryable_stream_error(exc) or attempt >= self.stream_retry_attempts:
                    raise
                attempt += 1
                reached_length = (
                    isinstance(exc, InferenceStreamError) and exc.finish_reason == "length"
                )
                if reached_length:
                    # The reasoning phase can consume the entire cap before emitting answer
                    # content. Retrying the identical thinking request repeats invisibly; a
                    # continuation/restart needs the direct answer now.
                    retry_params["enable_thinking"] = False
                    awaiting_completion_progress = True
                    yield "recovering", "The tutor is finishing the answer automatically…"
                    delay = 0.0
                else:
                    yield "recovering", "The tutor paused briefly — resuming automatically…"
                    delay = min(
                        4.0,
                        self.stream_retry_backoff_s * (2 ** (attempt - 1)),
                    )
                if delay:
                    if cancel_event is not None:
                        if cancel_event.wait(delay):
                            return
                    else:
                        time.sleep(delay)
                if cancel_event is not None and cancel_event.is_set():
                    return
                partial = writer.text
                if structured:
                    # Nothing from a failed structured attempt was exposed or persisted, so
                    # regenerate one valid schema root rather than concatenating JSON fragments.
                    request_messages = messages
                    protected_tail = min(3, max(1, len(messages) - 1))
                elif partial:
                    request_messages = [
                        *messages,
                        {"role": "assistant", "content": partial},
                        {"role": "user", "content": _RESUME_PROMPT},
                    ]
                    # Original user turn + partial assistant + continuation instruction.
                    protected_tail = 3
                else:
                    request_messages = messages
                    protected_tail = 1
                request_messages, request_params = self._fit_request(
                    request_messages,
                    retry_params,
                    protected_tail_messages=protected_tail,
                )
                stream = getattr(self.client, "retry_stream_events", self.client.stream_events)

    @staticmethod
    def _merge_generations(text: str, attempts: list[Generation]) -> Generation:
        """One honest metric record for a non-streaming completion that needed continuation."""
        if len(attempts) == 1 and attempts[0].text == text:
            return attempts[0]
        elapsed = sum(attempt.elapsed_s for attempt in attempts)
        completion_tokens = sum(attempt.completion_tokens for attempt in attempts)
        return Generation(
            text=text,
            prompt_tokens=sum(attempt.prompt_tokens for attempt in attempts),
            completion_tokens=completion_tokens,
            elapsed_s=elapsed,
            tokens_per_second=(completion_tokens / elapsed if elapsed > 0 else 0.0),
            # A multi-request aggregate is necessarily derived from our wall clock even when
            # each individual engine response included its own decode timing.
            from_wall_clock=True,
            finish_reason=attempts[-1].finish_reason,
        )

    def _chat_with_length_recovery(
        self,
        messages: list[Message],
        params: dict,
    ) -> Generation:
        """Finish a non-streaming answer when the engine returns HTTP 200 + `length`."""
        request_messages = messages
        request_params = params
        retry_params = dict(params)
        structured = "response_format" in params
        reply = ""
        attempts: list[Generation] = []
        awaiting_completion_progress = False
        for attempt_index in range(self.stream_retry_attempts + 1):
            prior_reply = reply
            try:
                generation = self.client.chat_with_timings(request_messages, **request_params)
            except Exception as exc:
                if reply and not structured:
                    raise InferenceStreamError(
                        str(exc) or "inference continuation failed",
                        retryable=_retryable_stream_error(exc),
                        finish_reason=getattr(exc, "finish_reason", None),
                        partial_text=reply,
                    ) from exc
                raise
            attempts.append(generation)
            if structured:
                # Each structured retry replaces the incomplete root; only a terminal attempt
                # is eligible to become the returned/persisted document.
                reply = generation.text
            elif reply:
                deduplicator = _ResumeDeduplicator(reply)
                reply += deduplicator.feed(generation.text) + deduplicator.finish()
            else:
                reply = generation.text
            made_progress = bool(generation.text) if structured else reply != prior_reply
            needs_retry = generation.finish_reason == "length" or (
                awaiting_completion_progress and not made_progress
            )
            if not needs_retry:
                return self._merge_generations(reply, attempts)
            if attempt_index >= self.stream_retry_attempts:
                raise InferenceStreamError(
                    "inference repeatedly reached its token limit before completion",
                    retryable=False,
                    finish_reason="length",
                    partial_text="" if structured else reply,
                )
            awaiting_completion_progress = True
            retry_params["enable_thinking"] = False
            if structured or not reply:
                request_messages = messages
                protected_tail = min(3, max(1, len(messages) - 1))
            else:
                request_messages = [
                    *messages,
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": _RESUME_PROMPT},
                ]
                protected_tail = 3
            request_messages, request_params = self._fit_request(
                request_messages,
                retry_params,
                protected_tail_messages=protected_tail,
            )
        raise AssertionError("unreachable length-recovery loop")

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
        turn_instruction: str | None = None,
        title: str | None = None,
        regenerate: bool = False,
        **params,
    ) -> ChatResult:
        cid = self._open(
            student_id,
            conversation_id,
            create=not regenerate,
            mode=mode,
            persona=persona,
            subject=subject,
            language=language,
            title=title,
        )
        if regenerate:
            messages = self._assemble_history(cid, system_prompt, turn_instruction)
            user_message_id = None
        else:
            messages = self._assemble(cid, system_prompt, message, turn_instruction)
            user_message_id = self.store.add_message(cid, "user", message)
        messages, request_params = self._fit_request(
            messages,
            params,
            protected_tail_messages=min(3, max(1, len(messages) - 1)),
        )
        try:
            generation = self._chat_with_length_recovery(messages, request_params)
        except InferenceStreamError as exc:
            if exc.partial_text:
                self.store.add_message(cid, "assistant", exc.partial_text)
            raise
        assistant_message_id = self.store.add_message(cid, "assistant", generation.text)
        return ChatResult(
            conversation_id=cid,
            reply=generation.text,
            generation=generation,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
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
        turn_instruction: str | None = None,
        title: str | None = None,
        **params,
    ) -> tuple[str, int, Iterator[str]]:
        """Returns (conversation_id, user_message_id, token iterator). The reply is persisted
        when the iterator finishes — including early close/error (partial persist)."""
        cid = self._open(
            student_id,
            conversation_id,
            mode=mode,
            persona=persona,
            subject=subject,
            language=language,
            title=title,
        )
        messages = self._assemble(cid, system_prompt, message, turn_instruction)
        user_message_id = self.store.add_message(cid, "user", message)
        messages, request_params = self._fit_request(
            messages,
            params,
            protected_tail_messages=min(3, max(1, len(messages) - 1)),
        )

        def _gen() -> Iterator[str]:
            writer = _ReplyWriter(self.store, cid, self.persist_interval_s)
            try:
                for kind, text in self._events_with_recovery(messages, request_params, writer):
                    if kind != "content":
                        continue
                    # Written through as it arrives: losing the assistant half of a turn
                    # corrupts the replayed history for every later turn, and a disconnect
                    # gives no reliable chance to save it afterwards.
                    writer.add(text)
                    yield text
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
        turn_instruction: str | None = None,
        title: str | None = None,
        regenerate: bool = False,
        cancel_event: threading.Event | None = None,
        **params,
    ) -> tuple[str, int | None, Iterator[tuple[str, str]]]:
        """Like `stream_chat`, but yields ('reasoning' | 'content', text) chunks so a client
        can render Qwen3 thinking as it happens. Only the answer content is persisted — the
        chain of thought is ephemeral, matching the non-streaming path which stores `content`.

        With ``regenerate`` the last stored user turn is re-answered and NO new user message is
        added (the 'answer now' path re-runs the in-flight turn without the thinking phase)."""
        cid = self._open(
            student_id,
            conversation_id,
            create=not regenerate,
            mode=mode,
            persona=persona,
            subject=subject,
            language=language,
            title=title,
        )
        if regenerate:
            messages = self._assemble_history(cid, system_prompt, turn_instruction)
            user_message_id = None
        else:
            messages = self._assemble(cid, system_prompt, message, turn_instruction)
            user_message_id = self.store.add_message(cid, "user", message)
        messages, request_params = self._fit_request(
            messages,
            params,
            protected_tail_messages=min(3, max(1, len(messages) - 1)),
        )

        writer = _ReplyWriter(self.store, cid, self.persist_interval_s)

        def _gen() -> Iterator[tuple[str, str]]:
            try:
                for kind, text in self._events_with_recovery(
                    messages, request_params, writer, cancel_event
                ):
                    if kind == "content":
                        writer.add(text)
                    yield kind, text
            finally:
                # Same write-through rule as stream_chat; reasoning stays ephemeral, so a
                # turn abandoned during the thinking phase still stores nothing.
                writer.flush()

        return cid, user_message_id, _ReplyEventStream(_gen(), writer)
