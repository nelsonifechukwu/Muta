"""The engine supervisor respawns llama-server after it dies, instead of 503ing forever."""

from __future__ import annotations

import threading

from orchestrator import main as main_mod


class _FakeProc:
    """A child that has already exited with a non-zero code."""

    def wait(self, timeout=None):  # noqa: ARG002 — signature parity with Popen.wait
        return 1


class _FakeServer:
    """Dies immediately on each start; the second start signals the loop to stop, so the
    supervisor performs exactly one respawn and then exits deterministically."""

    def __init__(self, stop: threading.Event) -> None:
        self._stop = stop
        self.ensures = 0
        self.process = None

    def ensure(self, log_file=None):  # noqa: ARG002
        self.ensures += 1
        if self.ensures >= 2:
            self._stop.set()  # end the loop after the first respawn
        self.process = _FakeProc()
        return self, True


def test_supervisor_respawns_a_dead_engine(monkeypatch):
    # Isolate the module-global restart bookkeeping.
    monkeypatch.setitem(main_mod._engine_state, "restarts", 0)
    monkeypatch.setitem(main_mod._engine_state, "last_exit_code", None)
    # Make backoff instant so the test doesn't sleep.
    monkeypatch.setattr(main_mod, "ENGINE_RESPAWN_BACKOFF_MIN_S", 0.0)
    monkeypatch.setattr(main_mod, "ENGINE_POLL_INTERVAL_S", 0.01)

    stop = threading.Event()
    server = _FakeServer(stop)
    thread, returned_stop = main_mod._start_engine_thread(server, log_file=None, stop=stop)
    thread.join(timeout=5.0)

    assert not thread.is_alive(), "supervisor thread did not terminate"
    assert server.ensures >= 2, "engine was not respawned after it died"
    assert main_mod._engine_state["restarts"] >= 1
    assert main_mod._engine_state["last_exit_code"] == 1
    assert returned_stop is stop or returned_stop.is_set()
