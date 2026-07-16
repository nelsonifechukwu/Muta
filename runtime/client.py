"""Thin HTTP client for llama-server's OpenAI-compatible chat endpoint.

Every product feature reaches the model through here, never by embedding llama.cpp in
process — the boundary the architecture already draws (ROADMAP A.2).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

Message = dict[str, str]


class InferenceClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        *,
        model: str = "qwen3-0.6b",
        enable_thinking: bool = False,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.enable_thinking = enable_thinking
        self.timeout = timeout

    def _payload(self, messages: list[Message], stream: bool, **params) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            # Qwen3 hybrid-reasoning switch; honoured by llama-server when --jinja is set.
            "chat_template_kwargs": {"enable_thinking": self.enable_thinking},
            **params,
        }
        return payload

    def chat(self, messages: list[Message], **params) -> str:
        """Non-streaming completion → the assistant's full reply text."""
        url = f"{self.base_url}/v1/chat/completions"
        r = httpx.post(url, json=self._payload(messages, False, **params), timeout=self.timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def stream(self, messages: list[Message], **params) -> Iterator[str]:
        """Streaming completion → yields content deltas as they arrive (SSE)."""
        url = f"{self.base_url}/v1/chat/completions"
        with httpx.stream(
            "POST", url, json=self._payload(messages, True, **params), timeout=self.timeout
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[len("data: ") :]
                if data.strip() == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta
