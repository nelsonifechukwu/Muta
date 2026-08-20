"""Cloud model boost — cloud when online, local otherwise, source never hidden (P3).

Wraps two `InferenceClient`-shaped backends behind the three methods `ChatEngine` uses.
The fallback policy is deliberately narrow:

- offline or unknown connectivity → local, no cloud attempt (a 3 s connect timeout per
  message would be its own outage);
- transient cloud failure BEFORE the first streamed chunk → silent local retry — the
  student sees nothing but a normal answer; permanent request/auth 4xx errors propagate;
- cloud failure MID-stream → propagate to ChatEngine, which resumes the same persisted
  assistant row locally with the partial reply included as the continuation boundary.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from typing import Protocol

import httpx

from runtime.client import InferenceStreamError

Message = dict[str, str]


class _ClientLike(Protocol):
    def stream_events(self, messages: list[Message], **params) -> Iterator[tuple[str, str]]: ...

    def chat_with_timings(self, messages: list[Message], **params): ...


class CloudFallbackClient:
    def __init__(
        self,
        *,
        cloud: _ClientLike,
        local: _ClientLike,
        online: Callable[[], bool | None],
    ) -> None:
        self.cloud = cloud
        self.local = local
        self.online = online
        #: Which backend produced the last completed/started answer — the UI badges it,
        #: because student text leaving the device must never be silent.
        self._source = threading.local()
        self.last_source = "local"

    @property
    def last_source(self) -> str:
        return getattr(self._source, "value", "local")

    @last_source.setter
    def last_source(self, value: str) -> None:
        self._source.value = value

    @staticmethod
    def _tag(events: Iterator[tuple[str, str]], source: str) -> Iterator[tuple[str, str]]:
        """Keep the model's first event first (TTFT preamble), then carry provenance in-band."""
        try:
            first = next(events)
        except StopIteration:
            return
        yield "source", source
        yield first
        yield from events

    def stream_events(self, messages: list[Message], **params) -> Iterator[tuple[str, str]]:
        if self.online() is not True:
            self.last_source = "local"
            yield from self._tag(self.local.stream_events(messages, **params), "local")
            return
        # Egress provenance precedes the blocking remote read. The provider can receive the
        # question and then reset/timeout/return 4xx before yielding a token; disclosure must
        # survive all of those paths, including a local fallback.
        self.last_source = "cloud"
        yield "source", "cloud"
        events = self.cloud.stream_events(messages, **params)
        try:
            first = next(events)
        except StopIteration:
            return
        except Exception as exc:  # noqa: BLE001 — classify before local fallback
            if isinstance(exc, InferenceStreamError) and not exc.retryable:
                raise
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in {
                408,
                425,
                429,
                500,
                502,
                503,
                504,
            }:
                raise
            self.last_source = "local"
            yield from self._tag(self.local.stream_events(messages, **params), "local")
            return
        yield first
        yield from events  # mid-stream failures propagate — see module docstring

    def stream(self, messages: list[Message], **params) -> Iterator[str]:
        for kind, text in self.stream_events(messages, **params):
            if kind == "content":
                yield text

    def retry_stream_events(self, messages: list[Message], **params) -> Iterator[tuple[str, str]]:
        """Resume an interrupted cloud turn locally instead of retrying the same weak link."""
        # If the first half already came from cloud, retain that disclosure even though the
        # continuation is local. Reporting only "local" would hide that student text left the
        # device; the UI's cloud badge intentionally means "cloud was involved".
        self.last_source = "local"
        yield from self._tag(self.local.stream_events(messages, **params), "local")

    def chat_with_timings(self, messages: list[Message], **params):
        if self.online() is True:
            try:
                result = self.cloud.chat_with_timings(messages, **params)
                self.last_source = "cloud"
                return result
            except Exception:  # noqa: BLE001 — non-streaming: any failure retries locally
                pass
        self.last_source = "local"
        return self.local.chat_with_timings(messages, **params)
