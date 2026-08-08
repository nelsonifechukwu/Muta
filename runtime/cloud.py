"""Cloud model boost — cloud when online, local otherwise, source never hidden (P3).

Wraps two `InferenceClient`-shaped backends behind the three methods `ChatEngine` uses.
The fallback policy is deliberately narrow:

- offline or unknown connectivity → local, no cloud attempt (a 3 s connect timeout per
  message would be its own outage);
- cloud failure BEFORE the first streamed chunk → silent local retry — the student sees
  nothing but a normal answer;
- cloud failure MID-stream → propagate. The dropped-stream path already persists the
  partial reply; silently restarting on local would duplicate half an answer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Protocol

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
        self.last_source = "local"

    def stream_events(self, messages: list[Message], **params) -> Iterator[tuple[str, str]]:
        if self.online() is not True:
            self.last_source = "local"
            yield from self.local.stream_events(messages, **params)
            return
        events = self.cloud.stream_events(messages, **params)
        try:
            first = next(events)
        except StopIteration:
            self.last_source = "cloud"
            return
        except Exception:  # noqa: BLE001 — nothing streamed yet; the student never knows
            self.last_source = "local"
            yield from self.local.stream_events(messages, **params)
            return
        self.last_source = "cloud"
        yield first
        yield from events  # mid-stream failures propagate — see module docstring

    def stream(self, messages: list[Message], **params) -> Iterator[str]:
        for kind, text in self.stream_events(messages, **params):
            if kind == "content":
                yield text

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
