"""`with_preamble` — the interleave between the warm-up model and the engine's stream.

This is the adversarial surface of the TTFT feature: a thread makes the engine's blocking
first call while the request thread streams filler. The invariants worth breaking things
over are ordering (no preamble after the tutor starts speaking), fidelity (the engine's
events arrive complete, in order, exactly once), and failure (an engine error still reaches
the caller as itself, and a broken preamble never breaks the turn).
"""

from __future__ import annotations

import threading
import time

import httpx
import pytest

from orchestrator.gateway.preamble import with_preamble


class FakeWriter:
    """Streams forever, one chunk per call — so the preamble is always the slow side and
    the test measures the interleave rather than a race it happened to win."""

    def __init__(self, chunk: str = "blah ") -> None:
        self.chunk = chunk
        self.closed = False

    def stream(self, seed_text="", *, max_tokens=48, temperature=0.8, seed=None):
        try:
            for _ in range(max_tokens):
                yield self.chunk
                time.sleep(0.002)
        finally:
            self.closed = True


def slow_engine(delay: float, events):
    """An engine whose FIRST event costs `delay` — the prefill window, and the only window
    the preamble is allowed to occupy."""

    def gen():
        time.sleep(delay)
        yield from events
    return gen()


def test_no_writer_is_an_exact_passthrough():
    events = [("reasoning", "hmm"), ("content", "42")]
    assert list(with_preamble(iter(events), None)) == events


def test_preamble_fills_the_prefill_window_then_stops():
    writer = FakeWriter()
    out = list(with_preamble(slow_engine(0.05, [("content", "a"), ("content", "b")]), writer))

    kinds = [k for k, _ in out]
    assert "preamble" in kinds, "the 50 ms prefill window produced no preamble at all"
    # Every preamble precedes every engine event: once the tutor speaks, the filler is over.
    assert kinds == sorted(kinds, key=lambda k: k != "preamble")
    assert [e for e in out if e[0] != "preamble"] == [("content", "a"), ("content", "b")]
    assert writer.closed, "the preamble generator must be closed, not abandoned mid-run"


def test_engine_events_are_never_dropped_or_duplicated():
    """The first event is pulled on a helper thread and re-yielded by the caller's thread —
    the exact place an off-by-one would eat or double a token."""
    events = [("content", str(i)) for i in range(25)]
    out = list(with_preamble(slow_engine(0.03, events), FakeWriter()))
    assert [e for e in out if e[0] != "preamble"] == events


def test_fast_engine_yields_little_or_no_preamble():
    """No artificial delay: nothing here waits for filler it does not need."""
    out = list(with_preamble(iter([("content", "instant")]), FakeWriter()))
    assert out[-1] == ("content", "instant")
    assert len([k for k, _ in out if k == "preamble"]) <= 1


def test_empty_engine_stream_still_terminates():
    out = list(with_preamble(slow_engine(0.02, []), FakeWriter()))
    assert all(k == "preamble" for k, _ in out)


def test_engine_error_propagates_unchanged():
    """`/chat/stream` catches httpx.HTTPError to emit its friendly message. Wrapping or
    swallowing the exception here would turn that into a 500 mid-stream."""

    def boom():
        time.sleep(0.02)
        raise httpx.ConnectError("engine down")
        yield  # pragma: no cover — generator marker

    with pytest.raises(httpx.ConnectError):
        list(with_preamble(boom(), FakeWriter()))


def test_broken_preamble_does_not_break_the_turn():
    class Exploding:
        def stream(self, *a, **k):
            yield "ok "
            raise RuntimeError("numpy said no")

    out = list(with_preamble(slow_engine(0.03, [("content", "answer")]), Exploding()))
    assert out[-1] == ("content", "answer")


def test_source_is_not_advanced_concurrently_with_the_consumer():
    """The helper thread must be done before the caller can touch the source generator —
    otherwise the route's `_close_events` lands on a generator that is still executing and
    a client disconnect becomes 'generator already executing'."""
    running = threading.Event()
    overlapped = []

    def gen():
        running.set()
        time.sleep(0.05)
        running.clear()
        yield ("content", "a")
        # If the consumer resumed us while the puller thread were still inside, this would
        # observe the flag still set.
        overlapped.append(running.is_set())
        yield ("content", "b")

    list(with_preamble(gen(), FakeWriter()))
    assert overlapped == [False]


def test_route_shutdown_order_survives_a_disconnect_mid_prefill():
    """The exact sequence `_sse`'s finally runs, exercised at the one moment it can bite:
    the client is gone, a preamble chunk has been sent, and the helper thread is still
    inside `next(events)`.

    Closing `events` *first* raises ValueError("generator already executing") — and in the
    route that exception fires inside a finally, skipping `sessions.release()` and leaking
    an admission slot for the life of the process. Closing the wrapper first joins the
    thread, so the second close is safe and idempotent.
    """
    events = slow_engine(0.15, [("content", "a")])
    stream = with_preamble(events, FakeWriter())
    assert next(stream)[0] == "preamble"

    stream.close()  # waits for the helper thread
    events.close()  # must not raise


def test_closing_the_engine_generator_first_is_the_trap_being_avoided():
    """Documents *why* the order above is load-bearing, so a future refactor that 'tidies'
    the two closes into one line has something that fails."""
    events = slow_engine(0.15, [("content", "a")])
    stream = with_preamble(events, FakeWriter())
    assert next(stream)[0] == "preamble"

    with pytest.raises(ValueError, match="already executing"):
        events.close()  # the wrong order, reproduced deliberately
    stream.close()


def test_closing_the_stream_early_does_not_leak_or_raise():
    """Client disconnect during the prefill window: the generator is closed mid-preamble."""
    writer = FakeWriter()
    stream = with_preamble(slow_engine(0.05, [("content", "a")]), writer)
    assert next(stream) == ("preamble", "blah ")
    stream.close()  # must not raise, and must not strand the helper thread
    assert writer.closed
    assert not any(t.name == "ttft-prefill" for t in threading.enumerate())
