"""The TTFT preamble through the real app: SSE shape, persistence, and metrics separation.

`test_preamble.py` covers the interleave in isolation. What is checked here is the wiring
that actually ships — that a `preamble` event reaches the browser under its own key, that
it stays out of the stored reply and out of `ttft_s`, and that turning the feature off
restores the previous stream byte-for-byte.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from orchestrator.gateway import deps
from orchestrator.gateway.ladder import DegradationLadder, GiB
from orchestrator.gateway.sessions import SessionManager
from orchestrator.main import app

client = TestClient(app)

PREFILL_S = 0.12  # the window the preamble is allowed to fill


class SlowEngine:
    """Engine whose first event costs PREFILL_S — the case the feature exists for. Records
    what ChatEngine would have persisted so the test can assert the preamble never lands."""

    def __init__(self) -> None:
        self.persisted: list[str] = []

    def stream_events_chat(self, **kwargs):
        cid = kwargs.get("conversation_id") or "conv-1"
        parts: list[str] = []

        def gen():
            time.sleep(PREFILL_S)
            for kind, text in [("reasoning", "hmm"), ("content", "x = "), ("content", "3")]:
                if kind == "content":
                    parts.append(text)
                yield kind, text
            self.persisted.append("".join(parts))

        return cid, 1, gen()


class StubWriter:
    """Stands in for the NumPy model: same interface, no 15 MB and no provisioning."""

    def stream(self, seed_text="", *, max_tokens=48, temperature=0.8, seed=None):
        for i in range(max_tokens):
            yield f"filler{i} "
            time.sleep(0.005)


@pytest.fixture
def wired_with_preamble():
    engine = SlowEngine()
    ladder = DegradationLadder(free_probe=lambda: 8 * GiB, reserve_bytes=0, poll_seconds=0.0)
    sessions = SessionManager(slots_count=2)
    app.dependency_overrides[deps.get_engine] = lambda: engine
    app.dependency_overrides[deps.get_ladder] = lambda: ladder
    app.dependency_overrides[deps.get_sessions] = lambda: sessions
    app.dependency_overrides[deps.get_preamble_writer] = lambda: StubWriter()
    yield engine
    app.dependency_overrides.clear()


@pytest.fixture
def wired_without_preamble():
    engine = SlowEngine()
    ladder = DegradationLadder(free_probe=lambda: 8 * GiB, reserve_bytes=0, poll_seconds=0.0)
    app.dependency_overrides[deps.get_engine] = lambda: engine
    app.dependency_overrides[deps.get_ladder] = lambda: ladder
    app.dependency_overrides[deps.get_sessions] = lambda: SessionManager(slots_count=2)
    app.dependency_overrides[deps.get_preamble_writer] = lambda: None
    yield engine
    app.dependency_overrides.clear()


def frames(response) -> list[dict]:
    out = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def test_preamble_reaches_the_client_before_the_first_real_token(wired_with_preamble):
    with client.stream(
        "POST",
        "/v1/chat/stream",
        headers={"Authorization": "Bearer s1"},
        json={"student_id": "s1", "message": "Solve x^2 = 9"},
    ) as response:
        evs = frames(response)

    kinds = [next(iter(e)) for e in evs]
    assert "preamble" in kinds, "a 120 ms prefill produced no preamble"
    first_real = min(i for i, e in enumerate(evs) if "reasoning" in e or "delta" in e)
    last_preamble = max(i for i, e in enumerate(evs) if "preamble" in e)
    assert last_preamble < first_real, "filler must stop the moment the tutor speaks"


def test_preamble_is_never_persisted_as_the_reply(wired_with_preamble):
    with client.stream(
        "POST",
        "/v1/chat/stream",
        headers={"Authorization": "Bearer s1"},
        json={"student_id": "s1", "message": "Solve x^2 = 9"},
    ) as response:
        frames(response)
    assert wired_with_preamble.persisted == ["x = 3"], "the stored reply must be engine-only"


def test_metrics_keep_the_two_first_token_numbers_apart(wired_with_preamble):
    """`ttft_s` is the tutor's. `preamble_ttft_s` is the pane's. Reporting the second as the
    first would be the dishonest version of this feature."""
    with client.stream(
        "POST",
        "/v1/chat/stream",
        headers={"Authorization": "Bearer s1"},
        json={"student_id": "s1", "message": "Solve x^2 = 9"},
    ) as response:
        done = frames(response)[-1]

    assert done["done"] is True
    assert done["preamble_ttft_s"] < done["ttft_s"]
    assert done["ttft_s"] >= PREFILL_S, "engine TTFT must still measure the real prefill"
    # Filler is not decoded output: it cannot inflate the token count or the rate.
    assert done["completion_tokens"] == 3


def test_disabled_preamble_leaves_the_stream_unchanged(wired_without_preamble):
    with client.stream(
        "POST",
        "/v1/chat/stream",
        headers={"Authorization": "Bearer s1"},
        json={"student_id": "s1", "message": "Solve x^2 = 9"},
    ) as response:
        evs = frames(response)

    assert not any("preamble" in e for e in evs)
    assert evs[-1]["preamble_ttft_s"] is None
    assert [next(iter(e)) for e in evs] == ["conversation_id", "reasoning", "delta", "delta", "done"]


def test_the_real_model_streams_through_the_real_route():
    """Everything above uses a stub writer. This one runs the actual NumPy GPT-Neo through
    the actual endpoint — the only check that would catch the model and the wiring being
    individually fine but incompatible."""
    from pathlib import Path

    from runtime.ttft import PreambleWriter

    model_dir = Path(__file__).resolve().parents[2] / "models" / "ttft"
    writer = PreambleWriter.load(model_dir)
    if writer is None:
        pytest.skip("TTFT model not provisioned (scripts/fetch_ttft_model.py)")
    writer.warmup()

    engine = SlowEngine()
    app.dependency_overrides[deps.get_engine] = lambda: engine
    app.dependency_overrides[deps.get_ladder] = lambda: DegradationLadder(
        free_probe=lambda: 8 * GiB, reserve_bytes=0, poll_seconds=0.0
    )
    app.dependency_overrides[deps.get_sessions] = lambda: SessionManager(slots_count=2)
    app.dependency_overrides[deps.get_preamble_writer] = lambda: writer
    try:
        with client.stream(
            "POST",
            "/v1/chat/stream",
            headers={"Authorization": "Bearer s1"},
            json={"student_id": "s1", "message": "Solve x^2 = 9"},
        ) as response:
            evs = frames(response)
    finally:
        app.dependency_overrides.clear()

    text = "".join(e["preamble"] for e in evs if "preamble" in e)
    assert text.strip(), "the real model produced no preamble inside a 120 ms window"
    assert engine.persisted == ["x = 3"]
    assert evs[-1]["preamble_ttft_s"] < 0.05, f"preamble was slow: {evs[-1]['preamble_ttft_s']}s"


def test_tutor_stream_carries_the_preamble_too(wired_with_preamble):
    with client.stream(
        "POST", "/v1/tutor/chat/stream", json={"session_id": "s1", "text": "Solve x^2 = 9"}
    ) as response:
        evs = frames(response)

    assert any("preamble" in e for e in evs)
    assert evs[-1]["completion_tokens"] == 3  # filler excluded here as well
