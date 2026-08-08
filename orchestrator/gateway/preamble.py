"""Interleave the TTFT preamble with the engine's own stream.

The shape of the problem: `ChatEngine.stream_events_chat` hands back a generator whose
*first* `next()` is the expensive one — it issues the HTTP request and blocks through the
whole of llama-server's prefill. Everything after that arrives at decode speed. So the
window worth filling is exactly "between the first `next()` and its return", and filling it
means doing two things at once in a sync endpoint.

Hence the one thread here: it makes that blocking first call, while this generator streams
preamble text on the request thread and stops the instant the real first event lands. No
part of the engine path is duplicated, reordered, or retried — the same generator is handed
back to the caller, positioned exactly where it would have been.

What the preamble is NOT: it is not the tutor's answer. It is yielded under its own
`'preamble'` kind, callers surface it as a distinct SSE key, and it never reaches
`ChatEngine`'s persistence path or the reported `ttft_s`. See docs/ttft-preamble.md.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator

from runtime.ttft import PreambleWriter

log = logging.getLogger("muta.gateway.preamble")

Event = tuple[str, str]


def with_preamble(
    events: Iterator[Event],
    writer: PreambleWriter | None,
    *,
    seed_text: str = "",
    max_tokens: int = 48,
    temperature: float = 0.8,
    seed: int | None = None,
) -> Iterator[Event]:
    """Yield `('preamble', text)` while the engine prefills, then the engine's own events.

    With `writer=None` this is `iter(events)` — the no-model path costs nothing and changes
    nothing, which is what makes the preamble safe to leave switched off.
    """
    source = iter(events)
    if writer is None:
        yield from source
        return

    first: list[Event] = []
    failure: list[BaseException] = []
    exhausted = threading.Event()
    ready = threading.Event()

    def _pull_first() -> None:
        try:
            first.append(next(source))
        except StopIteration:
            exhausted.set()
        except BaseException as e:  # noqa: BLE001 — re-raised on the request thread below
            failure.append(e)
        finally:
            ready.set()

    thread = threading.Thread(target=_pull_first, name="ttft-prefill", daemon=True)
    thread.start()

    try:
        stream = writer.stream(
            seed_text, max_tokens=max_tokens, temperature=temperature, seed=seed
        )
        try:
            for chunk in stream:
                if ready.is_set():
                    break
                yield "preamble", chunk
        except Exception as e:  # noqa: BLE001 — a broken preamble must not break the turn
            log.warning("TTFT preamble failed mid-stream (%r) — continuing without it", e)
        finally:
            stream.close()
    finally:
        # Never leave `source` being advanced by the helper thread while the caller's own
        # `finally` closes it — a generator closed while another thread is inside it raises
        # "generator already executing" and would turn a client disconnect into a 500. The
        # wait is bounded by the client's own request timeout (RuntimeConfig.request_timeout_s).
        ready.wait()

    if failure:
        raise failure[0]
    if exhausted.is_set():
        return
    yield first[0]
    yield from source
