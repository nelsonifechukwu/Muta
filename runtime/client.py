"""Thin HTTP client for llama-server's OpenAI-compatible chat endpoint.

Every product feature reaches the model through here, never by embedding llama.cpp in
process — the boundary the architecture already draws (ROADMAP A.2).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

Message = dict[str, Any]


class InferenceStreamError(RuntimeError):
    """A structured error frame emitted after an SSE response has already started."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        finish_reason: str | None = None,
        partial_text: str = "",
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.finish_reason = finish_reason
        self.partial_text = partial_text


@dataclass(frozen=True)
class Generation:
    """One completion plus the numbers the product path needs to compute TPS.

    `chat()` returns a bare str and always has, so `bench/profile.py` had nothing to measure.
    `from_wall_clock` records whether the rate came from the engine's own timings or from our
    stopwatch — a derived number must never be mistaken for a measured one.
    """

    text: str
    prompt_tokens: int
    completion_tokens: int
    elapsed_s: float
    tokens_per_second: float
    from_wall_clock: bool
    finish_reason: str | None = None


class InferenceClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        *,
        model: str = "qwen3-0.6b",
        enable_thinking: bool = False,
        timeout: float = 120.0,
        api_key: str | None = None,
        template_kwargs: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.enable_thinking = enable_thinking
        self.timeout = timeout
        # The same client speaks to llama-server (no key, jinja template switch) and to
        # cloud OpenAI-compatible endpoints (bearer key; strict providers 400 on unknown
        # fields, so template_kwargs=False drops the llama-server-only field).
        self._headers = {"authorization": f"Bearer {api_key}"} if api_key else {}
        self.template_kwargs = template_kwargs

    def _payload(self, messages: list[Message], stream: bool, **params) -> dict:
        # Per-request thinking override (the gateway maps the request's `thinking` level to
        # this); falls back to the client default set at construction.
        enable_thinking = params.pop("enable_thinking", self.enable_thinking)
        # llama-server-only per-request thinking cap ("Extended"). Popped here so it is never
        # sent to a strict cloud provider (which 400s on unknown fields — the same reason
        # chat_template_kwargs is gated below).
        reasoning_budget = params.pop("reasoning_budget_tokens", None)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            **params,
        }
        if self.template_kwargs:
            # Qwen3 hybrid-reasoning switch; honoured by llama-server when --jinja is set.
            payload["chat_template_kwargs"] = {"enable_thinking": enable_thinking}
            if reasoning_budget is not None:
                # Honoured on recent llama.cpp; older pins ignore the field (lenient parser),
                # so Extended degrades to a fuller answer rather than erroring.
                payload["reasoning_budget_tokens"] = reasoning_budget
        return payload

    def count_prompt_tokens(self, messages: list[Message], **params) -> int:
        """Count the exact chat-template prompt with the already-loaded local tokenizer.

        llama-server owns both the model's chat template and tokenizer. Asking it avoids
        shipping a second tokenizer (and its RAM) in Python, while keeping context fitting
        accurate enough that ordinary English is not treated as one token per byte. Callers
        retain a conservative local fallback if either optional endpoint is unavailable.
        """
        template_body: dict = {
            "messages": messages,
            "add_generation_prompt": True,
        }
        if self.template_kwargs:
            template_body["chat_template_kwargs"] = {
                "enable_thinking": params.get("enable_thinking", self.enable_thinking)
            }
        probe_timeout = min(self.timeout, 5.0)
        rendered = httpx.post(
            f"{self.base_url}/apply-template",
            json=template_body,
            timeout=probe_timeout,
            headers=self._headers,
        )
        rendered.raise_for_status()
        prompt = rendered.json().get("prompt")
        if not isinstance(prompt, str):
            raise TypeError("llama-server did not return a rendered chat prompt")
        tokenized = httpx.post(
            f"{self.base_url}/tokenize",
            json={"content": prompt, "add_special": True},
            timeout=probe_timeout,
            headers=self._headers,
        )
        tokenized.raise_for_status()
        tokens = tokenized.json().get("tokens")
        if not isinstance(tokens, list) or not all(isinstance(token, int) for token in tokens):
            raise ValueError("llama-server did not return prompt token ids")
        return len(tokens)

    def chat(self, messages: list[Message], **params) -> str:
        """Non-streaming completion → the assistant's full reply text."""
        return self.chat_with_timings(messages, **params).text

    def chat_with_timings(self, messages: list[Message], **params) -> Generation:
        """Non-streaming completion → reply plus token counts and generation rate."""
        url = f"{self.base_url}/v1/chat/completions"
        started = time.monotonic()
        r = httpx.post(
            url,
            json=self._payload(messages, False, **params),
            timeout=self.timeout,
            headers=self._headers,
        )
        r.raise_for_status()
        elapsed = time.monotonic() - started
        body = r.json()

        choice = body["choices"][0]
        text = choice["message"].get("content") or ""
        usage = body.get("usage") or {}
        completion_tokens = int(usage.get("completion_tokens") or 0)

        # llama-server reports its own decode rate; prefer it over our stopwatch, which also
        # counts HTTP and prefill time and so understates the engine.
        timings = body.get("timings") or {}
        engine_rate = timings.get("predicted_per_second")
        if isinstance(engine_rate, (int, float)) and engine_rate > 0:
            rate, from_wall_clock = float(engine_rate), False
        elif completion_tokens > 0 and elapsed > 0:
            rate, from_wall_clock = completion_tokens / elapsed, True
        else:
            rate, from_wall_clock = 0.0, True

        return Generation(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=completion_tokens,
            elapsed_s=elapsed,
            tokens_per_second=rate,
            from_wall_clock=from_wall_clock,
            finish_reason=(
                str(choice["finish_reason"]) if choice.get("finish_reason") is not None else None
            ),
        )

    def stream(self, messages: list[Message], **params) -> Iterator[str]:
        """Streaming completion → yields answer-content deltas as they arrive (SSE).

        Reasoning tokens (Qwen3 thinking) are dropped here so existing callers keep getting
        just the answer. Use `stream_events` to see the thinking too.
        """
        for kind, text in self.stream_events(messages, **params):
            if kind == "content":
                yield text

    def stream_events(self, messages: list[Message], **params) -> Iterator[tuple[str, str]]:
        """Streaming completion → yields ('reasoning' | 'content', text) chunks.

        With Qwen3 thinking on (`--jinja` + `enable_thinking`), llama-server streams the chain
        of thought in a separate `reasoning_content` delta field. A consumer that reads only
        `content` sees nothing during the think phase and appears to hang — so this surfaces
        both, tagged, and the caller decides how to render each.
        """
        cancel_event = params.pop("_muta_cancel_event", None)
        url = f"{self.base_url}/v1/chat/completions"
        with httpx.stream(
            "POST",
            url,
            json=self._payload(messages, True, **params),
            timeout=self.timeout,
            headers=self._headers,
        ) as r:
            r.raise_for_status()
            stream_done = threading.Event()
            if isinstance(cancel_event, threading.Event):
                # httpx's synchronous iterator can block inside a socket read for the full
                # request timeout. Closing its response from this tiny watcher interrupts that
                # read, so host removal is bounded even when llama-server goes silent.
                def close_on_cancel() -> None:
                    while not stream_done.is_set():
                        if cancel_event.wait(0.1):
                            close = getattr(r, "close", None)
                            if callable(close):
                                close()
                            return

                threading.Thread(
                    target=close_on_cancel,
                    name="muta-inference-cancel",
                    daemon=True,
                ).start()
            terminal = False
            finish_reason: str | None = None
            try:
                for line in r.iter_lines():
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[len("data: ") :]
                    if data.strip() == "[DONE]":
                        terminal = True
                        break
                    try:
                        body = json.loads(data)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    error = body.get("error") if isinstance(body, dict) else None
                    if error:
                        if isinstance(error, dict):
                            message = str(
                                error.get("message") or error.get("type") or "inference failed"
                            )
                            code = error.get("code")
                        else:
                            message, code = str(error), None
                        lower = message.lower()
                        retryable = (
                            "context size" not in lower
                            and "context window" not in lower
                            and (
                                str(code) in {"408", "425", "429", "500", "502", "503", "504"}
                                or "temporar" in lower
                                or "unavailable" in lower
                            )
                        )
                        raise InferenceStreamError(message, retryable=retryable)
                    try:
                        choice = body["choices"][0]
                        delta = choice["delta"]
                    except (KeyError, IndexError, TypeError):
                        continue
                    reason = choice.get("finish_reason")
                    if reason is not None:
                        terminal = True
                        finish_reason = str(reason)
                    reasoning = delta.get("reasoning_content")
                    if reasoning:
                        yield "reasoning", reasoning
                    content = delta.get("content")
                    if content:
                        yield "content", content
            finally:
                stream_done.set()
            if cancel_event is not None and cancel_event.is_set():
                return
            if not terminal:
                # A proxy/socket can end a chunked body cleanly without raising httpx. Unless
                # llama-server sent its terminal frame, that EOF is a truncated answer and
                # must enter the same bounded recovery path as a connection reset.
                raise InferenceStreamError(
                    "inference stream ended before completion",
                    retryable=True,
                )
            if finish_reason == "length":
                # This is a valid HTTP/SSE exchange but not a complete answer. Surface it through
                # ChatEngine's same-row continuation path instead of silently persisting a
                # mid-sentence response as successful completion.
                raise InferenceStreamError(
                    "inference reached its token limit before completion",
                    retryable=True,
                    finish_reason=finish_reason,
                )
